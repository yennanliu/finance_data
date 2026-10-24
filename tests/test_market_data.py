"""Tests for the report-vs-market-record checks (analysis.validate.market_data).

Background: docs/TECHNICAL_REPORT_REVIEW.md §7.4 (79 October reports carried
the previous session's close) and docs/FUNDAMENTAL_REPORT_REVIEW.md §12.3
(0050 quoted NT$195 for an ETF at NT$107).
"""

import pytest

from analysis.data import prices
from analysis.validate import market_data as M, parse_file

pytestmark = pytest.mark.unit


def bar(d, close, split=None):
    return {"date": d, "open": close, "high": close, "low": close, "close": close,
            "volume": 1, "div": None, "split": split}


BARS = [bar("2026-10-20", 139.79), bar("2026-10-21", 143.25), bar("2026-10-22", 131.69)]


def test_quoted_price_within_a_cent_or_so_passes():
    assert M.quote_mismatch(516.80, 516.79) is None
    assert M.quote_mismatch(None, 516.79) is None


def test_a_quoted_price_on_the_wrong_scale_is_caught():
    out = M.quote_mismatch(195.0, 106.90)
    assert out["diff_pct"] == pytest.approx(82.41)


def test_the_store_close_is_restated_back_through_later_splits():
    """The store is split-adjusted, so a pre-split report's close is only
    comparable once the later split is undone."""
    bars = [bar("2026-06-01", 100.0), bar("2026-06-02", 101.0, split=10.0)]
    assert M.recorded_close(bars, "2026-06-01") == 1000.0
    assert M.store_mismatch(1000.0, "2026-06-01", bars) is None


def test_a_close_the_store_disagrees_with_is_caught():
    out = M.store_mismatch(150.0, "2026-10-21", BARS)
    assert out["store"] == 143.25 and out["diff_pct"] == pytest.approx(4.71)


def test_no_store_bar_for_the_date_is_not_a_finding():
    """The nightly store update runs after generation, so today's bar may not
    be there yet."""
    assert M.store_mismatch(140.0, "2026-10-23", BARS) is None


def test_a_session_older_than_the_report_date_makes_the_close_stale():
    """SOFI 2026-10-23 (committed 01:05 UTC) used the 10-21 close although
    10-22's session had closed."""
    assert M.stale_sessions("2026-10-21", "2026-10-23", BARS) == ["2026-10-22"]


def test_a_session_on_the_report_date_itself_does_not():
    """The report date is the run's UTC date; that session may still be open."""
    assert M.stale_sessions("2026-10-21", "2026-10-22", BARS) == []


def test_unknown_or_missing_provenance_is_skipped():
    assert M.check({"price": "1", "price_date": "unknown"}, "skhy", "2026-10-23") == \
        {"store": None, "stale": []}
    assert M.check({}, "skhy", "2026-10-23") == {"store": None, "stale": []}


def test_parse_file_reports_store_and_freshness_findings(tmp_path, monkeypatch):
    store = tmp_path / "store"
    store.mkdir()
    prices.write_store("skhy", BARS, store)
    monkeypatch.setattr(prices, "STORE_DIR", store)

    d = tmp_path / "reports" / "skhy"
    d.mkdir(parents=True)
    p = d / "technical_analysis_2026-10-23_gemini.md"
    p.write_text("---\ntitle: x\nprice: 150.0\nprice_date: 2026-10-21\n---\n\n"
                 + "\n".join(f"第 {i} 行。" for i in range(100)), encoding="utf-8")
    issue = parse_file(p)
    assert {"STORE_MISMATCH", "STALE_PRICE"} <= set(issue.issues)
    assert "newer_sessions=['2026-10-22']" in issue.note
