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


def test_yoy_skips_a_point_whose_base_is_not_actually_a_year_back():
    """Stepping back four rows only lands a year earlier in a gapless store.

    PLTR's 2020-12-31 sits four rows after 2019-09-30 — 458 days apart — and
    AVAV has four more like it. Before the date check those published a growth
    rate computed against the wrong base, with nothing on the page to show it.
    """
    rows = four_quarters()
    del rows[1]                                    # a quarter nobody tagged
    rows += [row("2026-03-31", 2026, "Q1", revenue=150.0)]
    # 2026-03-31 is now four rows after 2025-03-31 + one gap, so the base is
    # further back than a year and the point must be dropped.
    assert FA.yoy_growth(rows, "revenue") == []


def test_yoy_tolerates_a_fiscal_calendar_that_drifts_a_few_days():
    """Fiscal years run 52 or 53 weeks, so quarter ends move; the guard exists
    to catch a missing quarter, not to police calendar slack."""
    ends = ["2024-06-29", "2024-09-28", "2024-12-28", "2025-03-29", "2025-06-28"]
    rows = [row(e, 2025, "Q1", revenue=100.0 + i) for i, e in enumerate(ends)]
    assert [p["t"] for p in FA.yoy_growth(rows, "revenue")] == ["2025-06-28"]


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
    # invested capital = equity 500 + debt 200 - cash 100 = 600; op income 200,
    # taxed at the 21% statutory rate because no income tax is tagged: after-tax
    assert r["roic"] == pytest.approx(200.0 * 0.79 / 600.0 * 100.0)


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


# ── split adjustment ─────────────────────────────────────────────────────────
def test_split_adjust_restates_rows_filed_before_a_split():
    """NVDA's quarter to April 2024 was filed before its 10:1 split; the
    quarter after it, after. Only the earlier row is restated."""
    rows = [row("2024-04-28", 2025, "Q1", eps_diluted=5.98, shares_diluted=2.49e9),
            row("2024-07-28", 2025, "Q2", eps_diluted=0.67, shares_diluted=24.85e9)]
    rows[0]["filed"], rows[1]["filed"] = "2024-05-29", "2024-08-28"
    bars = [{"date": "2024-06-10", "close": 121.79, "split": 10.0}]
    out = FA.split_adjust(rows, bars)
    assert out[0]["eps_diluted"] == pytest.approx(0.598)
    assert out[0]["shares_diluted"] == pytest.approx(24.9e9)
    assert out[1] is rows[1]                       # untouched rows pass through
    assert rows[0]["eps_diluted"] == 5.98          # the input is never mutated


def test_split_adjust_compounds_successive_splits():
    rows = [row("2020-03-31", 2020, "Q1", eps_diluted=8.0, shares_diluted=1.0)]
    rows[0]["filed"] = "2020-04-30"
    bars = [{"date": "2021-07-20", "close": 1, "split": 4.0},
            {"date": "2024-06-10", "close": 1, "split": 10.0}]
    out = FA.split_adjust(rows, bars)
    assert out[0]["eps_diluted"] == pytest.approx(0.2)
    assert out[0]["shares_diluted"] == pytest.approx(40.0)


def test_split_adjust_without_splits_is_the_identity():
    rows = four_quarters()
    assert FA.split_adjust(rows, [bar("2025-01-02", 10.0)]) is rows


# ── tax, NOPAT, ROIC ─────────────────────────────────────────────────────────
def test_effective_tax_rate_and_its_fallback():
    assert FA.effective_tax_rate({"income_tax": 25.0, "pretax_income": 100.0}) == 0.25
    # A loss year and a one-off benefit have no usable rate …
    assert FA.effective_tax_rate({"income_tax": 5.0, "pretax_income": -10.0}) is None
    assert FA.effective_tax_rate({"income_tax": -40.0, "pretax_income": 100.0}) is None
    # … so the statutory rate stands in.
    assert FA.tax_rate({"income_tax": -40.0, "pretax_income": 100.0}) == 0.21


def test_roic_uses_the_period_tax_rate_and_skips_negative_capital():
    t = FA.ttm(four_quarters(income_tax=2.5, pretax_income=10.0))  # 25% rate
    # NOPAT = 200 × 0.75 = 150; invested = 500 + 200 − 100 = 600
    assert FA.returns_on_capital(t)["roic"] == pytest.approx(25.0)
    flush = FA.ttm(four_quarters(cash_and_equiv=5000.0))
    assert FA.returns_on_capital(flush)["roic"] is None


# ── financial strength ───────────────────────────────────────────────────────
def test_financial_strength_ratios_by_hand():
    t = FA.ttm(four_quarters(interest_expense=5.0, current_assets=300.0,
                             current_liabilities=200.0))
    s = FA.financial_strength(t)
    assert s["cash_to_debt"] == pytest.approx(0.5)        # 100 / 200
    assert s["equity_to_asset"] == pytest.approx(0.5)     # 500 / 1000
    assert s["debt_to_equity"] == pytest.approx(0.4)      # 200 / 500
    assert s["debt_to_ebitda"] == pytest.approx(200 / 220)  # EBITDA 200 + 4×5
    assert s["interest_coverage"] == pytest.approx(10.0)  # 200 / 20
    assert s["current_ratio"] == pytest.approx(1.5)


def test_financial_strength_without_debt_reports_no_debt_ratio():
    s = FA.financial_strength(FA.ttm(four_quarters(long_term_debt=None)))
    assert s["debt"] is None
    assert s["cash_to_debt"] is None and s["debt_to_ebitda"] is None


def test_altman_z_by_hand():
    t = FA.ttm(four_quarters(current_assets=400.0, current_liabilities=200.0,
                             retained_earnings=300.0, total_liabilities=500.0))
    # WC/TA 0.2·1.2 + RE/TA 0.3·1.4 + EBIT/TA 0.2·3.3 + MVE/TL (10·50/500)·0.6
    # + S/TA 1.0·1.0 = 0.24 + 0.42 + 0.66 + 0.6 + 1.0
    assert FA.altman_z(t, 50.0) == pytest.approx(2.92)
    assert FA.altman_z(t, None) is None


def test_total_liabilities_falls_back_to_the_balance_sheet_identity():
    assert FA.total_liabilities({"total_assets": 1000.0, "total_equity": 400.0}) == 600.0
    assert FA.total_liabilities({"total_liabilities": 550.0,
                                 "total_assets": 1000.0, "total_equity": 400.0}) == 550.0


def test_piotroski_counts_only_testable_criteria():
    prev = {"net_income": 50.0, "total_assets": 1000.0, "ocf": 40.0,
            "long_term_debt": 300.0, "current_assets": 100.0,
            "current_liabilities": 100.0, "shares_diluted": 10.0,
            "revenue": 500.0, "gross_profit": None}
    cur = dict(prev, net_income=80.0, ocf=120.0, long_term_debt=200.0,
               current_assets=150.0, shares_diluted=11.0, revenue=600.0)
    p = FA.piotroski(cur, prev)
    assert p["tests"]["gross_margin_improving"] is None   # never tagged
    assert p["tests"]["no_dilution"] is False             # 10 → 11 shares
    assert p["tested"] == 8
    assert p["score"] == 7


def test_strength_tone_respects_direction():
    assert FA.strength_tone("current_ratio", 2.0) == "good"
    assert FA.strength_tone("current_ratio", 1.2) == "fair"
    assert FA.strength_tone("current_ratio", 0.8) == "weak"
    assert FA.strength_tone("debt_to_equity", 0.3) == "good"   # lower is better
    assert FA.strength_tone("debt_to_equity", 2.0) == "weak"
    assert FA.strength_tone("debt_to_equity", None) is None


def test_summary_carries_strength_and_a_year_ago_piotroski():
    rows = four_quarters() + [
        row(e, 2026, f"Q{i + 1}", **{k: v for k, v in four_quarters()[i].items()
                                     if k not in ("period_end", "fy", "fp", "form", "filed")})
        for i, e in enumerate(["2026-03-31", "2026-06-30", "2026-09-30", "2026-12-31"])]
    s = FA.summary(rows)
    assert s["strength_ttm"]["equity_to_asset"] == pytest.approx(0.5)
    assert s["piotroski"]["tested"] > 0
    assert FA.summary(four_quarters())["piotroski"] is None   # no year-ago TTM


# ── valuation ranges ─────────────────────────────────────────────────────────
def test_valuation_ranges_rank_today_against_history():
    series = {"pe": [{"t": f"2025-0{i}-30", "v": v}
                     for i, v in enumerate([10.0, 20.0, 30.0, 40.0], start=1)],
              "pb": [{"t": "2025-01-30", "v": 1.0}]}     # too short to rank
    r = FA.valuation_ranges(series)
    assert set(r) == {"pe"}
    assert (r["pe"]["min"], r["pe"]["median"], r["pe"]["max"]) == (10.0, 25.0, 40.0)
    assert r["pe"]["current"] == 40.0 and r["pe"]["rank"] == 100.0

    today = FA.valuation_ranges(series, {"pe": 15.0}, "2026-01-02")
    assert today["pe"]["current"] == 15.0
    assert today["pe"]["rank"] == 25.0                   # only 10× is ≤ 15×
    assert today["pe"]["as_of"] == "2026-01-02"
    # A multiple undefined today (a loss) gets no marker at all.
    assert FA.valuation_ranges(series, {"pe": None}) == {}


def test_piotroski_leverage_test_needs_assets_on_both_sides():
    """A missing total_assets is untestable, not a pass; debt-free both years is."""
    base = {"net_income": 10.0, "ocf": 20.0, "shares_diluted": 10.0,
            "revenue": 100.0, "total_assets": 1000.0}
    no_assets = FA.piotroski(dict(base, total_assets=None), base)
    assert no_assets["tests"]["leverage_falling"] is None
    debt_free = FA.piotroski(base, dict(base))
    assert debt_free["tests"]["leverage_falling"] is True


def test_split_adjust_ignores_a_comparative_filing_date():
    """GOOG's Q4-2020 row carries the 2023 10-K that re-reported its revenue;
    the EPS in it is still the pre-split figure from the original 10-K."""
    rows = [row("2020-12-31", 2020, "Q4", eps_diluted=22.23)]
    rows[0]["filed"] = "2023-02-03"
    out = FA.split_adjust(rows, [{"date": "2022-07-18", "close": 1, "split": 20.0}])
    assert out[0]["eps_diluted"] == pytest.approx(1.1115)


def test_piotroski_tone_matches_the_glossary_bands():
    """Glossary: 7–9 strong, 0–3 weak — so 4 is fair, on 9 tests or on 8."""
    assert FA.strength_tone("piotroski", 4 / 9) == "fair"
    assert FA.strength_tone("piotroski", 4 / 8) == "fair"
    assert FA.strength_tone("piotroski", 3 / 9) == "weak"
    assert FA.strength_tone("piotroski", 3 / 8) == "weak"
    assert FA.strength_tone("piotroski", 7 / 9) == "good"
