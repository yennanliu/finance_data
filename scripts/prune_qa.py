#!/usr/bin/env python3
"""Prune old QA audit artifacts, keeping only the N most recent run dates.

The nightly QA workflow (.github/workflows/qa_report_quality.yml) writes one
CSV + one summary per run into qa/. Left alone that directory grows forever, so
this trims it to a rolling window.

A "run date" is the YYYY-MM-DD stamp in the filename; all files sharing a date
are kept or dropped together. Undated files (README.md, .gitkeep) are untouched.

Usage:
  python scripts/prune_qa.py                    # keep 10 most recent dates
  python scripts/prune_qa.py --keep 30
  python scripts/prune_qa.py --keep 10 --dry-run
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

QA_DIR = Path(__file__).resolve().parent.parent / "qa"
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
DEFAULT_KEEP = 10


def dated_files(qa_dir: Path) -> dict[str, list[Path]]:
    """Map run date → files carrying that date."""
    by_date: dict[str, list[Path]] = {}
    for f in sorted(qa_dir.iterdir()):
        if not f.is_file():
            continue
        m = DATE_RE.search(f.name)
        if m:
            by_date.setdefault(m.group(1), []).append(f)
    return by_date


def prune(qa_dir: Path, keep: int, dry_run: bool = False) -> int:
    if not qa_dir.exists():
        print(f"{qa_dir} does not exist — nothing to prune.")
        return 0

    by_date = dated_files(qa_dir)
    if not by_date:
        print(f"No dated QA files in {qa_dir}.")
        return 0

    dates = sorted(by_date, reverse=True)
    keep_dates, drop_dates = dates[:keep], dates[keep:]

    print(f"QA run dates: {len(dates)} total, keeping {len(keep_dates)} "
          f"({keep_dates[-1]} → {keep_dates[0]})")

    if not drop_dates:
        print("Nothing to prune.")
        return 0

    removed = 0
    for d in drop_dates:
        for f in by_date[d]:
            print(f"  {'would remove' if dry_run else 'remove'} {f.relative_to(qa_dir.parent)}")
            if not dry_run:
                f.unlink()
            removed += 1

    verb = "Would remove" if dry_run else "Removed"
    print(f"\n{verb} {removed} file(s) across {len(drop_dates)} run date(s) "
          f"({drop_dates[-1]} → {drop_dates[0]}).")
    return removed


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--keep", type=int, default=DEFAULT_KEEP,
                   help=f"number of most recent run dates to keep (default: {DEFAULT_KEEP})")
    p.add_argument("--qa-dir", default=str(QA_DIR), help="QA directory (default: qa/)")
    p.add_argument("--dry-run", action="store_true", help="list what would be removed")
    args = p.parse_args()

    if args.keep < 1:
        print("ERROR: --keep must be >= 1", file=sys.stderr)
        sys.exit(1)

    prune(Path(args.qa_dir), args.keep, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
