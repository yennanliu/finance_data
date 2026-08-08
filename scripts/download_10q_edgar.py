#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["requests", "playwright"]
# ///
"""Download 10-Q (or 6-K) filings from SEC EDGAR as PDFs by ticker symbol.

Companion to ``download_10k_edgar.py``; both sit on the shared ``edgar_common``
plumbing and differ only in form, destination and naming. Output lands in
``10-q/<TICKER>/`` so tooling that indexes ``10-k/`` keeps seeing only annual
reports.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from edgar_common import download_filings  # noqa: E402  (path shim must precede import)

SAVE_DIR = Path(__file__).parent.parent / "10-q"
DEFAULT_YEARS = 1
# Forms whose periods repeat within a year, so filing date is the stable key.
PERIOD_AMBIGUOUS_FORMS = {"6-K"}


def quarterly_filename(ticker, filing, form_type):
    """Quarterlies cannot be keyed by year — a year holds three 10-Qs — so the
    period covered is the key. 6-K falls back to filing date because a single
    period can carry several of them (monthly revenue, dividends, AGM, ...)."""
    key = filing["date"] if form_type in PERIOD_AMBIGUOUS_FORMS else filing["period"]
    return f"{ticker.upper()}_{key}_{form_type}.pdf"


def download_10q(ticker, years=DEFAULT_YEARS, form_type="10-Q", limit=None):
    return download_filings(
        ticker,
        save_dir=SAVE_DIR,
        filename=quarterly_filename,
        form_type=form_type,
        years=years,
        limit=limit,
        # Deliberately no automatic 10-Q → 6-K fallback: 6-K is a catch-all
        # covering monthly revenue, dividend notices and AGM results, so the
        # most recent one is rarely the quarterly report. Point at the flag
        # instead of guessing which filing was meant.
        fallback_form=None,
        empty_hint=("(foreign private issuers file 6-K instead — rerun with --form 6-K)"
                    if form_type == "10-Q" else ""),
    )


def main():
    parser = argparse.ArgumentParser(
        description="Download SEC quarterly filings as PDFs from EDGAR")
    parser.add_argument("ticker", help="Stock ticker (e.g., AAPL, PLTR)")
    parser.add_argument("--years", type=int, default=DEFAULT_YEARS,
                        help=f"Years of history to fetch (default: {DEFAULT_YEARS})")
    parser.add_argument("--form", default="10-Q",
                        help="SEC form type (default: 10-Q; use 6-K for foreign filers like TSM)")
    parser.add_argument("--limit", type=int,
                        help="Keep only the N most recent matching filings")
    args = parser.parse_args()
    download_10q(args.ticker, args.years, args.form, args.limit)


if __name__ == "__main__":
    main()
