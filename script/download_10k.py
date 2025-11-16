#!/usr/bin/env python3
"""
Script to download 10-K reports from SEC EDGAR database.
Saves reports to the 10-k directory.
"""

import os
import requests
import json
import time
from datetime import datetime
from pathlib import Path


class SECDownloader:
    """Class to handle SEC EDGAR 10-K report downloads."""

    def __init__(self, email="your.email@example.com"):
        """
        Initialize the SEC downloader.

        Args:
            email: Your email for the User-Agent header (required by SEC)
        """
        self.base_url = "https://data.sec.gov"
        self.headers = {
            'User-Agent': f'{email}',
            'Accept-Encoding': 'gzip, deflate',
            'Host': 'data.sec.gov'
        }
        self.save_dir = Path(__file__).parent.parent / "10-k"
        self.save_dir.mkdir(exist_ok=True)

    def get_cik_from_ticker(self, ticker):
        """
        Get CIK number from ticker symbol.

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')

        Returns:
            CIK number as string (zero-padded to 10 digits)
        """
        ticker = ticker.upper()
        url = f"{self.base_url}/submissions/CIK{ticker}.json"

        try:
            # First, get the ticker to CIK mapping
            ticker_url = "https://www.sec.gov/files/company_tickers.json"
            response = requests.get(ticker_url, headers=self.headers)
            response.raise_for_status()

            companies = response.json()

            for company in companies.values():
                if company['ticker'] == ticker:
                    cik = str(company['cik_str']).zfill(10)
                    return cik

            print(f"Ticker {ticker} not found")
            return None

        except Exception as e:
            print(f"Error getting CIK for ticker {ticker}: {e}")
            return None

    def get_10k_filings(self, cik, count=5):
        """
        Get list of 10-K filings for a company.

        Args:
            cik: CIK number (zero-padded to 10 digits)
            count: Number of recent filings to retrieve

        Returns:
            List of filing information dictionaries
        """
        url = f"{self.base_url}/submissions/CIK{cik}.json"

        try:
            time.sleep(0.1)  # Rate limiting - SEC recommends no more than 10 requests per second
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()

            data = response.json()
            filings = data.get('filings', {}).get('recent', {})

            # Extract 10-K filings
            ten_k_filings = []
            forms = filings.get('form', [])

            for i, form in enumerate(forms):
                if form == '10-K' and len(ten_k_filings) < count:
                    filing_info = {
                        'accessionNumber': filings['accessionNumber'][i],
                        'filingDate': filings['filingDate'][i],
                        'reportDate': filings['reportDate'][i],
                        'primaryDocument': filings['primaryDocument'][i],
                        'company': data.get('name', 'Unknown')
                    }
                    ten_k_filings.append(filing_info)

            return ten_k_filings

        except Exception as e:
            print(f"Error getting filings for CIK {cik}: {e}")
            return []

    def download_filing(self, cik, filing_info, ticker):
        """
        Download a specific 10-K filing.

        Args:
            cik: CIK number
            filing_info: Dictionary with filing information
            ticker: Stock ticker symbol
        """
        accession = filing_info['accessionNumber'].replace('-', '')
        primary_doc = filing_info['primaryDocument']
        filing_date = filing_info['filingDate']

        # Construct download URL
        url = f"{self.base_url}/Archives/edgar/data/{int(cik)}/{accession}/{primary_doc}"

        # Create filename
        filename = f"{ticker}_{filing_date}_10K.html"
        filepath = self.save_dir / filename

        try:
            time.sleep(0.1)  # Rate limiting
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()

            # Save the file
            with open(filepath, 'wb') as f:
                f.write(response.content)

            print(f"✓ Downloaded: {filename}")
            return True

        except Exception as e:
            print(f"✗ Error downloading {filename}: {e}")
            return False

    def download_10k_by_ticker(self, ticker, count=5):
        """
        Download 10-K reports for a given ticker symbol.

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')
            count: Number of recent 10-K reports to download (default: 5)
        """
        print(f"\nDownloading 10-K reports for {ticker}...")
        print("=" * 50)

        # Get CIK
        cik = self.get_cik_from_ticker(ticker)
        if not cik:
            return

        print(f"CIK: {cik}")

        # Get filings
        filings = self.get_10k_filings(cik, count)

        if not filings:
            print(f"No 10-K filings found for {ticker}")
            return

        print(f"Found {len(filings)} 10-K filing(s)")
        print()

        # Download each filing
        success_count = 0
        for filing in filings:
            if self.download_filing(cik, filing, ticker):
                success_count += 1

        print()
        print(f"Successfully downloaded {success_count}/{len(filings)} filings")
        print(f"Saved to: {self.save_dir}")


def main():
    """Main function to run the downloader."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Download 10-K reports from SEC EDGAR',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python download_10k.py AAPL           # Download 5 most recent 10-K reports for Apple
  python download_10k.py AAPL -n 10     # Download 10 most recent reports
  python download_10k.py AAPL MSFT TSLA # Download reports for multiple companies
  python download_10k.py AAPL -e your.email@example.com  # Specify your email
        """
    )

    parser.add_argument(
        'tickers',
        nargs='+',
        help='Stock ticker symbol(s) (e.g., AAPL, MSFT, TSLA)'
    )

    parser.add_argument(
        '-n', '--number',
        type=int,
        default=5,
        help='Number of recent 10-K reports to download (default: 5)'
    )

    parser.add_argument(
        '-e', '--email',
        type=str,
        default='user@example.com',
        help='Your email address for SEC User-Agent header'
    )

    args = parser.parse_args()

    # Create downloader
    downloader = SECDownloader(email=args.email)

    # Download for each ticker
    for ticker in args.tickers:
        downloader.download_10k_by_ticker(ticker.upper(), count=args.number)
        time.sleep(0.5)  # Pause between different companies

    print("\n" + "=" * 50)
    print("Download complete!")


if __name__ == "__main__":
    main()
