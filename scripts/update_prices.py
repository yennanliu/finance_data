#!/usr/bin/env python3
"""
update_prices.py — maintain the committed OHLCV price store
===========================================================
Refreshes ``data/prices/<ticker>.csv``, the single source of truth for every
chart on the site. One CSV per ticker, up to ten years of daily bars.

The full history is fetched every run but written incrementally, so an ordinary
night appends one line per ticker while a split (which makes Yahoo restate the
whole history) rewrites the file. Nothing here detects splits — see
``scripts/analysis/data/prices.py`` and ``docs/PRICE_STORE_DESIGN.md``.

Chart payloads are *derived* from this store by ``scripts/build_docs.py`` at
docs-build time and are not committed.

Ticker universe (default): the union of
  • the tickers in ``scripts/.ticker_schedule.json``, and
  • every ticker directory that already has a report under ai_gen_report/,
so a chart exists for exactly the pages the docs build renders.

Run locally:
    python scripts/update_prices.py                  # whole universe
    python scripts/update_prices.py TSLA 0050         # a subset
    python scripts/update_prices.py --only-missing    # first-time tickers only
    python scripts/update_prices.py --dry-run         # report, write nothing

Run in CI: see .github/workflows/update_kline_data.yml (daily, commits the CSVs).

Fully offline-safe: importing this module does nothing; yfinance is imported
lazily inside the fetch, so the test suite never touches the network.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from analysis.data import prices

ROOT = Path(__file__).resolve().parent.parent
SCHEDULE_FILE = ROOT / "scripts" / ".ticker_schedule.json"
REPORT_ROOTS = [
    ROOT / "ai_gen_report" / "fundamental",
    ROOT / "ai_gen_report" / "technical",
    ROOT / "ai_gen_report" / "stock",
]


def discover_tickers() -> list[str]:
    """Union of scheduled tickers and tickers that already have report dirs."""
    keys: set[str] = set()

    if SCHEDULE_FILE.exists():
        try:
            sched = json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
            for group in sched.get("tickers", {}).values():
                for tk in group:
                    keys.add(prices.report_key(tk))
        except Exception as e:  # pragma: no cover - defensive
            print(f"  ⚠ could not read {SCHEDULE_FILE.name}: {e}")

    for root in REPORT_ROOTS:
        if root.exists():
            for d in root.iterdir():
                if d.is_dir():
                    keys.add(prices.report_key(d.name))

    return sorted(keys)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("tickers", nargs="*",
                   help="Tickers to refresh (default: full discovered universe)")
    p.add_argument("--store", default=str(prices.STORE_DIR),
                   help=f"Store directory (default: {prices.STORE_DIR})")
    p.add_argument("--years", type=int, default=prices.KEEP_YEARS,
                   help=f"Years of history to fetch and keep (default: {prices.KEEP_YEARS})")
    p.add_argument("--only-missing", action="store_true",
                   help="Skip tickers that already have a store file")
    p.add_argument("--dry-run", action="store_true",
                   help="Fetch and report what would change, but write nothing")
    return p.parse_args()


# Status → display glyph. `restated` is called out loudly because it is the one
# status whose commit diff is thousands of lines rather than one.
GLYPH = {
    "created":   "✓ created ",
    "appended":  "✓ appended",
    "restated":  "⟳ RESTATED",
    "unchanged": "· unchanged",
    "skipped":   "⚠ skipped ",
    "failed":    "✗ failed  ",
}


def main() -> None:
    args = parse_args()
    store_dir = Path(args.store)

    tickers = ([prices.report_key(t) for t in args.tickers]
               or discover_tickers())

    print(f"\n{'=' * 70}")
    rel = store_dir.relative_to(ROOT) if store_dir.is_relative_to(ROOT) else store_dir
    print(f"  price store → {rel}    ({args.years}y per ticker)")
    print(f"  {len(tickers)} tickers{'   [dry run]' if args.dry_run else ''}")
    print(f"{'=' * 70}\n")

    counts: dict[str, int] = {}
    for key in tickers:
        if args.only_missing and prices.store_path(key, store_dir).exists():
            counts["unchanged"] = counts.get("unchanged", 0) + 1
            continue

        symbol = prices.to_yf_symbol(key)
        if args.dry_run:
            status, detail = _dry_run_one(key, symbol, args.years, store_dir)
        else:
            status, detail = prices.update(key, symbol, args.years, store_dir)

        counts[status] = counts.get(status, 0) + 1
        print(f"  {GLYPH.get(status, status)}  {key:<10} ({symbol:<10}) {detail}")

    print(f"\n{'=' * 70}")
    print("  " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"{'=' * 70}\n")

    # Non-zero exit only when literally nothing succeeded, so CI catches a total
    # outage while tolerating a handful of individually-failing tickers.
    progressed = sum(counts.get(k, 0)
                     for k in ("created", "appended", "restated", "unchanged"))
    if tickers and not progressed:
        sys.exit(1)


def _dry_run_one(key: str, symbol: str, years: int, store_dir: Path):
    """Same decisions as prices.update() but without touching the disk."""
    old = prices.load_store(key, store_dir)
    try:
        new = prices.fetch_history(symbol, years)
    except Exception as e:
        return "failed", f"fetch error: {e}"
    if not new:
        return "failed", "no data"
    reason = prices.gate(new, old)
    if reason:
        return "skipped", reason

    merged = prices.trim(prices.upsert(old, new), years)
    current = prices.store_path(key, store_dir)
    text = prices.serialise(merged)
    if current.exists() and current.read_text(encoding="utf-8") == text:
        return "unchanged", f"{len(merged)} bars"
    if not old:
        return "created", f"would write {len(merged)} bars"
    changed = prices._restated_count(old, new)
    if changed:
        return "restated", f"would rewrite {changed} existing bars ({len(merged)} total)"
    return "appended", f"would write {len(merged) - len(old)} new bars"


if __name__ == "__main__":
    main()
