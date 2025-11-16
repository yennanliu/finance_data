#!/usr/bin/env python3
"""
Script to download 10-K PDF reports from annualreports.com.

This script scrapes annualreports.com to find and download all available
10-K annual reports in PDF format for a given company.

Features:
- Scrapes company annual reports page
- Finds all available 10-K PDFs
- Downloads PDFs to organized directory structure
- Supports resume on failed downloads
- Rate limiting to be respectful to the website

Usage:
    python download_10k_pdf.py apple-inc
    python download_10k_pdf.py tesla-inc -n 5
    python download_10k_pdf.py microsoft-corporation --start-year 2020
"""

import os
import requests
import time
import re
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


class AnnualReportsPDFDownloader:
    """Download 10-K PDFs from annualreports.com."""

    def __init__(self, base_url="https://www.annualreports.com"):
        """
        Initialize the downloader.

        Args:
            base_url: Base URL for annualreports.com
        """
        self.base_url = base_url
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        self.save_dir = Path(__file__).parent.parent / "10-k"
        self.save_dir.mkdir(exist_ok=True)

    def get_company_page(self, company_slug):
        """
        Fetch the company's annual reports page.

        Args:
            company_slug: Company URL slug (e.g., 'apple-inc')

        Returns:
            BeautifulSoup object or None
        """
        url = f"{self.base_url}/Company/{company_slug}"

        try:
            print(f"Fetching company page: {url}")
            time.sleep(1)  # Rate limiting
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()

            return BeautifulSoup(response.text, 'html.parser')

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print(f"Error: Company '{company_slug}' not found")
                print(f"Make sure you're using the correct company slug from the URL")
            else:
                print(f"HTTP Error: {e}")
            return None
        except Exception as e:
            print(f"Error fetching company page: {e}")
            return None

    def extract_pdf_links(self, soup, company_slug):
        """
        Extract all PDF links from the company page.

        Args:
            soup: BeautifulSoup object
            company_slug: Company URL slug

        Returns:
            List of tuples: [(year, pdf_url, title), ...]
        """
        pdf_links = []

        # Pattern 1: Find direct PDF links in HostedData directory
        # Format: /HostedData/AnnualReportArchive/a/NASDAQ_AAPL_2023.pdf
        for link in soup.find_all('a', href=True):
            href = link['href']

            # Look for PDF links
            if 'HostedData/AnnualReportArchive' in href and href.endswith('.pdf'):
                # Extract year from filename (e.g., NASDAQ_AAPL_2023.pdf)
                year_match = re.search(r'_(\d{4})\.pdf', href)
                if year_match:
                    year = year_match.group(1)
                    pdf_url = urljoin(self.base_url, href)
                    title = link.get_text(strip=True) or f"Annual Report {year}"
                    pdf_links.append((year, pdf_url, title))

        # Pattern 2: Look for download links with specific patterns
        # Some sites might have "Download" or "View PDF" buttons
        for link in soup.find_all('a', string=re.compile(r'(Download|View|PDF)', re.I)):
            href = link['href']
            if href.endswith('.pdf'):
                # Try to extract year from nearby text or link text
                year_match = re.search(r'20\d{2}|19\d{2}', link.get_text() + str(link.parent))
                if year_match:
                    year = year_match.group(0)
                    pdf_url = urljoin(self.base_url, href)
                    title = link.get_text(strip=True) or f"Annual Report {year}"
                    pdf_links.append((year, pdf_url, title))

        # Remove duplicates while preserving order
        seen = set()
        unique_links = []
        for year, url, title in pdf_links:
            if (year, url) not in seen:
                seen.add((year, url))
                unique_links.append((year, url, title))

        # Sort by year (newest first)
        unique_links.sort(key=lambda x: x[0], reverse=True)

        return unique_links

    def download_pdf(self, url, filepath):
        """
        Download a PDF file.

        Args:
            url: URL of the PDF
            filepath: Path to save the file

        Returns:
            True if successful, False otherwise
        """
        try:
            print(f"  Downloading: {url}")
            time.sleep(1.5)  # Rate limiting

            response = requests.get(url, headers=self.headers, timeout=60, stream=True)
            response.raise_for_status()

            # Check if response is actually a PDF
            content_type = response.headers.get('content-type', '')
            if 'pdf' not in content_type.lower() and not url.endswith('.pdf'):
                print(f"  Warning: Response might not be a PDF (content-type: {content_type})")

            # Download with progress
            total_size = int(response.headers.get('content-length', 0))

            with open(filepath, 'wb') as f:
                if total_size == 0:
                    f.write(response.content)
                else:
                    downloaded = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

            file_size = filepath.stat().st_size / 1024 / 1024
            print(f"  ✓ Downloaded: {filepath.name} ({file_size:.1f} MB)")
            return True

        except Exception as e:
            print(f"  ✗ Error downloading: {e}")
            if filepath.exists():
                filepath.unlink()  # Remove partial download
            return False

    def download_all(self, company_slug, max_count=None, start_year=None, end_year=None):
        """
        Download all available 10-K PDFs for a company.

        Args:
            company_slug: Company URL slug (e.g., 'apple-inc')
            max_count: Maximum number of reports to download (None = all)
            start_year: Only download reports from this year onwards
            end_year: Only download reports up to this year
        """
        print("=" * 80)
        print(f"10-K PDF Downloader - annualreports.com")
        print(f"Company: {company_slug}")
        print("=" * 80)

        # Fetch company page
        soup = self.get_company_page(company_slug)
        if not soup:
            return

        # Extract company name from page
        company_name = company_slug
        title_tag = soup.find('title')
        if title_tag:
            # Extract company name from title (usually "Apple Inc. | AnnualReports.com")
            match = re.match(r'^([^|]+)', title_tag.text.strip())
            if match:
                company_name = match.group(1).strip()
                # Remove special chars and extra text
                company_name = re.sub(r'AnnualReports\.com', '', company_name, flags=re.I)
                company_name = re.sub(r'[^\w\s-]', '', company_name)  # Remove special chars
                company_name = company_name.strip()
                company_name = re.sub(r'\s+', '_', company_name)  # Replace spaces with underscore

        print(f"Company Name: {company_name}")

        # Create company-specific directory
        company_dir = self.save_dir / company_name
        company_dir.mkdir(exist_ok=True)
        print(f"Save Directory: {company_dir}")

        # Extract PDF links
        print("\nSearching for available reports...")
        pdf_links = self.extract_pdf_links(soup, company_slug)

        if not pdf_links:
            print("No PDF reports found on this page")
            print("\nTip: Make sure the company has reports available at:")
            print(f"  {self.base_url}/Company/{company_slug}")
            return

        # Filter by year if specified
        if start_year or end_year:
            original_count = len(pdf_links)
            pdf_links = [
                (year, url, title) for year, url, title in pdf_links
                if (not start_year or int(year) >= int(start_year)) and
                   (not end_year or int(year) <= int(end_year))
            ]
            print(f"Filtered by year: {len(pdf_links)}/{original_count} reports")

        # Limit count if specified
        if max_count:
            pdf_links = pdf_links[:max_count]

        print(f"\nFound {len(pdf_links)} report(s) to download:")
        for year, url, title in pdf_links:
            print(f"  - {year}: {title}")

        # Download each PDF
        print(f"\nDownloading reports...")
        success_count = 0

        for i, (year, url, title) in enumerate(pdf_links, 1):
            print(f"\n[{i}/{len(pdf_links)}] {year} - {title}")

            # Create filename
            filename = f"{company_name}_{year}_10K.pdf"
            filepath = company_dir / filename

            # Skip if already exists
            if filepath.exists():
                file_size = filepath.stat().st_size / 1024 / 1024
                print(f"  ⊘ Already exists: {filename} ({file_size:.1f} MB)")
                success_count += 1
                continue

            # Download
            if self.download_pdf(url, filepath):
                success_count += 1

        # Summary
        print("\n" + "=" * 80)
        print(f"Download Summary:")
        print(f"  Successfully downloaded: {success_count}/{len(pdf_links)} reports")
        print(f"  Saved to: {company_dir}")
        print("=" * 80)


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Download 10-K PDFs from annualreports.com',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python download_10k_pdf.py apple-inc
  python download_10k_pdf.py apple-inc -n 5
  python download_10k_pdf.py tesla-inc --start-year 2020
  python download_10k_pdf.py microsoft-corporation --start-year 2018 --end-year 2022

Finding company slugs:
  1. Go to https://www.annualreports.com
  2. Search for your company
  3. The slug is in the URL: /Company/{slug}

  Examples:
    - Apple Inc: apple-inc
    - Tesla Inc: tesla-inc
    - Microsoft Corporation: microsoft-corporation
    - Alphabet Inc: alphabet-inc
        """
    )

    parser.add_argument(
        'company_slug',
        help='Company URL slug (e.g., apple-inc, tesla-inc)'
    )

    parser.add_argument(
        '-n', '--number',
        type=int,
        default=None,
        help='Maximum number of reports to download (default: all)'
    )

    parser.add_argument(
        '--start-year',
        type=int,
        default=None,
        help='Only download reports from this year onwards'
    )

    parser.add_argument(
        '--end-year',
        type=int,
        default=None,
        help='Only download reports up to this year'
    )

    args = parser.parse_args()

    # Create downloader and run
    downloader = AnnualReportsPDFDownloader()
    downloader.download_all(
        args.company_slug,
        max_count=args.number,
        start_year=args.start_year,
        end_year=args.end_year
    )


if __name__ == "__main__":
    main()
