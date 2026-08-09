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
  • 10-q/                      → docs/sec/10q.md   (index only, PDFs not copied)
  • 13-f/                      → docs/sec/13f.md
  • investor_day/              → docs/investor_day/
  • data/prices/               → docs/prices/<ticker>/  (charts + CSV download)
  • README.md                  → enriches docs/index.md

Run locally:   python scripts/build_docs.py
Run in CI:     automatically called before `mkdocs build`
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import date
from pathlib import Path

# The price store and the statistics derived from it. Safe to import at module
# scope: the analysis package defers every heavy dependency (pandas, yfinance,
# plotly) to inside its functions, and both of these modules are pure standard
# library — so the docs build stays dependency-light and offline.
from analysis.data import price_analytics, prices

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
        "quarterly_filings_for": "Quarterly Filings for",
        "year": "Year",
        "period": "Period",
        "filename": "Filename",
        "view": "View",
        "back_to_index": "Back to 10-K Index",
        "back_to_10q_index": "Back to 10-Q Index",
        "download_more": "Download More Filings",
        "download_desc": "Use the included Python scripts to download additional 10-K filings",
        "download_desc_10q": "Use the included Python scripts to download additional 10-Q filings",
        "quarterly_reports": "10-Q Quarterly Reports",
        "sec_quarterly_desc": "SEC quarterly filings (Form 10-Q) stored locally",
        "file_location_desc_10q": "10-Q PDFs are stored in the `10-q/` directory of the repository. Clone the repo to access them locally",
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
        # ── Price Data section ──
        "prices": "Price Data",
        "prices_desc": "{n} tickers · up to {years} years of daily OHLCV",
        "prices_intro": (
            "Every chart on this site is drawn from one committed dataset: a CSV per ticker "
            "under `data/prices/`, refreshed nightly from Yahoo Finance and capped at "
            "ten years of daily bars. This page publishes that dataset — browse the derived "
            "charts per ticker, or download the raw files and run your own analysis."
        ),
        "p_no_data": "No price data found.",
        "p_download": "📥 Download",
        "p_zip": "all_prices.zip",
        "p_zip_desc": "every ticker's CSV in one archive ({n} files)",
        "p_manifest_desc": "machine-readable summary of every ticker (last close, returns, volatility, file URLs)",
        "p_per_ticker_desc": "Per-ticker CSV links are in the table below, and on each ticker's page.",
        "p_columns": "CSV columns",
        "p_columns_desc": (
            "One row per trading session, oldest first. Prices are split- and "
            "dividend-adjusted, so a return computed from `close` is a total return. "
            "`div` and `split` carry the event on the day it happened and are empty otherwise."
        ),
        "p_coverage": "Coverage",
        "p_last": "Last",
        "p_52w_range": "52W Range",
        "p_avg_vol": "Avg Vol (30D)",
        "p_history": "History",
        "p_price_history": "Price History",
        "p_bars": "Bars",
        "p_returns": "📈 Returns",
        "p_key_stats": "📊 Key Statistics",
        "p_metric": "Metric",
        "p_value": "Value",
        "p_last_close": "Last close",
        "p_52w_high": "52-week high",
        "p_52w_low": "52-week low",
        "p_from_high": "From 52-week high",
        "p_range_pos": "Position in 52-week range",
        "p_ath": "Highest price on record",
        "p_max_dd": "Max drawdown (stored history)",
        "p_vol_1y": "Annualised volatility (1Y)",
        "p_cagr": "CAGR (stored history)",
        "p_drawdown": "📉 Drawdown from Peak",
        "p_drawdown_desc": (
            "How far the close sits below its running all-time high. The depth and the "
            "width of each trough say more about holding this name than any single return figure."
        ),
        "p_volatility": "🌡️ Rolling Volatility",
        "p_volatility_desc": (
            "Annualised standard deviation of daily returns over a rolling {window}-session window."
        ),
        "p_distribution": "🎲 Daily Return Distribution",
        "p_distribution_desc": (
            "How the daily moves are spread. Fat tails on either side mean the average "
            "return is a poor description of a typical day."
        ),
        "p_monthly": "🗓️ Monthly Returns",
        "p_monthly_desc": (
            "Calendar-month returns; the year column chains its months, so it only "
            "appears for years covered from January onward."
        ),
        "p_year": "Year",
        "p_year_total": "Total",
        "p_csv_desc": "raw daily OHLCV, {n:,} rows",
        "p_prices_json_desc": "the full history in the JSON shape the candlestick chart consumes",
        "p_analytics_json_desc": "pre-computed drawdown, rolling volatility and return histogram",
        "p_back_to_index": "← Back to Price Data",
        "p_more_charts": "Full price history, drawdown & CSV download",
        "p_disclaimer": (
            "Price data is sourced from Yahoo Finance and provided as-is for research and "
            "educational use. It is not verified against an official exchange feed and must "
            "not be relied on for trading decisions."
        ),
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
        "quarterly_filings_for": "季度文件 —",
        "year": "年份",
        "period": "期間",
        "filename": "檔案名稱",
        "view": "查看",
        "back_to_index": "返回 10-K 索引",
        "back_to_10q_index": "返回 10-Q 索引",
        "download_more": "下載更多文件",
        "download_desc": "使用包含的 Python 腳本下載額外的 10-K 文件",
        "download_desc_10q": "使用包含的 Python 腳本下載額外的 10-Q 文件",
        "quarterly_reports": "10-Q 季度報告",
        "sec_quarterly_desc": "本地儲存的 SEC 季度文件（Form 10-Q）",
        "file_location_desc_10q": "10-Q PDF 檔案儲存在存儲庫的 `10-q/` 目錄中。複製存儲庫以在本地訪問它們",
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
        # ── Price Data section ──
        "prices": "股價資料",
        "prices_desc": "{n} 檔標的 · 最多 {years} 年的每日 OHLCV",
        "prices_intro": (
            "本站所有圖表都來自同一份資料集：`data/prices/` 下每檔標的一個 CSV，"
            "每晚自 Yahoo Finance 更新，保留最多十年的日線資料。"
            "本頁將這份資料集公開 — 可瀏覽每檔標的的衍生圖表，也可直接下載原始檔案自行分析。"
        ),
        "p_no_data": "查無股價資料。",
        "p_download": "📥 下載",
        "p_zip": "all_prices.zip",
        "p_zip_desc": "所有標的的 CSV 打包下載（共 {n} 個檔案）",
        "p_manifest_desc": "機器可讀的彙總資料（最新收盤、報酬率、波動率、檔案網址）",
        "p_per_ticker_desc": "個別標的的 CSV 連結請見下方表格，或各標的頁面。",
        "p_columns": "CSV 欄位",
        "p_columns_desc": (
            "每個交易日一列，由舊到新。價格已還原股票分割與股利，"
            "因此以 `close` 計算的報酬率即為總報酬。"
            "`div` 與 `split` 僅在事件發生當日有值，其餘為空。"
        ),
        "p_coverage": "涵蓋標的",
        "p_last": "最新價",
        "p_52w_range": "52 週區間",
        "p_avg_vol": "30 日均量",
        "p_history": "資料期間",
        "p_price_history": "股價歷史",
        "p_bars": "資料筆數",
        "p_returns": "📈 報酬率",
        "p_key_stats": "📊 關鍵統計",
        "p_metric": "指標",
        "p_value": "數值",
        "p_last_close": "最新收盤",
        "p_52w_high": "52 週高點",
        "p_52w_low": "52 週低點",
        "p_from_high": "距 52 週高點",
        "p_range_pos": "於 52 週區間位置",
        "p_ath": "歷史最高價",
        "p_max_dd": "最大回撤（資料期間）",
        "p_vol_1y": "年化波動率（1 年）",
        "p_cagr": "年化報酬率 CAGR（資料期間）",
        "p_drawdown": "📉 距高點回撤",
        "p_drawdown_desc": (
            "收盤價低於歷史高點的幅度。回撤的深度與持續時間，"
            "比單一報酬率數字更能說明持有這檔標的的實際體感。"
        ),
        "p_volatility": "🌡️ 滾動波動率",
        "p_volatility_desc": "以滾動 {window} 個交易日計算的日報酬標準差（年化）。",
        "p_distribution": "🎲 日報酬分布",
        "p_distribution_desc": (
            "日漲跌幅的分布狀況。兩側若出現厚尾，代表平均報酬並不足以描述「一般的一天」。"
        ),
        "p_monthly": "🗓️ 月報酬",
        "p_monthly_desc": (
            "各日曆月份的報酬率；年度欄位由各月份連乘而得，"
            "因此僅在資料自 1 月起完整涵蓋的年度才會顯示。"
        ),
        "p_year": "年度",
        "p_year_total": "全年",
        "p_csv_desc": "原始每日 OHLCV，共 {n:,} 列",
        "p_prices_json_desc": "K線圖使用的完整歷史 JSON",
        "p_analytics_json_desc": "預先計算的回撤、滾動波動率與報酬分布",
        "p_back_to_index": "← 返回股價資料",
        "p_more_charts": "完整股價歷史、回撤圖與 CSV 下載",
        "p_disclaimer": (
            "股價資料來自 Yahoo Finance，僅供研究與教育用途，未與官方交易所行情核對，"
            "不得作為交易決策依據。"
        ),
    }
}

# ── Company metadata ──────────────────────────────────────────────────────────
COMPANY_META: dict[str, dict] = {
    "onds":     {"name": "Ondas Inc.",                "flag": "🚁", "sector": "Defense / Drone"},
    "ondas":    {"name": "Ondas Inc.",                "flag": "🚁", "sector": "Defense / Drone"},
    "msft":     {"name": "Microsoft Corp.",           "flag": "💻", "sector": "Technology"},
    "pltr":     {"name": "Palantir Technologies",     "flag": "🔮", "sector": "Data / AI"},
    "pl":       {"name": "Planet Labs PBC",           "flag": "🛰️",  "sector": "Space / Earth Imaging"},
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
    # Names carried by the price store but with no report directory of their own
    # — the Price Data section covers every CSV, so these keep it from falling
    # back to a bare ticker + "Equity" for a third of the table.
    "intc":     {"name": "Intel Corp.",               "flag": "🔷", "sector": "Semiconductors"},
    "mrvl":     {"name": "Marvell Technology",        "flag": "🌊", "sector": "Semiconductors"},
    "mu":       {"name": "Micron Technology",         "flag": "🧠", "sector": "Memory / Storage"},
    "nbis":     {"name": "Nebius Group",              "flag": "☁️",  "sector": "AI Cloud"},
    "nu":       {"name": "Nu Holdings",               "flag": "💜", "sector": "LatAm Fintech"},
    "sndk":     {"name": "SanDisk Corp.",             "flag": "💾", "sector": "Memory / Storage"},
    "uber":     {"name": "Uber Technologies",         "flag": "🚕", "sector": "Mobility / Delivery"},
    "wdc":      {"name": "Western Digital",           "flag": "💽", "sector": "Storage"},
    "qqq":      {"name": "Invesco QQQ Trust",         "flag": "📈", "sector": "ETF · Nasdaq-100"},
    "vti":      {"name": "Vanguard Total Stock Mkt",  "flag": "📈", "sector": "ETF · US Total Market"},
    "soxx":     {"name": "iShares Semiconductor ETF", "flag": "🔌", "sector": "ETF · Semiconductors"},
    "soxq":     {"name": "Invesco PHLX Semi ETF",     "flag": "🔌", "sector": "ETF · Semiconductors"},
    "robo":     {"name": "ROBO Global Robotics ETF",  "flag": "🤖", "sector": "ETF · Robotics / AI"},
    # skhy / spcx / wqtm are deliberately absent: get_meta falls back to the bare
    # ticker, which is honest, and a guessed company name on a data page is worse
    # than none. Add them when the real issuer name is confirmed.
    "0050":     {"name": "Yuanta Taiwan Top 50 ETF",  "flag": "🇹🇼", "sector": "ETF · Taiwan"},
    "2330.tw":  {"name": "TSMC (Taiwan listing)",     "flag": "🇹🇼", "sector": "Semiconductors / Foundry"},
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

# Bars per payload. 360 trading days of visible range (the widest range button)
# plus 200 bars of lookback so a client-side MA200 is fully defined at the left
# edge instead of starting 200 bars in.
KLINE_VISIBLE_BARS = 360
KLINE_LOOKBACK_BARS = 200

# …plus an allowance for as-of truncation. A dated report page clips the payload
# to its own date, so a report at the far end of the retention window would
# otherwise lose MA200 over the oldest part of its 360-bar view: measured against
# the real store, a 120-day-old report had MA200 defined for only 279 of 360
# visible bars. The allowance restores the full overlay for every *published*
# report at a cost of ~7 KB per (uncommitted) payload.
# Weekdays per calendar day. An *upper* bound on trading days, since holidays
# only ever remove sessions — deliberately not 252/365, which is the average and
# so runs short on a low-holiday window.
_TRADING_DAYS_PER_CALENDAR_DAY = 5 / 7
# A few bars of slack for calendar edges (a window can start and end mid-week).
KLINE_AS_OF_SLACK_BARS = 5
# Ceiling on that allowance, which also bounds the payload when retention is
# disabled (REPORT_RETENTION_DAYS=0 publishes arbitrarily old reports). Reports
# older than this still render; only MA200's left edge thins out.
KLINE_MAX_AS_OF_BARS = 504  # ≈ 2 years of trading days


def kline_as_of_allowance() -> int:
    """Extra bars carried so as-of truncation can't eat into the MA lookback."""
    if RETENTION_DAYS <= 0:
        return KLINE_MAX_AS_OF_BARS
    return min(KLINE_MAX_AS_OF_BARS,
               math.ceil(RETENTION_DAYS * _TRADING_DAYS_PER_CALENDAR_DAY)
               + KLINE_AS_OF_SLACK_BARS)


def kline_payload_bars() -> int:
    """Total bars to derive per ticker."""
    return KLINE_VISIBLE_BARS + kline_as_of_allowance() + KLINE_LOOKBACK_BARS


def kline_bars(ticker: str) -> "list[dict]":
    """Bars for a ticker's chart payload, oldest→newest ([] when unavailable).

    Reads the store live off the module global so tests can monkeypatch it.
    """
    bars = prices.load_store(ticker, PRICES_DIR)
    if not bars:
        return []
    return prices.window(bars, days=KLINE_VISIBLE_BARS + kline_as_of_allowance(),
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
                as_of: str = "", ma: str = "", ranges: str = "") -> str:
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
    ranges — range buttons to offer in trading days, e.g. "30,180,360". The
             Price Data pages carry the whole store, so they offer far longer
             windows than a report's 30/180/360.
    """
    if not kline_bars(ticker):
        return ""
    attrs = ['class="kline-widget"', f'data-ticker="{ticker.upper()}"',
             f'data-src="{src}"']
    if as_of:
        attrs.append(f'data-as-of="{as_of}"')
    if ma:
        attrs.append(f'data-ma="{ma}"')
    if ranges:
        attrs.append(f'data-ranges="{ranges}"')
    return f'<div {" ".join(attrs)}></div>'


# Overlays for technical reports: MA30/60 on, MA200 available but off by default,
# matching the moving averages the retired Plotly chart drew.
REPORT_MA = "30+,60+,200"


def report_chart_block(ticker: str, report: Path) -> str:
    """Chart markup for a dated technical report page ('' for anything else).

    Only technical reports get one — they are the pages that used to carry their
    own baked-in chart, and the analysis text discusses it directly. The chart is
    pinned to the report's date so it shows the prices the text was written
    about; `../kline.json` because report bodies are served one directory below
    the ticker index that hosts the payload.
    """
    if not report.name.startswith("technical_"):
        return ""
    d = _file_date(report)
    return kline_block(ticker, src="../kline.json",
                       as_of=d.isoformat() if d else "", ma=REPORT_MA)


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
    for sub in ["reports", "prices", "market_news", "notebooks", "sec", "investor_day"]:
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


# ── Legacy chart embeds ──────────────────────────────────────────────────────
# Until 2026-08 every technical report baked its own chart into the committed
# markdown: a collapsible static PNG plus a full Plotly HTML document (~46 KB of
# inline JSON each, 61.7 MB across 1,313 reports, and a ~3 MB plotly.js fetch per
# page view). Both are replaced by the shared widget, which reads the price store.
#
# Stripping at copy time rather than rewriting the sources means every existing
# report gets the new chart immediately and the change is reversible by reverting
# one function — the one-off source cleanup is then only about disk space.
_LEGACY_PNG_DETAILS_RE = re.compile(
    r"<details[^>]*>\s*<summary>.*?</summary>.*?technical_chart_.*?</details>\s*",
    re.S,
)
# plotly's to_html() emits a whole document, so the embed is exactly one
# <html>…</html> block.
_LEGACY_PLOTLY_RE = re.compile(r"<html>\s*<head>.*?</html>\s*", re.S)


def strip_legacy_chart_embed(content: str) -> str:
    """Remove a baked-in static-PNG block and/or inline Plotly document."""
    if "technical_chart_" in content:
        content = _LEGACY_PNG_DETAILS_RE.sub("", content)
    if "candlestick-chart" in content or "plot.ly" in content:
        content = _LEGACY_PLOTLY_RE.sub("", content)
    return content


def copy_file(src: Path, dst: Path, extra_meta: str = "", chart_block: str = ""):
    """Copy src → dst. For Markdown, merge `extra_meta` into the file's own
    front matter (re-emitted as a header table), strip legacy baked-in charts,
    optionally inject `chart_block` above the report body, repair chart embeds
    and pre-render Mermaid; uses a content-equality incremental check so changed
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
        content = strip_legacy_chart_embed(content)
        content = fix_static_chart_embed(content)
        if extra_meta:
            yaml_body, body = split_frontmatter(content)
            merged = f"{extra_meta}\n{yaml_body}" if yaml_body else extra_meta
            content = (
                f"---\n{merged}\n---\n\n"
                + frontmatter_table(yaml_body)
                + (f"{chart_block}\n\n" if chart_block else "")
                + body.lstrip("\n")
            )
        elif chart_block:
            yaml_body, body = split_frontmatter(content)
            head = f"---\n{yaml_body}\n---\n\n" if yaml_body else ""
            content = f"{head}{chart_block}\n\n{body.lstrip(chr(10))}"
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


def write_bytes(path: Path, data: bytes):
    """The same, for binary content: skip the write when the bytes are unchanged."""
    ensure(path.parent)
    if _INCREMENTAL and path.exists() and path.read_bytes() == data:
        return
    path.write_bytes(data)
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
    # Computed once: build_prices() publishes exactly these, and each ticker page
    # links across to its own only if it is among them.
    priced_keys = set(published_price_keys())

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
                copy_file(f, dst_dir / f.name, extra_meta=SEARCH_EXCLUDE_META,
                          chart_block=report_chart_block(ticker, f))
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
                lines.append(f"- [{report_label(f)}]({link_fn(f)}){{.report-link}}")
            lines.append("")
            older = ordered[RECENT_COUNT:]
            if older:
                lines.append(f'??? note "{t(lang, "show_older").format(n=len(older))}"')
                lines.append("")
                for f in older:
                    lines.append(f"    - [{report_label(f)}]({link_fn(f)}){{.report-link}}")
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
            # The hero chart only shows the last ~18 months; point readers at the
            # Price Data page for the full store, the derived charts and the CSV.
            # Guarded on the page actually existing — a sample build publishes
            # only a few tickers and --strict would reject a dangling link.
            if ticker in priced_keys:
                lines += [f"[:material-chart-line: {t(lang, 'p_more_charts')}]"
                          f"(../../prices/{ticker}/index.md){{.report-link}}", ""]
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
                # `.card-cta` renders the link as a filled button (extra.css) so
                # the primary action on each card reads as clickable at a glance.
                attrs = "{.card-cta target=_blank}" if is_html else "{.card-cta}"
                lines.append(f"-   __{title}__")
                lines.append("")
                lines.append(f"    ---")
                lines.append("")
                lines.append(f"    **{t(lang, 'latest')}:** {report_label(f)}")
                lines.append("")
                lines.append(
                    f"    [:octicons-arrow-right-24: {t(lang, 'open_latest')}]"
                    f"({link_fn(f)}){attrs}"
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
                lines.append(
                    f"- [{report_label(f)}]({html_link(f)}){{.report-link target=_blank}}"
                )
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
                top_lines.append(f"- [{report_label(f)}]({top_link(f)}){{.report-link}}")
            top_lines.append("")
            older = ordered[RECENT_COUNT:]
            if older:
                top_lines.append(f'??? note "{t(lang, "show_older").format(n=len(older))}"')
                top_lines.append("")
                for f in older:
                    top_lines.append(f"    - [{report_label(f)}]({top_link(f)}){{.report-link}}")
                top_lines.append("")

        emit_top_section("fundamental_analysis", fundamental_md)
        emit_top_section("technical_analysis", technical_md)
        emit_top_section("other_reports", other_md)
        if html_files:
            top_lines.append(f"**{t(lang, 'html_reports')}:**")
            top_lines.append("")
            for f in html_files:
                # Same full-width row treatment as the md reports above. The
                # `↗` marker that .report-link[target=_blank] adds replaces the
                # inline open-in-new icon these rows used to carry.
                label = report_label(f)
                if lang == "zh":
                    top_lines.append(f"- [{label}]({SITE_BASE}/reports/{ticker}/{f.name}){{.report-link target=_blank}}")
                else:
                    top_lines.append(f"- [{label}]({ticker}/{f.name}){{.report-link target=_blank}}")
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


# ── 3. 10-k / 10-q → docs/sec/{10k,10q}/ (per-company pages, GitHub PDF links) ─
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/yennanliu/finance_data/main"
GITHUB_BLOB_BASE = "https://github.com/yennanliu/finance_data/blob/main"

# Per-form knobs for build_filing_index(). 10-K filings are keyed by year
# (AAPL_2025_10-K.pdf); 10-Q filings by period-end date (AAPL_2025-06-28_10-Q.pdf),
# because three quarterlies share a year and would otherwise collapse onto one row.
FILING_SPECS = {
    "10k": {
        "src": SRC_10K,
        "repo_dir": "10-k",
        "label": "10-K",
        "title_key": "annual_reports",
        "desc_key": "sec_annual_desc",
        "location_key": "file_location_desc",
        "section_key": "annual_filings_for",
        "back_key": "back_to_index",
        "download_key": "download_desc",
        "period_key": "year",
        "download_cmd": [
            "# Reports here are auto-refreshed monthly from SEC EDGAR via GitHub Actions.",
            "# To fetch manually — recent 10-Ks for a ticker (auto-detects 20-F for",
            "# foreign filers like TSM); existing files are skipped:",
            "python scripts/download_10k_edgar.py AAPL --years 3",
        ],
    },
    "10q": {
        "src": SRC_10Q,
        "repo_dir": "10-q",
        "label": "10-Q",
        "title_key": "quarterly_reports",
        "desc_key": "sec_quarterly_desc",
        "location_key": "file_location_desc_10q",
        "section_key": "quarterly_filings_for",
        "back_key": "back_to_10q_index",
        "download_key": "download_desc_10q",
        "period_key": "period",
        "download_cmd": [
            "# Latest quarterly for a ticker; existing files are skipped.",
            "python scripts/download_10q_edgar.py AAPL --limit 1",
            "",
            "# Foreign private issuers (e.g. TSM) file 6-K rather than 10-Q.",
            "python scripts/download_10q_edgar.py TSM --form 6-K",
        ],
    },
}

# Full period-end date (10-Q) if present, else a bare year (10-K).
_PERIOD_RE = re.compile(r"((?:20|19)\d{2})(-\d{2}-\d{2})?")


def _filing_period(filename: str) -> "tuple[str, str]":
    """→ (display period, year) parsed off a filing filename; ('—', '') if absent."""
    m = _PERIOD_RE.search(filename)
    if not m:
        return "—", ""
    return m.group(0), m.group(1)


def build_filing_index(lang: str = "en", form: str = "10k"):
    spec = FILING_SPECS[form]
    src = spec["src"]
    docs_root = get_docs_root(lang)
    DST_SEC = docs_root / "sec"
    DST_FORM_DIR = DST_SEC / form
    ensure(DST_FORM_DIR)

    if not src.exists():
        write(DST_SEC / f"{form}.md", f"# {t(lang, spec['title_key'])}\n\nNo filings found.\n")
        return

    company_dirs = _sample_dirs(sorted([d for d in src.iterdir() if d.is_dir()]))
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
        years = {year for _, year in map(_filing_period, (p.name for p in pdfs)) if year}
        year_str = ", ".join(sorted(years, reverse=True)) if years else "—"

        # Format company display name
        display_name = meta["name"] if meta["name"] != ticker_clean.upper() else dir_name.replace("_", " ").rstrip(" -")

        # Create per-company sub-page
        slug = slugify(dir_name)
        dst_company = DST_FORM_DIR / slug
        ensure(dst_company)

        company_lines = [
            f"# {meta['flag']} {display_name} — {spec['label']}",
            "",
            f"> **{t(lang, 'ticker')}:** `{ticker_clean.upper()}` &nbsp;|&nbsp; "
            f"**{t(lang, 'sector')}:** {meta['sector']} &nbsp;|&nbsp; "
            f"**{t(lang, 'total')}:** {len(pdfs)} {t(lang, 'files')}",
            "",
            f"[:material-arrow-left: {t(lang, spec['back_key'])}](../../{form}.md)",
            "",
            "---",
            "",
            f"## {t(lang, spec['section_key'])} {display_name}",
            "",
            f"| {t(lang, spec['period_key'])} | {t(lang, 'filename')} | {t(lang, 'view')} |",
            "|------|----------|------|",
        ]

        for pdf in pdfs:
            period, _ = _filing_period(pdf.name)
            # URL-encode spaces in filename just in case
            safe_name = pdf.name.replace(" ", "%20")
            blob_url = f"{GITHUB_BLOB_BASE}/{spec['repo_dir']}/{dir_name}/{safe_name}"
            raw_url = f"{GITHUB_RAW_BASE}/{spec['repo_dir']}/{dir_name}/{safe_name}"
            company_lines.append(
                f"| {period} | `{pdf.name}` "
                f"| [:material-file-pdf-box: GitHub]({blob_url}){{target=_blank}} "
                f"&nbsp; [:material-download: Download]({raw_url}){{target=_blank}} |"
            )

        write(dst_company / "index.md", "\n".join(company_lines))

        # Row for main table — link to company sub-page
        table_rows.append(
            f"| {meta['flag']} [{display_name}]({form}/{slug}/index.md) "
            f"| `{ticker_clean.upper()}` "
            f"| {meta['sector']} | {len(pdfs)} | {year_str} |"
        )

    lines = [
        f"# {t(lang, spec['title_key'])}",
        "",
        f"> {t(lang, spec['desc_key'])}. {t(lang, 'total')}: **{total_pdfs} PDFs** ({len(table_rows)} {t(lang, 'companies')}).",
        f"> {t(lang, 'last_indexed')}: **{TODAY}**",
        "",
        f"!!! tip \"{t(lang, 'view_filings')}\"",
        f"    {t(lang, spec['location_key'])}: `git clone https://github.com/yennanliu/finance_data.git`  ",
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
        f"{t(lang, spec['download_key'])}:",
        "",
        "```bash",
    ] + spec["download_cmd"] + [
        "```",
        "",
        "See the [Scripts page](../scripts.md) for full documentation.",
    ]

    write(DST_SEC / f"{form}.md", "\n".join(lines))


# ── 4. 13-f / 6-k indices ────────────────────────────────────────────────────
# (10-Q is indexed by build_filing_index above, alongside 10-K.)
def build_other_sec(lang: str = "en"):
    docs_root = get_docs_root(lang)
    DST_SEC = docs_root / "sec"
    ensure(DST_SEC)

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
        "| [10-Q](10q.md) | Quarterly report | ✅ Indexed |",
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


# ── 6. data/prices → docs/prices/ ─────────────────────────────────────────────
# The committed price store already powers every chart on the site, but only as
# an implementation detail — nothing exposed the data itself. This section
# publishes it as a first-class dataset: a browsable page per ticker with the
# charts you cannot draw from candles alone (drawdown, rolling volatility,
# return distribution, monthly seasonality), plus the raw CSV to download.
#
# Every number shown here is derived at build time by
# scripts/analysis/data/price_analytics.py, so the page and the download can
# never disagree, and the arithmetic is covered by tests/test_price_analytics.py.

# The Price Data candlestick carries the *whole* store, so it offers ranges the
# report charts cannot: one month through ten years.
PRICE_PAGE_RANGES = "30,180,360,756,2520"
PRICE_PAGE_MA = "20+,60+,200"

# Heatmap shading thresholds (absolute monthly return, %) → CSS class suffix 1-4.
_HEAT_STEPS = (2.0, 5.0, 10.0)

_MONTH_ABBR = {
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
    "zh": tuple(f"{m}月" for m in range(1, 13)),
}


def price_keys() -> "list[str]":
    """Every ticker key in the committed store, sorted. Read live off the module
    global so tests can point PRICES_DIR at a fixture directory."""
    if not PRICES_DIR.exists():
        return []
    return sorted(p.name[:-4] for p in PRICES_DIR.glob("*.csv"))


def published_price_keys() -> "list[str]":
    """The keys build_prices() actually publishes (sample-capped).

    Report pages consult this before linking across, so the two sections can
    never disagree about which tickers have a Price Data page. Selection goes
    through _sample_dirs (via the same virtual-Path trick merged_ticker_dirs
    uses) so a sample build honours SAMPLE_TICKERS and covers the *same* names
    the report pages do, instead of the first three alphabetically.
    """
    return [p.name for p in _sample_dirs([Path(k) for k in price_keys()])]


def full_price_payload(key: str, bars: "list[dict]") -> str:
    """The whole stored history in the shape kline-chart.js consumes.

    Same schema as kline.json — the report pages just get a windowed slice of it
    — so one widget serves both without knowing which page it is on.
    """
    symbol = prices.to_yf_symbol(key)
    return json.dumps({
        "ticker": key.upper(),
        "symbol": symbol,
        "currency": prices.currency_for(symbol),
        "updated": bars[-1]["date"],
        "bars": [{"t": b["date"],
                  "o": float(prices.fmt_price(b["open"])),
                  "h": float(prices.fmt_price(b["high"])),
                  "l": float(prices.fmt_price(b["low"])),
                  "c": float(prices.fmt_price(b["close"])),
                  "v": b["volume"]} for b in bars],
    }, separators=(",", ":"))


def analytics_payload(key: str, bars: "list[dict]") -> str:
    """Pre-computed series for price-charts.js, plus the summary as metadata.

    The browser does no maths: it fetches this and draws. Keeping the
    computation in Python is what lets pytest assert on the numbers the site
    actually shows.
    """
    return json.dumps({
        "ticker": key.upper(),
        "updated": bars[-1]["date"],
        "summary": price_analytics.summary(bars),
        "drawdown": price_analytics.drawdown_series(bars),
        "volatility": price_analytics.volatility_series(bars),
        "histogram": price_analytics.return_histogram(bars),
    }, separators=(",", ":"))


def _pct_cell(v: "float | None", digits: int = 2) -> str:
    """A signed percentage as a coloured span ('—' when undefined).

    Raw HTML rather than attr_list: this lands inside a Markdown table cell,
    where `{.pos}` would be rendered literally.
    """
    if v is None:
        return "—"
    cls = "pos" if v >= 0 else "neg"
    return f'<span class="{cls}">{v:+.{digits}f}%</span>'


def _num(v: "float | None", digits: int = 2) -> str:
    return "—" if v is None else f"{v:,.{digits}f}"


def _compact_volume(v: "int | None") -> str:
    """Volume as 1.23B / 45.6M / 789K."""
    if not v:
        return "—"
    for unit, size in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(v) >= size:
            return f"{v / size:.2f}{unit}"
    return str(v)


def _heat_class(v: "float | None") -> str:
    """CSS class for a monthly-return heatmap cell."""
    if v is None:
        return ""
    prefix = "g" if v >= 0 else "r"
    level = 1 + sum(1 for step in _HEAT_STEPS if abs(v) >= step)
    return f"{prefix}{level}"


def monthly_heatmap(bars: "list[dict]", lang: str) -> "list[str]":
    """Monthly-return grid as a Markdown table wrapped in a `.pheat` div.

    Newest year on top, matching the newest-first ordering used everywhere else
    on the site. Cells carry both a colour and the number — the colour is an
    accent, never the only channel.
    """
    rows = price_analytics.monthly_returns(bars)
    if not rows:
        return []
    out = ['<div class="pheat" markdown="1">', "",
           "| " + t(lang, "p_year") + " | "
           + " | ".join(_MONTH_ABBR.get(lang, _MONTH_ABBR["en"])) + " | "
           + t(lang, "p_year_total") + " |",
           "|" + "---|" * 14]
    for row in reversed(rows):
        cells = []
        for m in range(1, 13):
            v = row["months"].get(m)
            if v is None:
                cells.append("")
                continue
            cls = _heat_class(v)
            cells.append(f'<span class="{cls}">{v:+.1f}</span>')
        total = row["year_pct"]
        cells.append(f"**{total:+.1f}**" if total is not None else "")
        out.append(f"| **{row['year']}** | " + " | ".join(cells) + " |")
    out += ["", "</div>", ""]
    return out


def pchart_block(*, src: str, series: str, kind: str, title: str,
                 color: str = "blue", unit: str = "%") -> str:
    """Raw-HTML div for one derived-analytics chart (see price-charts.js)."""
    return (f'<div class="pchart" data-src="{src}" data-series="{series}" '
            f'data-kind="{kind}" data-title="{title}" data-color="{color}" '
            f'data-unit="{unit}"></div>')


def _price_zip_bytes(keys: "list[str]") -> bytes:
    """Every published CSV in one deterministic archive.

    Fixed timestamps (and sorted members) so re-running the build produces
    byte-identical output — otherwise the incremental check would rewrite a
    multi-megabyte file on every run.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for key in keys:
            src = PRICES_DIR / f"{key}.csv"
            if not src.exists():
                continue
            info = zipfile.ZipInfo(f"prices/{key}.csv", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, src.read_bytes())
    return buf.getvalue()


def build_prices(lang: str = "en"):
    docs_root = get_docs_root(lang)
    DST_PRICES = docs_root / "prices"
    ensure(DST_PRICES)

    keys = published_price_keys()
    if not keys:
        write(DST_PRICES / "index.md",
              f"# {t(lang, 'prices')}\n\n{t(lang, 'p_no_data')}\n")
        return

    # Downloads are language-neutral: written once into the EN tree, linked
    # absolutely from ZH — the same rule the ZH report index already follows.
    download_base = "" if lang == "en" else f"{SITE_BASE}/prices/"

    rows: "list[str]" = []
    manifest: "list[dict]" = []

    for key in keys:
        bars = prices.load_store(key, PRICES_DIR)
        stats = price_analytics.summary(bars)
        if not stats:
            continue
        meta = get_meta(key)
        dst_dir = DST_PRICES / key
        ensure(dst_dir)

        # Chart payloads are written into *both* language trees so the pages work
        # under `mkdocs serve` in either tree; only the bulky raw CSV is shared.
        write(dst_dir / "prices.json", full_price_payload(key, bars))
        write(dst_dir / "analytics.json", analytics_payload(key, bars))
        csv_name = f"{key}.csv"
        if lang == "en":
            copy_file(PRICES_DIR / csv_name, dst_dir / csv_name)
        # Two links to the same file: the ticker page sits next to it, the index
        # one level up. ZH gets the absolute EN path in both cases.
        csv_href = (f"{download_base}{key}/{csv_name}" if download_base else csv_name)
        csv_href_index = (f"{download_base}{key}/{csv_name}" if download_base
                          else f"{key}/{csv_name}")

        write(dst_dir / "index.md",
              "\n".join(price_ticker_page(key, meta, stats, bars, csv_href, lang)))

        rows.append(
            # Link the .md, not the directory: MkDocs resolves it to the
            # directory URL and --strict can verify the target exists.
            f"| {meta['flag']} [{key.upper()}]({key}/index.md) | {meta['name']} "
            f"| {_num(stats['last_close'])} "
            f"| {_pct_cell(stats['returns']['1d'])} "
            f"| {_pct_cell(stats['returns']['1m'])} "
            f"| {_pct_cell(stats['ytd'])} "
            f"| {_pct_cell(stats['returns']['1y'])} "
            f"| {_num(stats['low_52w'])} – {_num(stats['high_52w'])} "
            f"| {_compact_volume(stats['avg_volume_30d'])} "
            f"| {stats['first_date']} → {stats['last_date']} "
            f"| [CSV]({csv_href_index}) |"
        )
        manifest.append({"ticker": key.upper(), "key": key,
                         "csv": f"{SITE_BASE}/prices/{key}/{csv_name}",
                         "prices_json": f"{SITE_BASE}/prices/{key}/prices.json",
                         "analytics_json": f"{SITE_BASE}/prices/{key}/analytics.json",
                         **stats})

    if lang == "en":
        # One-click bulk download, and a machine-readable manifest so the data is
        # usable from a script without scraping the page.
        write_bytes(DST_PRICES / "all_prices.zip", _price_zip_bytes(keys))
        write(DST_PRICES / "index.json",
              json.dumps({"updated": TODAY, "count": len(manifest),
                          "columns": list(prices.FIELDS), "tickers": manifest},
                         separators=(",", ":")))

    write(DST_PRICES / "index.md",
          "\n".join(price_index_page(rows, len(manifest), download_base, lang)))


def price_index_page(rows: "list[str]", count: int, download_base: str,
                     lang: str) -> "list[str]":
    """The Price Data landing page: what the dataset is, how to get it, and a
    sortable-by-eye overview of every ticker in it."""
    zip_href = f"{download_base}all_prices.zip" if download_base else "all_prices.zip"
    json_href = f"{download_base}index.json" if download_base else "index.json"
    return [
        f"# 💹 {t(lang, 'prices')}",
        "",
        f"> {t(lang, 'prices_desc').format(n=count, years=prices.KEEP_YEARS)}  "
        f"|  **{t(lang, 'last_updated')}:** {TODAY}",
        "",
        t(lang, "prices_intro"),
        "",
        f"## {t(lang, 'p_download')}",
        "",
        f"- :material-folder-zip: [**{t(lang, 'p_zip')}**]({zip_href}) — "
        f"{t(lang, 'p_zip_desc').format(n=count)}",
        f"- :material-code-json: [**`index.json`**]({json_href}) — "
        f"{t(lang, 'p_manifest_desc')}",
        f"- {t(lang, 'p_per_ticker_desc')}",
        "",
        f"### {t(lang, 'p_columns')}",
        "",
        "```",
        ",".join(prices.FIELDS),
        "```",
        "",
        t(lang, "p_columns_desc"),
        "",
        "```python",
        "import pandas as pd",
        "",
        f'url = "https://yennanliu.github.io{SITE_BASE}/prices/nvda/nvda.csv"',
        'df = pd.read_csv(url, parse_dates=["date"]).set_index("date")',
        'df["close"].pct_change().std() * (252 ** 0.5)  # annualised volatility',
        "```",
        "",
        f"## {t(lang, 'p_coverage')}",
        "",
        '<div class="ptable" markdown="1">',
        "",
        f"| {t(lang, 'ticker')} | {t(lang, 'company')} | {t(lang, 'p_last')} "
        f"| 1D | 1M | YTD | 1Y | {t(lang, 'p_52w_range')} | {t(lang, 'p_avg_vol')} "
        f"| {t(lang, 'p_history')} | CSV |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
        *rows,
        "",
        "</div>",
        "",
        f"!!! warning \"{t(lang, 'disclaimer')}\"",
        "",
        f"    {t(lang, 'p_disclaimer')}",
        "",
    ]


def price_ticker_page(key: str, meta: dict, stats: dict, bars: "list[dict]",
                      csv_href: str, lang: str) -> "list[str]":
    """One ticker's Price Data page: candles, derived charts, stats, download."""
    ret = stats["returns"]
    # get_meta falls back to the bare ticker for names it doesn't carry; without
    # this the heading would read "SKHY (SKHY)".
    title = (key.upper() if meta["name"] == key.upper()
             else f"{meta['name']} ({key.upper()})")
    lines = [
        f"# {meta['flag']} {title} — {t(lang, 'p_price_history')}",
        "",
        f"> **{t(lang, 'sector')}:** {meta['sector']}  |  "
        f"**{t(lang, 'p_bars')}:** {stats['bars']:,}  |  "
        f"{stats['first_date']} → {stats['last_date']}",
        "",
        kline_block(key, src="prices.json", ma=PRICE_PAGE_MA, ranges=PRICE_PAGE_RANGES),
        "",
        f"## {t(lang, 'p_returns')}",
        "",
        "| 1D | 1W | 1M | 3M | 6M | YTD | 1Y | 3Y | 5Y |",
        "|---|---|---|---|---|---|---|---|---|",
        "| " + " | ".join([
            _pct_cell(ret["1d"]), _pct_cell(ret["1w"]), _pct_cell(ret["1m"]),
            _pct_cell(ret["3m"]), _pct_cell(ret["6m"]), _pct_cell(stats["ytd"]),
            _pct_cell(ret["1y"]), _pct_cell(ret["3y"]), _pct_cell(ret["5y"]),
        ]) + " |",
        "",
        f"## {t(lang, 'p_key_stats')}",
        "",
        f"| {t(lang, 'p_metric')} | {t(lang, 'p_value')} |",
        "|---|---|",
        f"| {t(lang, 'p_last_close')} | **{_num(stats['last_close'])}** ({stats['last_date']}) |",
        f"| {t(lang, 'p_52w_high')} | {_num(stats['high_52w'])} |",
        f"| {t(lang, 'p_52w_low')} | {_num(stats['low_52w'])} |",
        f"| {t(lang, 'p_from_high')} | {_pct_cell(stats['from_52w_high'])} |",
        f"| {t(lang, 'p_range_pos')} | {_num(stats['range_position'], 0)}% |",
        f"| {t(lang, 'p_ath')} | {_num(stats['all_time_high'])} |",
        f"| {t(lang, 'p_max_dd')} | {_pct_cell(stats['max_drawdown'])} "
        f"({stats['max_drawdown_date']}) |",
        f"| {t(lang, 'p_vol_1y')} | {_num(stats['volatility_1y'])}% |",
        f"| {t(lang, 'p_cagr')} | {_pct_cell(stats['cagr'])} |",
        f"| {t(lang, 'p_avg_vol')} | {_compact_volume(stats['avg_volume_30d'])} |",
        "",
        f"## {t(lang, 'p_drawdown')}",
        "",
        t(lang, "p_drawdown_desc"),
        "",
        pchart_block(src="analytics.json", series="drawdown", kind="area",
                     title=t(lang, "p_drawdown"), color="red"),
        "",
        f"## {t(lang, 'p_volatility')}",
        "",
        t(lang, "p_volatility_desc").format(window=price_analytics.VOL_WINDOW),
        "",
        pchart_block(src="analytics.json", series="volatility", kind="line",
                     title=t(lang, "p_volatility"), color="amber"),
        "",
        f"## {t(lang, 'p_distribution')}",
        "",
        t(lang, "p_distribution_desc"),
        "",
        pchart_block(src="analytics.json", series="histogram", kind="histogram",
                     title=t(lang, "p_distribution"), color="blue"),
        "",
        f"## {t(lang, 'p_monthly')}",
        "",
        t(lang, "p_monthly_desc"),
        "",
    ]
    lines += monthly_heatmap(bars, lang)
    lines += [
        f"## {t(lang, 'p_download')}",
        "",
        f"- :material-file-delimited: [**{key}.csv**]({csv_href}) — "
        f"{t(lang, 'p_csv_desc').format(n=stats['bars'])}",
        "- :material-code-json: [`prices.json`](prices.json) — "
        f"{t(lang, 'p_prices_json_desc')}",
        "- :material-code-json: [`analytics.json`](analytics.json) — "
        f"{t(lang, 'p_analytics_json_desc')}",
        "",
        f"[{t(lang, 'p_back_to_index')}](../index.md)",
        "",
    ]
    return lines


# ── 7. scripts.md ─────────────────────────────────────────────────────────────
def build_scripts_page(lang: str = "en"):
    docs_root = get_docs_root(lang)
    scripts_page = docs_root / "scripts.md"
    script_dir = ROOT / "scripts"
    # Only entry points belong on this page — shared modules like edgar_common
    # are imported, not run, so a "python scripts/<name> --help" block would lie.
    py_scripts = sorted(
        p for p in script_dir.glob("*.py")
        if '__main__' in p.read_text(encoding="utf-8", errors="ignore")
    ) if script_dir.exists() else []
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


# ── 8. .pages files for awesome-pages plugin ──────────────────────────────────
def build_nav_pages(lang: str = "en"):
    """Write .pages files so awesome-pages controls navigation order."""
    docs_root = get_docs_root(lang)
    root_pages = docs_root / ".pages"
    # investor_day is deliberately absent: the section is still built and its
    # pages stay reachable by URL, but it no longer occupies a top-level tab.
    write(root_pages, "\n".join([
        "nav:",
        "  - index.md",
        "  - reports",
        "  - prices",
        "  - market_news",
        "  - notebooks",
        "  - sec",
        "  - scripts.md",
        "",
    ]))

    DST_REPORTS = docs_root / "reports"
    DST_PRICES = docs_root / "prices"
    DST_MARKET_NEWS = docs_root / "market_news"
    DST_NOTEBOOKS = docs_root / "notebooks"
    DST_SEC = docs_root / "sec"
    DST_INV_DAY = docs_root / "investor_day"

    for subdir in [DST_SEC, DST_INV_DAY]:
        if subdir.exists():
            pages_file = subdir / ".pages"
            write(pages_file, "nav:\n  - index.md\n  - ...\n")

    # Price Data section: localised nav title, index first then the tickers.
    if DST_PRICES.exists():
        write(DST_PRICES / ".pages",
              f"title: {t(lang, 'prices')}\nnav:\n  - index.md\n  - ...\n")
        for ticker_dir in DST_PRICES.iterdir():
            if ticker_dir.is_dir():
                # Quoted for the same reason as the report dirs: an all-digit
                # ticker ("0050") would otherwise parse as a YAML int.
                write(ticker_dir / ".pages", f'title: "{ticker_dir.name.upper()}"\n')

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

    # .pages for the 10k/ and 10q/ sub-directories inside sec/
    for form in FILING_SPECS:
        form_dir = DST_SEC / form
        if form_dir.exists():
            write(form_dir / ".pages", "nav:\n  - ...\n")


# ── 9. includes/abbreviations.md ─────────────────────────────────────────────
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
            for subdir in ["reports", "prices", "market_news", "notebooks", "sec", "investor_day"]:
                path = lang_dir / subdir
                if path.exists():
                    shutil.rmtree(path)
                    print(f"  clean {path.relative_to(ROOT)}/")

    # Build English version
    print(f"\n{'─'*70}")
    print(" Building English version (docs/)")
    print(f"{'─'*70}")

    print("\n[EN 1/9] Building ai_gen_report/stock reports...")
    build_reports(lang="en")

    print("\n[EN 2/9] Building ai_gen_report/market_news...")
    build_market_news(lang="en")

    print("\n[EN 3/9] Building notebook_llm pages...")
    build_notebooks(lang="en")

    print("\n[EN 4/9] Building 10-K + 10-Q indices...")
    build_filing_index(lang="en", form="10k")
    build_filing_index(lang="en", form="10q")

    print("\n[EN 5/9] Building other SEC indices (13-F, 6-K)...")
    build_other_sec(lang="en")

    print("\n[EN 6/9] Building investor_day pages...")
    build_investor_day(lang="en")

    print("\n[EN 7/9] Building price data pages...")
    build_prices(lang="en")

    print("\n[EN 8/9] Building scripts page...")
    build_scripts_page(lang="en")

    print("\n[EN 9/9] Writing .pages nav files & abbreviations...")
    build_nav_pages(lang="en")
    build_abbreviations(lang="en")

    # Build Traditional Chinese version
    print(f"\n{'─'*70}")
    print(" Building Traditional Chinese version (docs/zh/)")
    print(f"{'─'*70}")

    print("\n[ZH 1/9] Building ai_gen_report/stock reports...")
    build_reports(lang="zh")

    print("\n[ZH 2/9] Building ai_gen_report/market_news...")
    build_market_news(lang="zh")

    print("\n[ZH 3/9] Building notebook_llm pages...")
    build_notebooks(lang="zh")

    print("\n[ZH 4/9] Building 10-K + 10-Q indices...")
    build_filing_index(lang="zh", form="10k")
    build_filing_index(lang="zh", form="10q")

    print("\n[ZH 5/9] Building other SEC indices (13-F, 6-K)...")
    build_other_sec(lang="zh")

    print("\n[ZH 6/9] Building investor_day pages...")
    build_investor_day(lang="zh")

    print("\n[ZH 7/9] Building price data pages...")
    build_prices(lang="zh")

    print("\n[ZH 8/9] Building scripts page...")
    build_scripts_page(lang="zh")

    print("\n[ZH 9/9] Writing .pages nav files & abbreviations...")
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
