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
  MERMAID      - a ```mermaid flowchart has unrenderable syntax (unquoted parens
                 in a node label, stray parenthetical after a node closer)
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
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent))

from analysis.validate import (  # noqa: F401
    MIN_LINES, ReportIssue, parse_file, collect_reports,
)

# Default scan root (repo-relative); the detection logic lives in analysis.validate.
DEFAULT_ROOT = Path(__file__).parent.parent / "ai_gen_report" / "stock"


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
