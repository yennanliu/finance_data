#!/usr/bin/env python3
"""
Download all SEC filings (6-K PDFs) from Grab's investor relations page using Selenium
"""

import os
import time
import argparse
import requests
from urllib.parse import urljoin

def download_with_selenium():
    """Use Selenium to bypass Cloudflare and get the page"""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        print("Error: selenium and webdriver-manager are required")
        print("Install with: uv add selenium webdriver-manager")
        return None

    # Setup Chrome options
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    try:
        # Initialize the driver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        url = 'https://investors.grab.com/financial-information/sec-filings/default.aspx'
        print(f"Loading page: {url}")
        driver.get(url)

        # Wait for page to load (Cloudflare challenge may take time)
        print("Waiting for page to load (bypassing Cloudflare)...")
        time.sleep(10)  # Give Cloudflare time to process

        # Try to wait for specific content to load
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except:
            pass

        # Get the page source
        html_content = driver.page_source

        # Find all links
        links = driver.find_elements(By.TAG_NAME, "a")

        pdf_links = []
        for link in links:
            try:
                href = link.get_attribute('href')
                text = link.text.strip()

                if href and ('.pdf' in href.lower() or 'sec.gov' in href.lower()):
                    pdf_links.append({
                        'url': href,
                        'text': text
                    })
            except:
                continue

        driver.quit()

        return pdf_links

    except Exception as e:
        print(f"Error with Selenium: {e}")
        return None

def download_pdf(url, output_dir, filename=None):
    """Download a PDF file"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    if not filename:
        # Extract filename from URL
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
    parser = argparse.ArgumentParser(description='Download all PDFs from Grab investor relations using Selenium')
    parser.add_argument('--output-dir', '-o', default='6-k/grab', help='Output directory')
    args = parser.parse_args()

    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)

    print("=" * 60)
    print("Grabbing PDF links using Selenium...")
    print("=" * 60)

    pdf_links = download_with_selenium()

    if not pdf_links:
        print("\nNo PDF links found or error occurred")
        return

    print(f"\n{'=' * 60}")
    print(f"Found {len(pdf_links)} PDF links")
    print(f"{'=' * 60}\n")

    # Display all links
    for i, pdf_info in enumerate(pdf_links, 1):
        print(f"{i}. {pdf_info['text']}")
        print(f"   URL: {pdf_info['url']}")

    print(f"\n{'=' * 60}")
    print("Starting downloads...")
    print(f"{'=' * 60}\n")

    downloaded = 0
    failed = 0

    for i, pdf_info in enumerate(pdf_links, 1):
        print(f"\n[{i}/{len(pdf_links)}] {pdf_info['text']}")

        result = download_pdf(pdf_info['url'], args.output_dir)
        if result:
            downloaded += 1
        else:
            failed += 1

        # Be nice to the server
        time.sleep(2)

    print(f"\n{'=' * 60}")
    print(f"Download complete!")
    print(f"✓ Successfully downloaded: {downloaded}")
    print(f"✗ Failed: {failed}")
    print(f"Output directory: {args.output_dir}")
    print(f"{'=' * 60}")

if __name__ == '__main__':
    main()
