"""Tests for the DCF / WACC models (scripts/analysis/data/intrinsic_value.py).

Same rule as tests/test_fundamental_analytics.py: every expected value is worked
by hand here, so the figures on the Intrinsic value tab are asserted against
arithmetic rather than against a previous run of the same code.
"""

import pytest

from analysis.data import intrinsic_value as IV

pytestmark = pytest.mark.unit


def fy(year, **m):
    """One annual entry, as fundamental_analytics.annual_series returns them."""
    e = {"period_end": f"{year}-12-31", "fy": year, "fp": "FY",
         "shares_diluted": 10.0}
    e.update(m)
    return e


# ── CAGR ─────────────────────────────────────────────────────────────────────
def test_cagr_is_the_compound_rate():
    assert IV.cagr(100.0, 121.0, 2) == pytest.approx(0.10)
    assert IV.cagr(100.0, 50.0, 1) == pytest.approx(-0.5)


@pytest.mark.parametrize("first,last", [(-1.0, 5.0), (5.0, -1.0), (0.0, 5.0),
                                        (None, 5.0), (5.0, None)])
def test_cagr_has_no_rate_across_a_sign_change(first, last):
    """Growth from a loss to a profit is not a percentage."""
    assert IV.cagr(first, last, 3) is None


# ── DCF ──────────────────────────────────────────────────────────────────────
def test_dcf_with_growth_equal_to_discount_is_the_base_times_years():
    """g = d makes x = 1, so the growth stage is base × 10; terminal growth =
    discount makes y = 1, so the terminal stage is base × 10 too."""
    v = IV.dcf(2.0, 0.10, discount=0.10, terminal_growth=0.10)
    assert v["growth_value"] == pytest.approx(20.0)
    assert v["terminal_value"] == pytest.approx(20.0)
    assert v["fair_value"] == pytest.approx(40.0)


def test_dcf_one_year_each_stage_by_hand():
    # x = 1.2/1.1, y = 1.05/1.1
    # growth = 1 · x = 1.090909…; terminal = 1 · x · y = 1.041322…
    v = IV.dcf(1.0, 0.20, discount=0.10, growth_years=1, terminal_years=1,
               terminal_growth=0.05)
    assert v["growth_value"] == pytest.approx(1.2 / 1.1)
    assert v["terminal_value"] == pytest.approx(1.2 / 1.1 * 1.05 / 1.1)


@pytest.mark.parametrize("base", [0.0, -1.5, None])
def test_dcf_has_no_value_for_a_loss(base):
    assert IV.dcf(base, 0.1) is None


def test_margin_of_safety_sign():
    assert IV.margin_of_safety(100.0, 80.0) == pytest.approx(20.0)
    assert IV.margin_of_safety(100.0, 150.0) == pytest.approx(-50.0)
    assert IV.margin_of_safety(None, 80.0) is None


def test_implied_growth_inverts_the_dcf():
    fair = IV.dcf(3.0, 0.12)["fair_value"]
    assert IV.implied_growth(3.0, fair) == pytest.approx(0.12, abs=1e-6)


def test_implied_growth_is_none_when_no_rate_justifies_the_price():
    """A price beyond what 100% a year produces is reported, not invented."""
    assert IV.implied_growth(0.01, 1e9) is None
    assert IV.implied_growth(-1.0, 50.0) is None


def test_sensitivity_centre_cell_is_the_base_case():
    s = IV.sensitivity(2.0, 0.10, discount=0.10)
    assert s["discount_rates"] == [0.08, 0.09, 0.10, 0.11, 0.12]
    assert s["growth_rates"] == [0.06, 0.08, 0.10, 0.12, 0.14]
    assert s["values"][2][2] == pytest.approx(round(IV.dcf(2.0, 0.10)["fair_value"], 2))
    # Fair value rises with growth and falls with the discount rate.
    assert s["values"][2][0] < s["values"][2][4]
    assert s["values"][0][2] > s["values"][4][2]


def test_verdict_bands():
    assert IV.verdict(60.0, 100.0) == "sig_under"
    assert IV.verdict(90.0, 100.0) == "under"
    assert IV.verdict(120.0, 100.0) == "over"
    assert IV.verdict(400.0, 100.0) == "sig_over"
    assert IV.verdict(50.0, None) is None


# ── per-share growth ─────────────────────────────────────────────────────────
def test_per_share_divides_totals_by_diluted_shares():
    e = fy(2025, revenue=1000.0, operating_income=200.0, dep_amort=50.0,
           ocf=300.0, capex=100.0, total_equity=500.0, eps_diluted=1.5)
    ps = IV.per_share(e)
    assert ps["eps"] == 1.5                 # reported, not recomputed
    assert ps["revenue"] == 100.0           # 1000 / 10
    assert ps["ebitda"] == 25.0             # (200 + 50) / 10
    assert ps["fcf"] == 20.0                # (300 − 100) / 10
    assert ps["book_value"] == 50.0
    assert ps["dividends"] is None          # never tagged → absent, not zero


def test_growth_table_windows_need_years_exactly_that_far_apart():
    annual = [fy(y, revenue=100.0 * 1.1 ** (y - 2019)) for y in range(2019, 2026)]
    rows = IV.growth_table(annual, None)["rows"]
    # 2020 → 2025 is five years of 10% growth, 2022 → 2025 three, 2024 → 2025 one.
    for n in (5, 3, 1):
        assert rows["revenue"]["cagr"][n] == pytest.approx(0.10)
    # The last three fiscal years are shown alongside.
    assert [y for y, _ in rows["revenue"]["years"]] == [2023, 2024, 2025]


def test_growth_table_has_no_window_across_a_missing_year():
    annual = [fy(2019, revenue=100.0), fy(2025, revenue=200.0)]
    rows = IV.growth_table(annual, None)["rows"]
    assert rows["revenue"]["cagr"] == {5: None, 3: None, 1: None}


def test_default_growth_prefers_ebitda_then_clamps():
    annual = [fy(y, revenue=100.0, operating_income=10.0 * 1.5 ** (y - 2020),
                 dep_amort=0.0) for y in range(2020, 2026)]
    g = IV.default_growth(annual)
    assert g["metric"] == "ebitda" and g["years"] == 5
    assert g["raw"] == pytest.approx(0.5)
    assert g["rate"] == IV.GROWTH_CAP       # 50% a year is capped at 20%


def test_default_growth_falls_back_to_revenue_when_ebitda_has_no_rate():
    annual = [fy(y, revenue=100.0 * 1.05 ** (y - 2022), operating_income=-5.0,
                 dep_amort=1.0) for y in range(2022, 2026)]
    g = IV.default_growth(annual)
    assert g["metric"] == "revenue" and g["years"] == 3
    assert g["rate"] == pytest.approx(0.05)


def test_default_growth_floors_a_shrinking_history_at_flat():
    annual = [fy(y, revenue=100.0 * 0.9 ** (y - 2022)) for y in range(2022, 2026)]
    assert IV.default_growth(annual)["rate"] == IV.GROWTH_FLOOR


# ── WACC ─────────────────────────────────────────────────────────────────────
def test_wacc_by_hand():
    # cap = 10 × 100 = 1000, debt 250 → weights 0.8 / 0.2
    # ke = 4.25% + 1.2 × 5.5% = 10.85%; kd = 10 / 250 = 4%; tax = 20 / 100 = 20%
    # WACC = 0.8 × 10.85% + 0.2 × 4% × 0.8 = 8.68% + 0.64% = 9.32%
    e = fy(2025, long_term_debt=250.0, interest_expense=10.0,
           income_tax=20.0, pretax_income=100.0)
    w = IV.wacc(e, 100.0, 1.2)
    assert w["weight_equity"] == pytest.approx(0.8)
    assert w["cost_equity"] == pytest.approx(0.1085)
    assert w["cost_debt"] == pytest.approx(0.04)
    assert w["tax_rate"] == pytest.approx(0.20)
    assert w["wacc"] == pytest.approx(0.0932)


def test_wacc_without_debt_is_the_cost_of_equity():
    w = IV.wacc(fy(2025), 100.0, 1.0)
    assert w["weight_debt"] == 0.0
    assert w["wacc"] == pytest.approx(IV.RISK_FREE_RATE + IV.EQUITY_RISK_PREMIUM)


def test_wacc_rejects_an_implausible_cost_of_debt():
    """Interest tagged against a sliver of debt is a mis-tag, not a 400% rate."""
    e = fy(2025, long_term_debt=1.0, interest_expense=4.0)
    assert IV.wacc(e, 100.0, 1.0)["cost_debt"] == IV.RISK_FREE_RATE


def test_wacc_needs_a_beta_and_a_market_cap():
    assert IV.wacc(fy(2025), 100.0, None) is None
    assert IV.wacc(fy(2025), None, 1.0) is None


# ── the whole model ──────────────────────────────────────────────────────────
def _quarters(eps=1.0):
    rows = []
    for i, end in enumerate(["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"]):
        rows.append({"period_end": end, "fy": 2025, "fp": f"Q{i + 1}",
                     "form": "10-Q", "filed": end, "revenue": 100.0,
                     "operating_income": 20.0, "net_income": 10.0,
                     "eps_diluted": eps, "shares_diluted": 10.0,
                     "ocf": 15.0, "capex": 5.0, "total_equity": 500.0,
                     "dep_amort": 2.0})
    return rows


def test_model_prefers_eps_and_values_both_bases():
    bars = [{"date": "2026-01-02", "close": 40.0}]
    m = IV.model(_quarters(), bars)
    assert m["primary"] == "eps"
    assert m["bases"]["eps"]["base"] == 4.0          # four quarters of 1.0
    assert m["bases"]["fcf"]["base"] == 4.0          # (60 − 20) / 10
    assert m["price"] == 40.0
    assert m["wacc"] is None                         # no market store, no beta


def test_model_has_no_primary_basis_for_a_loss_maker():
    rows = _quarters(eps=-1.0)
    for r in rows:
        r["ocf"] = -5.0
    m = IV.model(rows, [{"date": "2026-01-02", "close": 40.0}])
    assert m["primary"] is None
    assert m["sensitivity"] is None


def test_model_needs_a_price():
    assert IV.model(_quarters(), []) is None
