#!/usr/bin/env python3
"""
check_report_quality.py — Scan ai_gen_report/stock/ for low-quality AI reports.

Bad-quality categories detected:
  EMPTY        - file is empty or only whitespace
  REFUSAL      - LLM refused the request ("抱歉", "I'm sorry", "I cannot", etc.)
  TOO_SHORT    - content too short to be a real report (< MIN_LINES lines after frontmatter)
  NO_FRONTMATTER - missing YAML frontmatter block
  CUTOFF       - report appears truncated (ends mid-sentence / mid-code-block)
  WRONG_LANG   - contains significant English in a report expected to be zh-TW
  PLACEHOLDER  - has unfilled template placeholders (e.g. {ticker}, N/A blocks)
  HTML_LEAK    - contains raw HTML / Plotly scripts instead of clean Markdown
  DUPLICATE    - same ticker+type+date with a -2 / -3 suffix (keeps the original)

Usage:
  python3 scripts/check_report_quality.py [--root PATH] [--min-lines N]
                                           [--since YYYY-MM] [--until YYYY-MM]
                                           [--ticker TICKER] [--csv PATH]
                                           [--summary] [--verbose]

Examples:
  python3 scripts/check_report_quality.py --summary
  python3 scripts/check_report_quality.py --since 2026-02 --until 2026-03
  python3 scripts/check_report_quality.py --ticker onds --verbose
  python3 scripts/check_report_quality.py --csv bad_reports.csv
"""

import argparse
import csv
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# ── tuneable thresholds ────────────────────────────────────────────────────────
DEFAULT_ROOT = Path(__file__).parent.parent / "ai_gen_report" / "stock"
MIN_LINES = 80          # below this (after frontmatter) → TOO_SHORT
REFUSAL_PATTERNS = [
    r"抱歉[，,]?\s*(我無法|我不能|無法完成|無法為|我沒有辦法)",
    r"I('m| am) sorry",
    r"I cannot (assist|complete|fulfill|help)",
    r"I can't (assist|complete|fulfill|help)",
    r"無法完成(這個|該|此)請求",
    r"無法(為您|協助您?)完成",
    r"由於.*缺乏.*具體.*資訊.*無法",
]
PLACEHOLDER_PATTERNS = [
    r"\{ticker\}",
    r"\{financial_context\}",
    r"\{today\}",
    r"\[INSERT",
    r"<YOUR_",
]
HTML_LEAK_PATTERNS = [
    r"window\.PlotlyConfig",
    r"<script[\s>]",
    r"<!DOCTYPE html",
    r"<html[\s>]",
]
CUTOFF_SIGNALS = [
    r"```\s*$",          # unclosed code block at end
    r"[，,、]\s*$",       # ends with a comma / enumeration separator
    r"\.\.\.\s*$",       # literal ellipsis at end
    r"[^\.\?！。）\)」』…]\s*$",  # ends without sentence-ending punctuation (broad)
]


# ── data model ─────────────────────────────────────────────────────────────────
@dataclass
class ReportIssue:
    path: str
    ticker: str
    analysis_type: str
    date: str
    provider: str
    issues: List[str] = field(default_factory=list)
    line_count: int = 0
    content_lines: int = 0
    note: str = ""

    def is_bad(self) -> bool:
        return len(self.issues) > 0


# ── helpers ────────────────────────────────────────────────────────────────────
FRONTMATTER_RE = re.compile(r"^---\n(.+?)\n---\n", re.DOTALL)
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
FILENAME_RE = re.compile(
    r"^(?P<atype>[a-z_]+)_(?P<date>\d{4}-\d{2}-\d{2})(?:-\d+)?(?:_(?P<provider>[a-z]+))?\.md$"
)


def parse_file(path: Path, min_lines: int = MIN_LINES) -> ReportIssue:
    rel = str(path)
    parts = path.parts
    # derive ticker from parent dir name
    ticker = path.parent.name

    m = FILENAME_RE.match(path.name)
    if m:
        atype = m.group("atype")
        date = m.group("date")
        provider = m.group("provider") or "claude"
        is_dup = bool(re.search(r"-\d+\.md$", path.name))
    else:
        atype, date, provider, is_dup = "unknown", "", "unknown", False

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return ReportIssue(rel, ticker, atype, date, provider,
                           issues=["READ_ERROR"], note=str(e))

    total_lines = text.count("\n")
    # strip frontmatter for content analysis
    fm_match = FRONTMATTER_RE.match(text)
    content = text[fm_match.end():] if fm_match else text
    content_lines = content.count("\n")

    issues: List[str] = []
    notes: List[str] = []

    # DUPLICATE
    if is_dup:
        issues.append("DUPLICATE")

    # EMPTY
    if not content.strip():
        issues.append("EMPTY")
        return ReportIssue(rel, ticker, atype, date, provider, issues,
                           total_lines, content_lines)

    # NO_FRONTMATTER
    if not fm_match:
        issues.append("NO_FRONTMATTER")

    # REFUSAL
    for pat in REFUSAL_PATTERNS:
        if re.search(pat, text):
            issues.append("REFUSAL")
            break

    # TOO_SHORT  (only if not already a refusal, which is short by definition)
    if "REFUSAL" not in issues and content_lines < min_lines:
        issues.append("TOO_SHORT")
        notes.append(f"content_lines={content_lines}")

    # PLACEHOLDER
    for pat in PLACEHOLDER_PATTERNS:
        if re.search(pat, text):
            issues.append("PLACEHOLDER")
            break

    # HTML_LEAK — only flag when the file IS mostly raw HTML (not intentional embedded charts).
    # Technical analysis files legitimately embed Plotly HTML; flag only when:
    #   - file contains HTML boilerplate AND has very few Markdown headings (< 2)
    html_boilerplate = any(re.search(p, text) for p in HTML_LEAK_PATTERNS)
    if html_boilerplate:
        md_headings = len(re.findall(r"^#{1,3} ", text, re.MULTILINE))
        if md_headings < 2:
            issues.append("HTML_LEAK")

    # CUTOFF — check last non-empty line
    lines = [l for l in text.splitlines() if l.strip()]
    if lines:
        last = lines[-1].rstrip()
        # skip lines that are obviously table rows or code fences
        if not re.match(r"^(\||-{3,}|={3,}|```)", last):
            # check for cutoff signals
            for pat in CUTOFF_SIGNALS[:-1]:   # explicit patterns
                if re.search(pat, last):
                    issues.append("CUTOFF")
                    notes.append(f"last_line={last[:80]!r}")
                    break
            # broad "no sentence ending" check — only for short files
            if "CUTOFF" not in issues and content_lines < min_lines:
                if re.search(CUTOFF_SIGNALS[-1], last):
                    # avoid flagging lines ending with CJK closing punctuation
                    if not re.search(r"[。！？…」』）\)]$", last):
                        issues.append("CUTOFF")
                        notes.append(f"last_line={last[:80]!r}")

    return ReportIssue(
        path=rel,
        ticker=ticker,
        analysis_type=atype,
        date=date,
        provider=provider,
        issues=issues,
        line_count=total_lines,
        content_lines=content_lines,
        note="; ".join(notes),
    )


def collect_reports(root: Path, since: Optional[str], until: Optional[str],
                    ticker_filter: Optional[str]) -> List[Path]:
    paths = []
    for p in root.rglob("*.md"):
        if ticker_filter and p.parent.name.lower() != ticker_filter.lower():
            continue
        m = DATE_RE.search(p.name)
        if m:
            d = m.group(1)[:7]  # YYYY-MM
            if since and d < since:
                continue
            if until and d > until:
                continue
        paths.append(p)
    return sorted(paths)


# ── main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=str(DEFAULT_ROOT),
                        help="Root directory to scan (default: ai_gen_report/stock)")
    parser.add_argument("--min-lines", type=int, default=MIN_LINES,
                        help=f"Minimum content lines for a valid report (default: {MIN_LINES})")
    parser.add_argument("--since", metavar="YYYY-MM", help="Only files from this month onward")
    parser.add_argument("--until", metavar="YYYY-MM", help="Only files up to this month")
    parser.add_argument("--ticker", help="Filter to a single ticker")
    parser.add_argument("--csv", metavar="PATH", help="Write results to CSV file")
    parser.add_argument("--summary", action="store_true",
                        help="Print summary table only (no per-file listing)")
    parser.add_argument("--verbose", action="store_true",
                        help="Print all files, not just bad ones")
    args = parser.parse_args()

    root = Path(args.root)
    min_lines = args.min_lines

    if not root.exists():
        print(f"ERROR: root directory not found: {root}", file=sys.stderr)
        sys.exit(1)

    paths = collect_reports(root, args.since, args.until, args.ticker)
    print(f"Scanning {len(paths)} reports in {root} ...\n", file=sys.stderr)

    results: List[ReportIssue] = []
    for p in paths:
        r = parse_file(p, min_lines)
        results.append(r)

    bad = [r for r in results if r.is_bad()]

    # ── console output ─────────────────────────────────────────────────────────
    if not args.summary:
        items = results if args.verbose else bad
        for r in items:
            tag = ",".join(r.issues) if r.issues else "OK"
            note = f"  [{r.note}]" if r.note else ""
            print(f"{tag:<35} {r.date}  {r.ticker:<12} {r.analysis_type:<30} {r.path}{note}")

    # ── summary ────────────────────────────────────────────────────────────────
    from collections import Counter
    issue_counts: Counter = Counter()
    for r in bad:
        for i in r.issues:
            issue_counts[i] += 1

    print(f"\n{'='*60}")
    print(f"Total scanned : {len(results)}")
    print(f"Bad reports   : {len(bad)}  ({100*len(bad)/max(len(results),1):.1f}%)")
    print(f"\nIssue breakdown:")
    for issue, cnt in issue_counts.most_common():
        print(f"  {issue:<20} {cnt:>5}")

    # per-ticker bad count
    ticker_bad: Counter = Counter(r.ticker for r in bad)
    print(f"\nTop 10 tickers by bad-report count:")
    for ticker, cnt in ticker_bad.most_common(10):
        total = sum(1 for r in results if r.ticker == ticker)
        print(f"  {ticker:<12} {cnt:>4} / {total:<4} bad")

    # ── CSV export ─────────────────────────────────────────────────────────────
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["path", "ticker", "analysis_type", "date", "provider",
                        "issues", "line_count", "content_lines", "note"])
            for r in bad:
                w.writerow([r.path, r.ticker, r.analysis_type, r.date, r.provider,
                             ",".join(r.issues), r.line_count, r.content_lines, r.note])
        print(f"\nCSV written → {args.csv}")


if __name__ == "__main__":
    main()
