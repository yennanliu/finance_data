#!/usr/bin/env python3
"""Shared SEC EDGAR plumbing for the ``download_10k_edgar`` / ``download_10q_edgar`` CLIs.

Everything here is filing-type agnostic: ticker→CIK lookup, submissions
enumeration (including the paginated archive blocks), locating the best
document inside a filing, and the HTML→PDF conversion.

What the two CLIs keep for themselves is only what genuinely differs — the
form they ask for, where the PDFs land, and how files are named:

* Annuals can be keyed by filing year, since there is at most one per year.
* Quarterlies cannot — a calendar year holds three 10-Qs — so they are keyed
  by the period covered. 6-K is keyed by filing date, since several 6-Ks can
  share one period.

This module is imported, never run directly, so it declares no PEP 723
dependency block; the entry scripts declare ``requests`` and ``playwright``
for it.
"""

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

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


def _matching_filings(block, form_type, cutoff):
    """Pull the (date, period, accession, primary_doc) of every filing of
    ``form_type`` filed in or after ``cutoff`` from one submissions block
    (arrays keyed by column)."""
    out = []
    periods = block.get("reportDate", [])
    for i, form in enumerate(block.get("form", [])):
        if form == form_type and int(block["filingDate"][i][:4]) >= cutoff:
            # reportDate is the period the filing covers. It is occasionally
            # blank, in which case the filing date is the best stand-in.
            period = periods[i] if i < len(periods) and periods[i] else block["filingDate"][i]
            out.append({
                "date": block["filingDate"][i],
                "period": period,
                "accession": block["accessionNumber"][i],
                "primary_doc": block["primaryDocument"][i],
            })
    return out


def get_filings(cik, form_type, years):
    r = requests.get(f"{DATA_URL}/submissions/CIK{cik}.json", headers=HEADERS, timeout=30)
    r.raise_for_status()
    filings = r.json()["filings"]
    cutoff = datetime.now().year - years + 1

    results = _matching_filings(filings["recent"], form_type, cutoff)

    # The "recent" block holds only ~1000 filings; high-volume filers (e.g. GOOG,
    # META) page older filings into separate archive files. Fetch those too when
    # the requested window reaches back beyond what "recent" covers.
    recent_dates = [d for d in filings["recent"].get("filingDate", []) if d]
    oldest_recent = int(min(recent_dates)[:4]) if recent_dates else cutoff
    if oldest_recent > cutoff:
        for extra in filings.get("files", []):
            time.sleep(0.2)
            er = requests.get(f"{DATA_URL}/submissions/{extra['name']}", headers=HEADERS, timeout=30)
            er.raise_for_status()
            results.extend(_matching_filings(er.json(), form_type, cutoff))

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


def download_filings(ticker, save_dir, filename, form_type, years,
                     limit=None, fallback_form=None, fallback_note="", empty_hint=""):
    """Fetch every ``form_type`` filing for ``ticker`` in the last ``years``.

    ``filename`` is a callable ``(ticker, filing, form_type) -> str`` deciding
    how each PDF is named; that is the one thing annual and quarterly callers
    genuinely disagree about.

    ``fallback_form`` retries with a different form when the first yields
    nothing (10-K → 20-F for foreign private issuers). Callers that cannot
    safely guess a substitute — 10-Q has no unambiguous counterpart, since 6-K
    is a catch-all — pass None and an ``empty_hint`` to point the user at the
    right flag instead.

    Returns False only when the ticker is unknown to EDGAR; a valid ticker with
    no matching filings is a successful no-op.
    """
    print(f"Looking up {ticker} on SEC EDGAR...")
    cik = get_cik(ticker)
    if not cik:
        print(f"  ✗ Ticker '{ticker}' not found in EDGAR")
        return False
    print(f"  CIK: {cik}")

    time.sleep(0.3)
    filings = get_filings(cik, form_type, years)
    if not filings and fallback_form:
        time.sleep(0.3)
        alt = get_filings(cik, fallback_form, years)
        if alt:
            print(f"  No {form_type} found; falling back to {fallback_form}{fallback_note}")
            form_type, filings = fallback_form, alt
    if not filings:
        print(f"  No {form_type} filings found in the last {years} years")
        if empty_hint:
            print(f"  {empty_hint}")
        return True

    if limit:
        filings = filings[:limit]
    print(f"  Found {len(filings)} {form_type} filing(s)")
    company_dir = Path(save_dir) / ticker.upper()
    company_dir.mkdir(parents=True, exist_ok=True)

    ok = 0
    for i, filing in enumerate(filings, 1):
        print(f"\n[{i}/{len(filings)}] period {filing['period']} (filed {filing['date']})")

        pdf_path = company_dir / filename(ticker, filing, form_type)
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
