#!/usr/bin/env python3
"""
build_docs.py — Finance Hub docs builder
=========================================
Generates the `docs/` directory content from source files:

  • ai_gen_report/fundamental/ → docs/reports/<ticker>/
  • ai_gen_report/technical/   → docs/reports/<ticker>/
  • ai_gen_report/stock/       → docs/reports/<ticker>/  (other analysis types, legacy HTML)
  • ai_gen_report/market_news/ → docs/market_news/<ticker>/
  • notebook_llm/              → docs/notebooks/<ticker>/
  • 10-k/                      → docs/sec/10k.md   (index only, PDFs not copied)
  • 10-q/                      → docs/sec/10q.md
  • 13-f/                      → docs/sec/13f.md
  • investor_day/              → docs/investor_day/
  • README.md                  → enriches docs/index.md

Run locally:   python scripts/build_docs.py
Run in CI:     automatically called before `mkdocs build`
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

# The price store. Safe to import at module scope: the analysis package defers
# every heavy dependency (pandas, yfinance, plotly) to inside its functions, and
# prices.py's read path is pure standard library — so the docs build stays
# dependency-light and offline.
from analysis.data import prices

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).resolve().parent.parent
DOCS       = ROOT / "docs"
DOCS_ZH    = ROOT / "docs" / "zh"
SITE       = ROOT / "site"

SRC_STOCK    = ROOT / "ai_gen_report" / "stock"
SRC_FUNDAMENTAL = ROOT / "ai_gen_report" / "fundamental"
SRC_TECHNICAL   = ROOT / "ai_gen_report" / "technical"
PRICES_DIR      = ROOT / "data" / "prices"           # committed OHLCV store; chart payloads are derived from it
SRC_MARKET_NEWS = ROOT / "ai_gen_report" / "market_news"
SRC_NOTEBOOK = ROOT / "notebook_llm"
SRC_10K      = ROOT / "10-k"
SRC_10Q      = ROOT / "10-q"
SRC_13F      = ROOT / "13-f"
SRC_6K       = ROOT / "6-k"
SRC_INV_DAY  = ROOT / "investor_day"

TODAY = date.today().isoformat()
# Fixed once at module load so retention filtering is identical across the
# sequential EN/ZH builds even if the run crosses midnight.
TODAY_DATE = date.fromisoformat(TODAY)

# ── Site root path (must match site_url in mkdocs.yml) ───────────────────────
# Used to build absolute cross-language links so the ZH index can link to the
# EN report pages instead of duplicating all files.
SITE_BASE = "/finance_data"

# ── Publishing controls ───────────────────────────────────────────────────────
# Perf fix #4 — retention window. Reports / market-news older than this many
# days are NOT mirrored into the published site (the source files under
# ai_gen_report/ are never touched, so this is fully reversible). This caps the
# deploy payload, build time, and search-index size as daily reports accumulate.
# Set REPORT_RETENTION_DAYS=0 to publish everything.
RETENTION_DAYS = int(os.environ.get("REPORT_RETENTION_DAYS", "120"))

# Perf fix #1 — search-index slimming. Merged into the front matter of dated
# report / news / notebook *body* pages so the MkDocs Material search plugin
# skips their (very large) full text. Index & landing pages stay searchable, so
# tickers and report titles remain discoverable while search_index.json stays
# small. These are YAML lines, not a full block — copy_file merges them with
# whatever front matter the source file already carries.
SEARCH_EXCLUDE_META = "search:\n  exclude: true"

_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _file_date(f: Path) -> "date | None":
    """Parse a YYYY-MM-DD date embedded in a filename; None if absent/invalid."""
    m = _DATE_RE.search(f.name)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def within_retention(f: Path) -> bool:
    """True if f should be published: recent enough, undated, or retention off.

    Undated files (hand-written pages, indexes) always publish.
    """
    if RETENTION_DAYS <= 0:
        return True
    d = _file_date(f)
    if d is None:
        return True
    return (TODAY_DATE - d).days <= RETENTION_DAYS


# Number of most-recent reports shown directly per section; the rest are tucked
# into a collapsible "Show N older reports" block so daily reports don't produce
# a giant wall of links.
RECENT_COUNT = 8


def by_date_desc(files: list[Path]) -> list[Path]:
    """Sort report files newest-first by the date embedded in the filename,
    falling back to reverse filename order for undated files."""
    return sorted(files, key=lambda f: (_file_date(f) or date.min, f.name), reverse=True)


def report_label(f: Path) -> str:
    """Human-friendly label for a dated report file: 'YYYY-MM-DD · Provider'.

    Drops the redundant analysis-type prefix (the section heading already says
    it) and falls back to a title-cased stem for files without an embedded date.
    """
    m = _DATE_RE.search(f.stem)
    if not m:
        return f.stem.replace("_", " ").title()
    date_str = m.group(0)
    provider = f.stem[m.end():].strip("_-").replace("_", " ").title()
    return f"{date_str} · {provider}" if provider else date_str

# ── Build mode ────────────────────────────────────────────────────────────────
# Pass --clean to force a full rebuild (deletes docs/ subdirs first).
# Default (incremental) skips files that haven't changed, cutting build time
# significantly on large repos.
_INCREMENTAL = "--clean" not in sys.argv

# ── Sample-build mode ─────────────────────────────────────────────────────────
# When SAMPLE_BUILD is set, cap the number of tickers/companies and the number
# of files built per directory so CI can exercise the whole pipeline on a tiny
# subset in seconds (see .github/workflows/sample_build.yml). This is a smoke
# test of the build code — it is never used by the production deploy from main.
SAMPLE_BUILD = os.environ.get("SAMPLE_BUILD", "").strip().lower() in ("1", "true", "yes")
SAMPLE_LIMIT = max(1, int(os.environ.get("SAMPLE_LIMIT", "3") or "3"))
# Optional comma-separated allowlist of tickers/companies to build in sample
# mode (matched case-insensitively against directory names). Lets CI target
# mermaid-heavy pages deterministically. Empty → just take the first N dirs.
SAMPLE_TICKERS = [s.strip().lower() for s in os.environ.get("SAMPLE_TICKERS", "").split(",") if s.strip()]


def _sample(items):
    """Cap a list to SAMPLE_LIMIT items in sample-build mode; else pass through."""
    items = list(items)
    return items[:SAMPLE_LIMIT] if SAMPLE_BUILD else items


def _sample_dirs(dirs):
    """Cap a list of ticker/company directories in sample mode. Honours
    SAMPLE_TICKERS when any match; otherwise falls back to the first N dirs."""
    if not SAMPLE_BUILD:
        return dirs
    dirs = list(dirs)
    if SAMPLE_TICKERS:
        picked = [d for d in dirs if d.name.lower() in SAMPLE_TICKERS]
        if picked:
            return picked[:SAMPLE_LIMIT]
    return dirs[:SAMPLE_LIMIT]


# Reports live across three roots: ai_gen_report/{fundamental,technical}/<ticker>
# (dedicated per-type dirs) and ai_gen_report/stock/<ticker> (other analysis
# types + legacy HTML). These helpers merge them per-ticker so the rest of
# build_reports() can keep treating a ticker as one flat file list.
def report_roots() -> list[Path]:
    """The report source roots, read live off module globals (not cached at
    import time) so tests can monkeypatch SRC_STOCK/SRC_FUNDAMENTAL/SRC_TECHNICAL."""
    return [SRC_FUNDAMENTAL, SRC_TECHNICAL, SRC_STOCK]


def merged_ticker_dirs() -> list[Path]:
    """Union of ticker names across the report roots, as sorted virtual Paths
    (only `.name` is meaningful — use ticker_files() to get real file lists)."""
    names = {d.name.lower() for root in report_roots() if root.exists() for d in root.iterdir() if d.is_dir()}
    return [Path(name) for name in sorted(names)]


def ticker_files(ticker: str) -> list[Path]:
    """All report files for a ticker, merged across the report roots."""
    files: list[Path] = []
    for root in report_roots():
        d = root / ticker
        if d.is_dir():
            files.extend(f for f in d.iterdir() if f.is_file())
    return sorted(files, key=lambda f: f.name)


# ── Language-specific text ────────────────────────────────────────────────────
LANG_TEXT = {
    "en": {
        "last_updated": "Last updated",
        "last_built": "Last built",
        "sector": "Sector",
        "available_reports": "Available Reports",
        "latest_reports": "🆕 Latest Reports",
        "open_latest": "Open latest",
        "latest": "Latest",
        "show_older": "Show {n} older reports",
        "markdown_reports": "📄 Markdown Reports",
        "html_reports": "🌐 Interactive HTML Reports",
        "fundamental_analysis": "📊 Fundamental Analysis",
        "technical_analysis": "📈 Technical Analysis",
        "other_reports": "🗂️ Other Reports",
        "price_target": "🎯 Price Target & Implied Return",
        "pt_scenario": "Scenario",
        "pt_prob": "Probability",
        "pt_target": "12M Target",
        "pt_current": "Current Price",
        "pt_return": "Implied Return",
        "pt_weighted": "Weighted Value",
        "pt_weighted_target": "Weighted Target",
        "pt_note": ("Scenario targets from the latest fundamental report ({report}); "
                    "current price as of {price_date} close. "
                    "Weighted value = probability × target."),
        "pt_note_default": "Probabilities are default Bear/Base/Bull weights (the report gave no probability column).",
        "analysis_reports": "Analysis Reports",
        "reports_nav_title": "AI Gen Reports",
        "market_news": "Market News",
        "market_news_desc": "AI-generated daily market news and stock-specific headline analysis",
        "ai_generated": "AI-generated investment research reports",
        "disclaimer": "Disclaimer",
        "disclaimer_text": "All reports are for educational purposes only and do not constitute investment advice.",
        "report_index": "Report Index",
        "ticker": "Ticker",
        "company": "Company",
        "files": "Files",
        "reports": "Reports",
        "ai_notebooks": "NotebookLLM",
        "deep_dive": "Deep-dive analysis generated with Google NotebookLM",
        "research_docs": "📑 Research Documents",
        "notes_outlines": "📝 Notes & Outlines",
        "about_notebooklm": "About NotebookLLM Reports",
        "notebooklm_desc": "These documents are AI-synthesised research reports created using Google NotebookLM from primary source materials (10-K filings, investor presentations, earnings calls). They provide deep-dive analysis from a structured, document-grounded AI perspective.",
        "sec_filings": "SEC Filings",
        "annual_reports": "10-K Annual Reports",
        "sec_annual_desc": "SEC annual filings (Form 10-K) stored locally",
        "total": "Total",
        "companies": "companies",
        "last_indexed": "Last indexed",
        "file_location": "File Location",
        "file_location_desc": "10-K PDFs are stored in the `10-k/` directory of the repository. Clone the repo to access them locally",
        "company_index": "Company Index",
        "years": "Years",
        "view_filings": "View Filings",
        "annual_filings_for": "Annual Filings for",
        "year": "Year",
        "filename": "Filename",
        "view": "View",
        "back_to_index": "Back to 10-K Index",
        "download_more": "Download More Filings",
        "download_desc": "Use the included Python scripts to download additional 10-K filings",
        "quarterly_reports": "10-Q Quarterly Reports",
        "quarterly_desc": "Quarterly SEC filings",
        "institutional_holdings": "13-F Institutional Holdings",
        "institutional_desc": "13-F filings track institutional investment managers' holdings",
        "current_reports": "6-K Current Reports",
        "foreign_desc": "Foreign private issuer current reports",
        "investor_day": "Investor Day Materials",
        "investor_day_desc": "Company presentations from investor days and analyst events",
        "presentations": "Presentations",
        "download_scripts": "Download Scripts",
        "scripts_desc": "Python and Bash tools for batch-downloading SEC filings",
    },
    "zh": {
        "last_updated": "最後更新",
        "last_built": "最後建置",
        "sector": "產業",
        "available_reports": "可用報告",
        "latest_reports": "🆕 最新報告",
        "open_latest": "查看最新",
        "latest": "最新",
        "show_older": "顯示其他 {n} 份報告",
        "markdown_reports": "📄 Markdown 報告",
        "html_reports": "🌐 互動式 HTML 報告",
        "fundamental_analysis": "📊 基本面分析",
        "technical_analysis": "📈 技術分析",
        "other_reports": "🗂️ 其他報告",
        "price_target": "🎯 目標價與隱含報酬率",
        "pt_scenario": "情境",
        "pt_prob": "發生機率",
        "pt_target": "12M 目標價",
        "pt_current": "當前股價",
        "pt_return": "隱含報酬率",
        "pt_weighted": "權重期望值",
        "pt_weighted_target": "加權目標價",
        "pt_note": ("情境目標價取自最新基本面報告（{report}）；當前股價為 {price_date} 收盤價。"
                    "權重期望值 = 發生機率 × 目標價。"),
        "pt_note_default": "發生機率採用預設的悲觀／基準／樂觀權重（報告未提供機率欄位）。",
        "analysis_reports": "分析報告",
        "reports_nav_title": "AI 生成報告",
        "market_news": "市場新聞",
        "market_news_desc": "AI 生成的每日市場新聞與個股消息彙整",
        "ai_generated": "AI 生成的投資研究報告",
        "disclaimer": "免責聲明",
        "disclaimer_text": "所有報告僅供教育目的，不構成投資建議。",
        "report_index": "報告索引",
        "ticker": "股票代號",
        "company": "公司",
        "files": "檔案",
        "reports": "報告",
        "ai_notebooks": "NotebookLLM",
        "deep_dive": "使用 Google NotebookLM 生成的深度分析",
        "research_docs": "📑 研究文件",
        "notes_outlines": "📝 筆記與大綱",
        "about_notebooklm": "關於 NotebookLLM 報告",
        "notebooklm_desc": "這些文件是使用 Google NotebookLM 從主要來源資料（10-K 文件、投資者簡報、財報電話會議）創建的 AI 綜合研究報告。它們從結構化、基於文件的 AI 視角提供深度分析。",
        "sec_filings": "SEC 文件",
        "annual_reports": "10-K 年度報告",
        "sec_annual_desc": "本地儲存的 SEC 年度文件（Form 10-K）",
        "total": "總計",
        "companies": "家公司",
        "last_indexed": "最後索引",
        "file_location": "檔案位置",
        "file_location_desc": "10-K PDF 檔案儲存在存儲庫的 `10-k/` 目錄中。複製存儲庫以在本地訪問它們",
        "company_index": "公司索引",
        "years": "年份",
        "view_filings": "查看文件",
        "annual_filings_for": "年度文件 —",
        "year": "年份",
        "filename": "檔案名稱",
        "view": "查看",
        "back_to_index": "返回 10-K 索引",
        "download_more": "下載更多文件",
        "download_desc": "使用包含的 Python 腳本下載額外的 10-K 文件",
        "quarterly_reports": "10-Q 季度報告",
        "quarterly_desc": "季度 SEC 文件",
        "institutional_holdings": "13-F 機構持股",
        "institutional_desc": "13-F 文件追蹤機構投資管理者的持股",
        "current_reports": "6-K 當前報告",
        "foreign_desc": "外國私人發行人當前報告",
        "investor_day": "投資者日資料",
        "investor_day_desc": "來自投資者日和分析師活動的公司簡報",
        "presentations": "簡報",
        "download_scripts": "下載腳本",
        "scripts_desc": "用於批量下載 SEC 文件的 Python 和 Bash 工具",
    }
}

# ── Company metadata ──────────────────────────────────────────────────────────
COMPANY_META: dict[str, dict] = {
    "onds":     {"name": "Ondas Inc.",                "flag": "🚁", "sector": "Defense / Drone"},
    "ondas":    {"name": "Ondas Inc.",                "flag": "🚁", "sector": "Defense / Drone"},
    "msft":     {"name": "Microsoft Corp.",           "flag": "💻", "sector": "Technology"},
    "pltr":     {"name": "Palantir Technologies",     "flag": "🔮", "sector": "Data / AI"},
    "tsla":     {"name": "Tesla Inc.",                "flag": "⚡", "sector": "EV / Robotics"},
    "grab":     {"name": "Grab Holdings",             "flag": "🚗", "sector": "Southeast Asia Tech"},
    "nvda":     {"name": "NVIDIA Corporation",        "flag": "🎮", "sector": "Semiconductors / AI"},
    "aapl":     {"name": "Apple Inc.",                "flag": "🍎", "sector": "Consumer Tech"},
    "amzn":     {"name": "Amazon.com Inc.",           "flag": "📦", "sector": "E-Commerce / Cloud"},
    "meta":     {"name": "Meta Platforms Inc.",       "flag": "📱", "sector": "Social Media / AI"},
    "googl":    {"name": "Alphabet Inc.",             "flag": "🔍", "sector": "Search / Cloud"},
    "rklb":     {"name": "Rocket Lab USA",            "flag": "🚀", "sector": "Space"},
    "avav":     {"name": "AeroVironment Inc.",        "flag": "✈️",  "sector": "Defense Drones"},
    "rcat":     {"name": "Red Cat Holdings",          "flag": "🐱", "sector": "Tactical UAS"},
    "ktos":     {"name": "Kratos Defense",            "flag": "🛡️",  "sector": "Defense"},
    "nee":      {"name": "NextEra Energy Inc.",       "flag": "🌱", "sector": "Clean Energy"},
    "sofi":     {"name": "SoFi Technologies",         "flag": "💳", "sector": "Fintech"},
    "vst":      {"name": "Vistra Corp.",              "flag": "⚡", "sector": "Utilities / Nuclear"},
    "vava":     {"name": "Vava (AeroVironment)",      "flag": "✈️",  "sector": "Defense"},
    "amd":      {"name": "Advanced Micro Devices",    "flag": "🔴", "sector": "Semiconductors"},
    "avgo":     {"name": "Broadcom Inc.",             "flag": "📡", "sector": "Semiconductors"},
    "brk.b":    {"name": "Berkshire Hathaway",        "flag": "🏦", "sector": "Conglomerate / Insurance"},
    "goog":     {"name": "Alphabet Inc.",             "flag": "🔍", "sector": "Search / Cloud"},
    "orcl":     {"name": "Oracle Corp.",              "flag": "🗄️",  "sector": "Enterprise Software / Cloud"},
    "tsm":      {"name": "Taiwan Semiconductor",      "flag": "🇹🇼", "sector": "Semiconductors / Foundry"},
}

def get_meta(ticker: str) -> dict:
    key = ticker.lower()
    return COMPANY_META.get(key, {
        "name": ticker.upper(),
        "flag": "📊",
        "sector": "Equity"
    })


# ── K線 hero chart ─────────────────────────────────────────────────────────────
# Chart payloads are *derived* from the committed price store (data/prices/*.csv,
# see docs/PRICE_STORE_DESIGN.md) at build time and written into docs/ — they are
# never committed. Deriving here keeps one source of truth for every chart and
# lets each page ask for the window it needs.

# Bars per payload: 360 trading days of visible range (the widest range button)
# plus 200 bars of lookback so a client-side MA200 is fully defined at the left
# edge instead of starting 200 bars in.
KLINE_VISIBLE_BARS = 360
KLINE_LOOKBACK_BARS = 200


def kline_bars(ticker: str) -> "list[dict]":
    """Bars for a ticker's chart payload, oldest→newest ([] when unavailable).

    Reads the store live off the module global so tests can monkeypatch it.
    """
    bars = prices.load_store(ticker, PRICES_DIR)
    if not bars:
        return []
    return prices.window(bars, days=KLINE_VISIBLE_BARS,
                         lookback=KLINE_LOOKBACK_BARS)


def kline_payload(ticker: str) -> "str | None":
    """The JSON text the widget fetches, or None when the store has no data.

    Short keys and rounded numbers keep the file small (~40 KB); the shape is
    what docs/javascripts/kline-chart.js already consumes.
    """
    bars = kline_bars(ticker)
    if not bars:
        return None
    symbol = prices.to_yf_symbol(ticker)
    return json.dumps({
        "ticker": ticker.upper(),
        "symbol": symbol,
        "currency": prices.currency_for(symbol),
        # The newest bar's date, not today's: the payload describes the data it
        # contains, so a stale store reads as stale rather than as fresh.
        "updated": bars[-1]["date"],
        "bars": [{"t": b["date"],
                  "o": float(prices.fmt_price(b["open"])),
                  "h": float(prices.fmt_price(b["high"])),
                  "l": float(prices.fmt_price(b["low"])),
                  "c": float(prices.fmt_price(b["close"])),
                  "v": b["volume"]} for b in bars],
    }, separators=(",", ":"))


def write_kline_payload(ticker: str, dst_dir: Path) -> bool:
    """Write <dst_dir>/kline.json for a ticker. False when there's no data."""
    payload = kline_payload(ticker)
    if payload is None:
        return False
    ensure(dst_dir)
    dst = dst_dir / "kline.json"
    if not dst.exists() or dst.read_text(encoding="utf-8") != payload:
        dst.write_text(payload, encoding="utf-8")
    return True


def kline_block(ticker: str, *, src: str = "kline.json",
                as_of: str = "", ma: str = "") -> str:
    """Raw-HTML div for the TradingView-style candlestick chart.

    Empty string when the store has no data, so pages without OHLCV never render
    a broken widget. `md_in_html` (see mkdocs.yml) lets this pass through
    unescaped.

    src    — fetch path *relative to the page's directory URL*. Report bodies are
             served one level deeper than the ticker index, hence "../kline.json".
             MkDocs rewrites relative paths in Markdown but not in raw HTML, so
             this has to be right at build time.
    as_of  — truncate the chart to this date. Required on dated report pages: the
             store is always current, so without it a report would show today's
             prices under text written about an older snapshot.
    ma     — moving averages to overlay, e.g. "30+,60+,200" ("+" = on by default).
    """
    if not kline_bars(ticker):
        return ""
    attrs = [f'class="kline-widget"', f'data-ticker="{ticker.upper()}"',
             f'data-src="{src}"']
    if as_of:
        attrs.append(f'data-as-of="{as_of}"')
    if ma:
        attrs.append(f'data-ma="{ma}"')
    return f'<div {" ".join(attrs)}></div>'


# ── Price-target scenario table (rendered directly under the hero chart) ──────
# Fundamental reports carry a Bear/Base/Bull scenario table, but the layouts are
# AI-generated and share almost nothing: column count/order/labels all vary, the
# target may sit behind several other $ columns (EPS, revenue, cash…), rows are
# labelled with an emoji, plain text, or both, and a probability column may be
# absent entirely. So we parse structurally — scan every pipe-table, key off a
# "目標價" column header, and read each field from its named column.
_SCENARIO_META = {
    "bear": ("🔴", "悲觀", "Bear"),
    "base": ("🟡", "基準", "Base"),
    "bull": ("🟢", "樂觀", "Bull"),
}
_SCENARIO_ORDER = ("bear", "base", "bull")
_EMOJI_TO_KEY = {"🔴": "bear", "🟡": "base", "🟢": "bull"}
_TEXT_TO_KEY = {"悲觀": "bear", "基準": "base", "樂觀": "bull",
                "bear": "bear", "base": "base", "bull": "bull"}
# Default weights used only when a table gives targets but no probability column.
_DEFAULT_PROBS = {"bear": 0.20, "base": 0.60, "bull": 0.20}

_MONEY_RE = re.compile(r"\$\s*(\d[\d,]*(?:\.\d+)?)")
_PCT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")


def _current_price(ticker: str) -> "tuple[float, str] | None":
    """Latest close and its date from the price store, or None."""
    bars = prices.load_store(ticker, PRICES_DIR)
    if not bars:
        return None
    last = bars[-1]
    try:
        return float(last["close"]), last["date"]
    except (KeyError, TypeError, ValueError):
        return None


def _table_cells(row: str) -> "list[str]":
    """Split a Markdown table row into cleaned cells (drops markdown emphasis)."""
    return [c.replace("*", "").replace("`", "").strip()
            for c in row.strip().strip("|").split("|")]


def _iter_pipe_tables(text: str):
    """Yield each Markdown pipe-table as a list of its raw lines."""
    block: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("|"):
            block.append(line)
        elif block:
            if len(block) >= 2:
                yield block
            block = []
    if len(block) >= 2:
        yield block


def _is_separator(cells: "list[str]") -> bool:
    return all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c)


def _target_col(header: "list[str]") -> "int | None":
    """Index of the target-price column (prefer '隱含…目標價' over any '目標價')."""
    cands = [i for i, h in enumerate(header) if "目標價" in h]
    if not cands:
        return None
    for i in cands:
        if "隱含" in header[i]:
            return i
    return cands[0]


def _prob_col(header: "list[str]") -> "int | None":
    """Index of the probability column ('發生機率' / '機率權重' / '權重'…),
    excluding return/contribution columns that also mention 機率/權重."""
    for i, h in enumerate(header):
        if ("機率" in h or "權重" in h) and not any(
            x in h for x in ("報酬", "回報", "貢獻", "期望", "目標")
        ):
            return i
    return None


def _classify_scenario(cell0: str) -> "str | None":
    """Map a table's first cell to bear/base/bull, or None if it isn't one."""
    s = cell0.strip()
    for emoji, key in _EMOJI_TO_KEY.items():
        if s.startswith(emoji):
            return key
    core = re.sub(r"\s+", "", s).lower()
    for kw, key in _TEXT_TO_KEY.items():
        if core in (kw, kw + "情境", kw + "case"):
            return key
    return None


def parse_scenario_targets(md_path: "Path") -> "list[dict]":
    """Extract Bear/Base/Bull rows (12M target + probability) from a fundamental
    report's scenario table.

    Scans every pipe-table and accepts the first one that has a '目標價' column
    and all three scenarios; upgrades to a later table if it additionally carries
    a probability column. When no probability column exists the default
    Bear/Base/Bull weights are applied. Returns [] (caller omits the block) if no
    table yields all three scenarios."""
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        return []

    best: "list[dict]" = []
    best_has_prob = False
    for block in _iter_pipe_tables(text):
        header = _table_cells(block[0])
        tgt_idx = _target_col(header)
        if tgt_idx is None:
            continue
        prob_idx = _prob_col(header)
        rows: dict[str, dict] = {}
        for raw in block[1:]:
            cells = _table_cells(raw)
            if not cells or _is_separator(cells) or tgt_idx >= len(cells):
                continue
            key = _classify_scenario(cells[0])
            if key is None or key in rows:
                continue
            money_m = _MONEY_RE.search(cells[tgt_idx])
            if not money_m:
                continue
            try:
                target = float(money_m.group(1).replace(",", ""))
            except ValueError:
                continue
            if target <= 0:
                continue
            prob = None
            if prob_idx is not None and prob_idx < len(cells):
                pm = _PCT_RE.search(cells[prob_idx])
                if pm:
                    prob = float(pm.group(1)) / 100.0
            emoji, zh, en = _SCENARIO_META[key]
            rows[key] = {"key": key, "zh": zh, "en": en, "emoji": emoji,
                         "target": target, "prob": prob}

        if len(rows) == 3:
            has_prob = all(rows[k]["prob"] is not None for k in rows)
            if not best or (has_prob and not best_has_prob):
                best = [rows[k] for k in _SCENARIO_ORDER]
                best_has_prob = has_prob

    if best and not best_has_prob:
        for s in best:
            s["prob"] = _DEFAULT_PROBS[s["key"]]
            s["prob_default"] = True
    return best


def _fmt_money(v: float) -> str:
    return f"${v:,.2f}"


def _fmt_pct(v: float) -> str:
    return f"{v * 100:+.1f}%"


def target_price_block(ticker: str, fund_md: "Path | None", lang: str) -> str:
    """Markdown for the price-target & implied-return table shown right under the
    hero chart. Scenario targets come from the latest fundamental report; the
    current price comes from the price store and implied returns are recomputed
    against it. Returns '' when either source is unavailable so the page degrades
    gracefully to just the chart."""
    if fund_md is None:
        return ""
    scenarios = parse_scenario_targets(fund_md)
    if not scenarios:
        return ""
    price_info = _current_price(ticker)
    if price_info is None:
        return ""
    current, price_date = price_info
    if current <= 0:
        return ""

    weighted_target = sum(s["prob"] * s["target"] for s in scenarios)
    total_prob = sum(s["prob"] for s in scenarios)
    weighted_ret = weighted_target / current - 1

    lbl = "zh" if lang == "zh" else "en"
    lines = [
        f"### {t(lang, 'price_target')}",
        "",
        (f"| {t(lang, 'pt_scenario')} | {t(lang, 'pt_prob')} | {t(lang, 'pt_target')} "
         f"| {t(lang, 'pt_current')} | {t(lang, 'pt_return')} | {t(lang, 'pt_weighted')} |"),
        "|---|---|---|---|---|---|",
    ]
    for s in scenarios:
        implied = s["target"] / current - 1
        contrib = s["prob"] * s["target"]
        lines.append(
            f"| {s['emoji']} {s[lbl]} | {s['prob'] * 100:.0f}% "
            f"| {_fmt_money(s['target'])} | {_fmt_money(current)} "
            f"| {_fmt_pct(implied)} | {_fmt_money(contrib)} |"
        )
    lines.append(
        f"| **{t(lang, 'pt_weighted_target')}** | {total_prob * 100:.0f}% "
        f"| **{_fmt_money(weighted_target)}** | {_fmt_money(current)} "
        f"| **{_fmt_pct(weighted_ret)}** | — |"
    )
    report_date = (d.isoformat() if (d := _file_date(fund_md)) else fund_md.stem)
    note = t(lang, "pt_note").format(report=report_date, price_date=price_date)
    if any(s.get("prob_default") for s in scenarios):
        note += " " + t(lang, "pt_note_default")
    lines += ["", f"> {note}", ""]
    return "\n".join(lines)


# ── Mermaid pre-rendering ─────────────────────────────────────────────────────
_MMDC = shutil.which("mmdc")  # None if not installed
_MERMAID_CACHE_FILE = ROOT / ".mermaid_cache.json"
_mermaid_cache: dict[str, str] = {}


def _load_mermaid_cache():
    global _mermaid_cache
    if _MERMAID_CACHE_FILE.exists():
        try:
            _mermaid_cache = json.loads(_MERMAID_CACHE_FILE.read_text())
        except Exception:
            _mermaid_cache = {}


def _save_mermaid_cache():
    _MERMAID_CACHE_FILE.write_text(json.dumps(_mermaid_cache, indent=2))


def _render_mermaid_block(diagram: str) -> str | None:
    """Render a Mermaid diagram string to an SVG string via mmdc.
    Returns the SVG string, or None on failure."""
    key = hashlib.md5(diagram.encode()).hexdigest()
    if key in _mermaid_cache:
        return _mermaid_cache[key]

    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "diagram.mmd"
        dst = Path(tmpdir) / "diagram.svg"
        src.write_text(diagram, encoding="utf-8")
        result = subprocess.run(
            [_MMDC, "-i", str(src), "-o", str(dst),
             "--backgroundColor", "transparent",
             "--theme", "dark"],
            capture_output=True, timeout=30,
        )
        if result.returncode != 0 or not dst.exists():
            return None
        svg = dst.read_text(encoding="utf-8")
        # Strip XML declaration and DOCTYPE if present
        svg = re.sub(r"<\?xml[^>]*\?>\s*", "", svg)
        svg = re.sub(r"<!DOCTYPE[^>]*>\s*", "", svg)
        _mermaid_cache[key] = svg
        return svg


# Mermaid syntax repair + fence matcher are shared with the report
# generator so both apply exactly one implementation. See
# analysis.utils.mermaid for the full rationale.
from analysis.utils.mermaid import (  # noqa: E402
    _MERMAID_FENCE_RE,
    sanitize_mermaid,
    sanitize_mermaid_blocks,
)


def prerender_mermaid(content: str) -> str:
    """Replace ```mermaid blocks with inline SVG if mmdc is available.
    Falls back to leaving the block unchanged if rendering fails."""
    if not _MMDC:
        return content

    def _replace(m: re.Match) -> str:
        diagram = m.group(1).strip()
        svg = _render_mermaid_block(diagram)
        if svg:
            return f'<div class="mermaid-svg">\n{svg}\n</div>'
        return m.group(0)  # fallback: keep original

    return _MERMAID_FENCE_RE.sub(_replace, content)


# ── Helpers ───────────────────────────────────────────────────────────────────
def t(lang: str, key: str) -> str:
    """Get translated text for the given language and key."""
    return LANG_TEXT.get(lang, LANG_TEXT["en"]).get(key, key)


def get_docs_root(lang: str) -> Path:
    """Get the docs root directory for the given language."""
    return DOCS_ZH if lang == "zh" else DOCS


def ensure(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def clean_generated(path: Path):
    """Remove generated sub-dirs, leave hand-crafted files."""
    for sub in ["reports", "market_news", "notebooks", "sec", "investor_day"]:
        target = path / sub
        if target.exists():
            shutil.rmtree(target)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "-", text.lower()).strip("-")


# ── Report header: front matter → rendered table ─────────────────────────────
# Reports are written with their own YAML front matter (title/date/ticker/…).
# MkDocs strips exactly ONE leading block, so prepending a second one left the
# report's own block visible as a run-on paragraph at the top of the page.
# Instead we merge the two into a single block and re-emit the report's fields
# as a Markdown table — the header GitHub renders for front matter natively.
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n", re.DOTALL)


def split_frontmatter(content: str) -> "tuple[str, str]":
    """Split a leading YAML front-matter block off `content` → (yaml, body)."""
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return "", content
    return m.group(1), content[m.end():]


def frontmatter_table(yaml_body: str) -> str:
    """Render the top-level `key: value` front-matter fields as a table."""
    rows = []
    for line in yaml_body.splitlines():
        # Skip blanks, comments and nested keys — only scalar fields are shown.
        if not line.strip() or line[:1] in (" ", "\t", "#"):
            continue
        key, sep, value = line.partition(":")
        value = value.strip().strip('"').strip("'").replace("|", r"\|")
        if not sep or not value:
            continue
        rows.append(f"| **{key.strip()}** | {value} |")
    if not rows:
        return ""
    return "\n".join(["| | |", "|---|---|", *rows]) + "\n\n"


# ── Static chart embed ───────────────────────────────────────────────────────
# `use_directory_urls` (MkDocs default) serves each report at <page>/index.html,
# so a bare relative `<img src="chart.png">` resolves one directory too deep.
# MkDocs rewrites relative paths for Markdown images but not for raw HTML, so
# convert the embed to Markdown and let md_in_html parse it inside <details>.
_STATIC_IMG_RE = re.compile(
    r'<img\s+src="(?P<src>[^"/:]+\.(?:png|jpe?g|gif|svg|webp))"'
    r'(?:\s+alt="(?P<alt>[^"]*)")?[^>]*>'
)


def fix_static_chart_embed(content: str) -> str:
    """Rewrite raw-HTML images with page-relative sources as Markdown images."""
    if "<img" not in content:
        return content
    # md_in_html needs the opt-in attribute to parse the Markdown we inject.
    content = content.replace("<details>\n<summary>", '<details markdown="1">\n<summary>')
    return _STATIC_IMG_RE.sub(
        lambda m: f'\n![{m.group("alt") or "Chart"}]({m.group("src")})\n', content
    )


def copy_file(src: Path, dst: Path, extra_meta: str = ""):
    """Copy src → dst. For Markdown, merge `extra_meta` into the file's own
    front matter (re-emitted as a header table), repair chart embeds and
    pre-render Mermaid; uses a content-equality incremental check so changed
    `extra_meta` is always applied. Binary files use a cheap mtime check."""
    ensure(dst.parent)
    if src.suffix == ".md":
        content = src.read_text(encoding="utf-8")
        # Repair LLM Mermaid syntax on every build (CI has no mmdc, so blocks
        # render client-side and must parse cleanly).
        content = sanitize_mermaid_blocks(content)
        if _MMDC:
            # Pre-render Mermaid blocks to SVG inline
            content = prerender_mermaid(content)
        content = fix_static_chart_embed(content)
        if extra_meta:
            yaml_body, body = split_frontmatter(content)
            merged = f"{extra_meta}\n{yaml_body}" if yaml_body else extra_meta
            content = (
                f"---\n{merged}\n---\n\n"
                + frontmatter_table(yaml_body)
                + body.lstrip("\n")
            )
        if _INCREMENTAL and dst.exists() and dst.read_text(encoding="utf-8") == content:
            return
        dst.write_text(content, encoding="utf-8")
        print(f"  copy  {src.relative_to(ROOT)}  →  {dst.relative_to(ROOT)}")
    else:
        # Incremental: skip if dst exists and source hasn't changed since last copy
        if _INCREMENTAL and dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
            return
        shutil.copy2(src, dst)
        print(f"  copy  {src.relative_to(ROOT)}  →  {dst.relative_to(ROOT)}")


def write(path: Path, content: str):
    ensure(path.parent)
    # Incremental: skip if the generated content is identical to what's on disk
    if _INCREMENTAL and path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8")
    print(f"  write {path.relative_to(ROOT)}")


# ── 1. ai_gen_report/stock → docs/reports/ ───────────────────────────────────
def build_reports(lang: str = "en"):
    docs_root = get_docs_root(lang)
    DST_REPORTS = docs_root / "reports"
    ensure(DST_REPORTS)
    report_index_rows: list[str] = []
    nav_entries: list[str] = []

    if not any(root.exists() for root in report_roots()):
        write(DST_REPORTS / "index.md", f"# {t(lang, 'reports')}\n\nNo reports found.\n")
        return

    tickers = _sample_dirs(merged_ticker_dirs())

    for ticker_dir in tickers:
        ticker = ticker_dir.name.lower()
        meta = get_meta(ticker)
        dst_dir = DST_REPORTS / ticker
        ensure(dst_dir)

        # Collect files for this ticker, merged across fundamental/technical/stock roots
        files = ticker_files(ticker)
        md_files   = [f for f in files if f.suffix == ".md"]
        html_files = [f for f in files if f.suffix == ".html"]
        other_files = [f for f in files if f.suffix not in (".md", ".html", "") and f.is_file()]

        # Perf fix #4 — only publish reports within the retention window
        md_files    = [f for f in md_files if within_retention(f)]
        html_files  = [f for f in html_files if within_retention(f)]
        other_files = [f for f in other_files if within_retention(f)]

        # Sample-build: cap files per ticker so a smoke build stays tiny.
        md_files    = _sample(md_files)
        html_files  = _sample(html_files)
        other_files = _sample(other_files)

        if not (md_files or html_files):
            continue  # skip empty dirs

        # Derive the OHLCV payload from the price store next to the page, so the
        # hero chart fetches it with a page-relative URL — works for EN and ZH
        # and under `mkdocs serve`. Report bodies in this same directory reach it
        # as "../kline.json" from their own directory URL.
        write_kline_payload(ticker, dst_dir)

        # Split md files by report type, newest-first so the latest is on top.
        technical_md = by_date_desc([f for f in md_files if f.name.startswith("technical_")])
        fundamental_md = by_date_desc([f for f in md_files if f.name.startswith("fundamental_")])
        other_md = by_date_desc([f for f in md_files if not f.name.startswith(("technical_", "fundamental_"))])
        html_files = by_date_desc(html_files)

        # EN: copy report files; ZH: skip copies — link to EN pages instead
        if lang == "en":
            for f in md_files:
                # Perf fix #1 — exclude report bodies from the search index
                copy_file(f, dst_dir / f.name, extra_meta=SEARCH_EXCLUDE_META)
            for f in html_files + other_files:
                copy_file(f, dst_dir / f.name)

        # For ZH, links point to the EN pages (absolute site paths).
        # For EN, links are relative (MkDocs resolves .md → directory URL).
        def report_link(f: Path) -> str:
            if lang == "zh":
                # Absolute link → EN report page
                return f"{SITE_BASE}/reports/{ticker}/{f.stem}/"
            return f.name  # relative, resolved by MkDocs

        def html_link(f: Path) -> str:
            if lang == "zh":
                return f"{SITE_BASE}/reports/{ticker}/{f.name}"
            return f.name

        def emit_section(heading: str, ordered: list[Path], link_fn):
            """Append a report section: the RECENT_COUNT newest shown directly,
            the remainder folded into a collapsible 'Show N older' block."""
            if not ordered:
                return
            lines.append(f"### {heading}")
            lines.append("")
            for f in ordered[:RECENT_COUNT]:
                lines.append(f"- [{report_label(f)}]({link_fn(f)})")
            lines.append("")
            older = ordered[RECENT_COUNT:]
            if older:
                lines.append(f'??? note "{t(lang, "show_older").format(n=len(older))}"')
                lines.append("")
                for f in older:
                    lines.append(f"    - [{report_label(f)}]({link_fn(f)})")
                lines.append("")

        # Generate per-ticker index.md
        lines = [
            f"# {meta['flag']} {meta['name']} ({ticker.upper()})",
            "",
            f"> **{t(lang, 'sector')}:** {meta['sector']}  |  **{t(lang, 'last_updated')}:** {TODAY}",
            "",
        ]
        # TradingView-style candlestick chart (30D/180D/360D) as the page hero.
        chart = kline_block(ticker)
        if chart:
            lines += [chart, ""]
        # Price-target & implied-return table directly under the chart, sourced
        # from the latest fundamental report's scenario targets.
        target_tbl = target_price_block(
            ticker, fundamental_md[0] if fundamental_md else None, lang
        )
        if target_tbl:
            lines += [target_tbl]
        lines += [
            "---",
            "",
        ]

        # Quick-access cards → the single newest report of each type.
        cards = []
        if fundamental_md:
            cards.append((t(lang, "fundamental_analysis"), fundamental_md[0], report_link, False))
        if technical_md:
            cards.append((t(lang, "technical_analysis"), technical_md[0], report_link, False))
        if other_md:
            cards.append((t(lang, "other_reports"), other_md[0], report_link, False))
        if html_files:
            cards.append((t(lang, "html_reports"), html_files[0], html_link, True))
        if cards:
            lines.append(f"## {t(lang, 'latest_reports')}")
            lines.append("")
            lines.append('<div class="grid cards" markdown>')
            lines.append("")
            for title, f, link_fn, is_html in cards:
                blank = "{target=_blank}" if is_html else ""
                lines.append(f"-   __{title}__")
                lines.append("")
                lines.append(f"    ---")
                lines.append("")
                lines.append(f"    **{t(lang, 'latest')}:** {report_label(f)}")
                lines.append("")
                lines.append(
                    f"    [:octicons-arrow-right-24: {t(lang, 'open_latest')}]"
                    f"({link_fn(f)}){blank}"
                )
                lines.append("")
            lines.append("</div>")
            lines.append("")

        lines.append(f"## {t(lang, 'available_reports')}")
        lines.append("")

        emit_section(t(lang, "fundamental_analysis"), fundamental_md, report_link)
        emit_section(t(lang, "technical_analysis"), technical_md, report_link)
        emit_section(t(lang, "other_reports"), other_md, report_link)

        if html_files:
            lines.append(f"### {t(lang, 'html_reports')}")
            lines.append("")
            for f in html_files:
                lines.append(f"- [{report_label(f)}]({html_link(f)}){{target=_blank}}")
            lines.append("")

        write(dst_dir / "index.md", "\n".join(lines))

        # Row for top-level index table
        fund_badge = f"📊 {len(fundamental_md)}" if fundamental_md else ""
        tech_badge = f"📈 {len(technical_md)}" if technical_md else ""
        other_badge = f"🗂️ {len(other_md)}" if other_md else ""
        html_badge = f"🌐 {len(html_files)}" if html_files else ""
        badges = " &nbsp; ".join(b for b in [fund_badge, tech_badge, other_badge, html_badge] if b)
        # Company name is redundant for tickers we have no metadata for (name
        # defaults to the ticker itself) — show a dash instead of repeating it.
        company = meta["name"] if meta["name"] != ticker.upper() else "—"
        # Whole rows are clickable (javascripts/clickable-rows.js), so no
        # separate "View" column is needed — the linked ticker doubles as it.
        report_index_rows.append(
            f"| {meta['flag']} **[{ticker.upper()}]({ticker}/index.md)** "
            f"| {company} | {meta['sector']} | {badges} |"
        )

    # Top-level reports/index.md
    top_lines = [
        f"# {t(lang, 'analysis_reports')}",
        "",
        f"> {t(lang, 'ai_generated')}. {t(lang, 'last_built')}: **{TODAY}**",
        "",
        f"!!! warning \"{t(lang, 'disclaimer')}\"",
        f"    {t(lang, 'disclaimer_text')}",
        "",
        f"## {t(lang, 'report_index')}",
        "",
        f"> 📊 = {t(lang, 'fundamental_analysis').replace('📊 ', '')}  &nbsp; "
        f"📈 = {t(lang, 'technical_analysis').replace('📈 ', '')}  &nbsp; "
        f"🗂️ = {t(lang, 'other_reports').replace('🗂️ ', '')}  &nbsp; "
        f"🌐 = {t(lang, 'html_reports').replace('🌐 ', '')}",
        "",
        f"| {t(lang, 'ticker')} | {t(lang, 'company')} | {t(lang, 'sector')} | {t(lang, 'reports')} |",
        "|--------|---------|--------|-------|",
    ] + report_index_rows

    # Per-ticker detail sections
    for ticker_dir in tickers:
        ticker = ticker_dir.name.lower()
        meta = get_meta(ticker)
        files = ticker_files(ticker)
        # Cap identically to the copy loop above so sample builds stay link-consistent.
        md_files   = _sample([f for f in files if f.suffix == ".md" and within_retention(f)])
        html_files = _sample([f for f in files if f.suffix == ".html" and within_retention(f)])
        if not (md_files or html_files):
            continue

        technical_md = by_date_desc([f for f in md_files if f.name.startswith("technical_")])
        fundamental_md = by_date_desc([f for f in md_files if f.name.startswith("fundamental_")])
        other_md = by_date_desc([f for f in md_files if not f.name.startswith(("technical_", "fundamental_"))])
        html_files = by_date_desc(html_files)

        top_lines += [
            "",
            f"---",
            "",
            f"## {meta['flag']} {ticker.upper()} — {meta['name']}",
            "",
            f"**{t(lang, 'sector')}:** {meta['sector']}",
            "",
        ]
        def top_link(f: Path) -> str:
            if lang == "zh":
                return f"{SITE_BASE}/reports/{ticker}/{f.stem}/"
            return f"{ticker}/{f.name}"

        def emit_top_section(label_key: str, ordered: list[Path]):
            """Newest-first list on the top-level index: newest RECENT_COUNT
            shown, the rest collapsed."""
            if not ordered:
                return
            top_lines.append(f"**{t(lang, label_key)}:**")
            top_lines.append("")
            for f in ordered[:RECENT_COUNT]:
                top_lines.append(f"- [{report_label(f)}]({top_link(f)})")
            top_lines.append("")
            older = ordered[RECENT_COUNT:]
            if older:
                top_lines.append(f'??? note "{t(lang, "show_older").format(n=len(older))}"')
                top_lines.append("")
                for f in older:
                    top_lines.append(f"    - [{report_label(f)}]({top_link(f)})")
                top_lines.append("")

        emit_top_section("fundamental_analysis", fundamental_md)
        emit_top_section("technical_analysis", technical_md)
        emit_top_section("other_reports", other_md)
        if html_files:
            top_lines.append(f"**{t(lang, 'html_reports')}:**")
            top_lines.append("")
            for f in html_files:
                label = report_label(f)
                if lang == "zh":
                    top_lines.append(f"- [:material-open-in-new: {label}]({SITE_BASE}/reports/{ticker}/{f.name}){{target=_blank .pdf-btn}}")
                else:
                    top_lines.append(f"- [:material-open-in-new: {label}]({ticker}/{f.name}){{target=_blank .pdf-btn}}")
            top_lines.append("")

    write(DST_REPORTS / "index.md", "\n".join(top_lines))


# ── 1b. ai_gen_report/market_news → docs/market_news/ ───────────────────────
def build_market_news(lang: str = "en"):
    """Build market news section from market_news/<ticker>/market_news_<date>_<provider>.md"""
    docs_root = get_docs_root(lang)
    DST_MARKET_NEWS = docs_root / "market_news"
    ensure(DST_MARKET_NEWS)

    if not SRC_MARKET_NEWS.exists():
        write(DST_MARKET_NEWS / "index.md", f"# {t(lang, 'market_news')}\n\nNo market news found.\n")
        return

    ticker_dirs = _sample_dirs(sorted([d for d in SRC_MARKET_NEWS.iterdir() if d.is_dir()]))
    index_rows: list[str] = []

    for ticker_dir in ticker_dirs:
        ticker = ticker_dir.name.lower()
        meta = get_meta(ticker)
        dst_ticker_dir = DST_MARKET_NEWS / ticker
        ensure(dst_ticker_dir)

        # Get all market_news_*.md files directly in ticker dir
        # Perf fix #4 — only publish news within the retention window
        md_files = _sample(sorted(
            [f for f in ticker_dir.iterdir() if f.is_file() and f.name.startswith("market_news_") and f.suffix == ".md" and within_retention(f)],
            reverse=True,
        ))
        # Also support legacy README.md in date subdirs
        date_dirs = _sample(sorted([d for d in ticker_dir.iterdir() if d.is_dir() and within_retention(d)], reverse=True))
        news_files = []

        for md_file in md_files:
            # Extract date from filename: market_news_YYYY-MM-DD_openai.md
            parts = md_file.stem.split("_")  # ['market', 'news', 'YYYY-MM-DD', 'openai']
            date_str = parts[2] if len(parts) >= 3 else md_file.stem
            if lang == "en":
                dst_file = dst_ticker_dir / md_file.name
                copy_file(md_file, dst_file, extra_meta=SEARCH_EXCLUDE_META)
                news_files.append((date_str, dst_file.name, None))
            else:
                # ZH: link to EN page, no copy
                en_url = f"{SITE_BASE}/market_news/{ticker}/{md_file.stem}/"
                news_files.append((date_str, md_file.name, en_url))

        for date_dir in date_dirs:
            readme = date_dir / "README.md"
            if readme.exists():
                if lang == "en":
                    dst_file = dst_ticker_dir / f"{date_dir.name}.md"
                    copy_file(readme, dst_file, extra_meta=SEARCH_EXCLUDE_META)
                    news_files.append((date_dir.name, dst_file.name, None))
                else:
                    en_url = f"{SITE_BASE}/market_news/{ticker}/{date_dir.name}/"
                    news_files.append((date_dir.name, f"{date_dir.name}.md", en_url))

        if not news_files:
            continue

        # Generate per-ticker index
        lines = [
            f"# {meta['flag']} {meta['name']} ({ticker.upper()}) — {t(lang, 'market_news')}",
            "",
            f"> **{t(lang, 'sector')}:** {meta['sector']}  |  **{t(lang, 'last_updated')}:** {TODAY}",
            "",
            "---",
            "",
            f"## 📰 {t(lang, 'market_news')}",
            "",
            f"| {t(lang, 'last_updated')} | {t(lang, 'reports')} |",
            "|------|--------|",
        ]
        for date_str, filename, en_url in news_files:
            link = en_url if en_url else filename
            lines.append(f"| {date_str} | [{date_str}]({link}) |")

        write(dst_ticker_dir / "index.md", "\n".join(lines))

        # Row for top-level index
        latest_date = news_files[0][0] if news_files else "—"
        company = meta["name"] if meta["name"] != ticker.upper() else "—"
        index_rows.append(
            f"| {meta['flag']} **[{ticker.upper()}]({ticker}/index.md)** "
            f"| {company} | {meta['sector']} "
            f"| {len(news_files)} | {latest_date} |"
        )

    # Top-level market_news/index.md
    top_lines = [
        f"# 📰 {t(lang, 'market_news')}",
        "",
        f"> {t(lang, 'market_news_desc')}. {t(lang, 'last_built')}: **{TODAY}**",
        "",
        f"!!! warning \"{t(lang, 'disclaimer')}\"",
        f"    {t(lang, 'disclaimer_text')}",
        "",
        f"## {t(lang, 'company_index')}",
        "",
        f"| {t(lang, 'ticker')} | {t(lang, 'company')} | {t(lang, 'sector')} | # {t(lang, 'reports')} | {t(lang, 'last_updated')} |",
        "|--------|---------|--------|---------|--------|",
    ] + index_rows

    write(DST_MARKET_NEWS / "index.md", "\n".join(top_lines))


# ── 2. notebook_llm → docs/notebooks/ ────────────────────────────────────────
# Perf fix #5 — notebook PDFs (14–19 MB each, ~200 MB total) are NOT copied into
# the published site. They are linked from GitHub raw instead, mirroring how the
# 10-K PDFs are handled. Keeps the GitHub Pages payload small.
NOTEBOOK_RAW_BASE = "https://raw.githubusercontent.com/yennanliu/finance_data/main/notebook_llm"


def build_notebooks(lang: str = "en"):
    docs_root = get_docs_root(lang)
    DST_NOTEBOOKS = docs_root / "notebooks"
    ensure(DST_NOTEBOOKS)

    if not SRC_NOTEBOOK.exists():
        write(DST_NOTEBOOKS / "index.md", f"# {t(lang, 'ai_notebooks')}\n\nNo notebooks found.\n")
        return

    ticker_dirs = _sample_dirs(sorted([d for d in SRC_NOTEBOOK.iterdir() if d.is_dir()]))
    index_rows: list[str] = []

    for ticker_dir in ticker_dirs:
        ticker = ticker_dir.name.lower()
        meta = get_meta(ticker)
        dst_dir = DST_NOTEBOOKS / ticker
        ensure(dst_dir)

        pdfs  = _sample(sorted(ticker_dir.glob("*.pdf")))
        txts  = _sample(sorted(ticker_dir.glob("*.txt")))
        mds   = _sample(sorted(ticker_dir.glob("*.md")))

        # EN: copy text/markdown only — PDFs are linked from GitHub (perf fix #5).
        # ZH: link to EN pages, no copy.
        if lang == "en":
            for f in txts + mds:
                # Exclude notebook bodies from the search index (perf fix #1)
                extra_meta = SEARCH_EXCLUDE_META if f.suffix == ".md" else ""
                copy_file(f, dst_dir / f.name, extra_meta=extra_meta)

        def nb_link(f: Path) -> str:
            # PDFs are not published with the site — link to the GitHub raw copy.
            if f.suffix == ".pdf":
                return f"{NOTEBOOK_RAW_BASE}/{ticker_dir.name}/{f.name}"
            if lang == "zh":
                # md files use directory URL; other non-md files keep the filename
                if f.suffix == ".md":
                    return f"{SITE_BASE}/notebooks/{ticker}/{f.stem}/"
                return f"{SITE_BASE}/notebooks/{ticker}/{f.name}"
            return f.name

        # Per-ticker index
        lines = [
            f"# {meta['flag']} {meta['name']} — {t(lang, 'ai_notebooks')}",
            "",
            f"> **{t(lang, 'sector')}:** {meta['sector']}",
            "",
            "---",
            "",
        ]

        if pdfs:
            lines += [f"## {t(lang, 'research_docs')}", ""]
            for f in pdfs:
                size_kb = int(f.stat().st_size / 1024)
                lines.append(
                    f"- [:material-file-pdf-box: {f.stem}]({nb_link(f)}){{target=_blank}}  "
                    f"<small>({size_kb} KB)</small>"
                )
            lines.append("")

        if txts or mds:
            lines += [f"## {t(lang, 'notes_outlines')}", ""]
            for f in list(txts) + list(mds):
                lines.append(f"- [{f.stem}]({nb_link(f)})")
            lines.append("")

        write(dst_dir / "index.md", "\n".join(lines))

        file_count = len(pdfs) + len(txts) + len(mds)
        index_rows.append(
            f"| {meta['flag']} [{ticker.upper()}]({ticker}/index.md) "
            f"| {meta['name']} | {meta['sector']} "
            f"| {len(pdfs)} PDFs, {len(txts)+len(mds)} notes |"
        )

    # Top-level notebooks/index.md
    top_lines = [
        f"# {t(lang, 'ai_notebooks')}",
        "",
        f"> {t(lang, 'deep_dive')}. {t(lang, 'last_built')}: **{TODAY}**",
        "",
        f"| | {t(lang, 'ticker')} | {t(lang, 'company')} | {t(lang, 'sector')} | {t(lang, 'files')} |",
        "|---|--------|---------|--------|-------|",
    ] + index_rows + [
        "",
        "---",
        "",
        f"## {t(lang, 'about_notebooklm')}",
        "",
        t(lang, 'notebooklm_desc'),
    ]

    write(DST_NOTEBOOKS / "index.md", "\n".join(top_lines))


# ── 3. 10-k → docs/sec/10k/ (per-company pages with GitHub PDF links) ────────
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/yennanliu/finance_data/main/10-k"
GITHUB_BLOB_BASE = "https://github.com/yennanliu/finance_data/blob/main/10-k"


def build_10k_index(lang: str = "en"):
    docs_root = get_docs_root(lang)
    DST_SEC = docs_root / "sec"
    DST_10K_DIR = DST_SEC / "10k"
    ensure(DST_10K_DIR)

    if not SRC_10K.exists():
        write(DST_SEC / "10k.md", f"# {t(lang, 'annual_reports')}\n\nNo filings found.\n")
        return

    company_dirs = _sample_dirs(sorted([d for d in SRC_10K.iterdir() if d.is_dir()]))
    table_rows: list[str] = []
    total_pdfs = 0

    for company_dir in company_dirs:
        pdfs = _sample(sorted(company_dir.glob("*.pdf"), key=lambda p: p.name, reverse=True))
        if not pdfs:
            continue
        total_pdfs += len(pdfs)

        # Try to extract ticker from dir name
        dir_name = company_dir.name
        # Patterns: "Apple_Inc_-", "aapl", "pltr", etc.
        ticker_guess = dir_name.split("_")[0] if "_" in dir_name else dir_name
        ticker_clean = ticker_guess.lower().strip("-").strip()
        meta = get_meta(ticker_clean)

        # Extract years from filenames
        years = set()
        for pdf in pdfs:
            m = re.search(r"(20\d{2}|19\d{2})", pdf.name)
            if m:
                years.add(m.group(1))
        year_str = ", ".join(sorted(years, reverse=True)) if years else "—"

        # Format company display name
        display_name = meta["name"] if meta["name"] != ticker_clean.upper() else dir_name.replace("_", " ").rstrip(" -")

        # Create per-company sub-page
        slug = slugify(dir_name)
        dst_company = DST_10K_DIR / slug
        ensure(dst_company)

        company_lines = [
            f"# {meta['flag']} {display_name} — 10-K",
            "",
            f"> **{t(lang, 'ticker')}:** `{ticker_clean.upper()}` &nbsp;|&nbsp; "
            f"**{t(lang, 'sector')}:** {meta['sector']} &nbsp;|&nbsp; "
            f"**{t(lang, 'total')}:** {len(pdfs)} {t(lang, 'files')}",
            "",
            f"[:material-arrow-left: {t(lang, 'back_to_index')}](../../10k.md)",
            "",
            "---",
            "",
            f"## {t(lang, 'annual_filings_for')} {display_name}",
            "",
            f"| {t(lang, 'year')} | {t(lang, 'filename')} | {t(lang, 'view')} |",
            "|------|----------|------|",
        ]

        for pdf in pdfs:
            m = re.search(r"(20\d{2}|19\d{2})", pdf.name)
            year = m.group(1) if m else "—"
            # URL-encode spaces in filename just in case
            safe_name = pdf.name.replace(" ", "%20")
            blob_url = f"{GITHUB_BLOB_BASE}/{dir_name}/{safe_name}"
            raw_url = f"{GITHUB_RAW_BASE}/{dir_name}/{safe_name}"
            company_lines.append(
                f"| {year} | `{pdf.name}` "
                f"| [:material-file-pdf-box: GitHub]({blob_url}){{target=_blank}} "
                f"&nbsp; [:material-download: Download]({raw_url}){{target=_blank}} |"
            )

        write(dst_company / "index.md", "\n".join(company_lines))

        # Row for main table — link to company sub-page
        table_rows.append(
            f"| {meta['flag']} [{display_name}](10k/{slug}/index.md) "
            f"| `{ticker_clean.upper()}` "
            f"| {meta['sector']} | {len(pdfs)} | {year_str} |"
        )

    lines = [
        f"# {t(lang, 'annual_reports')}",
        "",
        f"> {t(lang, 'sec_annual_desc')}. {t(lang, 'total')}: **{total_pdfs} PDFs** ({len(table_rows)} {t(lang, 'companies')}).",
        f"> {t(lang, 'last_indexed')}: **{TODAY}**",
        "",
        f"!!! tip \"{t(lang, 'view_filings')}\"",
        f"    {t(lang, 'file_location_desc')}: `git clone https://github.com/yennanliu/finance_data.git`  ",
        f"    Click any company below to view and download individual PDF filings directly from GitHub.",
        "",
        f"## {t(lang, 'company_index')}",
        "",
        f"| {t(lang, 'company')} | {t(lang, 'ticker')} | {t(lang, 'sector')} | # {t(lang, 'files')} | {t(lang, 'years')} |",
        "|---------|--------|--------|---------|-------|",
    ] + table_rows + [
        "",
        "---",
        "",
        f"## {t(lang, 'download_more')}",
        "",
        f"{t(lang, 'download_desc')}:",
        "",
        "```bash",
        "# Reports here are auto-refreshed monthly from SEC EDGAR via GitHub Actions.",
        "# To fetch manually — recent 10-Ks for a ticker (auto-detects 20-F for",
        "# foreign filers like TSM); existing files are skipped:",
        "python scripts/download_10k_edgar.py AAPL --years 3",
        "```",
        "",
        "See the [Scripts page](../scripts.md) for full documentation.",
    ]

    write(DST_SEC / "10k.md", "\n".join(lines))


# ── 4. 10-q / 13-f / 6-k indices ─────────────────────────────────────────────
def build_other_sec(lang: str = "en"):
    docs_root = get_docs_root(lang)
    DST_SEC = docs_root / "sec"
    ensure(DST_SEC)

    # 10-Q
    lines_10q = [
        "# 10-Q Quarterly Reports",
        "",
        f"> Quarterly SEC filings. Last indexed: **{TODAY}**",
        "",
        "!!! info",
        "    10-Q downloads are in progress. Use the download scripts to fetch filings.",
        "",
        "## Download",
        "",
        "```bash",
        "python scripts/download_10k_edgar.py AAPL --form 10-Q",
        "```",
    ]
    write(DST_SEC / "10q.md", "\n".join(lines_10q))

    # 13-F
    lines_13f = [
        "# 13-F Institutional Holdings",
        "",
        f"> 13-F filings track institutional investment managers' holdings. Last indexed: **{TODAY}**",
        "",
        "!!! info",
        "    13-F filings to be added. These reveal what major fund managers own each quarter.",
    ]
    write(DST_SEC / "13f.md", "\n".join(lines_13f))

    # 6-K (Grab)
    grab_6k = SRC_6K / "grab"
    pdfs_6k = _sample(list(grab_6k.glob("*.pdf"))) if grab_6k.exists() else []
    lines_6k = [
        "# 6-K Current Reports",
        "",
        f"> Foreign private issuer current reports. Last indexed: **{TODAY}**",
        "",
        "## Grab Holdings (GRAB)",
        "",
        f"**{len(pdfs_6k)} 6-K filings** stored in `6-k/grab/`",
        "",
        "| # | Filename |",
        "|---|----------|",
    ] + [f"| {i+1} | `{p.name}` |" for i, p in enumerate(pdfs_6k[:20])]

    if len(pdfs_6k) > 20:
        lines_6k.append(f"\n_... and {len(pdfs_6k)-20} more files_")

    write(DST_SEC / "6k.md", "\n".join(lines_6k))

    # SEC section index
    sec_index = [
        "# SEC Filings",
        "",
        "| Form | Description | Status |",
        "|------|-------------|--------|",
        "| [10-K](10k.md) | Annual report | ✅ Indexed |",
        "| [10-Q](10q.md) | Quarterly report | 🔄 In progress |",
        "| [13-F](13f.md) | Institutional holdings | 📋 Planned |",
        "| [6-K](6k.md) | Foreign current reports | ✅ Grab filings |",
    ]
    write(DST_SEC / "index.md", "\n".join(sec_index))


# ── 5. investor_day → docs/investor_day/ ──────────────────────────────────────
def build_investor_day(lang: str = "en"):
    docs_root = get_docs_root(lang)
    DST_INV_DAY = docs_root / "investor_day"
    ensure(DST_INV_DAY)

    if not SRC_INV_DAY.exists():
        write(DST_INV_DAY / "index.md", f"# {t(lang, 'investor_day')}\n\nNo materials found.\n")
        return

    rows: list[str] = []
    for company_dir in _sample_dirs(sorted([d for d in SRC_INV_DAY.iterdir() if d.is_dir()])):
        ticker = company_dir.name.lower()
        meta = get_meta(ticker)
        dst_dir = DST_INV_DAY / ticker
        ensure(dst_dir)

        pdfs = _sample(sorted(company_dir.glob("*.pdf")))
        for pdf in pdfs:
            copy_file(pdf, dst_dir / pdf.name)
            size_mb = round(pdf.stat().st_size / 1024 / 1024, 1)
            rows.append(
                f"| {meta['flag']} {meta['name']} | `{ticker.upper()}` "
                f"| [:material-file-pdf-box: {pdf.stem}]({ticker}/{pdf.name}){{target=_blank}} "
                f"| {size_mb} MB |"
            )

        if pdfs:
            inner = [
                f"# {meta['flag']} {meta['name']} — Investor Day",
                "",
                "## Presentations",
                "",
            ] + [
                f"- [:material-file-pdf-box: {pdf.stem}]({pdf.name}){{target=_blank}} ({round(pdf.stat().st_size/1024/1024,1)} MB)"
                for pdf in pdfs
            ]
            write(dst_dir / "index.md", "\n".join(inner))

    lines = [
        "# Investor Day Materials",
        "",
        f"> Company presentations from investor days and analyst events. Last updated: **{TODAY}**",
        "",
        "| Company | Ticker | Presentation | Size |",
        "|---------|--------|--------------|------|",
    ] + rows

    write(DST_INV_DAY / "index.md", "\n".join(lines))


# ── 6. scripts.md ─────────────────────────────────────────────────────────────
def build_scripts_page(lang: str = "en"):
    docs_root = get_docs_root(lang)
    scripts_page = docs_root / "scripts.md"
    script_dir = ROOT / "scripts"
    py_scripts = sorted(script_dir.glob("*.py")) if script_dir.exists() else []
    sh_scripts = sorted(script_dir.glob("*.sh")) if script_dir.exists() else []

    lines = [
        "# Download Scripts",
        "",
        f"> Python and Bash tools for batch-downloading SEC filings. Last updated: **{TODAY}**",
        "",
        "## Installation",
        "",
        "```bash",
        "git clone https://github.com/yennanliu/finance_data.git",
        "cd finance_data",
        "pip install -r requirements.txt  # or: uv sync",
        "```",
        "",
        "## Python Scripts",
        "",
    ]

    for script in py_scripts:
        lines += [
            f"### `{script.name}`",
            "",
            "```bash",
            f"python scripts/{script.name} --help",
            "```",
            "",
        ]

    if sh_scripts:
        lines += ["## Bash Scripts", ""]
        for script in sh_scripts:
            lines += [
                f"### `{script.name}`",
                "",
                "```bash",
                f"bash scripts/{script.name}",
                "```",
                "",
            ]

    lines += [
        "## SEC EDGAR API Notes",
        "",
        "- Maximum 10 requests/second (SEC rate limit)",
        "- Always include a `User-Agent` header with your contact email",
        "- Reports downloaded in PDF or HTML format",
        "",
        "```python",
        "headers = {'User-Agent': 'your.email@example.com'}",
        "```",
    ]

    write(scripts_page, "\n".join(lines))


# ── 7. .pages files for awesome-pages plugin ──────────────────────────────────
def build_nav_pages(lang: str = "en"):
    """Write .pages files so awesome-pages controls navigation order."""
    docs_root = get_docs_root(lang)
    root_pages = docs_root / ".pages"
    write(root_pages, "\n".join([
        "nav:",
        "  - index.md",
        "  - reports",
        "  - market_news",
        "  - notebooks",
        "  - sec",
        "  - investor_day",
        "  - scripts.md",
        "",
    ]))

    DST_REPORTS = docs_root / "reports"
    DST_MARKET_NEWS = docs_root / "market_news"
    DST_NOTEBOOKS = docs_root / "notebooks"
    DST_SEC = docs_root / "sec"
    DST_INV_DAY = docs_root / "investor_day"

    for subdir in [DST_SEC, DST_INV_DAY]:
        if subdir.exists():
            pages_file = subdir / ".pages"
            write(pages_file, "nav:\n  - index.md\n  - ...\n")

    # Reports section: rename the nav tab from "Reports" → "AI Gen Reports"
    if DST_REPORTS.exists():
        write(DST_REPORTS / ".pages", f"title: {t(lang, 'reports_nav_title')}\nnav:\n  - index.md\n  - ...\n")

    # Market News section: set display title in nav
    if DST_MARKET_NEWS.exists():
        market_news_title = t(lang, "market_news")
        write(DST_MARKET_NEWS / ".pages", f"title: {market_news_title}\nnav:\n  - index.md\n  - ...\n")

    # Perf fix #2b — keep individual dated reports OUT of the global nav tree.
    # Without this, awesome-pages adds every report page (~3,500) to the nav, so
    # navigation.prune can only trim collapsed branches and deep pages still
    # render thousands of nav links (~590 KB HTML each). Listing only index.md
    # per ticker keeps the sidebar to one entry per ticker; the report pages are
    # still built by MkDocs and reached via the per-ticker index tables.
    # (mkdocs.yml sets validation.nav.omitted_files: info so --strict tolerates
    # these intentionally-orphaned pages.)
    for section in [DST_REPORTS, DST_MARKET_NEWS]:
        if not section.exists():
            continue
        for ticker_dir in section.iterdir():
            if ticker_dir.is_dir():
                # Uppercase the ticker in the nav sidebar (awesome-pages would
                # otherwise title-case the folder name → "Sndk", "Tsla").
                # Quote the value: all-digit tickers (e.g. "0050") are otherwise
                # parsed as YAML ints and awesome-pages rejects a non-string title.
                write(ticker_dir / ".pages", f'title: "{ticker_dir.name.upper()}"\nnav:\n  - index.md\n')

    # Notebooks section: set display title to "NotebookLLM" in nav
    if DST_NOTEBOOKS.exists():
        write(DST_NOTEBOOKS / ".pages", "title: NotebookLLM\nnav:\n  - index.md\n  - ...\n")

    # .pages for the 10k/ sub-directory inside sec/
    DST_10K_DIR = DST_SEC / "10k"
    if DST_10K_DIR.exists():
        write(DST_10K_DIR / ".pages", "nav:\n  - ...\n")


# ── 8. includes/abbreviations.md ─────────────────────────────────────────────
def build_abbreviations(lang: str = "en"):
    docs_root = get_docs_root(lang)
    inc = docs_root / "includes"
    ensure(inc)
    abbr = inc / "abbreviations.md"
    if not abbr.exists():
        write(abbr, "\n".join([
            "*[SEC]: Securities and Exchange Commission",
            "*[EDGAR]: Electronic Data Gathering, Analysis, and Retrieval",
            "*[10-K]: Annual Report to Shareholders",
            "*[10-Q]: Quarterly Report",
            "*[13-F]: Institutional Investment Manager Holdings Report",
            "*[BVLOS]: Beyond Visual Line of Sight",
            "*[C-UAS]: Counter-Unmanned Aircraft System",
            "*[FAA]: Federal Aviation Administration",
            "*[P/S]: Price-to-Sales Ratio",
            "*[P/E]: Price-to-Earnings Ratio",
            "*[EBITDA]: Earnings Before Interest, Taxes, Depreciation, and Amortisation",
            "*[DCF]: Discounted Cash Flow",
            "*[TAM]: Total Addressable Market",
            "*[IoT]: Internet of Things",
            "",
        ]))


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*70}")
    print(" Finance Hub — building docs/ (EN + ZH)")
    print(f"{'='*70}\n")

    if _INCREMENTAL:
        print("  ⚡ Incremental mode — only changed files will be written (pass --clean to force full rebuild)")
    else:
        print("  🧹 Full rebuild mode — cleaning previously generated directories")

    if SAMPLE_BUILD:
        print(f"  🧪 SAMPLE build — capped to {SAMPLE_LIMIT} tickers/companies and "
              f"{SAMPLE_LIMIT} files per category (smoke test; not for production)")

    if _MMDC:
        print(f"  ⚡ mmdc found at {_MMDC} — Mermaid blocks will be pre-rendered to SVG")
        _load_mermaid_cache()
    else:
        print("  ℹ️  mmdc not found — Mermaid blocks will be rendered client-side")
        print("     Install with: npm install -g @mermaid-js/mermaid-cli")

    # Clean previously generated dirs (full rebuild only)
    if not _INCREMENTAL:
        for lang_dir in [DOCS, DOCS_ZH]:
            for subdir in ["reports", "market_news", "notebooks", "sec", "investor_day"]:
                path = lang_dir / subdir
                if path.exists():
                    shutil.rmtree(path)
                    print(f"  clean {path.relative_to(ROOT)}/")

    # Build English version
    print(f"\n{'─'*70}")
    print(" Building English version (docs/)")
    print(f"{'─'*70}")

    print("\n[EN 1/8] Building ai_gen_report/stock reports...")
    build_reports(lang="en")

    print("\n[EN 2/8] Building ai_gen_report/market_news...")
    build_market_news(lang="en")

    print("\n[EN 3/8] Building notebook_llm pages...")
    build_notebooks(lang="en")

    print("\n[EN 4/8] Building 10-K index...")
    build_10k_index(lang="en")

    print("\n[EN 5/8] Building other SEC indices (10-Q, 13-F, 6-K)...")
    build_other_sec(lang="en")

    print("\n[EN 6/8] Building investor_day pages...")
    build_investor_day(lang="en")

    print("\n[EN 7/8] Building scripts page...")
    build_scripts_page(lang="en")

    print("\n[EN 8/8] Writing .pages nav files & abbreviations...")
    build_nav_pages(lang="en")
    build_abbreviations(lang="en")

    # Build Traditional Chinese version
    print(f"\n{'─'*70}")
    print(" Building Traditional Chinese version (docs/zh/)")
    print(f"{'─'*70}")

    print("\n[ZH 1/8] Building ai_gen_report/stock reports...")
    build_reports(lang="zh")

    print("\n[ZH 2/8] Building ai_gen_report/market_news...")
    build_market_news(lang="zh")

    print("\n[ZH 3/8] Building notebook_llm pages...")
    build_notebooks(lang="zh")

    print("\n[ZH 4/8] Building 10-K index...")
    build_10k_index(lang="zh")

    print("\n[ZH 5/8] Building other SEC indices (10-Q, 13-F, 6-K)...")
    build_other_sec(lang="zh")

    print("\n[ZH 6/8] Building investor_day pages...")
    build_investor_day(lang="zh")

    print("\n[ZH 7/8] Building scripts page...")
    build_scripts_page(lang="zh")

    print("\n[ZH 8/8] Writing .pages nav files & abbreviations...")
    build_nav_pages(lang="zh")
    build_abbreviations(lang="zh")

    if _MMDC:
        _save_mermaid_cache()
        print(f"  Mermaid cache saved → {_MERMAID_CACHE_FILE.relative_to(ROOT)}")

    print(f"\n{'='*70}")
    print(" ✅  docs/ generated successfully (EN + ZH)")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
