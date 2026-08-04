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


def test_fetch_data_assembles_dict(monkeypatch):
    import types as _types
    fake_yf = _types.SimpleNamespace(Ticker=_FakeTicker)
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
