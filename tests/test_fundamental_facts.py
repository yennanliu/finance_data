"""Tests for the fundamental report's VERIFIED FIGURES block.

Each rule here exists because a published report got the figure wrong when the
model derived it itself (``docs/FUNDAMENTAL_REPORT_REVIEW.md`` §12): TTM growth
taken from a quarterly field, FCF from Yahoo's levered figure, capex backed out
to make a table add up, WACC copied from the prompt's example.
"""

import pandas as pd
import pytest

from scripts.analysis.context import build_context
from scripts.analysis.context.fundamental_facts import (
    compute_facts, render_facts, statement_facts, wacc_inputs,
)
from scripts.analysis.data import fundamentals as F
from scripts.analysis.data import report_inputs

pytestmark = pytest.mark.unit

ENDS = ["2024-09-30", "2024-12-31", "2025-03-31", "2025-06-30",
        "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]


def _rows(revenue=(10, 10, 10, 10, 11, 11, 11, 16), **over):
    """Eight quarters; TTM revenue 49 vs 40 (+22.5%), latest quarter 16 vs 10 (+60%)."""
    rows = []
    for i, (end, rev) in enumerate(zip(ENDS, revenue)):
        r = {m: None for m in F.METRICS}
        r.update(period_end=end, fy=int(end[:4]), fp=f"Q{(i % 4) + 1}",
                 form="10-Q", filed=end, revenue=rev * 1e9,
                 gross_profit=rev * 0.5e9, operating_income=rev * 0.1e9,
                 net_income=rev * 0.08e9, eps_diluted=0.1, shares_diluted=1e9,
                 ocf=3e9, capex=1e9, cash_and_equiv=20e9,
                 short_term_investments=5e9, long_term_debt=10e9,
                 short_term_debt=0.0, total_equity=50e9, total_assets=90e9)
        r.update({k: v[i] for k, v in over.items()})
        rows.append(r)
    return rows


def _data(**info):
    base = {"currency": "USD", "financialCurrency": "USD", "beta": 1.2,
            "marketCap": 500e9, "quoteType": "EQUITY", "totalDebt": 10e9}
    base.update(info)
    return {"ticker": "TEST", "info": base, "price_now": 100.0,
            "price_date": "2026-10-22", "income": None, "income_q": None,
            "cashflow_q": None}


def _inputs(rows=None, **kw):
    out = {"store_rows": _rows() if rows is None else rows, "bars": [],
           "risk_free": 0.04, "peers": [], "status": {}}
    out.update(kw)
    return out


# ── statements ───────────────────────────────────────────────────────────────
def test_ttm_growth_and_latest_quarter_growth_are_kept_apart():
    s = statement_facts(_rows(), "2026-10-22")
    assert s["revenue_ttm"] == pytest.approx(49e9)
    assert s["revenue_growth_ttm"] == pytest.approx(0.225)
    assert s["revenue_growth_q"] == pytest.approx(0.60)


def test_fcf_is_ocf_minus_capex_from_the_filings():
    s = statement_facts(_rows(), "2026-10-22")
    assert (s["ocf_ttm"], s["capex_ttm"], s["fcf_ttm"]) == (12e9, 4e9, 8e9)


def test_net_cash_and_roic_come_from_the_closing_quarter():
    s = statement_facts(_rows(), "2026-10-22")
    assert s["net_cash"] == pytest.approx(15e9)            # 20 + 5 − 10
    # After-tax OI ÷ (50 + 10 − 25); no tax tagged, so the 21% default rate.
    assert s["roic_ttm"] == pytest.approx(4.9 * 0.79 / 35, abs=1e-4)


def test_stale_statements_are_not_quoted_as_current():
    assert statement_facts(_rows(), "2027-09-01") is None


def test_growth_needs_a_quarter_a_year_back_by_date_not_by_position():
    rows = _rows()
    del rows[0]                    # 7 rows: four back is no longer a year back
    rows[2]["period_end"] = "2025-01-15"
    assert statement_facts(rows, "2026-10-22")["revenue_growth_ttm"] is None


def test_without_sec_data_falls_back_to_yahoo_and_reports_no_ttm_growth():
    f = compute_facts(_data(revenueGrowth=0.6, totalRevenue=49e9), _inputs(rows=[]))
    s = f["statements"]
    assert s["source"].startswith("Yahoo")
    assert s["revenue_growth_ttm"] is None and s["revenue_growth_q"] == 0.6


def test_a_fund_gets_no_statements_and_no_wacc():
    f = compute_facts(_data(quoteType="ETF"), _inputs())
    assert f["is_fund"] and f["statements"] is None and f["wacc"] is None
    assert "has no income statement" in render_facts(f)


# ── cost of capital ──────────────────────────────────────────────────────────
def test_wacc_components_are_exposed_and_combine():
    income = pd.DataFrame({pd.Timestamp("2025-12-31"): [0.5e9, 10e9, 2e9]},
                          index=["Interest Expense", "Pretax Income", "Tax Provision"])
    d = _data()
    d["income"] = income
    w = wacc_inputs(d["info"], d, {"debt": 10e9}, 0.04)
    assert w["cost_of_equity"] == pytest.approx(0.04 + 1.2 * 0.05)
    assert w["pre_tax_cost_of_debt"] == pytest.approx(0.05)
    assert w["tax_rate"] == pytest.approx(0.20)
    we, wd = 500 / 510, 10 / 510
    assert w["wacc"] == pytest.approx(we * 0.10 + wd * 0.05 * 0.8)


def test_wacc_withheld_when_market_cap_and_debt_are_in_different_currencies():
    d = _data(currency="USD", financialCurrency="TWD")
    w = wacc_inputs(d["info"], d, {"debt": 10e9}, 0.04)
    assert w["cost_of_equity"] is not None and w["wacc"] is None


def test_an_implausible_tax_rate_falls_back_to_the_default():
    income = pd.DataFrame({pd.Timestamp("2025-12-31"): [8e9, 1e9]},
                          index=["Tax Provision", "Pretax Income"])
    d = _data()
    d["income"] = income
    w = wacc_inputs(d["info"], d, None, 0.04)
    assert (w["tax_rate"], w["tax_source"]) == (0.21, "default")


# ── rendering / context ──────────────────────────────────────────────────────
def test_rendered_block_labels_periods_and_forbids_back_solving():
    text = render_facts(compute_facts(_data(), _inputs()))
    assert "Price (last completed session close, 2026-10-22): 100.00 USD" in text
    assert "Revenue growth (TTM vs prior TTM):     22.5%" in text
    assert "Revenue growth (LATEST QUARTER YoY):   60.0%" in text
    assert "Free cash flow (TTM) = OCF − capex:    8.00B USD" in text
    assert "Never back out a missing figure" in text
    assert "9.41" not in text


def test_peer_rows_withhold_mixed_currency_ratios():
    peers = [{"ticker": "TSM", "currency": "USD", "financialCurrency": "TWD",
              "trailingPE": 25.0, "enterpriseToEbitda": 4.08},
             {"ticker": "INTC", "currency": "USD", "financialCurrency": "USD",
              "trailingPE": 30.0, "enterpriseToEbitda": 12.0}]
    text = render_facts(compute_facts(_data(), _inputs(peers=peers)))
    assert "4.1x" not in text and "N/A (mixed ccy)" in text and "12.0x" in text


def test_missing_peers_must_be_marked_as_estimates():
    assert "估計值" in render_facts(compute_facts(_data(), _inputs()))


def test_context_carries_the_block_only_when_attached(minimal_data):
    assert "VERIFIED FIGURES" not in build_context(minimal_data, "fundamental-analysis")
    minimal_data["report_facts"] = compute_facts(_data(), _inputs())
    assert "VERIFIED FIGURES" in build_context(minimal_data, "fundamental-analysis")


# ── report_inputs (network layer, stubbed) ───────────────────────────────────
def test_store_rows_survive_an_sec_outage(monkeypatch):
    monkeypatch.setattr(report_inputs.fundamentals, "load_store", lambda key: _rows())
    monkeypatch.setattr(report_inputs.fundamentals, "cik_map",
                        lambda: (_ for _ in ()).throw(OSError("offline")))
    rows, status = report_inputs.store_rows("TEST")
    assert len(rows) == 8 and status == {"fundamentals_store": True, "sec_live": False}


def test_store_rows_take_newer_quarters_from_a_live_fetch(monkeypatch):
    committed = _rows()[:6]
    monkeypatch.setattr(report_inputs.fundamentals, "load_store", lambda key: committed)
    monkeypatch.setattr(report_inputs.fundamentals, "cik_map", lambda: {"TEST": "1"})
    monkeypatch.setattr(report_inputs.fundamentals, "fetch_facts", lambda cik: {"facts": {}})
    monkeypatch.setattr(report_inputs.fundamentals, "resolve", lambda facts: _rows())
    rows, status = report_inputs.store_rows("TEST")
    assert rows[-1]["period_end"] == "2026-06-30" and status["sec_live"]


def test_peers_skip_a_failing_lookup(monkeypatch):
    import types

    class _T:
        def __init__(self, sym):
            if sym == "GM":
                raise RuntimeError("404")
            self.info = {"trailingPE": 9.0, "currency": "USD"}

    monkeypatch.setattr(report_inputs, "_get_yf", lambda: types.SimpleNamespace(Ticker=_T))
    peers = report_inputs.peer_multiples("TSLA")
    assert [p["ticker"] for p in peers] == ["F", "RIVN"]


def test_the_price_store_wins_when_its_close_is_newer():
    data = {"price_now": 386.47, "price_date": "2026-10-21"}
    bars = [{"date": "2026-10-21", "close": 386.47}, {"date": "2026-10-22", "close": 374.58}]
    assert report_inputs.prefer_newer_close(data, bars)
    assert (data["price_now"], data["price_date"]) == (374.58, "2026-10-22")


def test_the_price_store_fills_a_missing_yahoo_price():
    data = {"price_now": None, "price_date": None}
    assert report_inputs.prefer_newer_close(data, [{"date": "2026-10-22", "close": 106.9}])
    assert data["price_now"] == 106.9


def test_a_newer_yahoo_close_is_kept():
    data = {"price_now": 374.58, "price_date": "2026-10-22"}
    assert not report_inputs.prefer_newer_close(data, [{"date": "2026-10-21", "close": 386.47}])
    assert data["price_now"] == 374.58


# ── FX for ADRs whose statements are in another currency ─────────────────────
KRW = {"pair": "KRWUSD=X", "rate": 1 / 1322.46, "date": "2026-10-23"}


def _adr_inputs(fx):
    return _inputs(rows=[], fx=fx)


def _adr_data():
    d = _data(currency="USD", financialCurrency="KRW", marketCap=100e9, totalDebt=20e12,
              totalCash=80e12, totalRevenue=189.17e12)
    d["cashflow_q"] = pd.DataFrame(
        {pd.Timestamp(e): [v, -c] for e, v, c in [
            ("2026-06-30", 65.41e12, 11.13e12), ("2026-03-31", 26.33e12, 7.87e12),
            ("2025-12-31", 20.86e12, 12.25e12), ("2025-09-30", 14.32e12, 5.26e12)]},
        index=["Operating Cash Flow", "Capital Expenditure"])
    return d


def test_fx_rate_converts_fcf_yield_for_an_adr():
    """SKHY: ₩90.43T TTM FCF over a USD market cap needs the day's KRW rate."""
    f = compute_facts(_adr_data(), _adr_inputs(KRW))
    fcf_krw = (65.41 + 26.33 + 20.86 + 14.32 - 11.13 - 7.87 - 12.25 - 5.26) * 1e12   # ₩90.41T
    assert f["fcf_yield"] == pytest.approx(fcf_krw / 1322.46 / 100e9, rel=1e-6)


def test_fx_rate_lets_the_wacc_weight_converted_debt():
    d = _adr_data()
    d["income"] = pd.DataFrame({pd.Timestamp("2025-12-31"): [0.6e12]}, index=["Interest Expense"])
    w = compute_facts(d, _adr_inputs(KRW))["wacc"]
    assert w["pre_tax_cost_of_debt"] == pytest.approx(0.03)          # same-currency ratio
    debt_usd = 20e12 / 1322.46
    assert w["debt_weight"] == pytest.approx(debt_usd / (100e9 + debt_usd))


def test_rendered_block_states_the_rate_and_converted_amounts():
    text = render_facts(compute_facts(_adr_data(), _adr_inputs(KRW)))
    assert "1 USD = 1,322.46 KRW" in text and "KRWUSD=X, 2026-10-23" in text
    assert "do not assume another" in text
    assert "(≈ " in text and " USD)" in text


def test_without_fx_nothing_is_converted_and_assumed_rates_are_forbidden():
    f = compute_facts(_adr_data(), _adr_inputs(None))
    assert f["fcf_yield"] is None and f["wacc"]["wacc"] is None
    text = render_facts(f)
    assert "No FX rate is available" in text and "(≈ " not in text


def test_fx_rate_lookup_uses_the_statement_to_quote_pair(monkeypatch):
    import types
    seen = []

    class _T:
        def __init__(self, sym):
            seen.append(sym)

        def history(self, period):
            idx = pd.DatetimeIndex(["2026-10-23"])
            return pd.DataFrame({"Close": [0.000756]}, index=idx)

    monkeypatch.setattr(report_inputs, "_get_yf", lambda: types.SimpleNamespace(Ticker=_T))
    assert report_inputs.fx_rate("KRW", "USD") == {"pair": "KRWUSD=X", "rate": 0.000756,
                                                  "date": "2026-10-23"}
    assert report_inputs.fx_rate("USD", "USD") is None and seen == ["KRWUSD=X"]


def test_gather_reports_fx_status_only_when_currencies_differ(monkeypatch):
    for name, value in [("store_rows", ([], {})), ("risk_free_rate", None),
                        ("peer_multiples", []), ("fx_rate", None)]:
        monkeypatch.setattr(report_inputs, name, lambda *a, _v=value: _v)
    monkeypatch.setattr(report_inputs.prices, "load_store", lambda key: [])
    assert "fx_rate" not in report_inputs.gather("AMD", {"currency": "USD", "financialCurrency": "USD"})["status"]
    assert report_inputs.gather("SKHY", {"currency": "USD", "financialCurrency": "KRW"})["status"]["fx_rate"] is False
