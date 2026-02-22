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
SITE       = ROOT / "site"

SRC_CLAUDE   = ROOT / "claude_code"
SRC_NOTEBOOK = ROOT / "notebook_llm"
SRC_10K      = ROOT / "10-k"
SRC_10Q      = ROOT / "10-q"
SRC_13F      = ROOT / "13-f"
SRC_6K       = ROOT / "6-k"
SRC_INV_DAY  = ROOT / "investor_day"

DST_REPORTS  = DOCS / "reports"
DST_NOTEBOOKS= DOCS / "notebooks"
DST_SEC      = DOCS / "sec"
DST_INV_DAY  = DOCS / "investor_day"

TODAY = date.today().isoformat()

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
def build_reports():
    ensure(DST_REPORTS)
    report_index_rows: list[str] = []
    nav_entries: list[str] = []

    if not SRC_CLAUDE.exists():
        write(DST_REPORTS / "index.md", "# Reports\n\nNo reports found.\n")
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
            f"> **Sector:** {meta['sector']}  |  **Last updated:** {TODAY}",
            "",
            "---",
            "",
            "## Available Reports",
            "",
        ]

        if md_files:
            lines.append("### 📄 Markdown Reports")
            lines.append("")
            for f in md_files:
                label = f.stem.replace("_", " ").title()
                lines.append(f"- [{label}]({f.name})")
            lines.append("")

        if html_files:
            lines.append("### 🌐 Interactive HTML Reports")
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
        "# Analysis Reports",
        "",
        f"> AI-generated investment research reports. Last built: **{TODAY}**",
        "",
        "!!! warning \"Disclaimer\"",
        "    All reports are for educational purposes only and do not constitute investment advice.",
        "",
        "## Report Index",
        "",
        "| | Ticker | Company | Sector | Files | Reports |",
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
            f"**Sector:** {meta['sector']}",
            "",
        ]
        if md_files:
            top_lines.append("**Markdown Reports:**")
            for f in md_files:
                label = f.stem.replace("_", " ").title()
                top_lines.append(f"- [{label}]({ticker}/{f.name})")
        if html_files:
            top_lines.append("")
            top_lines.append("**Interactive Reports (HTML):**")
            for f in html_files:
                label = f.stem.replace("_", " ").title()
                top_lines.append(f"- [:material-open-in-new: {label}]({ticker}/{f.name}){{target=_blank .pdf-btn}}")

    write(DST_REPORTS / "index.md", "\n".join(top_lines))


# ── 2. notebook_llm → docs/notebooks/ ────────────────────────────────────────
def build_notebooks():
    ensure(DST_NOTEBOOKS)

    if not SRC_NOTEBOOK.exists():
        write(DST_NOTEBOOKS / "index.md", "# AI Research Notebooks\n\nNo notebooks found.\n")
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
            f"# {meta['flag']} {meta['name']} — AI Notebooks",
            "",
            f"> **Sector:** {meta['sector']}",
            "",
            "---",
            "",
        ]

        if pdfs:
            lines += ["## 📑 Research Documents", ""]
            for f in pdfs:
                size_kb = int(f.stat().st_size / 1024)
                lines.append(
                    f"- [:material-file-pdf-box: {f.stem}]({f.name}){{target=_blank}}  "
                    f"<small>({size_kb} KB)</small>"
                )
            lines.append("")

        if txts or mds:
            lines += ["## 📝 Notes & Outlines", ""]
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
        "# AI Research Notebooks",
        "",
        f"> Deep-dive analysis generated with Google NotebookLM. Built: **{TODAY}**",
        "",
        "| | Ticker | Company | Sector | Files |",
        "|---|--------|---------|--------|-------|",
    ] + index_rows + [
        "",
        "---",
        "",
        "## About NotebookLM Reports",
        "",
        "These documents are AI-synthesised research reports created using Google NotebookLM",
        "from primary source materials (10-K filings, investor presentations, earnings calls).",
        "They provide deep-dive analysis from a structured, document-grounded AI perspective.",
    ]

    write(DST_NOTEBOOKS / "index.md", "\n".join(top_lines))


# ── 3. 10-k → docs/sec/10k.md (index, no PDF copy) ──────────────────────────
def build_10k_index():
    ensure(DST_SEC)

    if not SRC_10K.exists():
        write(DST_SEC / "10k.md", "# 10-K Filings\n\nNo filings found.\n")
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
        "# 10-K Annual Reports",
        "",
        f"> SEC annual filings (Form 10-K) stored locally. Total: **{total_pdfs} PDFs** across **{len(table_rows)} companies**.",
        f"> Last indexed: **{TODAY}**",
        "",
        "!!! info \"File Location\"",
        "    10-K PDFs are stored in the `10-k/` directory of the repository.",
        "    Clone the repo to access them locally: `git clone https://github.com/yennanliu/finance_data.git`",
        "",
        "## Company Index",
        "",
        "| Company | Ticker | Sector | # Files | Years |",
        "|---------|--------|--------|---------|-------|",
    ] + table_rows + [
        "",
        "---",
        "",
        "## Download More Filings",
        "",
        "Use the included Python scripts to download additional 10-K filings:",
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
def build_other_sec():
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
def build_investor_day():
    ensure(DST_INV_DAY)

    if not SRC_INV_DAY.exists():
        write(DST_INV_DAY / "index.md", "# Investor Day Materials\n\nNo materials found.\n")
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
def build_scripts_page():
    scripts_page = DOCS / "scripts.md"
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
def build_nav_pages():
    """Write .pages files so awesome-pages controls navigation order."""
    root_pages = DOCS / ".pages"
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

    for subdir in [DST_REPORTS, DST_NOTEBOOKS, DST_SEC, DST_INV_DAY]:
        if subdir.exists():
            pages_file = subdir / ".pages"
            write(pages_file, "nav:\n  - index.md\n  - ...\n")


# ── 8. includes/abbreviations.md ─────────────────────────────────────────────
def build_abbreviations():
    inc = DOCS / "includes"
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
    print(f"\n{'='*60}")
    print(" Finance Hub — building docs/")
    print(f"{'='*60}\n")

    # Clean previously generated dirs (keep hand-crafted files like index.md)
    for subdir in ["reports", "notebooks", "sec", "investor_day"]:
        path = DOCS / subdir
        if path.exists():
            shutil.rmtree(path)
            print(f"  clean {path.relative_to(ROOT)}/")

    print("\n[1/7] Building claude_code reports...")
    build_reports()

    print("\n[2/7] Building notebook_llm pages...")
    build_notebooks()

    print("\n[3/7] Building 10-K index...")
    build_10k_index()

    print("\n[4/7] Building other SEC indices (10-Q, 13-F, 6-K)...")
    build_other_sec()

    print("\n[5/7] Building investor_day pages...")
    build_investor_day()

    print("\n[6/7] Building scripts page...")
    build_scripts_page()

    print("\n[7/7] Writing .pages nav files & abbreviations...")
    build_nav_pages()
    build_abbreviations()

    print(f"\n{'='*60}")
    print(" ✅  docs/ generated successfully")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
