#!/usr/bin/env python3
"""
Download actual 10-K filings for a stock ticker.

Strategy (in order):
  1. annualreports.com  → PDF  (best for human reading)
  2. SEC EDGAR API      → HTML (official source, always available)

The ticker is resolved to a CIK via SEC's live company-lookup API.

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
from typing import List, Optional, Tuple

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


def _month(report_date: str) -> str:
    return report_date[5:7] if len(report_date) >= 7 else "12"


def lookup_cik(ticker: str) -> Optional[str]:
    """Resolve ticker → zero-padded CIK via SEC company-tickers API."""
    try:
        time.sleep(0.3)
        r = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=HEADERS_SEC, timeout=10,
        )
        r.raise_for_status()
        for entry in r.json().values():
            if entry["ticker"].upper() == ticker:
                return str(entry["cik_str"]).zfill(10)
    except Exception as e:
        print(f"  [warn] CIK lookup failed: {e}")
    return None


def get_10k_filings(cik: str, year_filter: Optional[str], count: int) -> List[dict]:
    """Return up to `count` 10-K filings from SEC submissions API."""
    try:
        time.sleep(0.3)
        r = requests.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            headers=HEADERS_SEC, timeout=15,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  [error] SEC submissions API: {e}")
        return []

    company_name = data.get("name", "Unknown")
    recent = data.get("filings", {}).get("recent", {})

    results = []
    for i, form in enumerate(recent.get("form", [])):
        if form != "10-K":
            continue
        report_date = recent["reportDate"][i]
        if year_filter and not report_date.startswith(year_filter):
            continue
        results.append({
            "company":         company_name,
            "cik":             cik,
            "reportDate":      report_date,
            "filingDate":      recent["filingDate"][i],
            "accessionNumber": recent["accessionNumber"][i],
            "primaryDocument": recent["primaryDocument"][i],
        })
        if len(results) >= count:
            break

    return results


def sec_download(filing: dict, out_dir: Path) -> Optional[Path]:
    """Download the 10-K HTML from SEC EDGAR archives."""
    accession = filing["accessionNumber"].replace("-", "")
    cik_int   = str(int(filing["cik"]))
    doc_name  = filing["primaryDocument"]
    url       = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession}/{doc_name}"

    year = filing["reportDate"][:4]
    mon  = _month(filing["reportDate"])
    ext  = doc_name.rsplit(".", 1)[-1] if "." in doc_name else "htm"
    filepath = out_dir / f"{out_dir.name}_{year}_{mon}.{ext}"

    if filepath.exists():
        print(f"  ⊘ Already exists: {filepath.name}")
        return filepath

    try:
        time.sleep(0.5)
        r = requests.get(url, headers=HEADERS_SEC, timeout=30)
        r.raise_for_status()
        filepath.write_bytes(r.content)
        print(f"  ✓ SEC HTML: {filepath.name}  ({filepath.stat().st_size/1024/1024:.1f} MB)")
        return filepath
    except Exception as e:
        print(f"  ✗ SEC download failed: {e}")
        return None


def _ar_fetch_pdfs(ticker: str) -> Tuple[Optional[str], List[Tuple[str, str]]]:
    """
    Fetch annualreports.com once for this ticker.
    Returns (slug, [(year, pdf_url), ...]) sorted newest-first.
    """
    try:
        time.sleep(0.5)
        r = requests.get(
            f"https://www.annualreports.com/Companies?search={ticker}",
            headers=HEADERS_BROWSER, timeout=10,
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        slug = next(
            (a["href"].split("/Company/")[1].strip("/")
             for a in soup.find_all("a", href=True)
             if a["href"].startswith("/Company/")),
            None,
        )
    except Exception as e:
        print(f"  [warn] annualreports.com search failed: {e}")
        return None, []

    if not slug:
        return None, []

    try:
        time.sleep(1)
        r = requests.get(
            f"https://www.annualreports.com/Company/{slug}",
            headers=HEADERS_BROWSER, timeout=15,
        )
        if r.status_code == 404:
            return slug, []
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        seen, pdfs = set(), []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "HostedData/AnnualReportArchive" in href and href.endswith(".pdf") and href not in seen:
                seen.add(href)
                m = re.search(r"_(\d{4})\.pdf", href)
                if m:
                    full = f"https://www.annualreports.com{href}" if href.startswith("/") else href
                    pdfs.append((m.group(1), full))

        pdfs.sort(key=lambda x: x[0], reverse=True)
        return slug, pdfs
    except Exception as e:
        print(f"  [warn] annualreports.com company page failed: {e}")
        return slug, []


def annualreports_pdf(
    ticker: str,
    report_date: str,
    out_dir: Path,
    all_pdfs: List[Tuple[str, str]],
) -> Optional[Path]:
    """Download a PDF from the pre-fetched annualreports.com list."""
    if not all_pdfs:
        return None

    target_year = report_date[:4]
    mon = _month(report_date)

    pdf_url, actual_year = None, None
    for yr, u in all_pdfs:
        if yr == target_year:
            pdf_url, actual_year = u, yr
            break
    if not pdf_url:
        actual_year, pdf_url = all_pdfs[0]
        print(f"  [info] Year {target_year} not found; using latest available: {actual_year}")

    filepath = out_dir / f"{ticker}_{actual_year}_{mon}.pdf"
    if filepath.exists():
        print(f"  ⊘ Already exists: {filepath.name}")
        return filepath

    try:
        print(f"  Downloading PDF: {pdf_url}")
        time.sleep(1.5)
        r = requests.get(pdf_url, headers=HEADERS_BROWSER, timeout=60, stream=True)
        r.raise_for_status()
        with open(filepath, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"  ✓ PDF: {filepath.name}  ({filepath.stat().st_size/1024/1024:.1f} MB)")
        return filepath
    except Exception as e:
        print(f"  ✗ annualreports.com download failed: {e}")
        return None


def download_10k(ticker: str, year_filter: Optional[str], count: int) -> None:
    ticker = ticker.upper()
    print(f"\n{'='*60}")
    print(f"  10-K Downloader  —  {ticker}" + (f"  FY{year_filter}" if year_filter else ""))
    print(f"{'='*60}")

    print(f"\nLooking up CIK for {ticker}...")
    cik = lookup_cik(ticker)
    if not cik:
        print(f"  [error] Could not resolve CIK for {ticker}")
        return
    print(f"  CIK: {cik}")

    filings = get_10k_filings(cik, year_filter, count)
    if not filings:
        print(f"  No 10-K filings found" + (f" for {year_filter}" if year_filter else ""))
        return

    print(f"\n  Found {len(filings)} filing(s):")
    for f in filings:
        print(f"    • {f['reportDate']}  (filed {f['filingDate']})  —  {f['company']}")

    out_dir = SAVE_DIR / ticker
    out_dir.mkdir(exist_ok=True)

    print(f"\nFetching annualreports.com PDF list for {ticker}...")
    _, all_pdfs = _ar_fetch_pdfs(ticker)
    if all_pdfs:
        print(f"  Found {len(all_pdfs)} PDF(s): {', '.join(yr for yr, _ in all_pdfs)}")
    else:
        print(f"  No PDFs found; will use SEC EDGAR HTML.")

    for i, filing in enumerate(filings, 1):
        year = filing["reportDate"][:4]
        print(f"\n[{i}/{len(filings)}] FY{year} — period ending {filing['reportDate']}")

        result = annualreports_pdf(ticker, filing["reportDate"], out_dir, all_pdfs)
        if not result:
            print(f"  Falling back to SEC EDGAR HTML...")
            result = sec_download(filing, out_dir)
        if not result:
            print(f"  ✗ All download attempts failed for FY{year}")

    print(f"\n{'='*60}")
    print(f"  Done. Files saved to: {out_dir}")
    print(f"{'='*60}\n")


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
    parser.add_argument("ticker",           help="Stock ticker (e.g. PLTR, AAPL)")
    parser.add_argument("year",  nargs="?", help="Fiscal year filter (e.g. 2024)")
    parser.add_argument("-n", "--number", type=int, default=1,
                        help="Number of reports to download (default: 1)")

    args = parser.parse_args()
    download_10k(args.ticker, args.year, args.number)


if __name__ == "__main__":
    main()
