#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["requests", "playwright"]
# ///
"""Download 10-K (or 20-F) filings from SEC EDGAR as PDFs by ticker symbol.

The EDGAR plumbing lives in ``edgar_common``; this module only decides which
form to ask for, where PDFs land, and how they are named.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from edgar_common import download_filings  # noqa: E402  (path shim must precede import)

SAVE_DIR = Path(__file__).parent.parent / "10-k"
DEFAULT_YEARS = 5


def annual_filename(ticker, filing, form_type):
    """Annual reports are keyed by filing year — there is at most one a year."""
    return f"{ticker.upper()}_{filing['date'][:4]}_{form_type}.pdf"


def download_10k(ticker, years=DEFAULT_YEARS, form_type="10-K"):
    return download_filings(
        ticker,
        save_dir=SAVE_DIR,
        filename=annual_filename,
        form_type=form_type,
        years=years,
        # Foreign private issuers (e.g. TSM) file 20-F instead of 10-K.
        fallback_form="20-F" if form_type == "10-K" else None,
        fallback_note=" (foreign private issuer)",
    )


def main():
    parser = argparse.ArgumentParser(description="Download SEC filings as PDFs from EDGAR")
    parser.add_argument("ticker", help="Stock ticker (e.g., AAPL, GOOGL)")
    parser.add_argument("--years", type=int, default=DEFAULT_YEARS,
                        help=f"Years of history to fetch (default: {DEFAULT_YEARS})")
    parser.add_argument("--form", default="10-K",
                        help="SEC form type (default: 10-K; use 20-F for foreign filers like TSM)")
    args = parser.parse_args()
    download_10k(args.ticker, args.years, args.form)


if __name__ == "__main__":
    main()
