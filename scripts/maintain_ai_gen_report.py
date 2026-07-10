#!/usr/bin/env python3
"""
maintain_ai_gen_report.py
==========================
Reusable maintenance for ai_gen_report/:

  1. reorg   — split ai_gen_report/stock/<ticker>/ into
               ai_gen_report/fundamental/<ticker>/ (fundamental_*) and
               ai_gen_report/technical/<ticker>/ (technical_analysis_*, technical_chart_*).
               Anything else (README.md, other analysis types) stays under stock/.
               Safe to re-run — already-moved files are simply skipped.

  2. prune   — delete dated report/news/chart files older than a cutoff date
               (filename must embed YYYY-MM-DD). README.md and undated files
               are always kept. Empty ticker directories are removed afterward.

Usage
-----
  python scripts/maintain_ai_gen_report.py reorg
  python scripts/maintain_ai_gen_report.py prune --before 2026-06-01
  python scripts/maintain_ai_gen_report.py prune --before 2026-06-01 --dry-run
"""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AI_GEN = ROOT / "ai_gen_report"

PRUNE_ROOTS = ["stock", "fundamental", "technical", "market_news"]
_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def file_date(f: Path) -> "date | None":
    m = _DATE_RE.search(f.name)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def reorg() -> None:
    src_stock = AI_GEN / "stock"
    if not src_stock.exists():
        print("no ai_gen_report/stock/ — nothing to reorg")
        return

    for ticker_dir in sorted(p for p in src_stock.iterdir() if p.is_dir()):
        ticker = ticker_dir.name
        for f in sorted(ticker_dir.iterdir()):
            if not f.is_file():
                continue
            if f.name.startswith("fundamental_"):
                dest_root = AI_GEN / "fundamental" / ticker
            elif f.name.startswith("technical_analysis_") or f.name.startswith("technical_chart_"):
                dest_root = AI_GEN / "technical" / ticker
            else:
                continue
            dest_root.mkdir(parents=True, exist_ok=True)
            dest = dest_root / f.name
            if dest.exists():
                continue
            f.rename(dest)
            print(f"  move  {f.relative_to(ROOT)}  ->  {dest.relative_to(ROOT)}")

    # prune now-empty ticker dirs under stock/
    for ticker_dir in sorted(p for p in src_stock.iterdir() if p.is_dir()):
        if not any(ticker_dir.iterdir()):
            ticker_dir.rmdir()
            print(f"  rmdir {ticker_dir.relative_to(ROOT)}")


def prune(before: date, dry_run: bool = False) -> None:
    removed = 0
    for root_name in PRUNE_ROOTS:
        root = AI_GEN / root_name
        if not root.exists():
            continue
        for ticker_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            for f in sorted(ticker_dir.iterdir()):
                if not f.is_file() or f.name == "README.md":
                    continue
                d = file_date(f)
                if d is None or d >= before:
                    continue
                removed += 1
                if dry_run:
                    print(f"  would remove  {f.relative_to(ROOT)}")
                else:
                    f.unlink()
                    print(f"  remove  {f.relative_to(ROOT)}")
            if not dry_run and ticker_dir.exists() and not any(ticker_dir.iterdir()):
                ticker_dir.rmdir()
                print(f"  rmdir {ticker_dir.relative_to(ROOT)}")
    print(f"\n{'would remove' if dry_run else 'removed'} {removed} file(s) dated before {before.isoformat()}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("reorg", help="split ai_gen_report/stock/ into fundamental/ and technical/")
    prune_p = sub.add_parser("prune", help="delete dated files older than --before")
    prune_p.add_argument("--before", required=True, help="cutoff date YYYY-MM-DD (exclusive of files on/after this date)")
    prune_p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if args.cmd == "reorg":
        reorg()
    elif args.cmd == "prune":
        prune(date.fromisoformat(args.before), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
