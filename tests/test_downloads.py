"""Unit/integration tests for the pure parsers in the download_* scripts.

Only the HTML/JSON parsing seams are tested; no browser, no real HTTP.
"""

import pytest
from bs4 import BeautifulSoup

import download_10k_pdf as d10
import download_10k_edgar as edgar
import download_grab_6k as grab

pytestmark = pytest.mark.integration


# ── download_10k_pdf: extract_pdf_links / parse_company_name ─────────────────

def test_extract_pdf_links_filters_and_sorts():
    html = """
      <a href="/HostedData/AnnualReportArchive/a/apple_2023.pdf">2023</a>
      <a href="/HostedData/AnnualReportArchive/a/apple_2021.pdf">2021</a>
      <a href="/HostedData/AnnualReportArchive/a/apple_2022.pdf">2022</a>
      <a href="/other/file.pdf">ignore</a>
      <a href="/HostedData/AnnualReportArchive/a/nodate.pdf">no year</a>
    """
    soup = BeautifulSoup(html, "html.parser")
    links = d10.extract_pdf_links(soup)
    years = [y for y, _ in links]
    assert years == [2023, 2022, 2021]  # newest first, non-archive + undated dropped
    assert all(u.startswith("https://www.annualreports.com") for _, u in links)


def test_extract_pdf_links_dedupes():
    html = """
      <a href="/HostedData/AnnualReportArchive/a/x_2023.pdf">dup1</a>
      <a href="/HostedData/AnnualReportArchive/a/x_2023.pdf">dup2</a>
    """
    soup = BeautifulSoup(html, "html.parser")
    assert len(d10.extract_pdf_links(soup)) == 1


def test_parse_company_name_from_title():
    # Current site uses " - "; older pages used " | ". Both must yield the same name.
    for sep in (" - ", " | "):
        soup = BeautifulSoup(f"<title>Apple Inc.{sep}AnnualReports.com</title>", "html.parser")
        assert d10.parse_company_name(soup, "fallback") == "Apple_Inc"


def test_parse_company_name_keeps_hyphen_in_name():
    soup = BeautifulSoup("<title>The Coca-Cola Company - AnnualReports.com</title>", "html.parser")
    assert d10.parse_company_name(soup, "fallback") == "The_Coca-Cola_Company"


def test_parse_company_name_fallback_when_no_title():
    soup = BeautifulSoup("<html></html>", "html.parser")
    assert d10.parse_company_name(soup, "fallback") == "fallback"


# ── download_10k_edgar: get_cik / get_filings ────────────────────────────────

class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_get_cik_normalizes_and_zero_pads(monkeypatch):
    payload = {
        "0": {"ticker": "AAPL", "cik_str": 320193},
        "1": {"ticker": "BRK-B", "cik_str": 1067983},
    }
    monkeypatch.setattr(edgar.requests, "get", lambda *a, **k: _Resp(payload))
    assert edgar.get_cik("AAPL") == "0000320193"
    assert edgar.get_cik("BRK.B") == "0001067983"   # dot normalised to dash
    assert edgar.get_cik("NOPE") is None


def test_get_filings_filters_by_form_and_sorts(monkeypatch):
    payload = {"filings": {"recent": {
        "form": ["10-K", "10-Q", "10-K"],
        "filingDate": ["2023-02-01", "2023-05-01", "2022-02-01"],
        "accessionNumber": ["a-2023", "q-2023", "a-2022"],
        "primaryDocument": ["d2023.htm", "q2023.htm", "d2022.htm"],
    }}}
    monkeypatch.setattr(edgar.requests, "get", lambda *a, **k: _Resp(payload))
    out = edgar.get_filings("0000320193", "10-K", years=20)
    assert [f["date"] for f in out] == ["2023-02-01", "2022-02-01"]  # 10-Q excluded, sorted desc
    assert out[0]["accession"] == "a-2023"


# ── download_grab_6k: extract_pdf_links ──────────────────────────────────────

def test_grab_extract_pdf_links():
    html = """
      <a href="/files/q1_6k.pdf">Q1 6-K</a>
      <a href="https://cdn.example.com/q2.PDF?x=1">Q2</a>
      <a href="/about">not a pdf</a>
    """
    links = grab.extract_pdf_links(html, "https://investors.grab.com")
    urls = [l["url"] for l in links]
    assert "https://investors.grab.com/files/q1_6k.pdf" in urls
    assert any("q2.PDF" in u for u in urls)
    assert all("/about" not in u for u in urls)
    assert links[0]["text"] == "Q1 6-K"
