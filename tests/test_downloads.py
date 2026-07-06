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


# ── download_10k_pdf: select_years (year-window filter) ──────────────────────

@pytest.mark.unit
def test_select_years_no_bounds_returns_all():
    links = [(2024, "u24"), (2023, "u23"), (2022, "u22")]
    assert d10.select_years(links) == links


@pytest.mark.unit
def test_select_years_inclusive_bounds():
    links = [(2024, "u24"), (2023, "u23"), (2022, "u22"), (2021, "u21")]
    # start only
    assert [y for y, _ in d10.select_years(links, start_year=2023)] == [2024, 2023]
    # end only
    assert [y for y, _ in d10.select_years(links, end_year=2022)] == [2022, 2021]
    # both — bounds are inclusive on each end
    assert [y for y, _ in d10.select_years(links, 2022, 2023)] == [2023, 2022]
    # single year
    assert d10.select_years(links, 2023, 2023) == [(2023, "u23")]


@pytest.mark.unit
def test_window_label_never_shows_none():
    # Regression: one-sided windows must not render "None" as a bound.
    assert d10._window_label(2020, 2023) == " for 2020–2023"
    assert d10._window_label(start_year=2020) == " since 2020"
    assert d10._window_label(end_year=2023) == " up to 2023"
    assert d10._window_label() == ""
    for label in (d10._window_label(2020), d10._window_label(end_year=2023)):
        assert "None" not in label


@pytest.mark.unit
def test_select_years_is_date_independent():
    """Regression: the old --years cutoff was computed from datetime.now(), so a
    report labelled 2024 fetched in 2026 got dropped. Value-based bounds must not."""
    links = [(2024, "u24"), (2023, "u23")]
    assert d10.select_years(links, 2023, 2024) == links  # nothing dropped regardless of "today"
    assert d10.select_years(links, start_year=2099) == []  # future window → empty, no error


# ── download_10k_pdf: download_10k (end-to-end, boundaries mocked) ────────────

def _fake_soup_with_years(years):
    anchors = "".join(
        f'<a href="/HostedData/AnnualReportArchive/m/NASDAQ_MSFT_{y}.pdf">{y}</a>'
        for y in years
    )
    return BeautifulSoup(f"<title>Microsoft Corporation - AnnualReports.com</title>{anchors}", "html.parser")


@pytest.fixture
def mock_download(monkeypatch, tmp_path):
    """Point SAVE_DIR at a tmp dir and stub the network seams. Returns the list
    of (url, filepath) that download_pdf was asked to fetch."""
    monkeypatch.setattr(d10, "SAVE_DIR", tmp_path)

    fetched = []

    def fake_download_pdf(url, filepath):
        fetched.append((url, filepath))
        filepath.write_bytes(b"%PDF-1.4 fake")
        return True

    monkeypatch.setattr(d10, "download_pdf", fake_download_pdf)
    return fetched, tmp_path


def test_download_10k_filters_by_window_and_names_dir(mock_download, monkeypatch):
    fetched, tmp_path = mock_download
    monkeypatch.setattr(d10, "fetch_page", lambda slug: _fake_soup_with_years([2024, 2023, 2022, 2021, 2020]))

    assert d10.download_10k("microsoft-corporation", start_year=2022, end_year=2024) is True

    company_dir = tmp_path / "Microsoft_Corporation"  # name derived from <title>, no "_-"
    assert company_dir.is_dir()
    got = sorted(p.name for p in company_dir.glob("*.pdf"))
    assert got == [
        "Microsoft_Corporation_2022_10K.pdf",
        "Microsoft_Corporation_2023_10K.pdf",
        "Microsoft_Corporation_2024_10K.pdf",
    ]
    assert len(fetched) == 3


def test_download_10k_no_bounds_downloads_all(mock_download, monkeypatch):
    fetched, _ = mock_download
    monkeypatch.setattr(d10, "fetch_page", lambda slug: _fake_soup_with_years([2024, 2023]))
    assert d10.download_10k("microsoft-corporation") is True
    assert len(fetched) == 2


def test_download_10k_skips_existing_files(mock_download, monkeypatch):
    fetched, tmp_path = mock_download
    monkeypatch.setattr(d10, "fetch_page", lambda slug: _fake_soup_with_years([2024, 2023]))
    # Pre-create the 2024 file so it should be skipped, not re-fetched.
    company_dir = tmp_path / "Microsoft_Corporation"
    company_dir.mkdir(parents=True)
    (company_dir / "Microsoft_Corporation_2024_10K.pdf").write_bytes(b"%PDF-1.4 old")

    d10.download_10k("microsoft-corporation")
    assert [fp.name for _, fp in fetched] == ["Microsoft_Corporation_2023_10K.pdf"]


def test_download_10k_returns_false_when_page_missing(mock_download, monkeypatch):
    monkeypatch.setattr(d10, "fetch_page", lambda slug: None)
    assert d10.download_10k("does-not-exist") is False


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


def test_download_10k_falls_back_to_20f(monkeypatch, tmp_path):
    """Foreign private issuers file 20-F; when no 10-K exists we retry as 20-F."""
    monkeypatch.setattr(edgar.time, "sleep", lambda *_a: None)
    monkeypatch.setattr(edgar, "SAVE_DIR", tmp_path)
    monkeypatch.setattr(edgar, "get_cik", lambda t: "0000000001")
    monkeypatch.setattr(edgar, "find_pdf_in_filing", lambda cik, acc: None)

    forms_tried = []

    def fake_get_filings(cik, form, years):
        forms_tried.append(form)
        if form == "10-K":
            return []  # foreign filer → no 10-K
        return [{"date": "2025-04-01", "accession": "a-2025", "primary_doc": "d.htm"}]

    monkeypatch.setattr(edgar, "get_filings", fake_get_filings)

    saved = []

    def fake_download_as_pdf(url, path):
        saved.append(path)
        path.write_bytes(b"%PDF-1.4")
        return True

    monkeypatch.setattr(edgar, "download_as_pdf", fake_download_as_pdf)

    assert edgar.download_10k("TSMFAKE", years=3) is True
    assert forms_tried == ["10-K", "20-F"]  # tried 10-K first, then fell back
    assert [p.name for p in saved] == ["TSMFAKE_2025_20-F.pdf"]


def test_download_10k_no_fallback_when_10k_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(edgar.time, "sleep", lambda *_a: None)
    monkeypatch.setattr(edgar, "SAVE_DIR", tmp_path)
    monkeypatch.setattr(edgar, "get_cik", lambda t: "0000000001")
    monkeypatch.setattr(edgar, "find_pdf_in_filing", lambda cik, acc: None)
    monkeypatch.setattr(edgar, "download_as_pdf", lambda url, path: True)

    forms_tried = []

    def fake_get_filings(cik, form, years):
        forms_tried.append(form)
        return [{"date": "2025-04-01", "accession": "a", "primary_doc": "d.htm"}]

    monkeypatch.setattr(edgar, "get_filings", fake_get_filings)
    edgar.download_10k("AAPL", years=1)
    assert forms_tried == ["10-K"]  # 10-K found → never queries 20-F


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
