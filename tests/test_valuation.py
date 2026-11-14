"""The fundamental report's valuation, computed in Python.

Each rule here answers a finding of the 2026-11-14 report review
(``docs/REPORT_REVIEW.md`` F1, F2, F5, F6): the model chose the §8.8 weights,
discounted at a raw beta, used methods that returned the price they were meant
to test, and filled the DCF tables by hand.
"""

import pytest

from scripts.analysis.config.valuation import (
    BETA_BOUNDS, CONSENSUS_WEIGHT, FCFF_TERMINAL_GROWTH, FCFF_YEARS,
    VALUATION_WEIGHTS, WACC_BOUNDS,
)
from scripts.analysis.context import valuation as V
from scripts.analysis.data import intrinsic_value as iv
from scripts.analysis.validate import arithmetic

pytestmark = pytest.mark.unit


# ── the FCFF model ───────────────────────────────────────────────────────────
def test_fade_runs_linearly_from_the_first_year_to_the_last():
    assert iv.fade(0.30, 0.03, 10)[0] == 0.30 and iv.fade(0.30, 0.03, 10)[-1] == pytest.approx(0.03)
    assert iv.fade(0.1, 0.4, 4) == pytest.approx([0.1, 0.2, 0.3, 0.4])


def test_fcff_dcf_matches_hand_arithmetic():
    # One year: revenue 100 → 110, EBIT 22, tax 4.4, NOPAT 17.6, D&A 5.5,
    # capex 6.6, FCFF 16.5, discounted at 10% → 15.0.
    m = iv.fcff_dcf(100.0, [0.10], [0.20], 0.20, 0.05, [0.06], 0.10, 0.03, net_cash=7.0)
    y = m["years"][0]
    assert (y["revenue"], y["ebit"], y["nopat"]) == pytest.approx((110.0, 22.0, 17.6))
    assert y["fcff"] == pytest.approx(16.5) and y["pv"] == pytest.approx(15.0)
    # Terminal value 16.5 × 1.03 ÷ (0.10 − 0.03) = 242.79, discounted one year.
    assert m["terminal_value"] == pytest.approx(16.5 * 1.03 / 0.07)
    assert m["enterprise_value"] == pytest.approx(15.0 + m["terminal_value"] / 1.10)
    assert m["equity_value"] == pytest.approx(m["enterprise_value"] + 7.0)


@pytest.mark.parametrize("kw", [
    {"op_margin": [-0.05]},          # a loss discounted forward is not a value
    {"wacc": 0.03},                  # WACC must exceed terminal growth
    {"da_pct": None},                # a missing input, never a guess
    {"capex_pct": [0.50]},           # capex above NOPAT + D&A: negative terminal FCFF
])
def test_fcff_dcf_refuses_what_it_cannot_value(kw):
    args = dict(revenue=100.0, growth=[0.10], op_margin=[0.20], tax_rate=0.20, da_pct=0.05,
                capex_pct=[0.06], wacc=0.10, terminal_growth=0.03)
    args.update(kw)
    assert iv.fcff_dcf(**args) is None


def test_sensitivity_is_computed_cell_by_cell_and_blank_where_wacc_is_not_above_g():
    def model(w, g):
        return iv.fcff_dcf(100.0, [0.10], [0.20], 0.20, 0.05, [0.06],
                           0.04 if w is None else w, 0.03 if g is None else g)
    grid = iv.fcff_sensitivity(model)
    centre = grid["values"][2][2]
    assert centre == pytest.approx(model(None, None)["equity_value"])
    assert grid["values"][4][0] is None                      # WACC 2% ≤ g 4%
    row = [v for v in grid["values"][0] if v is not None]    # a higher WACC is worth less
    assert row == sorted(row, reverse=True)


def test_solve_finds_the_input_and_reports_no_solution_out_of_range():
    assert iv.solve(lambda x: x * 10, 25.0, 0.0, 10.0) == pytest.approx(2.5)
    assert iv.solve(lambda x: x * 10, 250.0, 0.0, 10.0) is None


# ── cost of capital ──────────────────────────────────────────────────────────
def test_beta_is_blume_adjusted_and_held_in_a_band():
    assert V.adjusted_beta(1.6)[0] == pytest.approx(2 / 3 * 1.6 + 1 / 3)
    assert V.adjusted_beta(3.18)[0] == BETA_BOUNDS[1]        # RKLB's raw beta
    assert V.adjusted_beta(0.1)[0] == BETA_BOUNDS[0]
    beta, note = V.adjusted_beta(None)
    assert beta == 1.0 and "assumed" in note


def test_wacc_outside_the_band_is_held_at_the_bound():
    assert V.banded_wacc(0.1626) == WACC_BOUNDS[1]           # NVDA 2026-11-14
    assert V.banded_wacc(0.05) == WACC_BOUNDS[0]
    assert V.banded_wacc(0.10) == 0.10 and V.banded_wacc(None) is None


# ── company type ─────────────────────────────────────────────────────────────
def test_company_type_decides_the_weight_row():
    profit, loss = {"op_margin_ttm": 0.2}, {"op_margin_ttm": -0.1}
    assert V.archetype("nvda", {"sector": "Technology"}, profit) == "profitable"
    assert V.archetype("rklb", {"sector": "Industrials"}, loss) == "unprofitable"
    assert V.archetype("mu", {"sector": "Technology"}, profit) == "cyclical"
    assert V.archetype("sofi", {"sector": "Financial Services"}, profit) == "financial"
    assert V.archetype("x", {}, None) == "unprofitable"


# ── methods ──────────────────────────────────────────────────────────────────
PEERS = [
    {"ticker": "AAA", "forwardPE": 20.0, "enterpriseToEbitda": 15.0,
     "priceToSalesTrailing12Months": 5.0, "priceToBook": 4.0},
    {"ticker": "BBB", "forwardPE": 30.0, "enterpriseToEbitda": 25.0,
     "priceToSalesTrailing12Months": 9.0, "priceToBook": 6.0},
    {"ticker": "CCC", "forwardPE": 400.0, "enterpriseToEbitda": None,     # no earnings to speak of
     "priceToSalesTrailing12Months": 7.0, "priceToBook": 5.0},
]
STMT = {"revenue_ttm": 100e9, "op_margin_ttm": 0.30, "revenue_growth_ttm": 0.20,
        "da_ttm": 5e9, "capex_ttm": 6e9, "ebitda_ttm": 35e9, "net_cash": 10e9,
        "roic_ttm": 0.25, "op_margin_history": [0.20, 0.25, 0.28]}
INFO = {"marketCap": 1000e9, "forwardEps": 4.0, "bookValue": 20.0,
        "targetMeanPrice": 150.0, "numberOfAnalystOpinions": 30, "sector": "Technology",
        "currency": "USD", "financialCurrency": "USD"}
WACC = {"wacc": 0.10, "tax_rate": 0.20}


def test_peer_median_drops_outliers_and_needs_two_peers():
    multiple, used = V.peer_median(PEERS, "fwd_pe")
    assert multiple == 25.0 and used == ["AAA", "BBB"]       # 400x is left out
    assert V.peer_median(PEERS[:1], "fwd_pe")[0] is None
    mixed = [dict(p, currency="USD", financialCurrency="KRW") for p in PEERS]
    assert V.peer_median(mixed, "ps")[0] is None             # Yahoo divides USD by KRW
    assert V.peer_median(mixed, "fwd_pe")[0] == 25.0         # a per-share ratio is fine


def test_relative_methods_use_the_peer_median_never_the_companys_own_multiple():
    """NVDA 2026-11-14 held its own EV/EBITDA flat and got back its own price."""
    values = V.method_values(INFO, STMT, PEERS, {"available": False}, 100.0, 1000e9, 1.0)
    assert values["fwd_pe"]["value"] == pytest.approx(25.0 * 4.0)
    # EV = 20x × 35B = 700B, + 10B net cash = 710B, over 10B implied shares.
    assert values["ev_ebitda"]["value"] == pytest.approx(71.0)
    assert values["ps"]["value"] == pytest.approx(7.0 * 100e9 / 10e9)
    assert values["pb"]["value"] == pytest.approx(5.0 * 20.0)
    assert values["consensus"]["value"] == 150.0
    assert "dcf" not in values
    # Doubling the price changes no relative value: none of them reads it.
    again = V.method_values(INFO, STMT, PEERS, {"available": False}, 200.0, 2000e9, 1.0)
    assert again["fwd_pe"]["value"] == values["fwd_pe"]["value"]
    assert again["ev_ebitda"]["value"] == pytest.approx(values["ev_ebitda"]["value"])


def test_weights_are_fixed_by_type_and_sum_to_100():
    values = {k: {"value": 100.0, "basis": ""} for k in ("dcf", "fwd_pe", "ev_ebitda", "consensus")}
    rows = V.weigh("profitable", values)
    assert {r["key"]: r["weight_pct"] for r in rows} == {
        "dcf": 40, "fwd_pe": 25, "ev_ebitda": 25, "consensus": 10}
    for kind, base in VALUATION_WEIGHTS.items():
        assert sum(base.values()) == pytest.approx(1 - CONSENSUS_WEIGHT), kind


def test_a_method_without_a_value_drops_out_and_the_rest_are_rescaled():
    values = {k: {"value": 100.0, "basis": ""} for k in ("fwd_pe", "ev_ebitda", "consensus")}
    rows = V.weigh("profitable", values)                      # no DCF
    weights = {r["key"]: r["weight_pct"] for r in rows}
    assert weights == {"fwd_pe": 45, "ev_ebitda": 45, "consensus": 10}
    assert sum(weights.values()) == 100


def test_consensus_is_capped_and_is_never_a_valuation_on_its_own():
    assert V.weigh("profitable", {"consensus": {"value": 150.0, "basis": ""}}) == []
    values = {"ps": {"value": 50.0, "basis": ""}, "consensus": {"value": 150.0, "basis": ""}}
    assert {r["key"]: r["weight_pct"] for r in V.weigh("unprofitable", values)} == {
        "ps": 90, "consensus": 10}
    assert V.weigh("unprofitable", {"ps": {"value": 50.0, "basis": ""}})[0]["weight_pct"] == 100


def test_rating_follows_rule_20():
    assert [V.rating(m, 0.2, 0.1) for m in (-30, -15, 0, 15, 30)] == [
        "賣出", "減碼", "持有", "買入", "強烈買入"]
    assert V.rating(30, 0.05, 0.1) == "買入"                  # MOS ≥ 25% but ROIC ≤ WACC
    assert V.rating(None, 0.2, 0.1) is None


# ── the DCF as the report gets it ────────────────────────────────────────────
def test_dcf_assumptions_come_from_the_statements_not_from_the_model():
    d = V.build_dcf(STMT, 0.10, 0.20, 100.0, 1000e9, 1.0, "profitable")
    a = d["assumptions"]
    assert d["available"] and a["years"] == FCFF_YEARS
    assert a["start_growth"] == 0.20 and a["terminal_growth"] == FCFF_TERMINAL_GROWTH
    # Margin fades from TTM 30% to the median of (20, 25, 28, 30) = 26.5%.
    assert a["op_margin"] == 0.30 and a["op_margin_end"] == pytest.approx(0.265)
    years = d["model"]["years"]
    assert years[0]["op_margin"] == pytest.approx(0.30) and years[-1]["op_margin"] == pytest.approx(0.265)
    assert years[0]["growth"] == pytest.approx(0.20) and years[-1]["growth"] == pytest.approx(0.03)
    # Capex 6% fades to 1.1 × D&A (5%) = 5.5%.
    assert years[-1]["capex_pct"] == pytest.approx(0.055)
    assert d["value"] == pytest.approx(d["model"]["equity_value"] * 100.0 / 1000e9)


def test_growth_is_held_inside_its_band():
    hot = V.build_dcf(dict(STMT, revenue_growth_ttm=0.834), 0.10, 0.2, 100.0, 1000e9, 1.0, "profitable")
    assert hot["assumptions"]["start_growth"] == 0.30 and hot["assumptions"]["raw_growth"] == 0.834
    shrinking = V.build_dcf(dict(STMT, revenue_growth_ttm=-0.2), 0.10, 0.2, 100.0, 1000e9, 1.0, "profitable")
    assert shrinking["assumptions"]["start_growth"] == 0.0


def test_too_little_margin_history_holds_ttm():
    d = V.build_dcf(dict(STMT, op_margin_history=[0.10]), 0.10, 0.2, 100.0, 1000e9, 1.0, "profitable")
    assert d["assumptions"]["op_margin_end"] == 0.30 and d["assumptions"]["margin_years"] == 0


def test_scenarios_and_reverse_dcf_are_solved_not_estimated():
    d = V.build_dcf(STMT, 0.10, 0.20, 100.0, 1000e9, 1.0, "profitable")
    bear, base, bull = (s["value"] for s in d["scenarios"])
    assert bear < base < bull and base == pytest.approx(d["value"])
    assert d["scenario_weighted"] == pytest.approx(0.25 * bear + 0.5 * base + 0.25 * bull)
    grid = d["sensitivity"]
    assert grid["values"][2][2] == pytest.approx(d["value"])
    # At a price 5% under the model's value, the growth the price implies is a
    # little under the base case, and fed back in it reproduces that price.
    price = d["value"] * 0.95
    cheap = V.build_dcf(STMT, 0.10, 0.20, price, price * 10e9, 1.0, "profitable")
    assert 0.0 < cheap["implied_growth"] < 0.20
    back = V.build_dcf(dict(STMT, revenue_growth_ttm=cheap["implied_growth"]),
                       0.10, 0.20, price, price * 10e9, 1.0, "profitable")
    assert back["value"] == pytest.approx(price, rel=1e-4)
    assert 0.0 < cheap["implied_margin"] < 0.30


def test_reverse_dcf_reports_no_solution_rather_than_a_number():
    # A price a hundred times the model's value: no growth up to 100% reaches it.
    d = V.build_dcf(STMT, 0.10, 0.20, 100.0, 1000e9, 1.0, "profitable")
    dear = V.build_dcf(STMT, 0.10, 0.20, d["value"] * 100, d["value"] * 100 * 10e9, 1.0, "profitable")
    assert dear["implied_growth"] is None and dear["implied_margin"] is None


@pytest.mark.parametrize("stmt, kind, word", [
    (STMT, "financial", "lender"),
    (dict(STMT, op_margin_ttm=-0.1), "unprofitable", "not positive"),
    (dict(STMT, da_ttm=None), "profitable", "D&A"),
    (None, "profitable", "missing"),
])
def test_dcf_says_why_it_is_unavailable(stmt, kind, word):
    d = V.build_dcf(stmt, 0.10, 0.20, 100.0, 1000e9, 1.0, kind)
    assert not d["available"] and word in d["reason"]


def test_dcf_needs_an_fx_rate_when_currencies_differ():
    assert not V.build_dcf(STMT, 0.10, 0.20, 100.0, 1000e9, None, "profitable")["available"]
    usd = V.build_dcf(STMT, 0.10, 0.20, 100.0, 1000e9, 1.0, "profitable")["value"]
    # Statements in a currency worth half a quote-currency unit: half the value.
    assert V.build_dcf(STMT, 0.10, 0.20, 100.0, 1000e9, 0.5, "profitable")["value"] == pytest.approx(usd / 2)


# ── assembly ─────────────────────────────────────────────────────────────────
def test_build_gives_one_fair_value_mos_and_rating():
    v = V.build("test", INFO, STMT, WACC, PEERS, 100.0, 1.0)
    assert v["archetype"] == "profitable"
    assert [r["key"] for r in v["methods"]] == ["dcf", "fwd_pe", "ev_ebitda", "consensus"]
    total = round(sum(r["value"] * r["weight_pct"] / 100 for r in v["methods"]), 2)
    assert v["fair_value"] == total
    assert v["mos_pct"] == round((total - 100) / total * 100, 1)
    assert v["rating"] == V.rating(v["mos_pct"], 0.25, 0.10)


def test_build_without_any_method_gives_no_fair_value_and_no_rating():
    v = V.build("test", {"marketCap": 1e9}, {"op_margin_ttm": -0.2}, WACC, [], 10.0, 1.0)
    assert v["methods"] == [] and v["fair_value"] is None and v["rating"] is None


def test_front_matter_summary_round_trips():
    v = V.build("test", INFO, STMT, WACC, PEERS, 100.0, 1.0)
    parsed = arithmetic.parse_valuation(V.summary(v))
    assert [(k, w) for k, _, w in parsed] == [(r["key"], r["weight_pct"] / 100) for r in v["methods"]]
    assert [val for _, val, _ in parsed] == [r["value"] for r in v["methods"]]
    assert V.summary(None) == "" and arithmetic.parse_valuation("") == []
