#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["requests", "beautifulsoup4"]
# ///
"""Download recent 10-K PDFs from annualreports.com."""

import argparse
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.annualreports.com"
SAVE_DIR = Path(__file__).parent.parent / "10-k"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
}


def fetch_page(company_slug):
    url = f"{BASE_URL}/Company/{company_slug}"
    print(f"Fetching: {url}")
    time.sleep(1)
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except requests.exceptions.HTTPError as e:
        print(f"HTTP {e.response.status_code}: company '{company_slug}' not found")
    except Exception as e:
        print(f"Error fetching page: {e}")
    return None


def extract_pdf_links(soup):
    seen, links = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "HostedData/AnnualReportArchive" in href and href.endswith(".pdf"):
            m = re.search(r"_(\d{4})\.pdf", href)
            if m and href not in seen:
                seen.add(href)
                links.append((int(m.group(1)), urljoin(BASE_URL, href)))
    return sorted(links, reverse=True)  # newest first


def select_years(links, start_year=None, end_year=None):
    """Keep (year, url) pairs within the inclusive [start_year, end_year] window.

    Either bound may be None (open-ended). Filtering is purely value-based — it
    never depends on the current date, so recent reports are not dropped just
    because the archive lags the calendar year. Input order is preserved.
    """
    return [
        (yr, url) for yr, url in links
        if (start_year is None or yr >= start_year)
        and (end_year is None or yr <= end_year)
    ]


def _window_label(start_year=None, end_year=None):
    """Human-readable description of an inclusive year window for log messages."""
    if start_year and end_year:
        return f" for {start_year}–{end_year}"
    if start_year:
        return f" since {start_year}"
    if end_year:
        return f" up to {end_year}"
    return ""


def parse_company_name(soup, fallback):
    title = soup.find("title")
    if not title:
        return fallback
    # Title is "<Company> - AnnualReports.com" (older pages used " | " instead).
    name = re.split(r"\s*[|-]\s*AnnualReports\.com", title.text, flags=re.I)[0]
    name = re.sub(r"[^\w\s-]", "", name).strip()  # drop punctuation like "."
    name = re.sub(r"\s+", "_", name)
    return name or fallback


def download_pdf(url, filepath):
    print(f"  Downloading: {url}")
    time.sleep(1.5)
    try:
        r = requests.get(url, headers=HEADERS, timeout=60, stream=True)
        r.raise_for_status()
        with open(filepath, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        print(f"  ✓ {filepath.name} ({filepath.stat().st_size / 1e6:.1f} MB)")
        return True
    except Exception as e:
        print(f"  ✗ {e}")
        filepath.unlink(missing_ok=True)
        return False


def download_10k(company_slug, start_year=None, end_year=None):
    soup = fetch_page(company_slug)
    if not soup:
        return False

    name = parse_company_name(soup, company_slug)
    company_dir = SAVE_DIR / name
    company_dir.mkdir(parents=True, exist_ok=True)
    print(f"Company: {name} | Dir: {company_dir}")

    links = select_years(extract_pdf_links(soup), start_year, end_year)
    if not links:
        print(f"No reports found{_window_label(start_year, end_year)}")
        return True

    print(f"\nFound {len(links)} report(s):")
    ok = 0
    for i, (yr, url) in enumerate(links, 1):
        filepath = company_dir / f"{name}_{yr}_10K.pdf"
        print(f"\n[{i}/{len(links)}] {yr}")
        if filepath.exists():
            print(f"  ⊘ Already exists ({filepath.stat().st_size / 1e6:.1f} MB), skipping")
            ok += 1
            continue
        if download_pdf(url, filepath):
            ok += 1

    print(f"\nDone: {ok}/{len(links)} reports in {company_dir}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Download 10-K PDFs from annualreports.com")
    parser.add_argument("company_slug", help="Company URL slug (e.g., apple-inc)")
    parser.add_argument("--start-year", type=int,
                        help="Earliest report year to download (inclusive)")
    parser.add_argument("--end-year", type=int,
                        help="Latest report year to download (inclusive)")
    args = parser.parse_args()
    if args.start_year and args.end_year and args.start_year > args.end_year:
        parser.error("--start-year cannot be greater than --end-year")
    download_10k(args.company_slug, args.start_year, args.end_year)


if __name__ == "__main__":
    main()
