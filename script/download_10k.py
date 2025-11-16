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
            'User-Agent': f'Mozilla/5.0 (compatible; {email})',
            'Accept-Encoding': 'gzip, deflate',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }
        # Headers for data.sec.gov API calls
        self.api_headers = {
            'User-Agent': f'Company Name {email}',
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

        # Known ticker to CIK mappings (most common ones)
        # You can expand this dictionary as needed
        ticker_to_cik = {
            'AAPL': '0000320193',
            'MSFT': '0000789019',
            'GOOGL': '0001652044',
            'GOOG': '0001652044',
            'AMZN': '0001018724',
            'TSLA': '0001318605',
            'META': '0001326801',
            'NVDA': '0001045810',
            'JPM': '0000019617',
            'V': '0001403161',
            'WMT': '0000104169',
            'DIS': '0001744489',
            'NFLX': '0001065280',
            'PYPL': '0001633917',
            'INTC': '0000050863',
            'AMD': '0000002488',
            'ORCL': '0001341439',
            'IBM': '0000051143',
            'CSCO': '0000858877',
            'BA': '0000012927',
        }

        # Check if ticker is in our mapping
        if ticker in ticker_to_cik:
            return ticker_to_cik[ticker]

        # Try to fetch from SEC Edgar Search API
        try:
            # Use the SEC search API
            search_url = f"https://efts.sec.gov/LATEST/search-index"
            params = {
                'q': ticker,
                'dateRange': 'all',
                'category': 'form-cat1',  # Company filings
                'entityName': ticker
            }

            # Note: This endpoint may not always work, so we'll try an alternative
            # Alternative: Try to directly access submissions with the ticker
            # The SEC allows searching by ticker symbol in some cases

            print(f"Ticker {ticker} not in built-in list. Please add CIK manually or update ticker_to_cik dictionary.")
            print(f"You can find the CIK at: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={ticker}")
            return None

        except Exception as e:
            print(f"Error getting CIK for ticker {ticker}: {e}")
            print(f"You can find the CIK at: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={ticker}")
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
            response = requests.get(url, headers=self.api_headers)
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
        accession_number = filing_info['accessionNumber']
        accession = accession_number.replace('-', '')
        primary_doc = filing_info['primaryDocument']
        filing_date = filing_info['filingDate']

        # Extract CIK from accession number (format: CIK-YY-NNNNNN)
        # The CIK in the accession number is the filer's CIK for the URL path
        accession_cik = accession_number.split('-')[0].lstrip('0') or '0'

        # Construct download URL (use www.sec.gov for document downloads)
        url = f"https://www.sec.gov/Archives/edgar/data/{accession_cik}/{accession}/{primary_doc}"

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
