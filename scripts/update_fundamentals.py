#!/usr/bin/env python3
"""
update_fundamentals.py — maintain the committed quarterly fundamentals store
============================================================================
Refreshes ``data/fundamentals/<ticker>.csv``, ten years of reported quarterly
financial statements per ticker, sourced from SEC's XBRL ``companyfacts`` API.
Sibling of ``update_prices.py``; the two stores are joined at docs-build time to
produce the valuation charts.

The full history is fetched every run but written incrementally, so an ordinary
run changes nothing at all — fundamentals move once a quarter, not once a day.
The run that follows an earnings filing appends one row. A restatement rewrites
the affected rows. See ``scripts/analysis/data/fundamentals.py`` and
``docs/FUNDAMENTALS_STORE_EVAL.md``.

Chart payloads are *derived* from this store by ``scripts/build_docs.py`` and
are not committed.

Coverage is narrower than the price store's, and deliberately so: only SEC
registrants filing US-GAAP have XBRL facts to read. ETFs have no financial
statements at all, and foreign private issuers (TSM, GRAB, NU, NBIS) file IFRS,
which this does not yet map. Both are reported as `skipped`, not as failures.

Run locally:
    python scripts/update_fundamentals.py                 # whole universe
    python scripts/update_fundamentals.py NVDA MSFT       # a subset
    python scripts/update_fundamentals.py --only-missing  # first-time tickers
    python scripts/update_fundamentals.py --dry-run       # report, write nothing

Run in CI: see .github/workflows/update_fundamentals.yml (weekly, commits CSVs).

Fully offline-safe: importing this module does nothing; the network lives inside
fundamentals.fetch_facts, so the test suite never touches it.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from analysis.data import fundamentals, prices

ROOT = Path(__file__).resolve().parent.parent
SCHEDULE_FILE = ROOT / "scripts" / ".ticker_schedule.json"
REPORT_ROOTS = [
    ROOT / "ai_gen_report" / "fundamental",
    ROOT / "ai_gen_report" / "technical",
    ROOT / "ai_gen_report" / "stock",
]

# SEC asks for no more than 10 requests/second. One companyfacts payload is
# several megabytes, so the fetch itself paces us well below that; this is just
# a floor for the small-payload case.
REQUEST_INTERVAL = 0.15


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


def sec_symbol(key: str) -> str:
    """Report key → the symbol SEC files under.

    A Taiwan listing (``2330.tw``) is not an SEC registrant at all; its ADR
    trades as TSM and is a *different* filer, so the suffix is dropped rather
    than mapped and the lookup simply misses.
    """
    return key.split(".")[0].upper()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("tickers", nargs="*",
                   help="Tickers to refresh (default: full discovered universe)")
    p.add_argument("--store", default=str(fundamentals.STORE_DIR),
                   help=f"Store directory (default: {fundamentals.STORE_DIR})")
    p.add_argument("--years", type=int, default=fundamentals.KEEP_YEARS,
                   help=f"Years of history to keep (default: {fundamentals.KEEP_YEARS})")
    p.add_argument("--only-missing", action="store_true",
                   help="Skip tickers that already have a store file")
    p.add_argument("--dry-run", action="store_true",
                   help="Fetch and report what would change, but write nothing")
    return p.parse_args()


# Status → display glyph, matching update_prices.py so the two logs read alike.
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
    print(f"  fundamentals store → {rel}    ({args.years}y per ticker)")
    print(f"  {len(tickers)} tickers{'   [dry run]' if args.dry_run else ''}")
    print(f"{'=' * 70}\n")

    try:
        ciks = fundamentals.cik_map()
    except Exception as e:
        print(f"  ✗ could not fetch the SEC ticker→CIK map: {e}")
        sys.exit(1)

    counts: dict[str, int] = {}

    def tally(status: str, key: str, detail: str, cik: str = "—") -> None:
        counts[status] = counts.get(status, 0) + 1
        print(f"  {GLYPH.get(status, status)}  {key:<10} ({cik:<10}) {detail}")

    for key in tickers:
        if args.only_missing and fundamentals.store_path(key, store_dir).exists():
            counts["unchanged"] = counts.get("unchanged", 0) + 1
            continue

        cik = ciks.get(sec_symbol(key))
        if not cik:
            # An ETF, a non-US listing, or a ticker SEC files under another
            # name. Not an error — there is simply nothing to read.
            tally("skipped", key, "not an SEC registrant")
            continue

        status, detail = fundamentals.update(key, cik, args.years, store_dir,
                                             dry_run=args.dry_run)
        tally(status, key, detail, cik)
        time.sleep(REQUEST_INTERVAL)

    print(f"\n{'=' * 70}")
    print("  " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"{'=' * 70}\n")

    # Non-zero exit only when literally nothing succeeded, so CI catches a total
    # outage while tolerating individually-skipped tickers — of which there are
    # always some, since a third of the universe is ETFs.
    progressed = sum(counts.get(k, 0)
                     for k in ("created", "appended", "restated", "unchanged"))
    if tickers and not progressed:
        sys.exit(1)


if __name__ == "__main__":
    main()
