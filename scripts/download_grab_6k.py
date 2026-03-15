#!/usr/bin/env python3
"""
Download all SEC filings (6-K PDFs) from Grab's investor relations page
"""

import requests
from bs4 import BeautifulSoup
import os
import time
import argparse
from urllib.parse import urljoin, urlparse
import re

def fetch_page(url):
    """Fetch the webpage with proper headers"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text

def extract_pdf_links(html_content, base_url):
    """Extract all PDF links from the HTML"""
    soup = BeautifulSoup(html_content, 'html.parser')
    pdf_links = []

    # Find all links
    for link in soup.find_all('a', href=True):
        href = link['href']

        # Check if it's a PDF link
        if href.endswith('.pdf') or '.pdf' in href.lower():
            # Make absolute URL
            absolute_url = urljoin(base_url, href)

            # Get link text or parent text for context
            link_text = link.get_text(strip=True)

            pdf_links.append({
                'url': absolute_url,
                'text': link_text
            })

    return pdf_links

def download_pdf(url, output_dir):
    """Download a PDF file"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    # Extract filename from URL
    parsed_url = urlparse(url)
    filename = os.path.basename(parsed_url.path)

    # If filename is generic or empty, use the last part of the path
    if not filename or filename == 'default.aspx':
        # Try to get from query params or generate from URL
        filename = parsed_url.path.split('/')[-1]
        if not filename.endswith('.pdf'):
            filename = url.split('/')[-1]
            if not filename.endswith('.pdf'):
                filename = f"filing_{hash(url)}.pdf"

    output_path = os.path.join(output_dir, filename)

    # Skip if already exists
    if os.path.exists(output_path):
        print(f"✓ Already exists: {filename}")
        return output_path

    try:
        response = requests.get(url, headers=headers, timeout=30, stream=True)
        response.raise_for_status()

        # Save the PDF
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"✓ Downloaded: {filename}")
        return output_path
    except Exception as e:
        print(f"✗ Failed to download {filename}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Download all PDFs from Grab investor relations')
    parser.add_argument('--output-dir', '-o', default='6-k/grab', help='Output directory')
    parser.add_argument('--url', default='https://investors.grab.com/financial-information/sec-filings/default.aspx', help='URL to fetch')
    args = parser.parse_args()

    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)

    print(f"Fetching page: {args.url}")
    try:
        html_content = fetch_page(args.url)
    except Exception as e:
        print(f"Error fetching page: {e}")
        return

    print("Extracting PDF links...")
    pdf_links = extract_pdf_links(html_content, args.url)

    if not pdf_links:
        print("No PDF links found on the page")
        return

    print(f"\nFound {len(pdf_links)} PDF links")
    print("-" * 60)

    downloaded = 0
    failed = 0

    for i, pdf_info in enumerate(pdf_links, 1):
        print(f"\n[{i}/{len(pdf_links)}] {pdf_info['text']}")
        print(f"URL: {pdf_info['url']}")

        result = download_pdf(pdf_info['url'], args.output_dir)
        if result:
            downloaded += 1
        else:
            failed += 1

        # Be nice to the server
        time.sleep(1)

    print("\n" + "=" * 60)
    print(f"Download complete!")
    print(f"✓ Successfully downloaded: {downloaded}")
    print(f"✗ Failed: {failed}")
    print(f"Output directory: {args.output_dir}")

if __name__ == '__main__':
    main()
