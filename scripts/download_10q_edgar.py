#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["requests", "playwright"]
# ///
"""Download 10-Q (or 6-K) filings from SEC EDGAR as PDFs by ticker symbol.

Companion to ``download_10k_edgar.py``, which stays annual-only. The CIK
lookup, PDF discovery and HTML→PDF conversion are imported from that script
rather than duplicated; what differs here is filing selection and naming:

* Annuals can be keyed by filing year because there is at most one per year.
  Quarterlies cannot — a single calendar year holds three 10-Qs — so files are
  named by the *period* they cover: ``PLTR_2026-06-30_10-Q.pdf``.
* 6-K is a catch-all form for foreign private issuers (monthly revenue,
  dividend notices, AGM results, earnings releases) and several may share one
  period, so those are named by filing date instead.

Output lands in ``10-q/<TICKER>/`` so the annual-report tooling that indexes
``10-k/`` keeps seeing only annual reports.
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from download_10k_edgar import (  # noqa: E402  (path shim must precede import)
    DATA_URL,
    HEADERS,
    SEC_URL,
    download_as_pdf,
    find_pdf_in_filing,
    get_cik,
)

SAVE_DIR = Path(__file__).parent.parent / "10-q"
DEFAULT_YEARS = 1
# Forms whose periods repeat within a year, so filing date is the stable key.
PERIOD_AMBIGUOUS_FORMS = {"6-K"}


def _matching_filings(block, form_type, cutoff):
    """Pull (date, period, accession, primary_doc) for every ``form_type``
    filing made in or after ``cutoff`` from one submissions block."""
    out = []
    periods = block.get("reportDate", [])
    for i, form in enumerate(block.get("form", [])):
        if form == form_type and int(block["filingDate"][i][:4]) >= cutoff:
            # reportDate is the period covered; it is occasionally blank, in
            # which case the filing date is the best available stand-in.
            period = periods[i] if i < len(periods) and periods[i] else block["filingDate"][i]
            out.append({
                "date": block["filingDate"][i],
                "period": period,
                "accession": block["accessionNumber"][i],
                "primary_doc": block["primaryDocument"][i],
            })
    return out


def get_filings(cik, form_type, years):
    r = requests.get(f"{DATA_URL}/submissions/CIK{cik}.json", headers=HEADERS, timeout=30)
    r.raise_for_status()
    filings = r.json()["filings"]
    cutoff = datetime.now().year - years + 1

    results = _matching_filings(filings["recent"], form_type, cutoff)

    # The "recent" block holds only ~1000 filings; high-volume filers page
    # older ones into separate archive files. Fetch those only when the
    # requested window reaches back beyond what "recent" covers.
    recent_dates = [d for d in filings["recent"].get("filingDate", []) if d]
    oldest_recent = int(min(recent_dates)[:4]) if recent_dates else cutoff
    if oldest_recent > cutoff:
        for extra in filings.get("files", []):
            time.sleep(0.2)
            er = requests.get(f"{DATA_URL}/submissions/{extra['name']}", headers=HEADERS, timeout=30)
            er.raise_for_status()
            results.extend(_matching_filings(er.json(), form_type, cutoff))

    return sorted(results, key=lambda x: x["date"], reverse=True)


def filing_filename(ticker, filing, form_type):
    key = filing["date"] if form_type in PERIOD_AMBIGUOUS_FORMS else filing["period"]
    return f"{ticker.upper()}_{key}_{form_type}.pdf"


def download_10q(ticker, years=DEFAULT_YEARS, form_type="10-Q", limit=None):
    print(f"Looking up {ticker} on SEC EDGAR...")
    cik = get_cik(ticker)
    if not cik:
        print(f"  ✗ Ticker '{ticker}' not found in EDGAR")
        return False
    print(f"  CIK: {cik}")

    time.sleep(0.3)
    filings = get_filings(cik, form_type, years)
    if not filings:
        # Foreign private issuers file 6-K, not 10-Q. Do not fall back
        # automatically: 6-K covers everything from monthly revenue to AGM
        # results, so "most recent 6-K" is rarely the quarterly report. Ask
        # for it explicitly with --form 6-K once you know which one you want.
        print(f"  No {form_type} filings found in the last {years} year(s)")
        if form_type == "10-Q":
            print("  (foreign private issuers file 6-K instead — rerun with --form 6-K)")
        return True

    if limit:
        filings = filings[:limit]
    print(f"  Found {len(filings)} {form_type} filing(s)")
    company_dir = SAVE_DIR / ticker.upper()
    company_dir.mkdir(parents=True, exist_ok=True)

    ok = 0
    for i, filing in enumerate(filings, 1):
        print(f"\n[{i}/{len(filings)}] period {filing['period']} (filed {filing['date']})")

        pdf_path = company_dir / filing_filename(ticker, filing, form_type)
        if pdf_path.exists():
            print(f"  ⊘ Already exists ({pdf_path.stat().st_size / 1e6:.1f} MB), skipping")
            ok += 1
            continue

        # Use native PDF if EDGAR includes one, otherwise download HTML → convert
        time.sleep(0.3)
        pdf_name = find_pdf_in_filing(cik, filing["accession"])
        doc_name = pdf_name if pdf_name else filing["primary_doc"]

        acc_nodash = filing["accession"].replace("-", "")
        url = f"{SEC_URL}/Archives/edgar/data/{int(cik)}/{acc_nodash}/{doc_name}"
        time.sleep(0.5)
        if download_as_pdf(url, pdf_path):
            ok += 1

    print(f"\nDone: {ok}/{len(filings)} reports in {company_dir}")
    return True


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
