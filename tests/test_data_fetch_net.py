"""Integration tests for the network-touching helpers in data_fetch.

``_get_soup`` (requests), the three scrapers, and ``fetch_data`` (yfinance) are
exercised with their network boundary replaced by fakes — no real HTTP.
"""

import pandas as pd
import pytest
from bs4 import BeautifulSoup

# Patch targets must be the canonical module where these functions live and
# resolve their globals (analysis.data.sources), not the utils.data_fetch shim.
from scripts.analysis.data import sources as data_fetch
from scripts.analysis.data.sources import (
    fetch_finviz, fetch_stockanalysis, fetch_roic, fetch_data, _get_soup,
)

pytestmark = pytest.mark.integration


def _soup(html):
    return BeautifulSoup(html, "html.parser")


# ── _get_soup ────────────────────────────────────────────────────────────────

def test_get_soup_returns_soup_on_200(monkeypatch):
    resp = type("R", (), {"status_code": 200, "text": "<html><b>hi</b></html>"})()
    monkeypatch.setattr("requests.get", lambda *a, **k: resp)
    soup = _get_soup("http://x")
    assert soup is not None and soup.find("b").get_text() == "hi"


def test_get_soup_returns_none_on_403(monkeypatch):
    resp = type("R", (), {"status_code": 403, "text": ""})()
    monkeypatch.setattr("requests.get", lambda *a, **k: resp)
    assert _get_soup("http://x") is None


def test_get_soup_returns_none_on_exception(monkeypatch):
    monkeypatch.setattr(data_fetch.time, "sleep", lambda *_: None)

    def boom(*a, **k):
        raise ConnectionError("down")

    monkeypatch.setattr("requests.get", boom)
    assert _get_soup("http://x", retries=1) is None


def test_get_soup_retries_with_backoff_on_5xx(monkeypatch):
    # A transient 5xx must go through the retry/backoff path, not silently
    # fall through and re-request immediately.
    sleeps = {"n": 0}
    monkeypatch.setattr(data_fetch.time, "sleep", lambda *_: sleeps.__setitem__("n", sleeps["n"] + 1))

    class R:
        status_code = 503
        text = ""

        def raise_for_status(self):
            raise RuntimeError("503 Server Error")

    calls = {"n": 0}

    def get(*a, **k):
        calls["n"] += 1
        return R()

    monkeypatch.setattr("requests.get", get)
    assert _get_soup("http://x", retries=2) is None
    assert calls["n"] == 3       # initial + 2 retries
    assert sleeps["n"] == 2      # slept between retries (backoff applied)


# ── fetch_finviz ─────────────────────────────────────────────────────────────

def test_fetch_finviz_parses_pairs(monkeypatch):
    html = """<table class="snapshot-table2">
      <tr><td>P/E</td><td>15.2</td><td>ROE</td><td>12.30%</td></tr>
    </table>"""
    monkeypatch.setattr(data_fetch, "_get_soup", lambda *a, **k: _soup(html))
    out = fetch_finviz("AAPL")
    assert out["P/E"] == "15.2"
    assert out["ROE"] == "12.30%"


def test_fetch_finviz_empty_when_blocked(monkeypatch):
    monkeypatch.setattr(data_fetch, "_get_soup", lambda *a, **k: None)
    assert fetch_finviz("AAPL") == {}


# ── fetch_roic ───────────────────────────────────────────────────────────────

def test_fetch_roic_parses_tables(monkeypatch):
    html = """<table>
      <tr><th>Year</th><th>ROIC</th></tr>
      <tr><td>2023</td><td>15%</td></tr>
      <tr><td>2022</td><td>12%</td></tr>
    </table>"""
    monkeypatch.setattr(data_fetch, "_get_soup", lambda *a, **k: _soup(html))
    out = fetch_roic("AAPL")
    assert "table_0" in out
    assert out["table_0"]["headers"] == ["Year", "ROIC"]
    assert ["2023", "15%"] in out["table_0"]["rows"]


def test_fetch_roic_empty_when_blocked(monkeypatch):
    monkeypatch.setattr(data_fetch, "_get_soup", lambda *a, **k: None)
    assert fetch_roic("AAPL") == {}


# ── fetch_stockanalysis ──────────────────────────────────────────────────────

def test_fetch_stockanalysis_collects_tables(monkeypatch):
    html = "<table><tr><th>Revenue</th></tr><tr><td>100</td></tr></table>"
    monkeypatch.setattr(data_fetch, "_get_soup", lambda *a, **k: _soup(html))
    monkeypatch.setattr(data_fetch.time, "sleep", lambda *_: None)
    out = fetch_stockanalysis("AAPL")
    assert out.get("financials_annual")
    assert out.get("balance_sheet")


# ── fetch_data (yfinance) ────────────────────────────────────────────────────

class _FakeTicker:
    def __init__(self, symbol):
        self.symbol = symbol
        self.info = {"longName": "Test Co", "sector": "Tech", "trailingPE": 20.0}
        self.news = [{"title": "n1"}, {"title": "n2"}]
        # holders / actions: empty frames → skipped gracefully
        self._empty = pd.DataFrame()

    def history(self, period="2y"):
        idx = pd.date_range("2023-01-01", periods=300, freq="D")
        base = [100 + i * 0.1 for i in range(300)]
        return pd.DataFrame(
            {"Open": base, "High": [b + 1 for b in base],
             "Low": [b - 1 for b in base], "Close": base,
             "Volume": [1_000_000] * 300},
            index=idx,
        )

    # all of these are accessed via attribute; empty frames keep fetch_data quiet
    upgrades_downgrades = property(lambda self: self._empty)
    insider_transactions = property(lambda self: self._empty)
    major_holders = property(lambda self: self._empty)
    institutional_holders = property(lambda self: self._empty)
    mutualfund_holders = property(lambda self: self._empty)
    earnings_history = property(lambda self: self._empty)
    financials = property(lambda self: self._empty)
    quarterly_financials = property(lambda self: self._empty)
    balance_sheet = property(lambda self: self._empty)
    quarterly_balance_sheet = property(lambda self: self._empty)
    cashflow = property(lambda self: self._empty)
    quarterly_cashflow = property(lambda self: self._empty)


class _FakeSearch:
    def __init__(self, query, **kwargs):
        self.news = [{"title": "n1"}, {"title": "n2"}]


def test_yahoo_news_reads_search_not_ticker_news(monkeypatch):
    import types as _types
    calls = {}

    def search(query, **kwargs):
        calls.update(kwargs, query=query)
        return _FakeSearch(query)

    monkeypatch.setattr(data_fetch, "_get_yf", lambda: _types.SimpleNamespace(Search=search))
    assert [n["title"] for n in data_fetch.yahoo_news("AAPL", count=5)] == ["n1", "n2"]
    assert calls == {"query": "AAPL", "max_results": 0, "news_count": 5,
                     "enable_fuzzy_query": False}


def test_yahoo_news_fails_soft(monkeypatch):
    import types as _types

    def boom(*a, **k):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(data_fetch, "_get_yf", lambda: _types.SimpleNamespace(Search=boom))
    assert data_fetch.yahoo_news("AAPL") == []


def test_fetch_data_assembles_dict(monkeypatch):
    import types as _types
    fake_yf = _types.SimpleNamespace(Ticker=_FakeTicker, Search=_FakeSearch)
    monkeypatch.setattr(data_fetch, "_get_yf", lambda: fake_yf)
    # stub the three web scrapers so no HTTP happens
    monkeypatch.setattr(data_fetch, "fetch_finviz", lambda t: {"P/E": "20"})
    monkeypatch.setattr(data_fetch, "fetch_stockanalysis", lambda t: {})
    monkeypatch.setattr(data_fetch, "fetch_roic", lambda t: {})

    out = fetch_data("AAPL")
    assert out["ticker"] == "AAPL"
    assert out["info"]["longName"] == "Test Co"
    assert out["hist"] is not None and not out["hist"].empty
    assert out["price_now"] is not None
    assert out["price_series"]            # monthly resample populated
    assert len(out["news"]) == 2
    # empty statement frames normalise to None
    assert out["income"] is None
    # finviz text formatted from stub
    assert "finviz_text" in out


def test_get_yf_raises_datafetcherror_when_missing(monkeypatch):
    import sys as _sys
    from scripts.analysis.exceptions import DataFetchError
    # A None entry makes `import yfinance` raise ImportError.
    monkeypatch.setitem(_sys.modules, "yfinance", None)
    with pytest.raises(DataFetchError):
        data_fetch._get_yf()


def test_fetch_data_degrades_when_info_raises(monkeypatch):
    import types as _types

    class _InfoFails:
        news = []

        def __init__(self, symbol):
            self._e = pd.DataFrame()

        @property
        def info(self):
            raise RuntimeError("rate limited")

        def history(self, period="2y"):
            return pd.DataFrame()  # empty → price fields None, no crash

        upgrades_downgrades = property(lambda s: s._e)
        insider_transactions = property(lambda s: s._e)
        major_holders = property(lambda s: s._e)
        institutional_holders = property(lambda s: s._e)
        mutualfund_holders = property(lambda s: s._e)
        earnings_history = property(lambda s: s._e)
        financials = property(lambda s: s._e)
        quarterly_financials = property(lambda s: s._e)
        balance_sheet = property(lambda s: s._e)
        quarterly_balance_sheet = property(lambda s: s._e)
        cashflow = property(lambda s: s._e)
        quarterly_cashflow = property(lambda s: s._e)

    monkeypatch.setattr(data_fetch, "_get_yf",
                        lambda: _types.SimpleNamespace(Ticker=_InfoFails))
    monkeypatch.setattr(data_fetch, "fetch_finviz", lambda t: {})
    monkeypatch.setattr(data_fetch, "fetch_stockanalysis", lambda t: {})
    monkeypatch.setattr(data_fetch, "fetch_roic", lambda t: {})

    out = fetch_data("X")
    assert out["ticker"] == "X"
    assert out["info"] == {}     # info failure degraded, did not crash


def test_fetch_data_insider_with_missing_values(monkeypatch):
    """A row with None Shares/Value must not discard the whole insider section."""
    import types as _types
    ins = pd.DataFrame(
        {"Insider": ["Jane Doe"], "Transaction": ["Sale"], "Shares": [None], "Value": [None]},
        index=pd.to_datetime(["2024-01-01"]),
    )

    class T(_FakeTicker):
        insider_transactions = property(lambda self: ins)

    fake_yf = _types.SimpleNamespace(Ticker=lambda s: T(s))
    monkeypatch.setattr(data_fetch, "_get_yf", lambda: fake_yf)
    monkeypatch.setattr(data_fetch, "fetch_finviz", lambda t: {})
    monkeypatch.setattr(data_fetch, "fetch_stockanalysis", lambda t: {})
    monkeypatch.setattr(data_fetch, "fetch_roic", lambda t: {})

    out = fetch_data("X")
    assert "Jane Doe" in out["insider_text"]          # section survived
    assert out["insider_text"] != "  (no data)"


def _stub_scrapers(monkeypatch, finviz=None):
    monkeypatch.setattr(data_fetch, "fetch_finviz", lambda t: finviz or {})
    monkeypatch.setattr(data_fetch, "fetch_stockanalysis", lambda t: {})
    monkeypatch.setattr(data_fetch, "fetch_roic", lambda t: {})


def test_fetch_data_asks_yahoo_for_the_exchange_symbol(monkeypatch):
    """A bare "0050" is a 404 on Yahoo: the 2026-10-22 0050 report got no price
    or statements and valued the ETF at NT$195 from memory (it traded at 106.90)."""
    import types as _types
    seen = []

    class _Recording(_FakeTicker):
        def __init__(self, symbol):
            seen.append(symbol)
            super().__init__(symbol)

    monkeypatch.setattr(data_fetch, "_get_yf", lambda: _types.SimpleNamespace(Ticker=_Recording))
    _stub_scrapers(monkeypatch)
    out = fetch_data("0050")
    assert seen == ["0050.TW"]
    assert (out["ticker"], out["symbol"]) == ("0050", "0050.TW")


def test_fetch_data_records_which_sources_returned_data(monkeypatch):
    import types as _types
    monkeypatch.setattr(data_fetch, "_get_yf", lambda: _types.SimpleNamespace(Ticker=_FakeTicker))
    _stub_scrapers(monkeypatch, finviz={"P/E": "20"})
    status = fetch_data("AAPL")["source_status"]
    assert status["yfinance_info"] and status["yfinance_prices"] and status["finviz"]
    assert not status["roic"] and not status["stockanalysis"]
    assert not status["yfinance_statements"]   # the fake's frames are empty


def _tz_hist(dates, tz):
    idx = pd.DatetimeIndex(pd.to_datetime(dates)).tz_localize(tz)
    return pd.DataFrame({"Close": [100.0 + i for i in range(len(dates))]}, index=idx)


def test_last_completed_close_skips_a_session_still_open():
    from datetime import datetime
    tz = "America/New_York"
    hist = _tz_hist(["2026-10-21", "2026-10-22"], tz)
    midday = datetime(2026, 10, 22, 13, 40, tzinfo=hist.index.tz)
    assert data_fetch.last_completed_close(hist, now=midday) == (100.0, "2026-10-21")
    evening = datetime(2026, 10, 22, 22, 47, tzinfo=hist.index.tz)
    assert data_fetch.last_completed_close(hist, now=evening) == (101.0, "2026-10-22")


def test_last_completed_close_uses_the_exchange_close_time():
    """Taipei closes at 13:30, so a 14:00 bar dated today is final."""
    from datetime import datetime
    hist = _tz_hist(["2026-10-21", "2026-10-22"], "Asia/Taipei")
    after = datetime(2026, 10, 22, 14, 0, tzinfo=hist.index.tz)
    assert data_fetch.last_completed_close(hist, now=after)[1] == "2026-10-22"


def test_last_completed_close_of_nothing_is_none():
    assert data_fetch.last_completed_close(None) == (None, None)
    assert data_fetch.last_completed_close(pd.DataFrame({"Close": []})) == (None, None)


# ── quote_close: the official close when the daily bar is empty ──────────────

def _epoch(iso):
    from datetime import datetime
    return int(datetime.fromisoformat(iso).timestamp())


def test_quote_close_reads_a_close_stamped_at_the_session_end():
    """SKHY 2026-10-22: daily bar NaN, quote $131.69 at 16:00:00 ET."""
    info = {"regularMarketPrice": 131.69, "exchangeTimezoneName": "America/New_York",
            "regularMarketTime": _epoch("2026-10-22T20:00:00+00:00")}
    assert data_fetch.quote_close(info) == (131.69, "2026-10-22")


def test_quote_close_ignores_an_intraday_tick():
    info = {"regularMarketPrice": 130.0, "exchangeTimezoneName": "America/New_York",
            "regularMarketTime": _epoch("2026-10-22T17:40:00+00:00")}    # 13:40 ET
    assert data_fetch.quote_close(info) == (None, None)


def test_quote_close_uses_the_taipei_close_time():
    """0050 2026-10-22: no daily bar at all, quote NT$106.90 at 13:30:04 Taipei."""
    info = {"regularMarketPrice": 106.9, "exchangeTimezoneName": "Asia/Taipei",
            "regularMarketTime": _epoch("2026-10-22T05:30:04+00:00")}
    assert data_fetch.quote_close(info) == (106.9, "2026-10-22")


@pytest.mark.parametrize("info", [{}, {"regularMarketPrice": None, "regularMarketTime": 1},
                                  {"regularMarketPrice": "x", "regularMarketTime": 1}])
def test_quote_close_without_a_usable_quote_is_none(info):
    assert data_fetch.quote_close(info) == (None, None)


def test_fetch_data_prefers_a_newer_quote_close_over_an_empty_bar(monkeypatch):
    import types as _types

    class _EmptyLastBar(_FakeTicker):
        def __init__(self, symbol):
            super().__init__(symbol)
            self.info = {"regularMarketPrice": 131.69, "exchangeTimezoneName": "America/New_York",
                         "regularMarketTime": _epoch("2026-10-22T20:00:00+00:00")}

        def history(self, period="2y"):
            idx = pd.DatetimeIndex(pd.to_datetime(["2026-10-20", "2026-10-21", "2026-10-22"])
                                   ).tz_localize("America/New_York")
            return pd.DataFrame({"Open": [1.0] * 3, "High": [1.0] * 3, "Low": [1.0] * 3,
                                 "Close": [139.79, 143.25, float("nan")], "Volume": [1] * 3},
                                index=idx)

    monkeypatch.setattr(data_fetch, "_get_yf", lambda: _types.SimpleNamespace(Ticker=_EmptyLastBar))
    _stub_scrapers(monkeypatch)
    out = fetch_data("SKHY")
    assert (out["price_now"], out["price_date"]) == (131.69, "2026-10-22")
