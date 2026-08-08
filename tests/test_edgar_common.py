"""Tests for the shared EDGAR plumbing and the two CLIs sitting on it.

No browser and no real HTTP — ``requests`` and the PDF conversion are stubbed
at the module seam. The behaviour that matters most here is filename keying:
annual and quarterly filings disagree about it, and getting it wrong silently
drops filings (three 10-Qs in a year collapsing onto one name).
"""

import pytest

import download_10k_edgar as k10
import download_10q_edgar as q10
import edgar_common as ec

pytestmark = pytest.mark.integration


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """EDGAR politeness delays would otherwise make the suite crawl."""
    monkeypatch.setattr(ec.time, "sleep", lambda *_a: None)


# ── get_cik ──────────────────────────────────────────────────────────────────

def test_get_cik_normalizes_and_zero_pads(monkeypatch):
    payload = {
        "0": {"ticker": "AAPL", "cik_str": 320193},
        "1": {"ticker": "BRK-B", "cik_str": 1067983},
    }
    monkeypatch.setattr(ec.requests, "get", lambda *a, **k: _Resp(payload))
    assert ec.get_cik("AAPL") == "0000320193"
    assert ec.get_cik("BRK.B") == "0001067983"   # dot normalised to dash
    assert ec.get_cik("NOPE") is None


# ── _matching_filings: period extraction ─────────────────────────────────────

@pytest.mark.unit
def test_matching_filings_captures_period():
    block = {
        "form": ["10-Q"],
        "filingDate": ["2026-08-04"],
        "reportDate": ["2026-06-30"],
        "accessionNumber": ["a"],
        "primaryDocument": ["d.htm"],
    }
    (filing,) = ec._matching_filings(block, "10-Q", 2020)
    assert filing["period"] == "2026-06-30"
    assert filing["date"] == "2026-08-04"


@pytest.mark.unit
def test_matching_filings_period_falls_back_to_filing_date():
    """reportDate is occasionally blank; the filing date is the stand-in so
    naming never produces a bare '_10-Q.pdf'."""
    block = {
        "form": ["10-Q", "10-Q"],
        "filingDate": ["2026-08-04", "2026-05-05"],
        "reportDate": ["", "2026-03-31"],
        "accessionNumber": ["a", "b"],
        "primaryDocument": ["a.htm", "b.htm"],
    }
    out = ec._matching_filings(block, "10-Q", 2020)
    assert out[0]["period"] == "2026-08-04"   # blank → filing date
    assert out[1]["period"] == "2026-03-31"


@pytest.mark.unit
def test_matching_filings_period_survives_missing_report_date_column():
    """Older archive blocks may omit reportDate entirely."""
    block = {
        "form": ["10-K"],
        "filingDate": ["2015-02-01"],
        "accessionNumber": ["a"],
        "primaryDocument": ["d.htm"],
    }
    (filing,) = ec._matching_filings(block, "10-K", 2010)
    assert filing["period"] == "2015-02-01"


@pytest.mark.unit
def test_matching_filings_respects_form_and_cutoff():
    block = {
        "form": ["10-K", "10-Q", "10-K"],
        "filingDate": ["2026-02-01", "2026-05-01", "2019-02-01"],
        "reportDate": ["2025-12-31", "2026-03-31", "2018-12-31"],
        "accessionNumber": ["a", "b", "c"],
        "primaryDocument": ["a.htm", "b.htm", "c.htm"],
    }
    out = ec._matching_filings(block, "10-K", 2020)
    assert [f["accession"] for f in out] == ["a"]  # 10-Q dropped, pre-cutoff dropped


# ── get_filings ──────────────────────────────────────────────────────────────

def test_get_filings_filters_by_form_and_sorts(monkeypatch):
    payload = {"filings": {"recent": {
        "form": ["10-K", "10-Q", "10-K"],
        "filingDate": ["2023-02-01", "2023-05-01", "2022-02-01"],
        "reportDate": ["2022-12-31", "2023-03-31", "2021-12-31"],
        "accessionNumber": ["a-2023", "q-2023", "a-2022"],
        "primaryDocument": ["d2023.htm", "q2023.htm", "d2022.htm"],
    }}}
    monkeypatch.setattr(ec.requests, "get", lambda *a, **k: _Resp(payload))
    out = ec.get_filings("0000320193", "10-K", years=20)
    assert [f["date"] for f in out] == ["2023-02-01", "2022-02-01"]  # 10-Q excluded, sorted desc
    assert out[0]["accession"] == "a-2023"


def test_get_filings_pages_into_archive_files(monkeypatch):
    """When the requested window reaches past the 'recent' block, older filings
    are pulled from the paginated archive files too (GOOG/META case)."""
    main = {"filings": {
        "recent": {
            "form": ["10-K"],
            "filingDate": ["2025-02-01"],
            "reportDate": ["2024-12-31"],
            "accessionNumber": ["a-2025"],
            "primaryDocument": ["d2025.htm"],
        },
        "files": [{"name": "CIK-submissions-001.json"}],
    }}
    archive = {
        "form": ["10-K", "8-K", "10-K"],
        "filingDate": ["2021-02-01", "2021-03-01", "2020-02-01"],
        "reportDate": ["2020-12-31", "2021-03-01", "2019-12-31"],
        "accessionNumber": ["a-2021", "k-2021", "a-2020"],
        "primaryDocument": ["d2021.htm", "k.htm", "d2020.htm"],
    }

    def fake_get(url, *a, **k):
        return _Resp(main if url.endswith("CIK0000320193.json") else archive)

    monkeypatch.setattr(ec.requests, "get", fake_get)

    out = ec.get_filings("0000320193", "10-K", years=20)
    # recent (2025) + archive (2021, 2020); 8-K dropped; newest first
    assert [f["date"] for f in out] == ["2025-02-01", "2021-02-01", "2020-02-01"]


def test_get_filings_skips_archives_when_recent_covers_window(monkeypatch):
    # recent already reaches back to 2010, well before any realistic cutoff, so
    # the archive files must not be fetched.
    payload = {"filings": {
        "recent": {
            "form": ["10-K", "10-K"],
            "filingDate": ["2025-02-01", "2010-02-01"],
            "reportDate": ["2024-12-31", "2009-12-31"],
            "accessionNumber": ["a-2025", "a-2010"],
            "primaryDocument": ["d2025.htm", "d2010.htm"],
        },
        "files": [{"name": "should-not-be-fetched.json"}],
    }}
    fetched = []

    def fake_get(url, *a, **k):
        fetched.append(url)
        return _Resp(payload)

    monkeypatch.setattr(ec.requests, "get", fake_get)
    out = ec.get_filings("0000320193", "10-K", years=3)  # recent oldest (2010) predates cutoff
    assert [f["date"] for f in out] == ["2025-02-01"]
    assert len(fetched) == 1  # archive file never requested


# ── find_pdf_in_filing ───────────────────────────────────────────────────────

def test_find_pdf_in_filing_returns_pdf_name(monkeypatch):
    payload = {"directory": {"item": [
        {"name": "index.htm"}, {"name": "Report.PDF"},
    ]}}
    monkeypatch.setattr(ec.requests, "get", lambda *a, **k: _Resp(payload))
    assert ec.find_pdf_in_filing("0000320193", "0000320193-26-000001") == "Report.PDF"


def test_find_pdf_in_filing_returns_none_without_pdf(monkeypatch):
    payload = {"directory": {"item": [{"name": "index.htm"}]}}
    monkeypatch.setattr(ec.requests, "get", lambda *a, **k: _Resp(payload))
    assert ec.find_pdf_in_filing("0000320193", "acc") is None


def test_find_pdf_in_filing_swallows_errors(monkeypatch):
    """A missing index must degrade to the primary document, not crash the run."""
    def boom(*a, **k):
        raise RuntimeError("404")

    monkeypatch.setattr(ec.requests, "get", boom)
    assert ec.find_pdf_in_filing("0000320193", "acc") is None


# ── download_as_pdf ──────────────────────────────────────────────────────────

def test_download_as_pdf_saves_native_pdf_without_conversion(monkeypatch, tmp_path):
    converted = []
    monkeypatch.setattr(ec, "download_raw", lambda url, p: p.write_bytes(b"%PDF-1.4"))
    monkeypatch.setattr(ec, "html_to_pdf", lambda *a: converted.append(a))

    out = tmp_path / "x.pdf"
    assert ec.download_as_pdf("https://sec.gov/a/report.pdf", out) is True
    assert out.read_bytes() == b"%PDF-1.4"
    assert converted == []  # native PDF → no browser


def test_download_as_pdf_converts_html_and_removes_intermediate(monkeypatch, tmp_path):
    monkeypatch.setattr(ec, "download_raw", lambda url, p: p.write_bytes(b"<html>"))
    monkeypatch.setattr(ec, "html_to_pdf",
                        lambda html, pdf: pdf.write_bytes(b"%PDF-1.4 converted"))

    out = tmp_path / "x.pdf"
    assert ec.download_as_pdf("https://sec.gov/a/pltr-20260630.htm", out) is True
    assert out.read_bytes() == b"%PDF-1.4 converted"
    assert not (tmp_path / "x.htm").exists()  # scratch HTML cleaned up


def test_download_as_pdf_cleans_up_on_failure(monkeypatch, tmp_path):
    def boom(url, p):
        p.write_bytes(b"partial")
        raise RuntimeError("connection reset")

    monkeypatch.setattr(ec, "download_raw", boom)
    out = tmp_path / "x.pdf"
    assert ec.download_as_pdf("https://sec.gov/a/report.pdf", out) is False
    assert not out.exists()  # no truncated PDF left behind


# ── download_filings ─────────────────────────────────────────────────────────

@pytest.fixture
def stub_fetch(monkeypatch, tmp_path):
    """Stub the network seams of download_filings. Returns (saved_paths, tmp_path)."""
    monkeypatch.setattr(ec, "get_cik", lambda t: "0000000001")
    monkeypatch.setattr(ec, "find_pdf_in_filing", lambda cik, acc: None)

    saved = []

    def fake_download_as_pdf(url, path):
        saved.append(path)
        path.write_bytes(b"%PDF-1.4")
        return True

    monkeypatch.setattr(ec, "download_as_pdf", fake_download_as_pdf)
    return saved, tmp_path


def _filing(date, period, acc="a"):
    return {"date": date, "period": period, "accession": acc, "primary_doc": "d.htm"}


def test_download_filings_returns_false_for_unknown_ticker(monkeypatch, tmp_path):
    monkeypatch.setattr(ec, "get_cik", lambda t: None)
    assert ec.download_filings("NOPE", tmp_path, k10.annual_filename, "10-K", 5) is False


def test_download_filings_no_matches_is_a_successful_noop(monkeypatch, stub_fetch):
    saved, tmp_path = stub_fetch
    monkeypatch.setattr(ec, "get_filings", lambda *a: [])
    assert ec.download_filings("AAPL", tmp_path, k10.annual_filename, "10-K", 5) is True
    assert saved == []


def test_download_filings_honours_limit(monkeypatch, stub_fetch):
    saved, tmp_path = stub_fetch
    monkeypatch.setattr(ec, "get_filings", lambda *a: [
        _filing("2026-08-04", "2026-06-30", "a"),
        _filing("2026-05-05", "2026-03-31", "b"),
        _filing("2026-02-17", "2025-12-31", "c"),
    ])
    ec.download_filings("PLTR", tmp_path, q10.quarterly_filename, "10-Q", 1, limit=1)
    assert [p.name for p in saved] == ["PLTR_2026-06-30_10-Q.pdf"]  # newest only


def test_download_filings_skips_existing(monkeypatch, stub_fetch):
    saved, tmp_path = stub_fetch
    monkeypatch.setattr(ec, "get_filings", lambda *a: [
        _filing("2026-08-04", "2026-06-30", "a"),
        _filing("2026-05-05", "2026-03-31", "b"),
    ])
    company_dir = tmp_path / "PLTR"
    company_dir.mkdir()
    (company_dir / "PLTR_2026-06-30_10-Q.pdf").write_bytes(b"%PDF old")

    ec.download_filings("PLTR", tmp_path, q10.quarterly_filename, "10-Q", 1)
    assert [p.name for p in saved] == ["PLTR_2026-03-31_10-Q.pdf"]  # existing not refetched


def test_download_filings_uses_the_filename_callback(monkeypatch, stub_fetch):
    saved, tmp_path = stub_fetch
    monkeypatch.setattr(ec, "get_filings", lambda *a: [_filing("2026-02-17", "2025-12-31")])
    ec.download_filings("PLTR", tmp_path, lambda t, f, form: "custom.pdf", "10-K", 5)
    assert [p.name for p in saved] == ["custom.pdf"]


def test_download_filings_prefers_native_pdf_when_present(monkeypatch, stub_fetch):
    saved, tmp_path = stub_fetch
    urls = []
    monkeypatch.setattr(ec, "get_filings", lambda *a: [_filing("2026-02-17", "2025-12-31")])
    monkeypatch.setattr(ec, "find_pdf_in_filing", lambda cik, acc: "Native.pdf")
    monkeypatch.setattr(ec, "download_as_pdf", lambda url, p: urls.append(url) or True)
    ec.download_filings("PLTR", tmp_path, k10.annual_filename, "10-K", 5)
    assert urls[0].endswith("/Native.pdf")  # native PDF beats the iXBRL primary doc


def test_download_filings_falls_back_to_alternate_form(monkeypatch, stub_fetch):
    saved, tmp_path = stub_fetch
    tried = []

    def fake_get_filings(cik, form, years):
        tried.append(form)
        return [] if form == "10-K" else [_filing("2026-04-16", "2025-12-31")]

    monkeypatch.setattr(ec, "get_filings", fake_get_filings)
    ec.download_filings("TSM", tmp_path, k10.annual_filename, "10-K", 5,
                        fallback_form="20-F")
    assert tried == ["10-K", "20-F"]
    assert [p.name for p in saved] == ["TSM_2026_20-F.pdf"]  # named with the fallback form


def test_download_filings_without_fallback_does_not_retry(monkeypatch, stub_fetch):
    saved, tmp_path = stub_fetch
    tried = []

    def fake_get_filings(cik, form, years):
        tried.append(form)
        return []

    monkeypatch.setattr(ec, "get_filings", fake_get_filings)
    ec.download_filings("TSM", tmp_path, q10.quarterly_filename, "10-Q", 1)
    assert tried == ["10-Q"]  # no guessing at 6-K


def test_download_filings_prints_empty_hint(monkeypatch, stub_fetch, capsys):
    _, tmp_path = stub_fetch
    monkeypatch.setattr(ec, "get_filings", lambda *a: [])
    ec.download_filings("TSM", tmp_path, q10.quarterly_filename, "10-Q", 1,
                        empty_hint="rerun with --form 6-K")
    assert "rerun with --form 6-K" in capsys.readouterr().out


# ── download_10k_edgar ───────────────────────────────────────────────────────

@pytest.mark.unit
def test_annual_filename_keys_on_filing_year():
    name = k10.annual_filename("aapl", _filing("2025-10-31", "2025-09-27"), "10-K")
    assert name == "AAPL_2025_10-K.pdf"  # ticker upper-cased, keyed by filing year


def test_download_10k_falls_back_to_20f(monkeypatch, tmp_path, stub_fetch):
    """Foreign private issuers file 20-F; when no 10-K exists we retry as 20-F."""
    saved, tmp_path = stub_fetch
    monkeypatch.setattr(k10, "SAVE_DIR", tmp_path)
    tried = []

    def fake_get_filings(cik, form, years):
        tried.append(form)
        if form == "10-K":
            return []  # foreign filer → no 10-K
        return [_filing("2025-04-01", "2024-12-31", "a-2025")]

    monkeypatch.setattr(ec, "get_filings", fake_get_filings)

    assert k10.download_10k("TSMFAKE", years=3) is True
    assert tried == ["10-K", "20-F"]  # tried 10-K first, then fell back
    assert [p.name for p in saved] == ["TSMFAKE_2025_20-F.pdf"]


def test_download_10k_no_fallback_when_10k_exists(monkeypatch, stub_fetch):
    saved, tmp_path = stub_fetch
    monkeypatch.setattr(k10, "SAVE_DIR", tmp_path)
    tried = []

    def fake_get_filings(cik, form, years):
        tried.append(form)
        return [_filing("2025-04-01", "2024-12-31")]

    monkeypatch.setattr(ec, "get_filings", fake_get_filings)
    k10.download_10k("AAPL", years=1)
    assert tried == ["10-K"]  # 10-K found → never queries 20-F


def test_download_10k_explicit_20f_does_not_self_fallback(monkeypatch, stub_fetch):
    """--form 20-F must not retry 20-F a second time when it finds nothing."""
    _, tmp_path = stub_fetch
    monkeypatch.setattr(k10, "SAVE_DIR", tmp_path)
    tried = []

    def fake_get_filings(cik, form, years):
        tried.append(form)
        return []

    monkeypatch.setattr(ec, "get_filings", fake_get_filings)
    k10.download_10k("TSM", years=1, form_type="20-F")
    assert tried == ["20-F"]


# ── download_10q_edgar ───────────────────────────────────────────────────────

@pytest.mark.unit
def test_quarterly_filename_keys_on_period():
    name = q10.quarterly_filename("pltr", _filing("2026-08-04", "2026-06-30"), "10-Q")
    assert name == "PLTR_2026-06-30_10-Q.pdf"


@pytest.mark.unit
def test_quarterly_filename_keys_6k_on_filing_date():
    """TSM files several 6-Ks against one period (monthly revenue, dividends,
    AGM); keying on period would collapse them onto one name."""
    same_period = [
        _filing("2026-07-24", "2026-06-30"),
        _filing("2026-07-16", "2026-06-30"),
        _filing("2026-07-13", "2026-06-30"),
    ]
    names = {q10.quarterly_filename("TSM", f, "6-K") for f in same_period}
    assert names == {
        "TSM_2026-07-24_6-K.pdf",
        "TSM_2026-07-16_6-K.pdf",
        "TSM_2026-07-13_6-K.pdf",
    }


@pytest.mark.unit
def test_quarterly_filenames_are_distinct_within_one_year():
    """The reason quarterlies are not keyed by year: three 10-Qs share 2026, so
    the annual scheme would name them all PLTR_2026_10-Q.pdf and the 2nd and 3rd
    would be silently skipped as 'already exists'."""
    year_2026 = [
        _filing("2026-08-04", "2026-06-30"),
        _filing("2026-05-05", "2026-03-31"),
        _filing("2026-11-03", "2026-09-30"),
    ]
    quarterly = {q10.quarterly_filename("PLTR", f, "10-Q") for f in year_2026}
    annual = {k10.annual_filename("PLTR", f, "10-Q") for f in year_2026}
    assert len(quarterly) == 3          # period keying keeps them apart
    assert annual == {"PLTR_2026_10-Q.pdf"}  # year keying collapses all three


def test_download_10q_writes_under_quarterly_save_dir(monkeypatch, stub_fetch):
    saved, tmp_path = stub_fetch
    monkeypatch.setattr(q10, "SAVE_DIR", tmp_path)
    monkeypatch.setattr(ec, "get_filings", lambda *a: [_filing("2026-08-04", "2026-06-30")])

    assert q10.download_10q("PLTR") is True
    assert saved[0] == tmp_path / "PLTR" / "PLTR_2026-06-30_10-Q.pdf"


def test_download_10q_passes_limit_through(monkeypatch, stub_fetch):
    saved, tmp_path = stub_fetch
    monkeypatch.setattr(q10, "SAVE_DIR", tmp_path)
    monkeypatch.setattr(ec, "get_filings", lambda *a: [
        _filing("2026-08-04", "2026-06-30", "a"),
        _filing("2026-05-05", "2026-03-31", "b"),
    ])
    q10.download_10q("PLTR", limit=1)
    assert len(saved) == 1


def test_download_10q_hints_at_6k_for_foreign_filers(monkeypatch, stub_fetch, capsys):
    _, tmp_path = stub_fetch
    monkeypatch.setattr(q10, "SAVE_DIR", tmp_path)
    monkeypatch.setattr(ec, "get_filings", lambda *a: [])

    q10.download_10q("TSM")
    assert "--form 6-K" in capsys.readouterr().out


def test_download_10q_omits_hint_when_already_asking_for_6k(monkeypatch, stub_fetch, capsys):
    _, tmp_path = stub_fetch
    monkeypatch.setattr(q10, "SAVE_DIR", tmp_path)
    monkeypatch.setattr(ec, "get_filings", lambda *a: [])

    q10.download_10q("TSM", form_type="6-K")
    assert "--form 6-K" not in capsys.readouterr().out


@pytest.mark.unit
def test_the_two_clis_write_to_different_trees():
    """10-q/ is kept separate so tooling that indexes 10-k/ sees only annuals."""
    assert k10.SAVE_DIR.name == "10-k"
    assert q10.SAVE_DIR.name == "10-q"
