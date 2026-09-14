"""Tests for derived fundamentals (scripts/analysis/data/fundamental_analytics.py).

Every expected value here is worked by hand in the test itself, so the numbers
the site publishes are asserted against arithmetic rather than against a
previous run of the same code — the rule tests/test_price_analytics.py follows.

The other half of the file is about *absence*: a company that does not tag a
concept must produce None rather than a zero, because a zero on a financial page
asserts something false. AMZN genuinely does not tag quarterly gross profit.
"""

import pytest

from analysis.data import fundamental_analytics as FA

pytestmark = pytest.mark.unit


# ── helpers ──────────────────────────────────────────────────────────────────
def row(period_end, fy, fp, **m):
    r = {"period_end": period_end, "fy": fy, "fp": fp,
         "form": "10-Q", "filed": "2026-01-31"}
    r.update(m)
    return r


def four_quarters(**overrides):
    """FY2025: revenue 100/200/300/400, net income 10/20/30/40."""
    ends = ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"]
    rows = []
    for i, end in enumerate(ends):
        metrics = {
            "revenue": 100.0 * (i + 1),
            "gross_profit": 50.0 * (i + 1),
            "operating_income": 20.0 * (i + 1),
            "net_income": 10.0 * (i + 1),
            "eps_diluted": 1.0 * (i + 1),
            "shares_diluted": 10.0,
            "ocf": 30.0 * (i + 1),
            "capex": 5.0 * (i + 1),
            "total_assets": 1000.0,
            "total_equity": 500.0,
            "long_term_debt": 200.0,
            "cash_and_equiv": 100.0,
            "dep_amort": 5.0,
        }
        metrics.update(overrides)
        rows.append(row(end, 2025, f"Q{i + 1}", **metrics))
    return rows


def bar(date, close):
    return {"date": date, "close": close}


# ── TTM ──────────────────────────────────────────────────────────────────────
def test_ttm_sums_flows_and_carries_levels():
    t = FA.ttm(four_quarters())
    assert t["revenue"] == 1000.0            # 100+200+300+400
    assert t["net_income"] == 100.0          # 10+20+30+40
    assert t["ocf"] == 300.0                 # 30+60+90+120
    assert t["total_assets"] == 1000.0       # a level, carried not summed
    assert t["shares_diluted"] == 10.0       # an average, carried not summed
    assert t["eps_diluted"] == 10.0          # per-share earnings do accumulate


def test_ttm_needs_four_quarters():
    assert FA.ttm(four_quarters()[:3]) is None
    assert FA.ttm([]) is None


def test_ttm_is_none_when_a_quarter_lacks_the_metric():
    """A three-quarter sum is not a trailing-twelve-month figure."""
    rows = four_quarters()
    rows[1]["revenue"] = None
    assert FA.ttm(rows)["revenue"] is None


def test_ttm_series_starts_at_the_fourth_quarter():
    rows = four_quarters() + [row("2026-03-31", 2026, "Q1", revenue=500.0)]
    assert [t["period_end"] for t in FA.ttm_series(rows)] == \
        ["2025-12-31", "2026-03-31"]


def test_annual_series_skips_an_incomplete_year():
    rows = four_quarters() + [row("2026-03-31", 2026, "Q1", revenue=500.0)]
    years = FA.annual_series(rows)
    assert [y["fy"] for y in years] == [2025]
    assert years[0]["revenue"] == 1000.0


# ── growth ───────────────────────────────────────────────────────────────────
def test_yoy_compares_against_the_same_quarter_a_year_earlier():
    rows = four_quarters()
    rows += [row("2026-03-31", 2026, "Q1", revenue=150.0)]   # vs 100 → +50%
    assert FA.yoy_growth(rows, "revenue") == [{"t": "2026-03-31", "v": 50.0}]


def test_yoy_omits_a_point_whose_base_was_a_loss():
    """A swing from loss to profit is not a percentage."""
    rows = four_quarters()
    rows[0]["net_income"] = -10.0
    rows += [row("2026-03-31", 2026, "Q1", net_income=5.0)]
    assert FA.yoy_growth(rows, "net_income") == []


# ── margins and returns ──────────────────────────────────────────────────────
def test_margins_are_percentages_of_revenue():
    t = FA.ttm(four_quarters())          # revenue 1000, gross 500, op 200, net 100
    m = FA.margins(t)
    assert m["gross"] == pytest.approx(50.0)
    assert m["operating"] == pytest.approx(20.0)
    assert m["net"] == pytest.approx(10.0)


def test_margins_are_none_when_the_line_is_untagged():
    """AMZN does not tag quarterly gross profit; 0% would be a lie."""
    t = FA.ttm(four_quarters(gross_profit=None))
    assert FA.margins(t)["gross"] is None
    assert FA.margins(t)["net"] == pytest.approx(10.0)


def test_returns_on_capital_are_hand_checkable():
    t = FA.ttm(four_quarters())
    r = FA.returns_on_capital(t)
    assert r["roe"] == pytest.approx(20.0)   # net 100 / equity 500
    assert r["roa"] == pytest.approx(10.0)   # net 100 / assets 1000
    assert r["ros"] == pytest.approx(10.0)   # net 100 / revenue 1000
    # invested capital = equity 500 + debt 200 - cash 100 = 600; op income 200
    assert r["roic"] == pytest.approx(200.0 / 600.0 * 100.0)


def test_total_debt_tolerates_a_company_with_no_short_term_debt():
    assert FA.total_debt({"long_term_debt": 200.0, "short_term_debt": None}) == 200.0
    assert FA.total_debt({"long_term_debt": None, "short_term_debt": None}) is None


def test_free_cash_flow_subtracts_capex():
    t = FA.ttm(four_quarters())              # ocf 300, capex 50
    assert FA.free_cash_flow(t) == pytest.approx(250.0)


def test_ebitda_adds_back_depreciation():
    t = FA.ttm(four_quarters())              # op income 200, d&a 20
    assert FA.ebitda(t) == pytest.approx(220.0)


# ── valuation: the join against prices ───────────────────────────────────────
def test_multiples_are_hand_checkable():
    t = FA.ttm(four_quarters())              # revenue 1000, eps 10, equity 500
    m = FA.multiples(t, price=50.0)          # cap = 50 × 10 shares = 500
    assert m["pe"] == pytest.approx(5.0)     # 50 / 10
    assert m["ps"] == pytest.approx(0.5)     # 500 / 1000
    assert m["pb"] == pytest.approx(1.0)     # 500 / 500
    # EV = cap 500 + debt 200 - cash 100 = 600
    assert m["ev_sales"] == pytest.approx(0.6)
    assert m["ev_ebitda"] == pytest.approx(600.0 / 220.0)


def test_pe_is_none_when_earnings_are_negative():
    t = FA.ttm(four_quarters(eps_diluted=-1.0))
    assert FA.multiples(t, price=50.0)["pe"] is None


def test_multiples_are_none_without_a_price():
    assert FA.multiples(FA.ttm(four_quarters()), price=None)["ps"] is None


def test_price_lookup_falls_back_to_the_last_session_before_the_period_end():
    """Fiscal periods end on dates the market may not have traded."""
    bars = [bar("2025-12-29", 10.0), bar("2025-12-31", 12.0)]
    assert FA._close_on_or_before(bars, "2025-12-31") == 12.0
    assert FA._close_on_or_before(bars, "2025-12-30") == 10.0
    assert FA._close_on_or_before(bars, "2020-01-01") is None


def test_valuation_series_emits_one_point_per_ttm_period():
    rows = four_quarters()
    bars = [bar("2025-12-31", 50.0)]
    series = FA.valuation_series(rows, bars)
    assert series["ps"] == [{"t": "2025-12-31", "v": 0.5}]


def test_valuation_series_skips_periods_with_no_price_history():
    series = FA.valuation_series(four_quarters(), bars=[])
    assert series["ps"] == []


# ── the P/E river ────────────────────────────────────────────────────────────
def test_pe_bands_need_enough_history_to_rank():
    assert FA.pe_bands(four_quarters(), [bar("2025-12-31", 50.0)]) == {}


def test_pe_bands_sample_monthly_and_scale_eps_by_each_level():
    rows = four_quarters()
    for i, q in enumerate(["2026-03-31", "2026-06-30", "2026-09-30"]):
        rows.append(row(q, 2026, f"Q{i + 1}", revenue=100.0, gross_profit=50.0,
                        operating_income=20.0, net_income=10.0, eps_diluted=1.0,
                        shares_diluted=10.0, total_assets=1000.0,
                        total_equity=500.0))
    # Prices must reach back to the first TTM period end, or there is nothing
    # to rank and the chart is correctly withheld.
    bars = [bar("2025-12-31", 40.0)] + [bar(f"2026-{m:02d}-15", 40.0 + m)
                                        for m in range(1, 10)]
    out = FA.pe_bands(rows, bars)
    assert out["levels"]
    # One point per calendar month, and each band is eps × its level.
    assert len({p["t"][:7] for p in out["price"]}) == len(out["price"])
    lv = out["levels"][0]
    first = out["bands"][str(lv)][0]
    assert first["v"] == pytest.approx(lv * 10.0)  # TTM eps = 1+2+3+4


# ── summary ──────────────────────────────────────────────────────────────────
def test_summary_of_an_empty_store_is_none():
    assert FA.summary([]) is None


def test_summary_carries_ttm_figures_and_provenance():
    s = FA.summary(four_quarters(), [bar("2025-12-31", 50.0)])
    assert s["periods"] == 4
    assert s["last_period"] == "2025-12-31"
    assert s["last_form"] == "10-Q"
    assert s["revenue_ttm"] == 1000.0
    assert s["fcf_ttm"] == pytest.approx(250.0)
    assert s["margins_ttm"]["net"] == pytest.approx(10.0)
    assert s["multiples_ttm"]["pe"] == pytest.approx(5.0)


def test_summary_without_prices_omits_multiples_but_keeps_margins():
    s = FA.summary(four_quarters())
    assert s["multiples_ttm"]["ps"] is None
    assert s["margins_ttm"]["net"] == pytest.approx(10.0)


# ── against the committed store ──────────────────────────────────────────────
def test_committed_store_produces_sane_derived_values():
    """Ratios over real data, checked for plausibility rather than exact value.

    Catches a unit error or a sign flip in the join, which fixture-based tests
    cannot: a margin of 5,000% means shares and dollars got multiplied together.
    """
    from analysis.data import fundamentals, prices
    if not fundamentals.STORE_DIR.exists():
        pytest.skip("no committed fundamentals store")

    for path in sorted(fundamentals.STORE_DIR.glob("*.csv")):
        key = path.stem
        rows = fundamentals.load_store(key)
        t = FA.ttm(rows)
        if not t:
            continue
        m = FA.margins(t)
        for name, v in m.items():
            assert v is None or -500.0 <= v <= 100.0, f"{key} {name} margin {v}"

        bars = prices.load_store(key)
        if not bars:
            continue
        mult = FA.multiples(t, FA._close_on_or_before(bars, t["period_end"]))
        # A negative enterprise value is real — a company can trade below its
        # net cash — so the bound that matters is magnitude, which is what a
        # mis-scaled share count would blow out.
        for name, v in mult.items():
            assert v is None or abs(v) < 10_000, f"{key} {name} = {v}"
