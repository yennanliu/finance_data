#!/usr/bin/env python3
"""
build_docs.py — Finance Hub docs builder
=========================================
Generates the `docs/` directory content from source files:

  • claude_code/  → docs/reports/<ticker>/
  • notebook_llm/ → docs/notebooks/<ticker>/
  • 10-k/         → docs/sec/10k.md   (index only, PDFs not copied)
  • 10-q/         → docs/sec/10q.md
  • 13-f/         → docs/sec/13f.md
  • investor_day/ → docs/investor_day/
  • README.md     → enriches docs/index.md

Run locally:   python scripts/build_docs.py
Run in CI:     automatically called before `mkdocs build`
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).resolve().parent.parent
DOCS       = ROOT / "docs"
DOCS_ZH    = ROOT / "docs" / "zh"
SITE       = ROOT / "site"

SRC_CLAUDE   = ROOT / "claude_code"
SRC_NOTEBOOK = ROOT / "notebook_llm"
SRC_10K      = ROOT / "10-k"
SRC_10Q      = ROOT / "10-q"
SRC_13F      = ROOT / "13-f"
SRC_6K       = ROOT / "6-k"
SRC_INV_DAY  = ROOT / "investor_day"

TODAY = date.today().isoformat()

# ── Language-specific text ────────────────────────────────────────────────────
LANG_TEXT = {
    "en": {
        "last_updated": "Last updated",
        "last_built": "Last built",
        "sector": "Sector",
        "available_reports": "Available Reports",
        "markdown_reports": "📄 Markdown Reports",
        "html_reports": "🌐 Interactive HTML Reports",
        "analysis_reports": "Analysis Reports",
        "ai_generated": "AI-generated investment research reports",
        "disclaimer": "Disclaimer",
        "disclaimer_text": "All reports are for educational purposes only and do not constitute investment advice.",
        "report_index": "Report Index",
        "ticker": "Ticker",
        "company": "Company",
        "files": "Files",
        "reports": "Reports",
        "ai_notebooks": "AI Research Notebooks",
        "deep_dive": "Deep-dive analysis generated with Google NotebookLM",
        "research_docs": "📑 Research Documents",
        "notes_outlines": "📝 Notes & Outlines",
        "about_notebooklm": "About NotebookLM Reports",
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
        "markdown_reports": "📄 Markdown 報告",
        "html_reports": "🌐 互動式 HTML 報告",
        "analysis_reports": "分析報告",
        "ai_generated": "AI 生成的投資研究報告",
        "disclaimer": "免責聲明",
        "disclaimer_text": "所有報告僅供教育目的，不構成投資建議。",
        "report_index": "報告索引",
        "ticker": "股票代號",
        "company": "公司",
        "files": "檔案",
        "reports": "報告",
        "ai_notebooks": "AI 研究筆記",
        "deep_dive": "使用 Google NotebookLM 生成的深度分析",
        "research_docs": "📑 研究文件",
        "notes_outlines": "📝 筆記與大綱",
        "about_notebooklm": "關於 NotebookLM 報告",
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
}

def get_meta(ticker: str) -> dict:
    key = ticker.lower()
    return COMPANY_META.get(key, {
        "name": ticker.upper(),
        "flag": "📊",
        "sector": "Equity"
    })


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
    for sub in ["reports", "notebooks", "sec", "investor_day"]:
        target = path / sub
        if target.exists():
            shutil.rmtree(target)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "-", text.lower()).strip("-")


def copy_file(src: Path, dst: Path):
    ensure(dst.parent)
    shutil.copy2(src, dst)
    print(f"  copy  {src.relative_to(ROOT)}  →  {dst.relative_to(ROOT)}")


def write(path: Path, content: str):
    ensure(path.parent)
    path.write_text(content, encoding="utf-8")
    print(f"  write {path.relative_to(ROOT)}")


# ── 1. claude_code → docs/reports/ ───────────────────────────────────────────
def build_reports(lang: str = "en"):
    docs_root = get_docs_root(lang)
    DST_REPORTS = docs_root / "reports"
    ensure(DST_REPORTS)
    report_index_rows: list[str] = []
    nav_entries: list[str] = []

    if not SRC_CLAUDE.exists():
        write(DST_REPORTS / "index.md", f"# {t(lang, 'reports')}\n\nNo reports found.\n")
        return

    tickers = sorted([d for d in SRC_CLAUDE.iterdir() if d.is_dir()])

    for ticker_dir in tickers:
        ticker = ticker_dir.name.lower()
        meta = get_meta(ticker)
        dst_dir = DST_REPORTS / ticker
        ensure(dst_dir)

        # Collect files in this ticker directory
        files = sorted(ticker_dir.iterdir(), key=lambda f: f.name)
        md_files   = [f for f in files if f.suffix == ".md"]
        html_files = [f for f in files if f.suffix == ".html"]
        other_files = [f for f in files if f.suffix not in (".md", ".html", "") and f.is_file()]

        if not (md_files or html_files):
            continue  # skip empty dirs

        # Copy all md/html/other files
        for f in md_files + html_files + other_files:
            copy_file(f, dst_dir / f.name)

        # Generate per-ticker index.md
        lines = [
            f"# {meta['flag']} {meta['name']} ({ticker.upper()})",
            "",
            f"> **{t(lang, 'sector')}:** {meta['sector']}  |  **{t(lang, 'last_updated')}:** {TODAY}",
            "",
            "---",
            "",
            f"## {t(lang, 'available_reports')}",
            "",
        ]

        if md_files:
            lines.append(f"### {t(lang, 'markdown_reports')}")
            lines.append("")
            for f in md_files:
                label = f.stem.replace("_", " ").title()
                lines.append(f"- [{label}]({f.name})")
            lines.append("")

        if html_files:
            lines.append(f"### {t(lang, 'html_reports')}")
            lines.append("")
            for f in html_files:
                label = f.stem.replace("_", " ").title()
                lines.append(f"- [{label}]({f.name}){{target=_blank}}")
            lines.append("")

        write(dst_dir / "index.md", "\n".join(lines))

        # Row for top-level index table
        report_count = len(md_files) + len(html_files)
        report_list = ", ".join(
            [f"[{f.stem}]({ticker}/{f.name})" for f in md_files[:2]]
            + [f"[{f.stem} (HTML)]({ticker}/{f.name}){{target=_blank}}" for f in html_files[:1]]
        )
        report_index_rows.append(
            f"| {meta['flag']} [{ticker.upper()}](#{ticker}) "
            f"| {meta['name']} | {meta['sector']} "
            f"| {report_count} | {report_list} |"
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
        f"| | {t(lang, 'ticker')} | {t(lang, 'company')} | {t(lang, 'sector')} | {t(lang, 'files')} | {t(lang, 'reports')} |",
        "|---|--------|---------|--------|-------|---------|",
    ] + report_index_rows

    # Per-ticker detail sections
    for ticker_dir in tickers:
        ticker = ticker_dir.name.lower()
        meta = get_meta(ticker)
        files = sorted(ticker_dir.iterdir(), key=lambda f: f.name)
        md_files   = [f for f in files if f.suffix == ".md"]
        html_files = [f for f in files if f.suffix == ".html"]
        if not (md_files or html_files):
            continue

        top_lines += [
            "",
            f"---",
            "",
            f"## {meta['flag']} {ticker.upper()} — {meta['name']}",
            "",
            f"**{t(lang, 'sector')}:** {meta['sector']}",
            "",
        ]
        if md_files:
            top_lines.append(f"**{t(lang, 'markdown_reports')}:**")
            for f in md_files:
                label = f.stem.replace("_", " ").title()
                top_lines.append(f"- [{label}]({ticker}/{f.name})")
        if html_files:
            top_lines.append("")
            top_lines.append(f"**{t(lang, 'html_reports')}:**")
            for f in html_files:
                label = f.stem.replace("_", " ").title()
                top_lines.append(f"- [:material-open-in-new: {label}]({ticker}/{f.name}){{target=_blank .pdf-btn}}")

    write(DST_REPORTS / "index.md", "\n".join(top_lines))


# ── 2. notebook_llm → docs/notebooks/ ────────────────────────────────────────
def build_notebooks(lang: str = "en"):
    docs_root = get_docs_root(lang)
    DST_NOTEBOOKS = docs_root / "notebooks"
    ensure(DST_NOTEBOOKS)

    if not SRC_NOTEBOOK.exists():
        write(DST_NOTEBOOKS / "index.md", f"# {t(lang, 'ai_notebooks')}\n\nNo notebooks found.\n")
        return

    ticker_dirs = sorted([d for d in SRC_NOTEBOOK.iterdir() if d.is_dir()])
    index_rows: list[str] = []

    for ticker_dir in ticker_dirs:
        ticker = ticker_dir.name.lower()
        meta = get_meta(ticker)
        dst_dir = DST_NOTEBOOKS / ticker
        ensure(dst_dir)

        pdfs  = sorted(ticker_dir.glob("*.pdf"))
        txts  = sorted(ticker_dir.glob("*.txt"))
        mds   = sorted(ticker_dir.glob("*.md"))

        # Copy everything (notebooks are few, manageable size)
        for f in list(pdfs) + list(txts) + list(mds):
            copy_file(f, dst_dir / f.name)

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
                    f"- [:material-file-pdf-box: {f.stem}]({f.name}){{target=_blank}}  "
                    f"<small>({size_kb} KB)</small>"
                )
            lines.append("")

        if txts or mds:
            lines += [f"## {t(lang, 'notes_outlines')}", ""]
            for f in list(txts) + list(mds):
                lines.append(f"- [{f.stem}]({f.name})")
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


# ── 3. 10-k → docs/sec/10k.md (index, no PDF copy) ──────────────────────────
def build_10k_index(lang: str = "en"):
    docs_root = get_docs_root(lang)
    DST_SEC = docs_root / "sec"
    ensure(DST_SEC)

    if not SRC_10K.exists():
        write(DST_SEC / "10k.md", f"# {t(lang, 'annual_reports')}\n\nNo filings found.\n")
        return

    company_dirs = sorted([d for d in SRC_10K.iterdir() if d.is_dir()])
    table_rows: list[str] = []
    total_pdfs = 0

    for company_dir in company_dirs:
        pdfs = sorted(company_dir.glob("*.pdf"))
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

        table_rows.append(
            f"| {meta['flag']} {display_name} | `{ticker_clean.upper()}` "
            f"| {meta['sector']} | {len(pdfs)} | {year_str} |"
        )

    lines = [
        f"# {t(lang, 'annual_reports')}",
        "",
        f"> {t(lang, 'sec_annual_desc')}. {t(lang, 'total')}: **{total_pdfs} PDFs** ({len(table_rows)} {t(lang, 'companies')}).",
        f"> {t(lang, 'last_indexed')}: **{TODAY}**",
        "",
        f"!!! info \"{t(lang, 'file_location')}\"",
        f"    {t(lang, 'file_location_desc')}: `git clone https://github.com/yennanliu/finance_data.git`",
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
        "# Download 5 most recent 10-Ks for a ticker",
        "python script/download_10k_pdf.py apple-inc",
        "",
        "# Download for multiple companies (batch)",
        "bash script/batch_download_vti_top25.sh",
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
        "python script/download_10k_pdf.py AAPL --form 10-Q",
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
    pdfs_6k = list(grab_6k.glob("*.pdf")) if grab_6k.exists() else []
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
    for company_dir in sorted([d for d in SRC_INV_DAY.iterdir() if d.is_dir()]):
        ticker = company_dir.name.lower()
        meta = get_meta(ticker)
        dst_dir = DST_INV_DAY / ticker
        ensure(dst_dir)

        pdfs = sorted(company_dir.glob("*.pdf"))
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
    script_dir = ROOT / "script"
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
            f"python script/{script.name} --help",
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
                f"bash script/{script.name}",
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
        "  - notebooks",
        "  - sec",
        "  - investor_day",
        "  - scripts.md",
        "",
    ]))

    DST_REPORTS = docs_root / "reports"
    DST_NOTEBOOKS = docs_root / "notebooks"
    DST_SEC = docs_root / "sec"
    DST_INV_DAY = docs_root / "investor_day"

    for subdir in [DST_REPORTS, DST_NOTEBOOKS, DST_SEC, DST_INV_DAY]:
        if subdir.exists():
            pages_file = subdir / ".pages"
            write(pages_file, "nav:\n  - index.md\n  - ...\n")


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

    # Clean previously generated dirs for both languages
    for lang_dir in [DOCS, DOCS_ZH]:
        for subdir in ["reports", "notebooks", "sec", "investor_day"]:
            path = lang_dir / subdir
            if path.exists():
                shutil.rmtree(path)
                print(f"  clean {path.relative_to(ROOT)}/")

    # Build English version
    print(f"\n{'─'*70}")
    print(" Building English version (docs/)")
    print(f"{'─'*70}")

    print("\n[EN 1/7] Building claude_code reports...")
    build_reports(lang="en")

    print("\n[EN 2/7] Building notebook_llm pages...")
    build_notebooks(lang="en")

    print("\n[EN 3/7] Building 10-K index...")
    build_10k_index(lang="en")

    print("\n[EN 4/7] Building other SEC indices (10-Q, 13-F, 6-K)...")
    build_other_sec(lang="en")

    print("\n[EN 5/7] Building investor_day pages...")
    build_investor_day(lang="en")

    print("\n[EN 6/7] Building scripts page...")
    build_scripts_page(lang="en")

    print("\n[EN 7/7] Writing .pages nav files & abbreviations...")
    build_nav_pages(lang="en")
    build_abbreviations(lang="en")

    # Build Traditional Chinese version
    print(f"\n{'─'*70}")
    print(" Building Traditional Chinese version (docs/zh/)")
    print(f"{'─'*70}")

    print("\n[ZH 1/7] Building claude_code reports...")
    build_reports(lang="zh")

    print("\n[ZH 2/7] Building notebook_llm pages...")
    build_notebooks(lang="zh")

    print("\n[ZH 3/7] Building 10-K index...")
    build_10k_index(lang="zh")

    print("\n[ZH 4/7] Building other SEC indices (10-Q, 13-F, 6-K)...")
    build_other_sec(lang="zh")

    print("\n[ZH 5/7] Building investor_day pages...")
    build_investor_day(lang="zh")

    print("\n[ZH 6/7] Building scripts page...")
    build_scripts_page(lang="zh")

    print("\n[ZH 7/7] Writing .pages nav files & abbreviations...")
    build_nav_pages(lang="zh")
    build_abbreviations(lang="zh")

    print(f"\n{'='*70}")
    print(" ✅  docs/ generated successfully (EN + ZH)")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
