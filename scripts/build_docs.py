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
  • data/prices/ + data/fundamentals/
                               → docs/data/<ticker>/  (charts + CSV downloads)
  • README.md                  → enriches docs/index.md

Run locally:   python scripts/build_docs.py
Run in CI:     automatically called before `mkdocs build`
"""

from __future__ import annotations

import hashlib
import html
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
from analysis.data import (fundamental_analytics, fundamentals,
                          price_analytics, prices)

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).resolve().parent.parent
DOCS       = ROOT / "docs"
DOCS_ZH    = ROOT / "docs" / "zh"
SITE       = ROOT / "site"

SRC_STOCK    = ROOT / "ai_gen_report" / "stock"
SRC_FUNDAMENTAL = ROOT / "ai_gen_report" / "fundamental"
SRC_TECHNICAL   = ROOT / "ai_gen_report" / "technical"
PRICES_DIR      = ROOT / "data" / "prices"           # committed OHLCV store; chart payloads are derived from it
FUNDAMENTALS_DIR = ROOT / "data" / "fundamentals"    # committed quarterly statements; ratios are derived from it
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


# Report category is carried in the filename prefix that generate_analysis.py
# writes (see ANALYSIS_TYPES' filename_prefix). Naming the rule once keeps the
# per-ticker page and the top-level index from ever disagreeing about which
# section a report belongs in.
TECHNICAL_PREFIX = "technical_"
FUNDAMENTAL_PREFIX = "fundamental_"


def split_by_type(md_files: list[Path]) -> "tuple[list[Path], list[Path], list[Path]]":
    """Split report files into (technical, fundamental, other), newest-first."""
    return (
        by_date_desc([f for f in md_files if f.name.startswith(TECHNICAL_PREFIX)]),
        by_date_desc([f for f in md_files if f.name.startswith(FUNDAMENTAL_PREFIX)]),
        by_date_desc([f for f in md_files
                      if not f.name.startswith((TECHNICAL_PREFIX, FUNDAMENTAL_PREFIX))]),
    )


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
        # Name of this language, as the nav tab and language switcher label it.
        "lang_name": "English",
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
        "p_download": "📥 Download",
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
        "p_bars": "Bars",
        "p_returns": "📈 Returns",
        "p_key_stats": "📊 Key Statistics",
        "p_metric": "Metric",
        "p_value": "Value",
        "p_last_close": "Last close",
        "p_52w_high": "52-week high",
        "p_52w_low": "52-week low",
        "p_of_range": "of range",
        "p_vol_short": "Volatility (1Y)",
        "p_from_high": "From 52-week high",
        "p_range_pos": "Position in 52-week range",
        "p_ath": "Highest price on record",
        "p_max_dd": "Max drawdown (stored history)",
        "p_vol_1y": "Annualised volatility (1Y)",
        "p_cagr": "CAGR (stored history)",
        "p_drawdown": "📉 Drawdown from Peak",
        "p_volatility": "🌡️ Rolling Volatility",
        "p_distribution": "🎲 Daily Return Distribution",
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
        "p_disclaimer": (
            "Price data is sourced from Yahoo Finance and provided as-is for research and "
            "educational use. It is not verified against an official exchange feed and must "
            "not be relied on for trading decisions."
        ),
        # ── Financials section ──
        "f_coverage": "Coverage",
        "f_coverage_desc": (
            "Only SEC registrants filing US-GAAP have XBRL facts to read, so ETFs, "
            "non-US listings and IFRS filers (TSM, GRAB, NU, NBIS) are absent rather "
            "than empty."
        ),
        "f_statements": "💰 Statements",
        "f_profitability": "📊 Profitability",
        "f_valuation": "⚖️ Valuation",
        "f_revenue": "Revenue",
        "f_yoy": "YoY",
        "f_eps_basic": "EPS (basic)",
        "f_eps_diluted": "EPS (diluted)",
        "f_operating_income": "Operating Income",
        "f_net_income": "Net Income",
        "f_opex": "Operating Expenses",
        "f_rnd": "R&D",
        "f_sga": "SG&A",
        "f_cash_flow": "Cash Flow",
        "f_ocf": "Operating CF",
        "f_fcf": "Free CF",
        "f_cash_debt": "Cash & Debt",
        "f_cash": "Cash & investments",
        "f_debt": "Total debt",
        "f_margins": "Margins",
        "f_gross_margin": "Gross",
        "f_operating_margin": "Operating",
        "f_net_margin": "Net",
        "f_row_gross_margin": "Gross margin",
        "f_row_operating_margin": "Operating margin",
        "f_row_net_margin": "Net margin",
        "f_returns": "Return on Capital",
        "f_ros": "Return on Sales",
        "f_pe": "P/E",
        "f_ps": "P/S",
        "f_pb": "P/B",
        "f_ev_sales": "EV/Sales",
        "f_ev_ebitda": "EV/EBITDA",
        "f_pe_bands": "P/E Bands",
        "f_price": "Price",
        "f_periods": "Periods",
        "f_latest_quarter": "Latest quarter",
        "f_ttm": "TTM",
        "f_key_figures": "📋 Key Figures",
        "f_filed": "Filed",
        "f_source_filing": "Source filing",
        "f_csv_desc": "reported quarterly statements, {n} periods",
        "f_json_desc": "every derived series the charts on this page consume",
        "f_quarterly_note": (
            "Figures are per fiscal quarter. Filers report cash flow and many income "
            "items year-to-date and stop tagging the fourth quarter separately, so a "
            "discrete quarter is reconciled by differencing consecutive year-to-date "
            "figures — arithmetic on reported numbers, not an estimate. A blank cell "
            "means the company does not tag that concept."
        ),
        "f_snapshot": "💵 Financials (TTM)",
        "f_snapshot_note": (
            "Trailing twelve months from the company's own SEC filings, as of "
            "{period} ({form}). Valuation multiples use the close on that date."
        ),
        "f_see_all": "All financial charts",
        "f_disclaimer": (
            "Figures come from SEC XBRL filings and are provided as-is for research and "
            "educational use. Concept mapping across filers is imperfect and restatements "
            "are not tracked; verify against the filing itself before relying on any number."
        ),
        # ── Market Data: the merged Price + Financials section ──
        "md": "Market Data",
        "md_desc": "{n} tickers · daily prices and reported quarterly statements",
        "md_intro": (
            "Price and fundamentals for the same company, on one page. Both come from "
            "committed datasets in this repository — daily OHLCV under `data/prices/`, "
            "refreshed nightly from Yahoo Finance, and reported quarterly statements "
            "under `data/fundamentals/`, taken from each company's own SEC filings via "
            "the XBRL `companyfacts` API. Every chart and every ratio below is derived "
            "from those two files at build time, so the picture and the download can "
            "never disagree."
        ),
        "md_no_data": "No market data found.",
        "md_tab_overview": "🧭 Overview",
        "md_tab_price": "📈 Price",
        "md_tab_financials": "💰 Financials",
        "md_tab_valuation": "⚖️ Valuation",
        "md_tab_data": "📥 Data & glossary",
        "md_tabs_hint": (
            "<b>{n} tabs</b> — the rest of this page is behind them. "
            "Click to switch between price history, financial statements, "
            "valuation and the raw data."
        ),
        "md_back_to_index": "← Back to Market Data",
        "md_more": "Full price history, financial statements & CSV downloads",
        "md_price_only": "No SEC fundamentals for this ticker — price data only.",
        "md_price_missing": "No price store for this ticker — financial statements only.",
        "md_moved": "This page has moved",
        "md_moved_body": "Price Data and Financials are now one **Market Data** section.",
        "md_open": "Open the Market Data page",
        "md_file_prices": "Prices",
        "md_file_financials": "Financials",
        "md_zip": "market_data.zip",
        "md_zip_desc": "every ticker's price and financials CSV in one archive ({n} tickers)",
        "md_manifest_desc": (
            "machine-readable summary of every ticker — last close, returns, "
            "volatility, TTM revenue, margins, multiples and file URLs"
        ),
        # Axis captions. Lightweight Charts prints the axis values but has no
        # concept of an axis title, so these are drawn as DOM text beside the
        # canvas — the "what am I looking at" the charts were missing.
        "ax_quarter": "Fiscal quarter",
        "ax_session": "Trading session",
        "ax_month": "Month",
        "ax_return_bucket": "Daily return bucket",
        "ax_usd": "USD",
        "ax_usd_share": "USD per share",
        "ax_pct": "% of revenue",
        "ax_pct_plain": "%",
        "ax_growth": "YoY growth %",
        "ax_annualised": "Annualised %",
        "ax_multiple": "× (multiple)",
        "ax_sessions": "Sessions",
        "ax_drawdown": "% below peak",
        # ── What each chart means ──
        "f_revenue_note": (
            "Total sales booked in each fiscal quarter (bars, left-to-right in time) "
            "against the same quarter a year earlier (line). The year-on-year line "
            "strips out seasonality, which a quarter-on-quarter comparison cannot."
        ),
        "f_operating_income_note": (
            "Profit from running the business — revenue less cost of sales and operating "
            "expenses, before interest and tax. This is the line that says whether the "
            "core operation makes money."
        ),
        "f_net_income_note": (
            "The bottom line: what is left for shareholders after every cost, including "
            "interest, tax and one-offs. It moves around more than operating income "
            "because one-offs land here."
        ),
        "f_eps_note": (
            "Net income divided by the share count, assuming every option and "
            "convertible is exercised. Buybacks lift it without the business earning "
            "more; issuance dilutes it without the business earning less."
        ),
        "f_opex_note": (
            "What the company spends to run and grow itself, split into research & "
            "development and selling, general & administrative. The bands stack, so the "
            "outer edge is the combined total."
        ),
        "f_cash_flow_note": (
            "Cash actually generated by operations, and what survives after capital "
            "spending (free cash flow = operating cash flow − capex). Profit is an "
            "opinion; cash flow is closer to a fact."
        ),
        "f_cash_debt_note": (
            "Cash and short-term investments against total borrowings. Cash above debt "
            "is a net-cash balance sheet — the company could repay everything tomorrow."
        ),
        "f_margins_note": (
            "How much of each revenue dollar survives: after the direct cost of the "
            "product (gross), after the cost of running the company (operating), and "
            "after everything including tax (net). Computed on trailing twelve months."
        ),
        "f_returns_note": (
            "How hard the capital works. ROE = profit ÷ shareholders' equity, ROA = "
            "profit ÷ all assets, ROIC = after-tax operating profit ÷ the debt and "
            "equity actually invested. ROIC is the one that ignores how the business "
            "was financed."
        ),
        "f_ros_note": (
            "Operating profit as a share of revenue — the same idea as operating margin, "
            "kept alongside the return series for comparison."
        ),
        "f_pe_note": (
            "Price ÷ trailing-twelve-month earnings per share: how many dollars the "
            "market pays for one dollar of annual profit. 20× means it would take twenty "
            "years of today's earnings to repay today's price. High means the market "
            "expects growth — or that earnings are temporarily depressed."
        ),
        "f_ps_note": (
            "Price ÷ trailing-twelve-month revenue per share. The multiple of last "
            "resort for a company that has sales but no profit yet, since it says "
            "nothing about whether those sales ever convert to cash."
        ),
        "f_pb_note": (
            "Price ÷ book value per share, where book value is assets minus "
            "liabilities. Meaningful for banks and asset-heavy businesses; close to "
            "meaningless where the real assets are brands and code, which the balance "
            "sheet never records."
        ),
        "f_ev_sales_note": (
            "Enterprise value ÷ revenue. Enterprise value is market cap plus debt minus "
            "cash — what it would cost to buy the whole business outright — so unlike "
            "P/S it is not flattered by a large cash pile."
        ),
        "f_ev_ebitda_note": (
            "Enterprise value ÷ earnings before interest, tax, depreciation and "
            "amortisation. The standard acquisition yardstick, because it compares "
            "companies before their financing and accounting choices diverge."
        ),
        "p_drawdown_note": (
            "How far the close sits below its own running all-time high. Zero means a "
            "new high; −40% means you would need a 67% gain just to get back to even."
        ),
        "p_volatility_note": (
            "The standard deviation of daily returns over the last {window} sessions, "
            "scaled to a year. 30% roughly means a one-in-three chance of ending the "
            "year more than 30% away from where it started."
        ),
        "p_distribution_note": (
            "How many sessions landed in each daily-move bucket. Fat tails on either "
            "side mean the average day is a poor description of a typical day."
        ),
        "f_pe_bands_note": (
            "The monthly close (blue) against what the price would have been at this "
            "ticker's own historical P/E levels. Above the top band the market is "
            "paying more for these earnings than it ever has; below the bottom band, "
            "less. The bands say what has been paid, not what it is worth."
        ),
        # ── Glossary ──
        "g_title": "📖 How to read these charts",
        "g_intro": (
            "Every term used on this page, in one place. Ratios are computed on "
            "trailing twelve months (the last four reported quarters) unless stated "
            "otherwise, so a single seasonal quarter never distorts them."
        ),
        "g_term": "Term",
        "g_means": "What it means",
        "g_rows": [
            ("TTM", "Trailing twelve months — the last four reported quarters added together. Used instead of a single quarter so seasonality and one-off quarters do not distort a ratio."),
            ("YoY", "Year-on-year: this quarter against the same quarter a year earlier."),
            ("Gross margin", "Revenue less the direct cost of the product, as a share of revenue. What the product itself earns before any company overhead."),
            ("Operating margin", "Operating profit as a share of revenue — after R&D and SG&A, before interest and tax."),
            ("Net margin", "Net profit as a share of revenue, after everything including tax."),
            ("EPS (diluted)", "Net income per share, assuming every option and convertible is exercised."),
            ("FCF", "Free cash flow: operating cash flow minus capital expenditure. The cash left over for dividends, buybacks and debt repayment."),
            ("ROE", "Return on equity: profit ÷ shareholders' equity. Flattered by debt, since borrowing shrinks the denominator."),
            ("ROA", "Return on assets: profit ÷ total assets. Unflattered by debt, and correspondingly lower."),
            ("ROIC", "Return on invested capital: after-tax operating profit ÷ (debt + equity). The cleanest read on whether the business earns more than its capital costs."),
            ("P/E", "Price ÷ earnings per share. Dollars paid for one dollar of annual profit. Undefined when earnings are negative."),
            ("P/S", "Price ÷ revenue per share. Used where there is no profit to divide by."),
            ("P/B", "Price ÷ book value per share (assets − liabilities). Informative for banks; close to meaningless for software."),
            ("EV", "Enterprise value: market cap + total debt − cash. What buying the whole business outright would cost."),
            ("EV/EBITDA", "Enterprise value ÷ earnings before interest, tax, depreciation and amortisation. Compares companies before financing and accounting choices diverge."),
            ("Drawdown", "How far below its own running all-time high the price sits, in percent."),
            ("Volatility", "Standard deviation of daily returns, annualised. A measure of how far the price typically wanders, not of which direction."),
            ("CAGR", "Compound annual growth rate: the single yearly rate that turns the first close into the last."),
            ("Max drawdown", "The deepest peak-to-trough fall in the stored history — the worst loss a buy-and-hold holder would have sat through."),
        ],
        "g_avg": "avg",
    },
    "zh": {
        "lang_name": "繁體中文",
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
        "p_download": "📥 下載",
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
        "p_bars": "資料筆數",
        "p_returns": "📈 報酬率",
        "p_key_stats": "📊 關鍵統計",
        "p_metric": "指標",
        "p_value": "數值",
        "p_last_close": "最新收盤",
        "p_52w_high": "52 週高點",
        "p_52w_low": "52 週低點",
        "p_of_range": "區間位置",
        "p_vol_short": "波動率（1 年）",
        "p_from_high": "距 52 週高點",
        "p_range_pos": "於 52 週區間位置",
        "p_ath": "歷史最高價",
        "p_max_dd": "最大回撤（資料期間）",
        "p_vol_1y": "年化波動率（1 年）",
        "p_cagr": "年化報酬率 CAGR（資料期間）",
        "p_drawdown": "📉 距高點回撤",
        "p_volatility": "🌡️ 滾動波動率",
        "p_distribution": "🎲 日報酬分布",
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
        "p_disclaimer": (
            "股價資料來自 Yahoo Finance，僅供研究與教育用途，未與官方交易所行情核對，"
            "不得作為交易決策依據。"
        ),
        # ── Financials section ──
        "f_coverage": "資料涵蓋範圍",
        "f_coverage_desc": (
            "僅有向 SEC 申報且採用 US-GAAP 的發行人具備可讀取的 XBRL 資料，"
            "因此 ETF、非美股掛牌與採用 IFRS 的發行人（TSM、GRAB、NU、NBIS）並未收錄，"
            "而非顯示為空白。"
        ),
        "f_statements": "💰 財務報表",
        "f_profitability": "📊 獲利能力",
        "f_valuation": "⚖️ 估值",
        "f_revenue": "營收",
        "f_yoy": "年增率",
        "f_eps_basic": "每股盈餘",
        "f_eps_diluted": "稀釋每股盈餘",
        "f_operating_income": "營業利益",
        "f_net_income": "淨利",
        "f_opex": "營業費用",
        "f_rnd": "研發費用",
        "f_sga": "管銷費用",
        "f_cash_flow": "現金流",
        "f_ocf": "營運現金流量",
        "f_fcf": "自由現金流量",
        "f_cash_debt": "現金與債務",
        "f_cash": "現金及短期投資",
        "f_debt": "總負債",
        "f_margins": "三率",
        "f_gross_margin": "毛利率",
        "f_operating_margin": "營業利益率",
        "f_net_margin": "淨利率",
        "f_row_gross_margin": "毛利率",
        "f_row_operating_margin": "營業利益率",
        "f_row_net_margin": "淨利率",
        "f_returns": "經營報酬率",
        "f_ros": "營收報酬率",
        "f_pe": "本益比",
        "f_ps": "股價營收比",
        "f_pb": "股價淨值比",
        "f_ev_sales": "EV/Sales",
        "f_ev_ebitda": "EV/EBITDA",
        "f_pe_bands": "本益比河流圖",
        "f_price": "股價",
        "f_periods": "期數",
        "f_latest_quarter": "最新一季",
        "f_ttm": "近四季",
        "f_key_figures": "📋 重點數據",
        "f_filed": "申報日",
        "f_source_filing": "來源文件",
        "f_csv_desc": "已申報之季度財務報表，共 {n} 期",
        "f_json_desc": "本頁圖表所使用之全部推導序列",
        "f_quarterly_note": (
            "數字以會計季度為單位。發行人之現金流量與多項損益項目係以年初至今累計方式申報，"
            "且通常不單獨標記第四季，因此單季數字係以相鄰累計數相減還原——"
            "此為對已申報數字的算術運算，並非估計值。空白表示該公司未標記該科目。"
        ),
        "f_snapshot": "💵 財報摘要（近四季）",
        "f_snapshot_note": (
            "取自該公司向 SEC 申報之文件，截至 {period}（{form}）。"
            "估值倍數以該日收盤價計算。"
        ),
        "f_see_all": "查看完整財報圖表",
        "f_disclaimer": (
            "數據來自 SEC XBRL 申報文件，僅供研究與教育用途。跨發行人之科目對應並不完美，"
            "且未追蹤財報重編；引用任何數字前請與原始申報文件核對。"
        ),
        # ── Market Data: the merged Price + Financials section ──
        "md": "市場數據",
        "md_desc": "{n} 檔標的 · 每日股價與已申報之季度財務報表",
        "md_intro": (
            "同一家公司的股價與財報，整合於同一頁。兩者皆取自本專案已提交的資料集——"
            "`data/prices/` 下的每日 OHLCV（每晚自 Yahoo Finance 更新），"
            "以及 `data/fundamentals/` 下、透過 XBRL `companyfacts` API 取得的季度財務報表。"
            "以下所有圖表與比率皆於建置時由這兩份檔案推導，因此圖表與下載檔永遠一致。"
        ),
        "md_no_data": "查無市場數據。",
        "md_tab_overview": "🧭 總覽",
        "md_tab_price": "📈 股價",
        "md_tab_financials": "💰 財報",
        "md_tab_valuation": "⚖️ 估值",
        "md_tab_data": "📥 資料與名詞",
        "md_tabs_hint": (
            "<b>共 {n} 個分頁</b>——本頁其餘內容都在其中，"
            "點擊即可在股價走勢、財務報表、估值與原始資料之間切換。"
        ),
        "md_back_to_index": "← 返回市場數據",
        "md_more": "完整股價歷史、財務報表與 CSV 下載",
        "md_price_only": "此標的無 SEC 財報資料，僅提供股價數據。",
        "md_price_missing": "此標的無股價資料，僅提供財務報表。",
        "md_moved": "本頁已搬移",
        "md_moved_body": "「股價資料」與「財報數據」已合併為 **市場數據** 專區。",
        "md_open": "前往市場數據頁面",
        "md_file_prices": "股價",
        "md_file_financials": "財報",
        "md_zip": "market_data.zip",
        "md_zip_desc": "所有標的之股價與財報 CSV 合併封存（共 {n} 檔）",
        "md_manifest_desc": (
            "每檔標的之機器可讀摘要——最新收盤價、報酬率、波動度、"
            "近四季營收、利潤率、估值倍數與檔案網址"
        ),
        "ax_quarter": "財報季度",
        "ax_session": "交易日",
        "ax_month": "月份",
        "ax_return_bucket": "單日漲跌幅區間",
        "ax_usd": "美元",
        "ax_usd_share": "美元／股",
        "ax_pct": "占營收比重 %",
        "ax_pct_plain": "%",
        "ax_growth": "年增率 %",
        "ax_annualised": "年化 %",
        "ax_multiple": "× 倍數",
        "ax_sessions": "交易日數",
        "ax_drawdown": "距高點 %",
        "f_revenue_note": (
            "每一會計季度認列的總營收（柱狀，由左至右為時間），"
            "以及與去年同季相比的年增率（折線）。年增率可排除季節性影響，這是季對季比較做不到的。"
        ),
        "f_operating_income_note": (
            "本業經營所產生的獲利——營收扣除銷貨成本與營業費用，但尚未計入利息與稅負。"
            "這條線決定了核心業務本身是否賺錢。"
        ),
        "f_net_income_note": (
            "最終獲利：扣除包含利息、稅負與一次性項目在內的所有成本後，歸屬股東的金額。"
            "由於一次性項目落在這一層，其波動通常大於營業利益。"
        ),
        "f_eps_note": (
            "淨利除以股數，並假設所有選擇權與可轉債均已行使。"
            "庫藏股會在公司沒有多賺的情況下推升此數字；增資則會在公司沒有少賺的情況下稀釋它。"
        ),
        "f_opex_note": (
            "維持營運與成長所投入的費用，分為研發費用與管銷費用。"
            "兩段為堆疊呈現，因此外緣代表兩者合計。"
        ),
        "f_cash_flow_note": (
            "營運實際產生的現金，以及扣除資本支出後所剩下的部分"
            "（自由現金流量 = 營運現金流量 − 資本支出）。獲利是一種看法，現金流則更接近事實。"
        ),
        "f_cash_debt_note": (
            "現金及短期投資與總借款的對比。現金高於債務即為淨現金狀態——公司明天就能全數償還。"
        ),
        "f_margins_note": (
            "每一元營收最後留下多少：扣除產品直接成本後（毛利率）、"
            "扣除營運成本後（營業利益率）、以及扣除包含稅負在內的一切之後（淨利率）。以近四季計算。"
        ),
        "f_returns_note": (
            "資本的運用效率。ROE = 獲利 ÷ 股東權益，ROA = 獲利 ÷ 總資產，"
            "ROIC = 稅後營業利益 ÷ 實際投入的債權與股權。ROIC 是唯一不受融資方式影響的指標。"
        ),
        "f_ros_note": (
            "營業利益占營收的比重——與營業利益率同義，"
            "此處與經營報酬率並列以便對照。"
        ),
        "f_pe_note": (
            "股價 ÷ 近四季每股盈餘：市場為每一元年度獲利所支付的價格。"
            "20× 表示以今日盈餘水準需二十年才能回收今日股價。"
            "數值偏高代表市場預期成長——或代表盈餘暫時受壓抑。"
        ),
        "f_ps_note": (
            "股價 ÷ 近四季每股營收。對於有營收但尚無獲利的公司，這是不得已的估值方式，"
            "因為它完全無法說明這些營收是否終將轉化為現金。"
        ),
        "f_pb_note": (
            "股價 ÷ 每股淨值（資產減負債）。對銀行與重資產業具參考價值；"
            "對於真正資產是品牌與程式碼、而資產負債表從不記錄的公司則近乎無意義。"
        ),
        "f_ev_sales_note": (
            "企業價值 ÷ 營收。企業價值 = 市值 + 負債 − 現金，即買下整間公司的代價，"
            "因此不像股價營收比會被大量現金部位美化。"
        ),
        "f_ev_ebitda_note": (
            "企業價值 ÷ 稅息折舊攤銷前獲利。併購評價的標準尺度，"
            "因為它在各公司融資與會計選擇分歧之前就完成比較。"
        ),
        "p_drawdown_note": (
            "收盤價距離其自身歷史新高的幅度。0 代表創新高；"
            "−40% 則代表需要上漲 67% 才能回到原點。"
        ),
        "p_volatility_note": (
            "近 {window} 個交易日之日報酬標準差，年化後表示。"
            "30% 大致代表約三分之一的機率，一年後價格會偏離起點超過 30%。"
        ),
        "p_distribution_note": (
            "各單日漲跌幅區間的交易日數。兩側的厚尾代表「平均的一天」"
            "並不能代表「典型的一天」。"
        ),
        "f_pe_bands_note": (
            "月收盤價（藍線）對照該檔標的自身歷史本益比水準所對應的價格。"
            "高於最上緣代表市場為這些盈餘付出的價格高於以往；低於最下緣則相反。"
            "河流圖說明的是市場付過多少，而非其應有價值。"
        ),
        "g_title": "📖 圖表與名詞說明",
        "g_intro": (
            "本頁所使用的名詞彙整於此。除另有說明外，所有比率皆以近四季"
            "（最近四個已申報季度）計算，因此單一季節性季度不會造成失真。"
        ),
        "g_term": "名詞",
        "g_means": "意義",
        "g_rows": [
            ("TTM（近四季）", "最近四個已申報季度的合計。改用近四季而非單季，可避免季節性與一次性項目扭曲比率。"),
            ("YoY（年增率）", "本季與去年同季相比。"),
            ("毛利率", "營收扣除產品直接成本後占營收的比重，即產品本身在分攤公司管銷前所賺取的部分。"),
            ("營業利益率", "營業利益占營收的比重——已扣除研發與管銷費用，尚未計入利息與稅負。"),
            ("淨利率", "淨利占營收的比重，已扣除包含稅負在內的所有項目。"),
            ("稀釋每股盈餘", "假設所有選擇權與可轉債均已行使後的每股淨利。"),
            ("自由現金流量", "營運現金流量減資本支出，即可用於股利、庫藏股與償債的現金。"),
            ("ROE（股東權益報酬率）", "獲利 ÷ 股東權益。舉債會縮小分母，因而美化此數字。"),
            ("ROA（資產報酬率）", "獲利 ÷ 總資產。不受舉債美化，數值因此較低。"),
            ("ROIC（投入資本報酬率）", "稅後營業利益 ÷（負債 + 股東權益）。判斷本業報酬是否高於資金成本最乾淨的指標。"),
            ("本益比 P/E", "股價 ÷ 每股盈餘，即為每一元年度獲利所付出的價格。盈餘為負時無意義。"),
            ("股價營收比 P/S", "股價 ÷ 每股營收。適用於尚無獲利可供相除的公司。"),
            ("股價淨值比 P/B", "股價 ÷ 每股淨值（資產 − 負債）。對銀行具參考價值，對軟體業則近乎無意義。"),
            ("企業價值 EV", "市值 + 總負債 − 現金，即買下整間公司的代價。"),
            ("EV/EBITDA", "企業價值 ÷ 稅息折舊攤銷前獲利，可在融資與會計選擇分歧前完成跨公司比較。"),
            ("回撤 Drawdown", "股價距離其自身歷史新高的百分比。"),
            ("波動度 Volatility", "日報酬標準差之年化值。衡量價格通常擺盪的幅度，而非方向。"),
            ("年化報酬率 CAGR", "將期初收盤價變為期末收盤價所需的單一年度複合成長率。"),
            ("最大回撤", "資料期間內最深的高點至低點跌幅——長期持有者實際承受過的最大虧損。"),
        ],
        "g_avg": "平均",
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


# ── Price-store read cache ───────────────────────────────────────────────────
# One build re-reads the same ticker CSV from many places: the hero chart, every
# dated technical report page (~1,600 of them), the current-price lookup, the
# published-keys probe and the Price Data pages — each ~2,500 rows, twice over
# for the EN and ZH trees. Parsing is pure and the file does not change during a
# build, so cache on the file's identity (path + mtime + size) rather than the
# key alone: a rewritten store still re-reads, which keeps tests that
# monkeypatch PRICES_DIR honest.
_STORE_CACHE: "dict[tuple, list[dict]]" = {}


def store_bars(key: str) -> "list[dict]":
    """`prices.load_store` for this build, memoised. Never mutate the result."""
    path = prices.store_path(key, PRICES_DIR)
    try:
        st = path.stat()
        ident = (str(path), st.st_mtime_ns, st.st_size)
    except OSError:  # missing store — load_store returns [] for it anyway
        ident = (str(path), None, None)
    if ident not in _STORE_CACHE:
        _STORE_CACHE[ident] = prices.load_store(key, PRICES_DIR)
    return _STORE_CACHE[ident]


def kline_bars(ticker: str) -> "list[dict]":
    """Bars for a ticker's chart payload, oldest→newest ([] when unavailable).

    Reads the store live off the module global so tests can monkeypatch it.
    """
    bars = store_bars(ticker)
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
    if not report.name.startswith(TECHNICAL_PREFIX):
        return ""
    d = _file_date(report)
    return kline_block(ticker, src="../kline.json",
                       as_of=d.isoformat() if d else "", ma=REPORT_MA)


# ── Ticker hero: identity, and the numbers checked before anything is read ───
# A report index used to open with a gradient h1, a one-line blockquote, and
# then 400px of candlestick chart. Everything a reader checks before deciding
# whether to open a 40-page report — what it costs, what it has done this year,
# where in its own 52-week band it is sitting — was a section away, on the
# Market Data page. The hero lifts those onto the page the ticker's nav entry
# actually points at.
#
# Every figure comes from price_analytics.summary() over the committed store —
# the same call the Market Data pages make — so the two can never disagree, and
# none of it is computed in JS (docs/PRICE_STORE_DESIGN.md §12). It is static
# HTML, so it also renders with JS off, when the chart below it does not.

def _esc(text) -> str:
    """Escape interpolated text. Company names and sectors are repo data rather
    than model output, but they land in raw HTML that Markdown will not clean up
    on the way past."""
    return html.escape(str(text), quote=True)


def _tone(v: "float | None") -> str:
    """The up/down modifier for a signed figure ('' when there is no figure)."""
    return "" if v is None else (" is-up" if v >= 0 else " is-down")


def _signed_pct(v: "float | None", digits: int = 2) -> str:
    """A signed percentage with no colour of its own — the tile carries that as
    a class, so this is _pct_cell's counterpart outside a Markdown table."""
    return "—" if v is None else f"{v:+,.{digits}f}%"


def _tkstat(label: str, value: str, *, sub: str = "", tone: str = "") -> str:
    """One KPI tile. `value` is already-formatted markup; the rest is escaped."""
    out = ['<div class="tkstat">',
           f'<span class="tkstat__k">{_esc(label)}</span>',
           f'<span class="tkstat__v{tone}">{value}</span>']
    if sub:
        out.append(f'<span class="tkstat__s">{_esc(sub)}</span>')
    out.append("</div>")
    return "".join(out)


def _range_tile(stats: dict, lang: str) -> str:
    """The 52-week band as a rail with the last close marked on it.

    A high and a low are two numbers; where today sits between them is the
    reading, and it is the one thing a row of numbers cannot show. The marker
    offset is arithmetic over the store, so it is computed here and handed to
    CSS as a percentage rather than derived in the browser.
    """
    lo, hi, pos = (stats.get("low_52w"), stats.get("high_52w"),
                   stats.get("range_position"))
    if lo is None or hi is None or pos is None:
        return ""
    pos = min(100.0, max(0.0, pos))
    return (
        '<div class="tkstat tkstat--wide">'
        f'<span class="tkstat__k">{_esc(t(lang, "p_52w_range"))}</span>'
        '<div class="tkrange" role="presentation">'
        f'<span class="tkrange__dot" style="left:{pos:.1f}%"></span></div>'
        '<div class="tkrange__ends">'
        f'<span>{_num(lo)}</span>'
        f'<span class="tkrange__pos">{_pct_plain(pos, 0)} '
        f'{_esc(t(lang, "p_of_range"))}</span>'
        f'<span>{_num(hi)}</span></div></div>'
    )


def ticker_hero_block(ticker: str, meta: dict, counts: "list[str]",
                      lang: str) -> str:
    """The identity chips and KPI tiles that open a ticker's report index.

    Degrades in one step: a ticker with no OHLCV in the store still gets its
    chips, just no tiles — the same rule the chart below already follows.
    """
    bars = store_bars(ticker)
    stats = price_analytics.summary(bars) if bars else None

    chips = [f'<span class="tkchip tkchip--sym">{_esc(ticker.upper())}</span>',
             f'<span class="tkchip">{_esc(meta["sector"])}</span>']
    if counts:
        chips.append('<span class="tkchip tkchip--dim">'
                     f'{_esc(" · ".join(counts))}</span>')
    chips.append(f'<span class="tkchip tkchip--dim">'
                 f'{_esc(t(lang, "last_updated"))} {TODAY}</span>')

    tiles: "list[str]" = []
    if stats:
        ret = stats["returns"]
        currency = prices.currency_for(prices.to_yf_symbol(ticker))
        # Currency in the label rather than beside the date: the tile is a
        # sixth of the content width, and "USD · 2026-09-17" wraps in it.
        tiles.append(_tkstat(f'{t(lang, "p_last_close")} ({currency})',
                             _num(stats["last_close"]), sub=stats["last_date"]))
        # Labelled with the same bare period codes the Market Data returns table
        # uses, which need no translating and read the same in both trees.
        for label, value in (("1D", ret.get("1d")), ("1M", ret.get("1m")),
                             ("YTD", stats.get("ytd")), ("1Y", ret.get("1y"))):
            tiles.append(_tkstat(label, _signed_pct(value), tone=_tone(value)))
        # The Market Data stat table has room for "Annualised volatility (1Y)";
        # a tile in a six-across grid does not, and a clipped label is worse
        # than a short one.
        tiles.append(_tkstat(t(lang, "p_vol_short"),
                             _pct_plain(stats.get("volatility_1y"), 1)))
        tiles.append(_range_tile(stats, lang))

    return "\n".join([
        '<div class="tkhero">',
        '  <div class="tkhero__id">',
        f'    <span class="tkhero__mark">{_esc(meta["flag"])}</span>',
        f'    <div class="tkhero__chips">{"".join(chips)}</div>',
        '  </div>',
        *([f'  <div class="tkstats">{"".join(t_ for t_ in tiles if t_)}</div>']
          if tiles else []),
        "</div>",
    ])


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
    bars = store_bars(ticker)
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


def scenario_rail(scenarios: "list[dict]", current: float,
                  weighted: float, lang: str) -> str:
    """The bear/base/bull spread drawn on one axis, with today's price on it.

    The table underneath already carries every number; what it cannot show is
    the shape — whether the current price sits below the bear case or halfway to
    the bull one, and how far apart the three cases actually are. Two reports
    with identical +23.8% weighted upside can look completely different here.

    All positions are percentages computed in Python. The scale is padded 8%
    either side so a marker at an extreme still has a visible tick rather than
    being clipped flush against the end of the track.
    """
    points = [s["target"] for s in scenarios] + [current, weighted]
    lo, hi = min(points), max(points)
    if hi <= lo:
        return ""
    pad = (hi - lo) * 0.08
    lo, hi = lo - pad, hi + pad

    def at(v: float) -> float:
        return (v - lo) / (hi - lo) * 100

    lbl = "zh" if lang == "zh" else "en"
    band_l, band_r = at(min(s["target"] for s in scenarios)), at(
        max(s["target"] for s in scenarios))
    ticks = "".join(
        f'<span class="tkrail__tick is-{s["key"]}" style="left:{at(s["target"]):.1f}%"></span>'
        for s in scenarios)
    keys = "".join(
        f'<span class="tkrail__key is-{s["key"]}">{s["emoji"]} '
        f'{_esc(s[lbl])} <b>{_fmt_money(s["target"])}</b></span>'
        for s in scenarios)
    return "\n".join([
        '<div class="tkrail">',
        '  <div class="tkrail__track">',
        f'    <span class="tkrail__band" style="left:{band_l:.1f}%;'
        f'width:{max(band_r - band_l, 0):.1f}%"></span>',
        f'    {ticks}',
        f'    <span class="tkrail__now" style="left:{at(current):.1f}%"></span>',
        f'    <span class="tkrail__wt" style="left:{at(weighted):.1f}%"></span>',
        '  </div>',
        '  <div class="tkrail__legend">',
        f'    {keys}',
        f'    <span class="tkrail__key is-now">{_esc(t(lang, "pt_current"))} '
        f'<b>{_fmt_money(current)}</b></span>',
        f'    <span class="tkrail__key is-wt">'
        f'{_esc(t(lang, "pt_weighted_target"))} '
        f'<b>{_fmt_money(weighted)}</b> '
        f'<i class="{"is-up" if weighted >= current else "is-down"}">'
        f'{_fmt_pct(weighted / current - 1)}</i></span>',
        '  </div>',
        '</div>',
    ])


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
        scenario_rail(scenarios, current, weighted_target, lang),
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


# ── Financials snapshot on the report page ───────────────────────────────────
# The Market Data page carries twenty-odd charts; putting them all here would
# bury the reports this page exists to index. What earns its place is the
# trailing-twelve-month line and the three charts that answer "is this company
# growing, is it profitable, and what is the market paying" — the rest stays one
# click away.
#
# Both the table and the charts read the payload build_market_data() already
# writes at ../../data/<ticker>/fundamentals.json, so nothing is duplicated and
# the two sections can never disagree. That relative path resolves correctly in
# both language trees, because the payload is written into each of them.
FUND_SNAPSHOT_SRC = "../../data/{ticker}/fundamentals.json"


def fundamentals_snapshot_block(ticker: str, lang: str) -> str:
    """Compact TTM table + three headline charts, or "" when there is no store.

    Returns markdown rather than appending to a list so the caller can treat it
    the same way it treats target_price_block().
    """
    rows = fundamental_rows(ticker)
    if not rows:
        return ""
    stats = fundamental_analytics.summary(rows, store_bars(ticker))
    if not stats:
        return ""

    margins = stats.get("margins_ttm") or {}
    returns = stats.get("returns_ttm") or {}
    mult = stats.get("multiples_ttm") or {}
    src = FUND_SNAPSHOT_SRC.format(ticker=ticker)

    def chart(**kw):
        return pchart_block(src=src, **kw)

    # Seven figures in a seven-column table is a table only in the technical
    # sense: one row, no comparison down any column, and at phone width it
    # became a horizontal scroll. The same seven read as tiles, which is what
    # the hero above already established as this page's shape for "numbers at a
    # glance", and they wrap instead of scrolling.
    yoy = stats.get("revenue_yoy")
    out = [
        f"### {t(lang, 'f_snapshot')}",
        "",
        '<div class="tkstats tkstats--fin">' + "".join([
            _tkstat(f"{t(lang, 'f_revenue')} ({t(lang, 'f_ttm')})",
                    _money(stats.get("revenue_ttm"))),
            _tkstat(t(lang, "f_yoy"), _signed_pct(yoy), tone=_tone(yoy)),
            _tkstat(t(lang, "f_row_gross_margin"),
                    _pct_plain(margins.get("gross"))),
            _tkstat(t(lang, "f_row_net_margin"),
                    _pct_plain(margins.get("net"))),
            _tkstat("ROE", _pct_plain(returns.get("roe"))),
            _tkstat(t(lang, "f_pe"), _mult(mult.get("pe"))),
            _tkstat(t(lang, "f_fcf"), _money(stats.get("fcf_ttm"))),
        ]) + "</div>",
        "",
        t(lang, "f_snapshot_note").format(period=stats["last_period"],
                                          form=stats["last_form"]),
        "",
        chart(series="revenue,revenue_yoy", kind="bars+line",
              title=t(lang, "f_revenue"), color="green,blue",
              labels=f"{t(lang, 'f_revenue')},{t(lang, 'f_yoy')}",
              fmt="money", unit="", fmt2="percent",
              note=t(lang, "f_revenue_note"), ylabel=t(lang, "ax_usd"),
              ylabel2=t(lang, "ax_growth"), xlabel=t(lang, "ax_quarter")),
        "",
        chart(series="margin_gross,margin_operating,margin_net", kind="multiline",
              title=t(lang, "f_margins"), color="blue,amber,green",
              labels=f"{t(lang, 'f_gross_margin')},"
                     f"{t(lang, 'f_operating_margin')},{t(lang, 'f_net_margin')}",
              note=t(lang, "f_margins_note"), ylabel=t(lang, "ax_pct"),
              xlabel=t(lang, "ax_quarter")),
        "",
        chart(series="pe", kind="area", title=t(lang, "f_pe"),
              color="blue", unit="×", note=t(lang, "f_pe_note"),
              ylabel=t(lang, "ax_multiple"), xlabel=t(lang, "ax_quarter")),
        "",
        f"[:material-finance: {t(lang, 'f_see_all')}]"
        f"(../../{MD_DIR}/{ticker}/index.md){{.report-link}}",
        "",
    ]
    return "\n".join(out)


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
    for sub in ["reports", "data", "prices", "fundamentals", "market_news",
                "notebooks", "sec", "investor_day"]:
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
    # Computed once: build_market_data() publishes exactly these, and each
    # ticker page links across to its own only if it is among them — a sample
    # build publishes a few tickers and --strict would reject a dangling link.
    priced_keys = set(published_price_keys())
    fundamental_link_keys = set(published_fundamental_keys())

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
        technical_md, fundamental_md, other_md = split_by_type(md_files)
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

        # Generate per-ticker index.md. How many of each report type exist —
        # shown as a hero chip here and as a cell on the top-level index below.
        counts = [c for c in [
            f"📊 {len(fundamental_md)}" if fundamental_md else "",
            f"📈 {len(technical_md)}" if technical_md else "",
            f"🗂️ {len(other_md)}" if other_md else "",
            f"🌐 {len(html_files)}" if html_files else "",
        ] if c]
        lines = [
            # No flag in the h1: extra.css paints h1 text through a clipped
            # gradient, which a twemoji SVG ignores in favour of its own fill —
            # so "✈️" rendered as a black plane on the dark scheme's near-black
            # background. The hero carries it instead, on a card, at icon size.
            f"# {meta['name']} ({ticker.upper()})",
            "",
            ticker_hero_block(ticker, meta, counts, lang),
            "",
        ]
        # TradingView-style candlestick chart (30D/180D/360D) as the page hero.
        chart = kline_block(ticker)
        if chart:
            lines += [chart, ""]
            # The hero chart only shows the last ~18 months; point readers at the
            # Market Data page for the full store, the derived charts and the
            # CSVs. Guarded on the page actually existing — a sample build
            # publishes only a few tickers and --strict would reject a dangling
            # link.
            if ticker in priced_keys:
                lines += [f"[:material-chart-line: {t(lang, 'md_more')}]"
                          f"(../../{MD_DIR}/{ticker}/index.md){{.report-link}}", ""]
        # Price-target & implied-return table directly under the chart, sourced
        # from the latest fundamental report's scenario targets.
        target_tbl = target_price_block(
            ticker, fundamental_md[0] if fundamental_md else None, lang
        )
        if target_tbl:
            lines += [target_tbl]

        # Reported fundamentals: a trailing-twelve-month line and the three
        # charts worth reading at a glance, with the other thirteen one click
        # away. Guarded on the section having published a page for this ticker,
        # since the block links to it and --strict rejects a dangling link.
        if ticker in fundamental_link_keys:
            snapshot = fundamentals_snapshot_block(ticker, lang)
            if snapshot:
                lines += [snapshot]
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

        # Row for top-level index table — the same per-type counts the hero
        # chip carries, spaced for a table cell instead of a chip.
        badges = " &nbsp; ".join(counts)
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

        technical_md, fundamental_md, other_md = split_by_type(md_files)
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
            "# Reports here are auto-refreshed monthly from SEC EDGAR via GitHub Actions.",
            "# To fetch manually — latest quarterly for a ticker; existing files are skipped:",
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
    """Published tickers whose Market Data page has a price half.

    Report pages consult this before linking across, so the sections can never
    disagree about which tickers have a page. The sampling lives in
    market_data_keys() so both halves of a sample build cover the same names.
    """
    return [k for k in market_data_keys() if store_bars(k)]


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


def analytics_payload_dict(key: str, bars: "list[dict]") -> dict:
    """Pre-computed series for price-charts.js, plus the summary as metadata.

    The browser does no maths: it fetches this and draws. Keeping the
    computation in Python is what lets pytest assert on the numbers the site
    actually shows — and lets the page builder read the same series back, so a
    chart's average line is the average of the points it is drawn over.
    """
    return {
        "ticker": key.upper(),
        "updated": bars[-1]["date"],
        "summary": price_analytics.summary(bars),
        "drawdown": price_analytics.drawdown_series(bars),
        "volatility": price_analytics.volatility_series(bars),
        "histogram": price_analytics.return_histogram(bars),
    }


def analytics_payload(key: str, bars: "list[dict]") -> str:
    return json.dumps(analytics_payload_dict(key, bars), separators=(",", ":"))


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


def _pct_plain(v: "float | None", digits: int = 2) -> str:
    """An unsigned percentage. The suffix lives inside the helper so a missing
    value renders as '—' rather than '—%'."""
    return "—" if v is None else f"{v:,.{digits}f}%"


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
                 color: str = "blue", unit: str = "%",
                 labels: str = "", fmt: str = "", fmt2: str = "",
                 unit2: str = "", note: str = "", ylabel: str = "",
                 ylabel2: str = "", xlabel: str = "",
                 ref: "float | None" = None, ref_label: str = "") -> str:
    """Raw-HTML div for one derived-analytics chart (see price-charts.js).

    ``series``, ``color`` and ``labels`` may each be a comma-separated list to
    draw several series on one chart. The optional attributes are emitted only
    when set, so a single-series widget renders the same markup it always has.

    ``note`` is the one line saying what the chart means, and ``ylabel`` /
    ``ylabel2`` / ``xlabel`` name the axes: Lightweight Charts prints axis
    *values* but has no concept of an axis title, and a P/E river with neither
    is only readable by someone who already knows what a P/E band is.

    ``ref`` draws a dashed horizontal reference line — a historical average,
    say. The value is computed here rather than in the browser, for the same
    reason every other number is.
    """
    attrs = [f'data-src="{src}"', f'data-series="{series}"',
             f'data-kind="{kind}"', f'data-title="{title}"',
             f'data-color="{color}"', f'data-unit="{unit}"']
    for name, value in (("data-labels", labels), ("data-format", fmt),
                        ("data-format2", fmt2), ("data-unit2", unit2),
                        ("data-note", note), ("data-ylabel", ylabel),
                        ("data-ylabel2", ylabel2), ("data-xlabel", xlabel),
                        ("data-ref", "" if ref is None else f"{ref:g}"),
                        ("data-ref-label", ref_label)):
        if value != "":
            attrs.append(f'{name}="{value}"')
    return f'<div class="pchart" {" ".join(attrs)}></div>'


def _store_zip_bytes(price_keys_: "list[str]",
                     fundamental_keys_: "list[str]") -> bytes:
    """Every published CSV, both stores, in one deterministic archive.

    Members are namespaced prices/ and fundamentals/ because a ticker has a CSV
    in each and they are different tables.

    Fixed timestamps (and sorted members) so re-running the build produces
    byte-identical output — otherwise the incremental check would rewrite a
    multi-megabyte file on every run.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for folder, root, keys in (("prices", PRICES_DIR, price_keys_),
                                   ("fundamentals", FUNDAMENTALS_DIR,
                                    fundamental_keys_)):
            for key in keys:
                src = root / f"{key}.csv"
                if not src.exists():
                    continue
                info = zipfile.ZipInfo(f"{folder}/{key}.csv",
                                       date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, src.read_bytes())
    return buf.getvalue()


# ── 7b. Financials ───────────────────────────────────────────────────────────
# Mirrors the Price Data section exactly: a store under data/, an overview page,
# a page per ticker, and a JSON payload the charts fetch. Every number comes
# from scripts/analysis/data/fundamental_analytics.py, so the page and the
# download can never disagree and the arithmetic is covered by
# tests/test_fundamental_analytics.py.
def fundamental_keys() -> "list[str]":
    if not FUNDAMENTALS_DIR.exists():
        return []
    return sorted(p.stem for p in FUNDAMENTALS_DIR.glob("*.csv"))


def published_fundamental_keys() -> "list[str]":
    """Published tickers whose Market Data page has a financials half.

    Report pages consult this before linking across; the sampling lives in
    market_data_keys() so a sample build covers the same names throughout.
    """
    return [k for k in market_data_keys() if fundamental_rows(k)]


_FUND_ROWS_CACHE: "dict[str, list[dict]]" = {}


def fundamental_rows(key: str) -> "list[dict]":
    """Parsed store rows for one ticker, read at most once per build."""
    if key not in _FUND_ROWS_CACHE:
        _FUND_ROWS_CACHE[key] = fundamentals.load_store(key, FUNDAMENTALS_DIR)
    return _FUND_ROWS_CACHE[key]


def _series(rows: "list[dict]", metric: str) -> "list[dict]":
    """A metric as {t, v} points, skipping periods the filer does not tag."""
    return [{"t": r["period_end"], "v": r[metric]}
            for r in rows if r.get(metric) is not None]


def _derived_series(rows: "list[dict]", fn, key: str) -> "list[dict]":
    """A computed ratio as {t, v} points, over whichever periods yield one."""
    out = []
    for r in rows:
        v = fn(r).get(key)
        if v is not None:
            out.append({"t": r["period_end"], "v": round(v, 2)})
    return out


def fundamentals_payload_dict(key: str, rows: "list[dict]",
                              bars: "list[dict]") -> dict:
    """Every series the financial charts draw, in one payload.

    Returned as a dict so the page builder can read the same series back — the
    dashed average on a P/E chart is the average of exactly the points drawn.

    Ratios are computed on trailing-twelve-month figures rather than on single
    quarters: a margin is meaningful either way, but a P/E built on one
    quarter's earnings would be four times too high, and a seasonal business's
    quarterly margin swings would drown the trend.
    """
    ttm = fundamental_analytics.ttm_series(rows)
    valuation = fundamental_analytics.valuation_series(rows, bars)

    payload = {
        "ticker": key.upper(),
        "updated": TODAY,
        "summary": fundamental_analytics.summary(rows, bars),
    }

    # Reported figures, per quarter, straight out of the store.
    for metric in ("revenue", "gross_profit", "operating_income", "net_income",
                   "eps_basic", "eps_diluted", "ocf", "capex",
                   "rnd_expense", "sga_expense"):
        payload[metric] = _series(rows, metric)

    # Growth, against the same quarter a year earlier.
    for metric in ("revenue", "operating_income", "net_income",
                   "eps_basic", "eps_diluted"):
        payload[f"{metric}_yoy"] = fundamental_analytics.yoy_growth(rows, metric)

    # Operating expenses stack, so the outer series carries the cumulative
    # total: Lightweight Charts has no stacking and the JS draws largest first.
    stacked_total, rnd_only = [], []
    for r in rows:
        rnd, sga = r.get("rnd_expense"), r.get("sga_expense")
        if rnd is None and sga is None:
            continue
        stacked_total.append({"t": r["period_end"], "v": (rnd or 0) + (sga or 0)})
        if rnd is not None:
            rnd_only.append({"t": r["period_end"], "v": rnd})
    payload["opex_total"] = stacked_total
    payload["opex_rnd"] = rnd_only

    payload["fcf"] = [{"t": r["period_end"], "v": v} for r in rows
                      if (v := fundamental_analytics.free_cash_flow(r)) is not None]
    payload["cash"] = [
        {"t": r["period_end"],
         "v": (r.get("cash_and_equiv") or 0) + (r.get("short_term_investments") or 0)}
        for r in rows if r.get("cash_and_equiv") is not None
    ]
    payload["debt"] = [{"t": r["period_end"], "v": v} for r in rows
                       if (v := fundamental_analytics.total_debt(r)) is not None]

    # Ratios, on TTM figures.
    for name, key_ in (("margin_gross", "gross"), ("margin_operating", "operating"),
                       ("margin_net", "net")):
        payload[name] = _derived_series(ttm, fundamental_analytics.margins, key_)
    for name in ("roe", "roa", "roic", "ros"):
        payload[name] = _derived_series(
            ttm, fundamental_analytics.returns_on_capital, name)

    payload.update(valuation)

    bands = fundamental_analytics.pe_bands(rows, bars)
    if bands:
        payload["pe_price"] = bands["price"]
        for i, level in enumerate(bands["levels"]):
            payload[f"pe_band_{i}"] = bands["bands"][str(level)]
        payload["pe_levels"] = bands["levels"]

    return payload


def fundamentals_payload(key: str, rows: "list[dict]", bars: "list[dict]") -> str:
    return json.dumps(fundamentals_payload_dict(key, rows, bars),
                      separators=(",", ":"), default=float)


def _money(v: "float | None") -> str:
    """A financial figure as $1.23B. The unit lives in the helper so a missing
    value renders as '—' rather than '$—'."""
    if v is None:
        return "—"
    sign = "-" if v < 0 else ""
    a = abs(v)
    for unit, size in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if a >= size:
            return f"{sign}${a / size:.2f}{unit}"
    return f"{sign}${a:,.2f}"


def _mult(v: "float | None") -> str:
    return "—" if v is None else f"{v:,.1f}×"


# ── 6b. docs/data → the merged Market Data section ───────────────────────────
# Price Data and Financials used to be two sections describing the same company
# from two angles: two nav tabs, two overview tables, two pages per ticker, and
# a cross-link between them that readers had to bounce along. They are one
# section now — one page per ticker, tabbed, reading from both committed stores.
#
# The old URLs still resolve: build_legacy_redirects() leaves a stub at each of
# /prices/<ticker>/ and /fundamentals/<ticker>/ pointing at the merged page.
#
# Every number is still derived at build time by price_analytics.py and
# fundamental_analytics.py, so the page and the downloads can never disagree,
# and the arithmetic stays covered by tests/test_price_analytics.py and
# tests/test_fundamental_analytics.py.

MD_DIR = "data"          # docs/<MD_DIR>/ — the merged section's directory
LEGACY_DIRS = ("prices", "fundamentals")


def market_data_keys() -> "list[str]":
    """Every ticker the merged section publishes: one with a usable price store,
    a usable fundamentals store, or both.

    Sampling happens here and nowhere else, so a sample build covers the same
    names in both halves of a page. Drawing the price and fundamentals samples
    separately — which is what the two sections used to do — could pick two
    different sets of tickers and leave a page half-built.

    Stores that parse to nothing are dropped: a ticker added to data/prices/
    before the first update_prices.py run leaves a header-only CSV behind, and
    listing it would publish a page with no chart on it.
    """
    keys = sorted({k for k in price_keys() if store_bars(k)}
                  | {k for k in fundamental_keys() if fundamental_rows(k)})
    return [p.name for p in _sample_dirs([Path(k) for k in keys])]


def _tab(title: str, body: "list[str]") -> "list[str]":
    """One Material content tab (pymdownx.tabbed, alternate_style).

    Body lines are indented four spaces to become the tab's content; blank lines
    are left genuinely blank, because an indented blank line inside a tab reads
    as a code block to Python-Markdown.
    """
    out = [f'=== "{title}"', ""]
    out += [("    " + line) if line.strip() else "" for line in body]
    out.append("")
    return out


def glossary_block(lang: str) -> "list[str]":
    """The 'what does P/E even mean' table, as a collapsed details block.

    Every chart card carries its own one-line explainer; this is the same
    material gathered in one place for a reader who wants the whole vocabulary
    rather than the one term in front of them.
    """
    rows = (LANG_TEXT.get(lang, LANG_TEXT["en"]).get("g_rows")
            or LANG_TEXT["en"]["g_rows"])
    out = [f'??? info "{t(lang, "g_title")}"',
           "",
           f"    {t(lang, 'g_intro')}",
           "",
           f"    | {t(lang, 'g_term')} | {t(lang, 'g_means')} |",
           "    |---|---|"]
    out += [f"    | **{term}** | {desc} |" for term, desc in rows]
    out.append("")
    return out


def _avg(points: "list[dict] | None") -> "float | None":
    """The dashed reference line a valuation chart draws against itself."""
    return price_analytics.series_average(points or [])


def _disclaimer_block(lang: str, key: str) -> "list[str]":
    return [f'!!! warning "{t(lang, "disclaimer")}"', "", f"    {t(lang, key)}", ""]


# ── the five tabs ────────────────────────────────────────────────────────────
def _overview_tab(key: str, stats: "dict | None", fstats: "dict | None",
                  lang: str) -> "list[str]":
    """Candles, headline returns and the trailing-twelve-month figures — what a
    reader wants before deciding which of the other tabs to open."""
    body: "list[str]" = []
    chart = kline_block(key, src="prices.json", ma=PRICE_PAGE_MA,
                        ranges=PRICE_PAGE_RANGES)
    if chart:
        body += [chart, ""]

    if stats:
        ret = stats["returns"]
        body += [
            f"### {t(lang, 'p_returns')}",
            "",
            "| 1D | 1W | 1M | 3M | 6M | YTD | 1Y | 3Y | 5Y |",
            "|---|---|---|---|---|---|---|---|---|",
            "| " + " | ".join([
                _pct_cell(ret["1d"]), _pct_cell(ret["1w"]), _pct_cell(ret["1m"]),
                _pct_cell(ret["3m"]), _pct_cell(ret["6m"]), _pct_cell(stats["ytd"]),
                _pct_cell(ret["1y"]), _pct_cell(ret["3y"]), _pct_cell(ret["5y"]),
            ]) + " |",
            "",
            f"### {t(lang, 'p_key_stats')}",
            "",
            f"| {t(lang, 'p_metric')} | {t(lang, 'p_value')} |",
            "|---|---|",
            f"| {t(lang, 'p_last_close')} | **{_num(stats['last_close'])}** "
            f"({stats['last_date']}) |",
            f"| {t(lang, 'p_52w_high')} | {_num(stats['high_52w'])} |",
            f"| {t(lang, 'p_52w_low')} | {_num(stats['low_52w'])} |",
            f"| {t(lang, 'p_from_high')} | {_pct_cell(stats['from_52w_high'])} |",
            f"| {t(lang, 'p_range_pos')} | {_pct_plain(stats['range_position'], 0)} |",
            f"| {t(lang, 'p_ath')} | {_num(stats['all_time_high'])} |",
            f"| {t(lang, 'p_max_dd')} | {_pct_cell(stats['max_drawdown'])} "
            f"({stats['max_drawdown_date']}) |",
            f"| {t(lang, 'p_vol_1y')} | {_pct_plain(stats['volatility_1y'])} |",
            f"| {t(lang, 'p_cagr')} | {_pct_cell(stats['cagr'])} |",
            f"| {t(lang, 'p_avg_vol')} | {_compact_volume(stats['avg_volume_30d'])} |",
            "",
        ]

    if fstats:
        margins = fstats.get("margins_ttm") or {}
        returns = fstats.get("returns_ttm") or {}
        mult = fstats.get("multiples_ttm") or {}
        body += [
            f"### {t(lang, 'f_key_figures')}",
            "",
            f"| {t(lang, 'p_metric')} | {t(lang, 'f_latest_quarter')} "
            f"| {t(lang, 'f_ttm')} |",
            "|---|---|---|",
            f"| {t(lang, 'f_revenue')} | {_money(fstats.get('revenue_q'))} "
            f"| **{_money(fstats.get('revenue_ttm'))}** |",
            f"| {t(lang, 'f_net_income')} | {_money(fstats.get('net_income_q'))} "
            f"| {_money(fstats.get('net_income_ttm'))} |",
            f"| {t(lang, 'f_eps_diluted')} | — | {_num(fstats.get('eps_ttm'))} |",
            f"| {t(lang, 'f_fcf')} | — | {_money(fstats.get('fcf_ttm'))} |",
            f"| {t(lang, 'f_row_gross_margin')} | — "
            f"| {_pct_plain(margins.get('gross'))} |",
            f"| {t(lang, 'f_row_operating_margin')} | — "
            f"| {_pct_plain(margins.get('operating'))} |",
            f"| {t(lang, 'f_row_net_margin')} | — "
            f"| {_pct_plain(margins.get('net'))} |",
            f"| ROE | — | {_pct_plain(returns.get('roe'))} |",
            f"| {t(lang, 'f_pe')} | — | {_mult(mult.get('pe'))} |",
            "",
            t(lang, "f_quarterly_note"),
            "",
        ]
    elif stats:
        body += [t(lang, "md_price_only"), ""]
    if not stats:
        body += [t(lang, "md_price_missing"), ""]

    return body


def _price_tab(bars: "list[dict]", analytics: dict, lang: str) -> "list[str]":
    """The three charts you cannot draw from candles alone, plus seasonality."""
    src = "analytics.json"
    body = [
        f"### {t(lang, 'p_drawdown')}",
        "",
        pchart_block(src=src, series="drawdown", kind="area",
                     title=t(lang, "p_drawdown"), color="red",
                     note=t(lang, "p_drawdown_note"),
                     ylabel=t(lang, "ax_drawdown"), xlabel=t(lang, "ax_session")),
        "",
        f"### {t(lang, 'p_volatility')}",
        "",
        pchart_block(src=src, series="volatility", kind="line",
                     title=t(lang, "p_volatility"), color="amber",
                     note=t(lang, "p_volatility_note").format(
                         window=price_analytics.VOL_WINDOW),
                     ylabel=t(lang, "ax_annualised"),
                     xlabel=t(lang, "ax_session"),
                     ref=_avg(analytics.get("volatility")),
                     ref_label=t(lang, "g_avg")),
        "",
        f"### {t(lang, 'p_distribution')}",
        "",
        pchart_block(src=src, series="histogram", kind="histogram",
                     title=t(lang, "p_distribution"), color="blue",
                     note=t(lang, "p_distribution_note"),
                     ylabel=t(lang, "ax_sessions"),
                     xlabel=t(lang, "ax_return_bucket")),
        "",
        f"### {t(lang, 'p_monthly')}",
        "",
        t(lang, "p_monthly_desc"),
        "",
    ]
    body += monthly_heatmap(bars, lang)
    return body


def _financials_tab(lang: str) -> "list[str]":
    """Statements and profitability. Every card names its axes and says in one
    line what it is showing, so the page reads without prior vocabulary."""
    src = "fundamentals.json"
    quarter, usd, pct = (t(lang, "ax_quarter"), t(lang, "ax_usd"),
                         t(lang, "ax_pct"))
    growth = t(lang, "ax_growth")

    def money_and_growth(series, title, note, colors):
        return pchart_block(
            src=src, series=series, kind="bars+line", title=title, color=colors,
            labels=f"{title},{t(lang, 'f_yoy')}", fmt="money", unit="",
            fmt2="percent", note=note, ylabel=usd, ylabel2=growth,
            xlabel=quarter)

    return [
        f"### {t(lang, 'f_statements')}",
        "",
        money_and_growth("revenue,revenue_yoy", t(lang, "f_revenue"),
                         t(lang, "f_revenue_note"), "green,blue"),
        "",
        money_and_growth("operating_income,operating_income_yoy",
                         t(lang, "f_operating_income"),
                         t(lang, "f_operating_income_note"), "amber,blue"),
        "",
        money_and_growth("net_income,net_income_yoy", t(lang, "f_net_income"),
                         t(lang, "f_net_income_note"), "blue,amber"),
        "",
        pchart_block(src=src, series="eps_diluted,eps_diluted_yoy",
                     kind="bars+line", title=t(lang, "f_eps_diluted"),
                     color="amber,blue",
                     labels=f"{t(lang, 'f_eps_diluted')},{t(lang, 'f_yoy')}",
                     fmt="plain", unit="", fmt2="percent",
                     note=t(lang, "f_eps_note"),
                     ylabel=t(lang, "ax_usd_share"), ylabel2=growth,
                     xlabel=quarter),
        "",
        # Smallest series first: the JS draws a stack largest-first so the
        # component paints over the cumulative total rather than under it.
        pchart_block(src=src, series="opex_rnd,opex_total", kind="stacked",
                     title=t(lang, "f_opex"), color="amber,blue",
                     labels=f"{t(lang, 'f_rnd')},{t(lang, 'f_opex')}",
                     fmt="money", unit="", note=t(lang, "f_opex_note"),
                     ylabel=usd, xlabel=quarter),
        "",
        pchart_block(src=src, series="ocf,fcf", kind="multiline",
                     title=t(lang, "f_cash_flow"), color="green,blue",
                     labels=f"{t(lang, 'f_ocf')},{t(lang, 'f_fcf')}",
                     fmt="money", unit="", note=t(lang, "f_cash_flow_note"),
                     ylabel=usd, xlabel=quarter),
        "",
        pchart_block(src=src, series="cash,debt", kind="multiline",
                     title=t(lang, "f_cash_debt"), color="blue,red",
                     labels=f"{t(lang, 'f_cash')},{t(lang, 'f_debt')}",
                     fmt="money", unit="", note=t(lang, "f_cash_debt_note"),
                     ylabel=usd, xlabel=quarter),
        "",
        f"### {t(lang, 'f_profitability')}",
        "",
        pchart_block(src=src, series="margin_gross,margin_operating,margin_net",
                     kind="multiline", title=t(lang, "f_margins"),
                     color="blue,amber,green",
                     labels=f"{t(lang, 'f_gross_margin')},"
                            f"{t(lang, 'f_operating_margin')},"
                            f"{t(lang, 'f_net_margin')}",
                     note=t(lang, "f_margins_note"), ylabel=pct,
                     xlabel=quarter),
        "",
        pchart_block(src=src, series="roe,roa,roic", kind="multiline",
                     title=t(lang, "f_returns"), color="blue,amber,green",
                     labels="ROE,ROA,ROIC", note=t(lang, "f_returns_note"),
                     ylabel=t(lang, "ax_pct_plain"), xlabel=quarter),
        "",
        pchart_block(src=src, series="ros", kind="area", title=t(lang, "f_ros"),
                     color="green", note=t(lang, "f_ros_note"),
                     ylabel=pct, xlabel=quarter),
        "",
    ]


def _valuation_tab(payload: dict, lang: str) -> "list[str]":
    """The multiples, each drawn against its own historical average.

    A P/E of 32x reads differently against a 26x ten-year average than against a
    40x one, so every multiple carries that average as a dashed line. The number
    is computed in Python (price_analytics.series_average) like everything else.
    """
    src = "fundamentals.json"
    quarter = t(lang, "ax_quarter")
    mult_axis = t(lang, "ax_multiple")
    avg = t(lang, "g_avg")

    def multiple(series, title, note, color):
        return pchart_block(src=src, series=series, kind="area", title=title,
                            color=color, unit="×", note=note,
                            ylabel=mult_axis, xlabel=quarter,
                            ref=_avg(payload.get(series)), ref_label=avg)

    body = [
        f"### {t(lang, 'f_valuation')}",
        "",
        multiple("pe", t(lang, "f_pe"), t(lang, "f_pe_note"), "blue"),
        "",
        multiple("ps", t(lang, "f_ps"), t(lang, "f_ps_note"), "green"),
        "",
        multiple("pb", t(lang, "f_pb"), t(lang, "f_pb_note"), "amber"),
        "",
        multiple("ev_sales", t(lang, "f_ev_sales"),
                 t(lang, "f_ev_sales_note"), "blue"),
        "",
        multiple("ev_ebitda", t(lang, "f_ev_ebitda"),
                 t(lang, "f_ev_ebitda_note"), "amber"),
        "",
    ]

    # The P/E river only exists for a ticker with enough positive-earnings
    # history to rank, so it is emitted conditionally rather than as an empty box.
    levels = payload.get("pe_levels") or []
    if levels:
        names = ["pe_price"] + [f"pe_band_{i}" for i in range(len(levels))]
        band_labels = [t(lang, "f_price")] + [f"{lv:g}×" for lv in levels]
        colours = ["blue"] + ["green", "teal", "amber", "violet",
                              "red"][:len(levels)]
        body += [
            f"### {t(lang, 'f_pe_bands')}",
            "",
            pchart_block(src=src, series=",".join(names), kind="multiline",
                         title=t(lang, "f_pe_bands"), color=",".join(colours),
                         labels=",".join(band_labels), fmt="money", unit="",
                         note=t(lang, "f_pe_bands_note"),
                         ylabel=t(lang, "ax_usd"), xlabel=t(lang, "ax_month")),
            "",
        ]
    return body


def _data_tab(key: str, stats: "dict | None", fstats: "dict | None",
              price_csv_href: str, fund_csv_href: str, lang: str) -> "list[str]":
    """Downloads for both stores, the glossary, and the disclaimers.

    The two CSVs carry an explicit `download` attribute; the JSON payloads do
    not. Both are served fine — the CSV URL returns 200 text/csv — but what a
    browser *does* with that response is content-type roulette: JSON renders in
    the built-in viewer, while `text/csv` navigates away from the page and
    silently drops a file in the downloads folder, which reads as a dead link.
    `download` makes the click unambiguously a save, under the store's own
    filename rather than whatever the URL's last segment happens to be.
    """
    body = [f"### {t(lang, 'p_download')}", ""]
    if stats:
        body += [
            f"- :material-file-delimited: [**{key}.csv**]({price_csv_href})"
            f'{{download="{key}.csv"}} — '
            f"{t(lang, 'p_csv_desc').format(n=stats['bars'])}",
            "- :material-code-json: [`prices.json`](prices.json) — "
            f"{t(lang, 'p_prices_json_desc')}",
            "- :material-code-json: [`analytics.json`](analytics.json) — "
            f"{t(lang, 'p_analytics_json_desc')}",
        ]
    if fstats:
        body += [
            f"- :material-file-delimited: [**{key}_financials.csv**]"
            f"({fund_csv_href})"
            f'{{download="{key}_financials.csv"}} — '
            f"{t(lang, 'f_csv_desc').format(n=fstats['periods'])}",
            f"- :material-code-json: [`fundamentals.json`](fundamentals.json) — "
            f"{t(lang, 'f_json_desc')}",
        ]
    body.append("")
    body += glossary_block(lang)
    body += _disclaimer_block(lang, "p_disclaimer")
    if fstats:
        body += _disclaimer_block(lang, "f_disclaimer")
    return body


def market_data_ticker_page(key: str, meta: dict, stats: "dict | None",
                            fstats: "dict | None", bars: "list[dict]",
                            analytics: dict, payload: dict,
                            price_csv_href: str, fund_csv_href: str,
                            lang: str) -> "list[str]":
    """One ticker's Market Data page: price and fundamentals, five tabs.

    Twenty-odd charts on one page would be a wall if they were stacked; tabs let
    a reader take the half they came for. price-charts.js builds each chart as
    it scrolls into view, so the collapsed tabs cost nothing until opened.
    """
    # get_meta falls back to the bare ticker for names it doesn't carry; without
    # this the heading would read "SKHY (SKHY)".
    title = (key.upper() if meta["name"] == key.upper()
             else f"{meta['name']} ({key.upper()})")

    facts = [f"**{t(lang, 'sector')}:** {meta['sector']}"]
    if stats:
        facts.append(f"**{t(lang, 'p_bars')}:** {stats['bars']:,} "
                     f"({stats['first_date']} → {stats['last_date']})")
    if fstats:
        facts.append(f"**{t(lang, 'f_periods')}:** {fstats['periods']} "
                     f"({fstats['first_period']} → {fstats['last_period']})")
        facts.append(f"**{t(lang, 'f_source_filing')}:** {fstats['last_form']} "
                     f"({t(lang, 'f_filed')} {fstats['last_filed']})")

    tabs: "list[tuple[str, list[str]]]" = [
        (t(lang, "md_tab_overview"), _overview_tab(key, stats, fstats, lang)),
    ]
    if stats:
        tabs.append((t(lang, "md_tab_price"),
                     _price_tab(bars, analytics, lang)))
    if fstats:
        tabs.append((t(lang, "md_tab_financials"), _financials_tab(lang)))
        # Every multiple needs a share price, so the valuation tab is only
        # meaningful when both stores are present.
        if stats:
            tabs.append((t(lang, "md_tab_valuation"),
                         _valuation_tab(payload, lang)))
    tabs.append((t(lang, "md_tab_data"),
                 _data_tab(key, stats, fstats, price_csv_href,
                           fund_csv_href, lang)))

    lines = [
        f"# {meta['flag']} {title} — {t(lang, 'md')}",
        "",
        "> " + "  |  ".join(facts),
        "",
        # A label for the tab bar, and the hook prices.css hangs the segmented
        # styling off: it is scoped to `.tabcue + .tabbed-set`, so the site's
        # other content tabs keep the theme's own look. It has to be the tab
        # set's immediately-preceding sibling, hence no blank-line-separated
        # prose between the two.
        f'<div class="tabcue">{t(lang, "md_tabs_hint").format(n=len(tabs))}</div>',
    ]
    for tab_title, body in tabs:
        lines += _tab(tab_title, body)

    lines += [f"[{t(lang, 'md_back_to_index')}](../index.md)", ""]
    return lines


def market_data_index_page(rows: "list[str]", count: int, download_base: str,
                           lang: str) -> "list[str]":
    """The Market Data landing page: what the datasets are, how to get them, and
    one row per ticker carrying both a price and a fundamentals read."""
    zip_href = f"{download_base}market_data.zip" if download_base else "market_data.zip"
    json_href = f"{download_base}index.json" if download_base else "index.json"
    return [
        f"# 💹 {t(lang, 'md')}",
        "",
        f"> {t(lang, 'md_desc').format(n=count)}  "
        f"|  **{t(lang, 'last_updated')}:** {TODAY}",
        "",
        t(lang, "md_intro"),
        "",
        f"!!! info \"{t(lang, 'f_coverage')}\"",
        "",
        f"    {t(lang, 'f_coverage_desc')}",
        "",
        f"## {t(lang, 'p_download')}",
        "",
        f"- :material-folder-zip: [**{t(lang, 'md_zip')}**]({zip_href})"
        f'{{download="market_data.zip"}} — '
        f"{t(lang, 'md_zip_desc').format(n=count)}",
        f"- :material-code-json: [**`index.json`**]({json_href}) — "
        f"{t(lang, 'md_manifest_desc')}",
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
        f'url = "https://yennanliu.github.io{SITE_BASE}/{MD_DIR}/nvda/nvda.csv"',
        'df = pd.read_csv(url, parse_dates=["date"]).set_index("date")',
        'df["close"].pct_change().std() * (252 ** 0.5)  # annualised volatility',
        "```",
        "",
        f"## {t(lang, 'p_coverage')}",
        "",
        '<div class="ptable" markdown="1">',
        "",
        f"| {t(lang, 'ticker')} | {t(lang, 'company')} | {t(lang, 'p_last')} "
        f"| 1M | YTD | 1Y | {t(lang, 'p_52w_range')} "
        f"| {t(lang, 'f_revenue')} ({t(lang, 'f_ttm')}) | {t(lang, 'f_yoy')} "
        f"| {t(lang, 'f_row_net_margin')} | ROE | {t(lang, 'f_pe')} "
        f"| {t(lang, 'files')} |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        *rows,
        "",
        "</div>",
        "",
        *glossary_block(lang),
        f"!!! warning \"{t(lang, 'disclaimer')}\"",
        "",
        f"    {t(lang, 'p_disclaimer')}",
        "",
        f"    {t(lang, 'f_disclaimer')}",
        "",
    ]


def build_market_data(lang: str = "en"):
    docs_root = get_docs_root(lang)
    DST = docs_root / MD_DIR
    ensure(DST)

    keys = market_data_keys()
    if not keys:
        write(DST / "index.md",
              f"# {t(lang, 'md')}\n\n{t(lang, 'md_no_data')}\n")
        return

    # Downloads are language-neutral: written once into the EN tree, linked
    # absolutely from ZH — the same rule the ZH report index already follows.
    download_base = "" if lang == "en" else f"{SITE_BASE}/{MD_DIR}/"

    index_rows: "list[str]" = []
    manifest: "list[dict]" = []
    zipped_price: "list[str]" = []
    zipped_fund: "list[str]" = []

    for key in keys:
        bars = store_bars(key)
        rows = fundamental_rows(key)
        stats = price_analytics.summary(bars) if bars else None
        fstats = fundamental_analytics.summary(rows, bars) if rows else None
        if not stats and not fstats:
            continue

        meta = get_meta(key)
        dst_dir = DST / key
        ensure(dst_dir)

        # Chart payloads are written into *both* language trees so the pages
        # work under `mkdocs serve` in either tree; only the bulky raw CSVs are
        # shared, and live in the EN tree.
        analytics: dict = {}
        payload: dict = {}
        price_csv = f"{key}.csv"
        fund_csv = f"{key}_financials.csv"

        if stats:
            analytics = analytics_payload_dict(key, bars)
            write(dst_dir / "prices.json", full_price_payload(key, bars))
            write(dst_dir / "analytics.json",
                  json.dumps(analytics, separators=(",", ":")))
            if lang == "en":
                copy_file(PRICES_DIR / price_csv, dst_dir / price_csv)
            zipped_price.append(key)

        if fstats:
            payload = fundamentals_payload_dict(key, rows, bars)
            write(dst_dir / "fundamentals.json",
                  json.dumps(payload, separators=(",", ":"), default=float))
            if lang == "en":
                # Renamed on the way in: two CSVs sit side by side in this
                # directory now, and "<ticker>.csv" is the price one.
                copy_file(FUNDAMENTALS_DIR / f"{key}.csv", dst_dir / fund_csv)
            zipped_fund.append(key)

        # Two links to the same file: the ticker page sits next to it, the index
        # one level up. ZH gets the absolute EN path in both cases.
        def href(name: str) -> str:
            return f"{download_base}{key}/{name}" if download_base else name

        def href_index(name: str) -> str:
            return (f"{download_base}{key}/{name}" if download_base
                    else f"{key}/{name}")

        write(dst_dir / "index.md", "\n".join(market_data_ticker_page(
            key, meta, stats, fstats, bars, analytics, payload,
            href(price_csv), href(fund_csv), lang)))

        ret = (stats or {}).get("returns") or {}
        margins = (fstats or {}).get("margins_ttm") or {}
        returns = (fstats or {}).get("returns_ttm") or {}
        multiples = (fstats or {}).get("multiples_ttm") or {}
        files = []
        if stats:
            # Same `download` reasoning as _data_tab(): these are files, and a
            # table cell is the last place a reader wants a navigation that
            # silently turns into one.
            files.append(f"[{t(lang, 'md_file_prices')}]"
                         f"({href_index(price_csv)})"
                         f'{{download="{price_csv}"}}')
        if fstats:
            files.append(f"[{t(lang, 'md_file_financials')}]"
                         f"({href_index(fund_csv)})"
                         f'{{download="{fund_csv}"}}')
        index_rows.append(
            # Link the .md, not the directory: MkDocs resolves it to the
            # directory URL and --strict can verify the target exists.
            f"| {meta['flag']} [{key.upper()}]({key}/index.md) | {meta['name']} "
            f"| {_num((stats or {}).get('last_close'))} "
            f"| {_pct_cell(ret.get('1m'))} "
            f"| {_pct_cell((stats or {}).get('ytd'))} "
            f"| {_pct_cell(ret.get('1y'))} "
            f"| {_num((stats or {}).get('low_52w'))} – "
            f"{_num((stats or {}).get('high_52w'))} "
            f"| {_money((fstats or {}).get('revenue_ttm'))} "
            f"| {_pct_cell((fstats or {}).get('revenue_yoy'))} "
            f"| {_pct_plain(margins.get('net'))} "
            f"| {_pct_plain(returns.get('roe'))} "
            f"| {_mult(multiples.get('pe'))} "
            f"| {' · '.join(files) or '—'} |"
        )

        entry = {"ticker": key.upper(), "key": key,
                 "page": f"{SITE_BASE}/{MD_DIR}/{key}/"}
        if stats:
            entry.update({
                "csv": f"{SITE_BASE}/{MD_DIR}/{key}/{price_csv}",
                "prices_json": f"{SITE_BASE}/{MD_DIR}/{key}/prices.json",
                "analytics_json": f"{SITE_BASE}/{MD_DIR}/{key}/analytics.json",
                **stats})
        if fstats:
            entry.update({
                "fundamentals_csv": f"{SITE_BASE}/{MD_DIR}/{key}/{fund_csv}",
                "fundamentals_json":
                    f"{SITE_BASE}/{MD_DIR}/{key}/fundamentals.json",
                **fstats})
        manifest.append(entry)

    if lang == "en":
        # One-click bulk download, and a machine-readable manifest so the data is
        # usable from a script without scraping the page.
        write_bytes(DST / "market_data.zip",
                    _store_zip_bytes(zipped_price, zipped_fund))
        write(DST / "index.json",
              json.dumps({"updated": TODAY, "count": len(manifest),
                          "price_columns": list(prices.FIELDS),
                          "fundamentals_columns": list(fundamentals.FIELDS),
                          "tickers": manifest},
                         separators=(",", ":"), default=float))

    write(DST / "index.md",
          "\n".join(market_data_index_page(index_rows, len(manifest),
                                           download_base, lang)))


# ── 6c. redirects for the two sections this one replaced ─────────────────────
def build_legacy_redirects(lang: str = "en"):
    """Leave a stub at every /prices/<t>/ and /fundamentals/<t>/ URL.

    Those pages were linked from elsewhere on the web before the merge, so they
    keep resolving: a meta refresh for a browser, and a plain link for anything
    that does not follow one. `hide: true` keeps the stubs out of the nav — they
    are an obligation to old links, not a section.
    """
    docs_root = get_docs_root(lang)
    keys = market_data_keys()
    for legacy in LEGACY_DIRS:
        base = docs_root / legacy
        ensure(base)
        write(base / ".pages", "hide: true\nnav:\n  - index.md\n  - ...\n")
        write(base / "index.md",
              "\n".join(_redirect_page(t(lang, "md"), "../data/", lang)))
        for key in keys:
            ensure(base / key)
            write(base / key / ".pages", f'title: "{key.upper()}"\nhide: true\n')
            write(base / key / "index.md", "\n".join(
                _redirect_page(key.upper(), f"../../{MD_DIR}/{key}/", lang)))


def _redirect_page(label: str, target: str, lang: str) -> "list[str]":
    """A stub page: meta refresh, plus the link spelled out for anything that
    does not act on one (a crawler, a reader with JS off, a `curl`)."""
    return [
        "---",
        f"title: {label}",
        "search:",
        "  exclude: true",
        "---",
        "",
        f'<meta http-equiv="refresh" content="0; url={target}">',
        "",
        f"# {t(lang, 'md_moved')}",
        "",
        t(lang, "md_moved_body"),
        "",
        f"[:material-arrow-right: {t(lang, 'md_open')}]({target}index.md)"
        "{.report-link}",
        "",
    ]


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
    #
    # `zh` is listed on the EN root so the Traditional Chinese tree is part of
    # the nav at all. Without it awesome-pages drops docs/zh/ entirely (a `nav:`
    # with no `...` is exhaustive), every ZH page inherited the *English* tab
    # row, and the localised titles written below were never rendered — the ZH
    # Market Data pages existed but nothing on the site linked to them.
    # overrides/partials/tabs.html reads this subtree to build the ZH tab row.
    nav_sections = [
        "  - index.md",
        "  - reports",
        "  - data",
        "  - market_news",
        "  - notebooks",
        "  - sec",
        # Titled explicitly: the page body is English-only, so on the ZH tree
        # its H1 would otherwise put "Download Scripts" in the Chinese tab row.
        f"  - {t(lang, 'download_scripts')}: scripts.md",
    ]
    if lang == "en":
        nav_sections.append("  - zh")
    write(root_pages, "\n".join([
        # A translated tree is a nav section, and carries its own language as
        # the section title. On the EN root — which *is* the site root — a
        # `title:` would rename the whole site instead.
        *([f"title: {t(lang, 'lang_name')}"] if lang != "en" else []),
        "nav:",
        *nav_sections,
        "",
    ]))

    DST_REPORTS = docs_root / "reports"
    DST_MARKET_DATA = docs_root / MD_DIR
    DST_MARKET_NEWS = docs_root / "market_news"
    DST_NOTEBOOKS = docs_root / "notebooks"
    DST_SEC = docs_root / "sec"
    DST_INV_DAY = docs_root / "investor_day"

    # Titled, not just ordered: without a `title:` awesome-pages falls back to
    # the directory name and the tab reads "Sec" in both languages.
    for subdir, title_key in [(DST_SEC, "sec_filings"),
                              (DST_INV_DAY, "investor_day")]:
        if subdir.exists():
            pages_file = subdir / ".pages"
            write(pages_file,
                  f"title: {t(lang, title_key)}\nnav:\n  - index.md\n  - ...\n")

    # Market Data section: localised nav title, index first then the tickers.
    # The /prices/ and /fundamentals/ trees it replaced still exist as redirect
    # stubs; build_legacy_redirects() writes their .pages with `hide: true`, so
    # they stay out of the nav rather than doubling every ticker in it.
    if DST_MARKET_DATA.exists():
        write(DST_MARKET_DATA / ".pages",
              f"title: {t(lang, 'md')}\nnav:\n  - index.md\n  - ...\n")
        for ticker_dir in DST_MARKET_DATA.iterdir():
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
            for subdir in ["reports", "data", "prices", "fundamentals",
                           "market_news", "notebooks", "sec", "investor_day"]:
                path = lang_dir / subdir
                if path.exists():
                    shutil.rmtree(path)
                    print(f"  clean {path.relative_to(ROOT)}/")

    # Build English version
    print(f"\n{'─'*70}")
    print(" Building English version (docs/)")
    print(f"{'─'*70}")

    print("\n[EN 1/10] Building ai_gen_report/stock reports...")
    build_reports(lang="en")

    print("\n[EN 2/10] Building ai_gen_report/market_news...")
    build_market_news(lang="en")

    print("\n[EN 3/10] Building notebook_llm pages...")
    build_notebooks(lang="en")

    print("\n[EN 4/10] Building 10-K + 10-Q indices...")
    build_filing_index(lang="en", form="10k")
    build_filing_index(lang="en", form="10q")

    print("\n[EN 5/10] Building other SEC indices (13-F, 6-K)...")
    build_other_sec(lang="en")

    print("\n[EN 6/10] Building investor_day pages...")
    build_investor_day(lang="en")

    print("\n[EN 7/10] Building market data pages (prices + financials)...")
    build_market_data(lang="en")

    print("\n[EN 8/10] Writing redirects for the pre-merge URLs...")
    build_legacy_redirects(lang="en")

    print("\n[EN 9/10] Building scripts page...")
    build_scripts_page(lang="en")

    print("\n[EN 10/10] Writing .pages nav files & abbreviations...")
    build_nav_pages(lang="en")
    build_abbreviations(lang="en")

    # Build Traditional Chinese version
    print(f"\n{'─'*70}")
    print(" Building Traditional Chinese version (docs/zh/)")
    print(f"{'─'*70}")

    print("\n[ZH 1/10] Building ai_gen_report/stock reports...")
    build_reports(lang="zh")

    print("\n[ZH 2/10] Building ai_gen_report/market_news...")
    build_market_news(lang="zh")

    print("\n[ZH 3/10] Building notebook_llm pages...")
    build_notebooks(lang="zh")

    print("\n[ZH 4/10] Building 10-K + 10-Q indices...")
    build_filing_index(lang="zh", form="10k")
    build_filing_index(lang="zh", form="10q")

    print("\n[ZH 5/10] Building other SEC indices (13-F, 6-K)...")
    build_other_sec(lang="zh")

    print("\n[ZH 6/10] Building investor_day pages...")
    build_investor_day(lang="zh")

    print("\n[ZH 7/10] Building market data pages (prices + financials)...")
    build_market_data(lang="zh")

    print("\n[ZH 8/10] Writing redirects for the pre-merge URLs...")
    build_legacy_redirects(lang="zh")

    print("\n[ZH 9/10] Building scripts page...")
    build_scripts_page(lang="zh")

    print("\n[ZH 10/10] Writing .pages nav files & abbreviations...")
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
