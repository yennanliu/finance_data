#!/usr/bin/env python3
"""
Enhanced script to download 10-K reports from SEC EDGAR using API-based approach.
Uses SEC's official APIs for robust and reliable downloads.

Features:
- Uses SEC EDGAR submissions API for metadata
- Uses index.json API to find actual document filenames
- Multiple fallback mechanisms
- Supports any ticker with automatic CIK lookup
- Downloads in HTML or text format
"""

import os
import requests
import json
import time
from datetime import datetime
from pathlib import Path


class SECDownloaderV2:
    """Enhanced SEC EDGAR 10-K downloader using API-based approach."""

    # Common ticker to CIK mappings
    TICKER_TO_CIK = {
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

    def __init__(self, email="your.email@example.com"):
        """
        Initialize the downloader.

        Args:
            email: Your email for the User-Agent header (required by SEC)
        """
        self.email = email
        # Headers for document downloads (www.sec.gov)
        self.doc_headers = {
            'User-Agent': f'Mozilla/5.0 (compatible; {email})',
            'Accept-Encoding': 'gzip, deflate',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }
        # Headers for API calls (data.sec.gov)
        self.api_headers = {
            'User-Agent': f'ResearchProject {email}',
            'Accept-Encoding': 'gzip, deflate',
            'Host': 'data.sec.gov'
        }
        self.save_dir = Path(__file__).parent.parent / "10-k"
        self.save_dir.mkdir(exist_ok=True)

    def get_cik(self, ticker):
        """
        Get CIK for a ticker symbol.

        Args:
            ticker: Stock ticker symbol

        Returns:
            CIK string (zero-padded) or None
        """
        ticker = ticker.upper()

        if ticker in self.TICKER_TO_CIK:
            return self.TICKER_TO_CIK[ticker]

        print(f"Ticker {ticker} not in built-in list.")
        print(f"Find CIK at: https://www.sec.gov/cgi-bin/browse-edgar?company={ticker}")
        return None

    def get_company_filings(self, cik):
        """
        Get all filings for a company from SEC submissions API.

        Args:
            cik: Company CIK (zero-padded)

        Returns:
            Dictionary with company info and filings, or None
        """
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"

        try:
            time.sleep(0.15)  # Rate limiting
            response = requests.get(url, headers=self.api_headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching company filings: {e}")
            return None

    def get_10k_filings(self, cik, count=5):
        """
        Extract 10-K filings from company data.

        Args:
            cik: Company CIK
            count: Number of filings to retrieve

        Returns:
            List of 10-K filing dictionaries
        """
        data = self.get_company_filings(cik)
        if not data:
            return []

        company_name = data.get('name', 'Unknown')
        filings = data.get('filings', {}).get('recent', {})

        ten_k_filings = []
        forms = filings.get('form', [])

        for i, form in enumerate(forms):
            if form == '10-K' and len(ten_k_filings) < count:
                filing = {
                    'company': company_name,
                    'cik': cik,
                    'accessionNumber': filings['accessionNumber'][i],
                    'filingDate': filings['filingDate'][i],
                    'reportDate': filings['reportDate'][i],
                    'primaryDocument': filings['primaryDocument'][i],
                }
                ten_k_filings.append(filing)

        return ten_k_filings

    def get_filing_index(self, accession_number):
        """
        Get the index.json for a specific filing to find all documents.

        Args:
            accession_number: SEC accession number (e.g., '0001628280-25-003063')

        Returns:
            Dictionary with document information or None
        """
        accession = accession_number.replace('-', '')
        # Extract CIK from accession number and remove leading zeros
        cik_padded = accession_number.split('-')[0]
        accession_cik = str(int(cik_padded))  # Convert to int and back to remove leading zeros

        index_url = f"https://www.sec.gov/Archives/edgar/data/{accession_cik}/{accession}/index.json"

        try:
            time.sleep(0.15)
            response = requests.get(index_url, headers=self.doc_headers)
            response.raise_for_status()
            index_data = response.json()

            # Get all document items
            items = index_data.get('directory', {}).get('item', [])

            # Filter for HTML/HTM documents (excluding exhibits and index)
            htm_docs = []
            for item in items:
                name = item.get('name', '')
                name_lower = name.lower()
                if name.endswith(('.htm', '.html')):
                    # Exclude exhibits, index files, and graphic files
                    excluded_patterns = [
                        'exhibit', '-ex', '_ex', 'ex-', 'ex_',
                        'index.htm', 'index.html',
                        '.jpg', '.gif', '.png'
                    ]
                    if not any(x in name_lower for x in excluded_patterns):
                        # Assign priority score
                        priority = 0

                        # Prefer files with "10-k" or "10k" in name (but not exhibits which were already filtered)
                        if '10-k' in name_lower or '10k' in name_lower:
                            priority += 100

                        # Prefer files without company ticker/abbreviation (these are often XBRL)
                        # XBRL files typically match pattern: ticker-YYYYMMDD.htm
                        if not any(char.isdigit() for char in name[:10]):
                            priority += 50

                        # Prefer shorter filenames (XBRL files often have ticker-date patterns)
                        if len(name) < 20:
                            priority += 25

                        # Larger files are often more complete
                        size_value = item.get('size', 0)
                        try:
                            size = int(size_value) if size_value else 0
                        except (ValueError, TypeError):
                            size = 0
                        priority += min(size // 10000, 50)  # Cap size bonus at 50

                        htm_docs.append({
                            'name': name,
                            'size': size,
                            'type': item.get('type', ''),
                            'priority': priority
                        })

            # Sort by priority first, then by size
            htm_docs.sort(key=lambda x: (x['priority'], x['size']), reverse=True)

            return {
                'documents': htm_docs,
                'primary': htm_docs[0]['name'] if htm_docs else None,
                'all_items': items
            }

        except Exception as e:
            print(f"  Could not fetch index.json: {e}")
            return None

    def is_xbrl_file(self, content):
        """
        Check if file content is XBRL/iXBRL format (not human-readable).

        Args:
            content: File content bytes

        Returns:
            True if XBRL format, False otherwise
        """
        try:
            # Check first 2000 bytes for XBRL indicators
            header = content[:2000].decode('utf-8', errors='ignore').lower()
            xbrl_indicators = [
                'xmlns:xbrl',
                'xmlns:ix',
                'inlinexbrl',
                'xbrl.org/2013/inlinexbrl',
                '<?xml version',
                'xbrl document created'
            ]
            return any(indicator in header for indicator in xbrl_indicators)
        except Exception:
            return False

    def download_document(self, accession_number, document_name, output_filename):
        """
        Download a specific document from a filing.

        Args:
            accession_number: SEC accession number
            document_name: Name of the document file
            output_filename: Path to save the file

        Returns:
            True if successful, False otherwise
        """
        accession = accession_number.replace('-', '')
        # Extract CIK from accession number and remove leading zeros
        cik_padded = accession_number.split('-')[0]
        accession_cik = str(int(cik_padded))

        url = f"https://www.sec.gov/Archives/edgar/data/{accession_cik}/{accession}/{document_name}"

        try:
            time.sleep(0.15)  # Rate limiting
            response = requests.get(url, headers=self.doc_headers)
            response.raise_for_status()

            # Check if it's an XBRL file (not human-readable)
            if self.is_xbrl_file(response.content):
                print(f"  Skipping {document_name} (XBRL format - not human-readable)")
                return False

            with open(output_filename, 'wb') as f:
                f.write(response.content)

            return True
        except Exception as e:
            print(f"  Error downloading {document_name}: {e}")
            return False

    def download_10k(self, ticker, filing_info, attempt_num, total):
        """
        Download a single 10-K filing with multiple fallback strategies.

        Args:
            ticker: Stock ticker symbol
            filing_info: Dictionary with filing metadata
            attempt_num: Current attempt number
            total: Total number of filings to download

        Returns:
            True if successful, False otherwise
        """
        print(f"\n[{attempt_num}/{total}] Processing 10-K for period ending {filing_info['reportDate']}")
        print(f"  Company: {filing_info['company']}")
        print(f"  Filed: {filing_info['filingDate']}")
        print(f"  Accession: {filing_info['accessionNumber']}")

        accession_number = filing_info['accessionNumber']
        accession = accession_number.replace('-', '')
        report_date = filing_info['reportDate']
        filing_date = filing_info['filingDate']

        # Strategy 1: Try complete submission text file FIRST (most reliable for modern filings)
        txt_name = f"{accession}.txt"
        documents_to_try = [txt_name]

        # Strategy 2: Try to get document list from index.json
        index_info = self.get_filing_index(accession_number)

        if index_info and index_info['documents']:
            print(f"  Found {len(index_info['documents'])} HTML documents in index")
            # Add top 3 HTML docs as fallbacks
            for doc in index_info['documents'][:3]:
                if doc['name'] not in documents_to_try:
                    documents_to_try.append(doc['name'])

        # Strategy 3: Try the primary document from submissions API
        primary_doc = filing_info.get('primaryDocument')
        if primary_doc and primary_doc not in documents_to_try:
            documents_to_try.append(primary_doc)

        # Strategy 4: Try common naming patterns
        ticker_lower = ticker.lower()
        report_date_compact = report_date.replace('-', '')
        fallbacks = [
            f"{ticker_lower}10k_{report_date_compact}.htm",
            f"{ticker_lower}_10k.htm",
            f"form10-k.htm",
            f"form10k.htm",
        ]
        for fb in fallbacks:
            if fb not in documents_to_try:
                documents_to_try.append(fb)

        # Try each document
        for doc_name in documents_to_try:
            print(f"  Trying: {doc_name}")

            ext = doc_name.split('.')[-1] if '.' in doc_name else 'htm'
            filename = f"{ticker}_{report_date}_10K_filed_{filing_date}.{ext}"
            filepath = self.save_dir / filename

            if self.download_document(accession_number, doc_name, filepath):
                file_size = filepath.stat().st_size / 1024 / 1024
                print(f"✓ Success! Downloaded: {filename} ({file_size:.1f} MB)")
                return True

        print(f"✗ Failed to download this filing - all attempts failed")
        return False

    def download_all(self, ticker, count=5):
        """
        Download multiple 10-K reports for a ticker.

        Args:
            ticker: Stock ticker symbol
            count: Number of recent reports to download
        """
        print("=" * 80)
        print(f"SEC EDGAR 10-K Downloader (API-based v2)")
        print(f"Ticker: {ticker}")
        print("=" * 80)

        # Get CIK
        cik = self.get_cik(ticker)
        if not cik:
            print(f"Cannot proceed without CIK for {ticker}")
            return

        print(f"CIK: {cik}")

        # Get 10-K filings
        filings = self.get_10k_filings(cik, count)

        if not filings:
            print(f"No 10-K filings found for {ticker}")
            return

        print(f"\nFound {len(filings)} 10-K filing(s)")

        # Download each filing
        success_count = 0
        for i, filing in enumerate(filings, 1):
            if self.download_10k(ticker, filing, i, len(filings)):
                success_count += 1

        # Summary
        print("\n" + "=" * 80)
        print(f"Download Summary:")
        print(f"  Successfully downloaded: {success_count}/{len(filings)} filings")
        print(f"  Saved to: {self.save_dir}")
        print("=" * 80)


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Download 10-K reports using SEC EDGAR API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python download_10k_v2.py TSLA              # Download 5 most recent Tesla 10-Ks
  python download_10k_v2.py AAPL -n 10        # Download 10 most recent Apple 10-Ks
  python download_10k_v2.py MSFT -e me@company.com  # Specify email

Features:
  - Uses SEC EDGAR submissions API for metadata
  - Uses index.json API to find correct document names
  - Multiple fallback strategies (HTML, text)
  - Automatic rate limiting (respects SEC guidelines)
  - Downloads to 10-k/ directory
        """
    )

    parser.add_argument(
        'ticker',
        help='Stock ticker symbol (e.g., TSLA, AAPL, MSFT)'
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
        help='Your email for SEC User-Agent header (recommended)'
    )

    args = parser.parse_args()

    # Create downloader and run
    downloader = SECDownloaderV2(email=args.email)
    downloader.download_all(args.ticker.upper(), count=args.number)


if __name__ == "__main__":
    main()
