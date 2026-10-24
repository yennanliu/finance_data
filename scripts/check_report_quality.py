#!/usr/bin/env python3
"""
check_report_quality.py — Scan ai_gen_report/{fundamental,technical,stock}/ for
low-quality AI reports.

Every issue code it can emit, with a one-line description, is listed in
``analysis.validate.ISSUE_TYPES`` and printed beside its count in the summary:
mechanical failures (empty, refusal, truncated, placeholder, bad Mermaid …),
a fundamental report's missing chapters, and accuracy — the report against
its own arithmetic, the close and levels it was given, and the committed price
store.

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
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent))

from analysis.validate import (  # noqa: F401
    ISSUE_TYPES, MIN_LINES, ReportIssue, parse_file, collect_reports,
)

# Default scan roots (repo-relative); the detection logic lives in analysis.validate.
AI_GEN_REPORT = Path(__file__).parent.parent / "ai_gen_report"
DEFAULT_ROOTS = [AI_GEN_REPORT / "fundamental", AI_GEN_REPORT / "technical", AI_GEN_REPORT / "stock"]


RECENT_DAYS = 2   # one generation cycle: report crons run 17:00–03:00 UTC


def recent_dates(days: int, today=None) -> "set[str]":
    """The last ``days`` UTC date stamps, today included."""
    today = today or datetime.now(timezone.utc).date()
    return {(today - timedelta(days=n)).isoformat() for n in range(days)}


def print_breakdown(results: List[ReportIssue], title: str) -> None:
    """Scanned / bad counts and per-issue counts for one slice of reports."""
    bad = [r for r in results if r.is_bad()]
    counts = Counter(i for r in bad for i in r.issues)
    print(f"\n{title}")
    print(f"Total scanned : {len(results)}")
    print(f"Bad reports   : {len(bad)}  ({100*len(bad)/max(len(results),1):.1f}%)")
    print("\nIssue breakdown:")
    for issue, cnt in counts.most_common():
        print(f"  {issue:<20} {cnt:>5}  {ISSUE_TYPES.get(issue, '')}")


# ── main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=None,
                        help="Root directory to scan (default: ai_gen_report/{fundamental,technical,stock})")
    parser.add_argument("--min-lines", type=int, default=MIN_LINES,
                        help=f"Minimum content lines for a valid report (default: {MIN_LINES})")
    parser.add_argument("--since", metavar="YYYY-MM", help="Only files from this month onward")
    parser.add_argument("--until", metavar="YYYY-MM", help="Only files up to this month")
    parser.add_argument("--ticker", help="Filter to a single ticker")
    parser.add_argument("--recent-days", type=int, default=RECENT_DAYS,
                        help="Also summarise reports stamped in the last N UTC days — what "
                             f"the current code produces (default: {RECENT_DAYS}; 0 to skip)")
    parser.add_argument("--csv", metavar="PATH", help="Write results to CSV file")
    parser.add_argument("--summary", action="store_true",
                        help="Print summary table only (no per-file listing)")
    parser.add_argument("--verbose", action="store_true",
                        help="Print all files, not just bad ones")
    args = parser.parse_args()

    roots = [Path(args.root)] if args.root else DEFAULT_ROOTS
    min_lines = args.min_lines

    roots = [r for r in roots if r.exists()]
    if not roots:
        print(f"ERROR: no root directory found: {args.root or DEFAULT_ROOTS}", file=sys.stderr)
        sys.exit(1)

    paths = sorted({p for r in roots for p in collect_reports(r, args.since, args.until, args.ticker)})
    print(f"Scanning {len(paths)} reports in {', '.join(str(r) for r in roots)} ...\n", file=sys.stderr)

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
    # The recent slice first: the whole-corpus counts are dominated by reports
    # written before a fix landed, so they say little about today's code.
    print(f"\n{'='*60}")
    if args.recent_days > 0:
        dates = recent_dates(args.recent_days)
        print_breakdown([r for r in results if r.date in dates],
                        f"Recent — last {args.recent_days} UTC days ({', '.join(sorted(dates))})")
        print(f"\n{'-'*60}")
    print_breakdown(results, "All scanned reports")

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
