#!/usr/bin/env python3
"""
Download actual 10-K filings for a stock ticker.

Strategy (in order):
  1. annualreports.com  → PDF  (best for human reading)
  2. SEC EDGAR API      → HTML (official source, always available)

The ticker is resolved to a CIK via SEC's live company-lookup API,
so no hardcoded ticker→CIK mapping is needed.

Usage:
  python download_10k_scrape.py PLTR              # latest 10-K
  python download_10k_scrape.py PLTR 2024         # fiscal year 2024
  python download_10k_scrape.py AAPL 2023 -n 1    # 1 report for FY2023
  python download_10k_scrape.py MSFT -n 3         # 3 most recent
"""

import argparse
import re
import time
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup


HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}
HEADERS_SEC = {
    "User-Agent": "ResearchProject f339339@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}

SAVE_DIR = Path(__file__).parent.parent / "10-k"
SAVE_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# SEC helpers
# ─────────────────────────────────────────────────────────────────────────────

def lookup_cik(ticker: str) -> Optional[str]:
    """Resolve ticker → zero-padded CIK via SEC company-search API."""
    url = "https://efts.sec.gov/LATEST/search-index?q=%22{}%22&dateRange=custom&startdt=2000-01-01&forms=10-K".format(ticker)
    # Use the tickers.json endpoint — faster and authoritative
    try:
        time.sleep(0.3)
        r = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=HEADERS_SEC, timeout=10,
        )
        r.raise_for_status()
        for entry in r.json().values():
            if entry["ticker"].upper() == ticker.upper():
                return str(entry["cik_str"]).zfill(10)
    except Exception as e:
        print(f"  [warn] CIK lookup failed: {e}")
    return None


def get_10k_filings(cik: str, year_filter: Optional[str], count: int) -> list[dict]:
    """Return up to `count` 10-K filings from SEC submissions API, optionally filtered by fiscal year."""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        time.sleep(0.3)
        r = requests.get(url, headers=HEADERS_SEC, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  [error] SEC submissions API: {e}")
        return []

    company_name = data.get("name", "Unknown")
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])

    results = []
    for i, form in enumerate(forms):
        if form != "10-K":
            continue
        report_date = recent["reportDate"][i]        # e.g. "2024-12-31"
        filing_date = recent["filingDate"][i]
        accession   = recent["accessionNumber"][i]
        primary_doc = recent["primaryDocument"][i]

        if year_filter and not report_date.startswith(year_filter):
            continue

        results.append({
            "company":        company_name,
            "cik":            cik,
            "reportDate":     report_date,
            "filingDate":     filing_date,
            "accessionNumber": accession,
            "primaryDocument": primary_doc,
        })
        if len(results) >= count:
            break

    return results


def sec_download(filing: dict, out_dir: Path) -> Optional[Path]:
    """Download the 10-K HTML from SEC EDGAR archives."""
    accession = filing["accessionNumber"].replace("-", "")
    cik_int   = str(int(filing["cik"]))   # no leading zeros for archive URL
    doc_name  = filing["primaryDocument"]
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession}/{doc_name}"

    report_date = filing["reportDate"]          # e.g. "2024-06-30"
    year  = report_date[:4]
    month = report_date[5:7] if len(report_date) >= 7 else "12"
    ext   = doc_name.rsplit(".", 1)[-1] if "." in doc_name else "htm"
    ticker = out_dir.name
    filename = f"{ticker}_{year}_{month}.{ext}"
    filepath = out_dir / filename

    if filepath.exists():
        print(f"  ⊘ Already exists: {filepath.name}")
        return filepath

    try:
        time.sleep(0.5)
        r = requests.get(url, headers=HEADERS_SEC, timeout=30)
        r.raise_for_status()
        filepath.write_bytes(r.content)
        size_mb = filepath.stat().st_size / 1024 / 1024
        print(f"  ✓ SEC HTML: {filepath.name}  ({size_mb:.1f} MB)")
        return filepath
    except Exception as e:
        print(f"  ✗ SEC download failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# annualreports.com helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ar_slug_via_search(ticker: str) -> Optional[str]:
    """Resolve annualreports.com company slug by searching with ticker symbol."""
    try:
        time.sleep(0.5)
        r = requests.get(
            f"https://www.annualreports.com/Companies?search={ticker}",
            headers=HEADERS_BROWSER, timeout=10,
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("/Company/"):
                return href.split("/Company/")[1].strip("/")
    except Exception as e:
        print(f"  [warn] annualreports.com search failed: {e}")
    return None


def annualreports_pdf(company_name: str, ticker: str, report_date: str, out_dir: Path) -> Optional[Path]:
    """Try to download a PDF from annualreports.com for the given report date."""
    year  = report_date[:4]
    month = report_date[5:7] if len(report_date) >= 7 else "12"

    slug = _ar_slug_via_search(ticker)
    if not slug:
        print(f"  [skip] annualreports.com: could not find slug for {ticker}")
        return None
    url = f"https://www.annualreports.com/Company/{slug}"

    filename = f"{ticker}_{year}_{month}.pdf"
    filepath = out_dir / filename

    if filepath.exists():
        print(f"  ⊘ Already exists: {filepath.name}")
        return filepath

    try:
        time.sleep(1)
        r = requests.get(url, headers=HEADERS_BROWSER, timeout=15)
        if r.status_code == 404:
            print(f"  [skip] annualreports.com: company page not found ({slug})")
            return None
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Find PDF link matching the year; fall back to most recent available
        pdf_url = None
        all_pdfs = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "HostedData/AnnualReportArchive" in href and href.endswith(".pdf"):
                full = f"https://www.annualreports.com{href}" if href.startswith("/") else href
                m = re.search(r"_(\d{4})\.pdf", href)
                if m:
                    all_pdfs.append((m.group(1), full))

        all_pdfs.sort(key=lambda x: x[0], reverse=True)  # newest first
        for yr, u in all_pdfs:
            if yr == year:
                pdf_url = u
                break
        # If exact year not found, use latest available
        if not pdf_url and all_pdfs:
            latest_yr, pdf_url = all_pdfs[0]
            print(f"  [info] Year {year} not found; using latest available: {latest_yr}")

        if not pdf_url:
            print(f"  [skip] annualreports.com: no PDFs found at all")
            return None

        print(f"  Downloading PDF: {pdf_url}")
        time.sleep(1.5)
        r2 = requests.get(pdf_url, headers=HEADERS_BROWSER, timeout=60, stream=True)
        r2.raise_for_status()
        with open(filepath, "wb") as f:
            for chunk in r2.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        size_mb = filepath.stat().st_size / 1024 / 1024
        print(f"  ✓ PDF: {filepath.name}  ({size_mb:.1f} MB)")
        return filepath

    except Exception as e:
        print(f"  ✗ annualreports.com failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Main downloader
# ─────────────────────────────────────────────────────────────────────────────

def download_10k(ticker: str, year_filter: Optional[str], count: int) -> None:
    ticker = ticker.upper()
    print(f"\n{'='*60}")
    print(f"  10-K Downloader  —  {ticker}" + (f"  FY{year_filter}" if year_filter else ""))
    print(f"{'='*60}")

    # 1. Resolve CIK
    print(f"\nLooking up CIK for {ticker}...")
    cik = lookup_cik(ticker)
    if not cik:
        print(f"  [error] Could not resolve CIK for {ticker}")
        return
    print(f"  CIK: {cik}")

    # 2. Find 10-K filings
    filings = get_10k_filings(cik, year_filter, count)
    if not filings:
        print(f"  No 10-K filings found" + (f" for {year_filter}" if year_filter else ""))
        return

    print(f"\n  Found {len(filings)} filing(s):")
    for f in filings:
        print(f"    • {f['reportDate']}  (filed {f['filingDate']})  —  {f['company']}")

    # 3. Download each filing
    out_dir = SAVE_DIR / ticker
    out_dir.mkdir(exist_ok=True)

    for i, filing in enumerate(filings, 1):
        year = filing["reportDate"][:4]
        print(f"\n[{i}/{len(filings)}] FY{year} — period ending {filing['reportDate']}")

        # Try PDF first, fall back to SEC HTML
        result = annualreports_pdf(filing["company"], ticker, filing["reportDate"], out_dir)
        if not result:
            print(f"  Falling back to SEC EDGAR HTML...")
            result = sec_download(filing, out_dir)

        if not result:
            print(f"  ✗ All download attempts failed for FY{year}")

    print(f"\n{'='*60}")
    print(f"  Done. Files saved to: {out_dir}")
    print(f"{'='*60}\n")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Download actual 10-K filings (PDF or HTML)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python download_10k_scrape.py PLTR              # latest 10-K
  python download_10k_scrape.py PLTR 2024         # FY2024 only
  python download_10k_scrape.py AAPL 2023 -n 1   # 1 report for FY2023
  python download_10k_scrape.py MSFT -n 3         # 3 most recent
        """,
    )
    parser.add_argument("ticker",          help="Stock ticker (e.g. PLTR, AAPL)")
    parser.add_argument("year",  nargs="?", help="Fiscal year filter (e.g. 2024)")
    parser.add_argument("-n", "--number", type=int, default=1,
                        help="Number of reports to download (default: 1)")

    args = parser.parse_args()
    download_10k(args.ticker, args.year, args.number)


if __name__ == "__main__":
    main()
