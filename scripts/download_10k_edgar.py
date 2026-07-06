#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["requests", "playwright"]
# ///
"""Download 10-K (or 20-F) filings from SEC EDGAR as PDFs by ticker symbol."""

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

SAVE_DIR = Path(__file__).parent.parent / "10-k"
DEFAULT_YEARS = 5
HEADERS = {"User-Agent": "finance-data-research contact@example.com"}
SEC_URL = "https://www.sec.gov"
DATA_URL = "https://data.sec.gov"


def get_cik(ticker):
    r = requests.get(f"{SEC_URL}/files/company_tickers.json", headers=HEADERS, timeout=30)
    r.raise_for_status()
    normalized = ticker.upper().replace(".", "-")  # BRK.B → BRK-B
    for entry in r.json().values():
        if entry["ticker"].upper() == normalized:
            return str(entry["cik_str"]).zfill(10)
    return None


def get_filings(cik, form_type, years):
    r = requests.get(f"{DATA_URL}/submissions/CIK{cik}.json", headers=HEADERS, timeout=30)
    r.raise_for_status()
    recent = r.json()["filings"]["recent"]
    cutoff = datetime.now().year - years + 1

    results = []
    for i, form in enumerate(recent["form"]):
        if form == form_type and int(recent["filingDate"][i][:4]) >= cutoff:
            results.append({
                "date": recent["filingDate"][i],
                "accession": recent["accessionNumber"][i],
                "primary_doc": recent["primaryDocument"][i],
            })
    return sorted(results, key=lambda x: x["date"], reverse=True)


def find_pdf_in_filing(cik, accession):
    acc_nodash = accession.replace("-", "")
    # directory path uses no-dash; index filename keeps dashes
    url = f"{SEC_URL}/Archives/edgar/data/{int(cik)}/{acc_nodash}/{accession}-index.json"
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        for item in r.json().get("directory", {}).get("item", []):
            if item.get("name", "").lower().endswith(".pdf"):
                return item["name"]
    except Exception:
        pass
    return None


def download_raw(url, filepath):
    r = requests.get(url, headers=HEADERS, timeout=120, stream=True)
    r.raise_for_status()
    with open(filepath, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)


def html_to_pdf(html_path, pdf_path):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:
            if "Executable doesn't exist" in str(e):
                print("  Installing Chromium (one-time, ~120 MB)...")
                subprocess.run(
                    [sys.executable, "-m", "playwright", "install", "chromium"],
                    check=True,
                )
                browser = p.chromium.launch()
            else:
                raise
        page = browser.new_page()
        page.goto(f"file://{html_path.absolute()}", wait_until="load")
        page.pdf(path=str(pdf_path), format="Letter", print_background=True)
        browser.close()


def download_as_pdf(url, pdf_path):
    print(f"  Downloading: {url}")
    try:
        if url.lower().endswith(".pdf"):
            download_raw(url, pdf_path)
        else:
            html_path = pdf_path.with_suffix(".htm")
            download_raw(url, html_path)
            print("  Converting to PDF...")
            html_to_pdf(html_path, pdf_path)
            html_path.unlink()

        print(f"  ✓ {pdf_path.name} ({pdf_path.stat().st_size / 1e6:.1f} MB)")
        return True
    except Exception as e:
        print(f"  ✗ {e}")
        pdf_path.unlink(missing_ok=True)
        return False


def download_10k(ticker, years=DEFAULT_YEARS, form_type="10-K"):
    print(f"Looking up {ticker} on SEC EDGAR...")
    cik = get_cik(ticker)
    if not cik:
        print(f"  ✗ Ticker '{ticker}' not found in EDGAR")
        return False
    print(f"  CIK: {cik}")

    time.sleep(0.3)
    filings = get_filings(cik, form_type, years)
    if not filings and form_type == "10-K":
        # Foreign private issuers (e.g. TSM) file 20-F instead of 10-K.
        time.sleep(0.3)
        alt = get_filings(cik, "20-F", years)
        if alt:
            print("  No 10-K found; falling back to 20-F (foreign private issuer)")
            form_type, filings = "20-F", alt
    if not filings:
        print(f"  No {form_type} filings found in the last {years} years")
        return True

    print(f"  Found {len(filings)} {form_type} filing(s)")
    company_dir = SAVE_DIR / ticker.upper()
    company_dir.mkdir(parents=True, exist_ok=True)

    ok = 0
    for i, filing in enumerate(filings, 1):
        year = filing["date"][:4]
        print(f"\n[{i}/{len(filings)}] {year} ({filing['date']})")

        pdf_path = company_dir / f"{ticker.upper()}_{year}_{form_type}.pdf"
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
