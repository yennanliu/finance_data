"""intrinsic_value.py — DCF, reverse DCF, WACC and per-share growth
===================================================================
The models behind the Market Data page's **Intrinsic value** tab and its
ROIC-vs-WACC chart. Same two rules as :mod:`price_analytics` and
:mod:`fundamental_analytics`: pure standard library, rows in and plain data out,
so every figure on the page is asserted in ``tests/test_intrinsic_value.py``
against hand-worked arithmetic.

What separates this module from its siblings is that its outputs rest on
**assumptions**, not just on reported figures: a discount rate, a growth rate,
a risk-free rate, an equity risk premium. Each is a named constant below and is
printed on the page next to the number it produced, so a reader can see what
would have to be true for the fair value to hold — and redo it with their own.

The DCF is the *earnings-power* form GuruFocus uses: a per-share base (EPS or
free cash flow per share) grown for ten years at a growth-stage rate, then for
ten more at a terminal rate, each year discounted back. Unlike a perpetuity
model it has no terminal multiple to blow up when growth approaches the
discount rate, and it needs nothing a 10-K does not report.

**A negative base has no fair value.** Discounting a loss forward does not
produce a negative price; it produces a meaningless one. Every model here
returns None rather than a number for it.
"""

from __future__ import annotations

from . import fundamental_analytics as fa
from . import price_analytics as pa

# ── assumptions ──────────────────────────────────────────────────────────────
# Printed on the page beside every figure they produce. Change them here and
# the page, the payload and the tests all move together.
DISCOUNT_RATE = 0.10        # required annual return used to discount the DCF
GROWTH_YEARS = 10           # length of the growth stage
TERMINAL_YEARS = 10         # length of the terminal stage
TERMINAL_GROWTH = 0.04      # growth in the terminal stage — roughly nominal GDP
GROWTH_CAP = 0.20           # no business compounds faster than this for a decade
GROWTH_FLOOR = 0.0          # a shrinking history is modelled as flat, not as decline

RISK_FREE_RATE = 0.0425     # ~10-year US Treasury yield
EQUITY_RISK_PREMIUM = 0.055 # long-run US equity premium over Treasuries
MAX_COST_OF_DEBT = 0.15     # interest ÷ debt above this is a mis-tag, not a rate

# The growth windows the per-share table reports, longest first. Not 10: the
# store keeps ten years of quarters, which is nine complete fiscal years at
# most, and a ten-year CAGR needs eleven year-ends.
GROWTH_WINDOWS = (5, 3, 1)

# Per-share metrics, in table order. Each maps an annual/TTM entry to a total
# that is then divided by the diluted share count.
PER_SHARE = ("eps", "revenue", "operating_income", "ebitda", "fcf",
             "dividends", "book_value")


# ── small helpers ────────────────────────────────────────────────────────────
def cagr(first: "float | None", last: "float | None",
         years: float) -> "float | None":
    """Compound annual growth from ``first`` to ``last``, as a fraction.

    Undefined across a sign change or from zero — growth from a loss to a
    profit has no rate — so both ends must be positive.
    """
    if first is None or last is None or first <= 0 or last <= 0 or years <= 0:
        return None
    return (last / first) ** (1.0 / years) - 1.0


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def per_share(entry: "dict") -> "dict":
    """Every :data:`PER_SHARE` metric for one annual or TTM entry.

    EPS is the reported diluted figure; the rest are totals over the diluted
    weighted-average share count. A missing share count leaves every derived
    figure None rather than guessing one.
    """
    shares = entry.get("shares_diluted")
    totals = {
        "revenue": entry.get("revenue"),
        "operating_income": entry.get("operating_income"),
        "ebitda": fa.ebitda(entry),
        "fcf": fa.free_cash_flow(entry),
        "dividends": entry.get("dividends_paid"),
        "book_value": entry.get("total_equity"),
    }
    out = {"eps": entry.get("eps_diluted")}
    for k, v in totals.items():
        out[k] = v / shares if v is not None and shares else None
    return out


# ── per-share growth table ───────────────────────────────────────────────────
def growth_table(annual: "list[dict]", ttm_entry: "dict | None",
                 bars: "list[dict] | None" = None,
                 show_years: int = 3) -> "dict":
    """GuruFocus's per-share data panel: CAGRs over 5/3/1 years, the last
    ``show_years`` fiscal years, and the TTM figure, for every metric.

    A window's CAGR runs between fiscal years exactly that many years apart, so
    a store with a gap never passes off nine years of growth as ten. Price is
    the close on each fiscal year end, so its CAGR is a price (not total) return.
    """
    by_fy = {e["fy"]: e for e in annual}
    last_fy = annual[-1]["fy"] if annual else None
    shown = annual[-show_years:]

    def price_at(entry):
        return fa._close_on_or_before(bars or [], entry["period_end"]) if bars else None

    def value(entry, metric):
        if metric == "price":
            return price_at(entry)
        return per_share(entry)[metric]

    ttm_values = per_share(ttm_entry) if ttm_entry else {}
    ttm_values["price"] = float(bars[-1]["close"]) if ttm_entry and bars else None

    rows = {}
    for metric in PER_SHARE + ("price",):
        growth = {}
        for n in GROWTH_WINDOWS:
            then = by_fy.get(last_fy - n) if last_fy is not None else None
            growth[n] = (None if then is None else
                         cagr(value(then, metric), value(annual[-1], metric), n))
        rows[metric] = {
            "cagr": growth,
            "years": [(e["fy"], value(e, metric)) for e in shown],
            "ttm": ttm_values.get(metric),
        }
    return {"fiscal_years": [e["fy"] for e in shown],
            "ttm_period": ttm_entry and ttm_entry["period_end"],
            "rows": rows}


def default_growth(annual: "list[dict]") -> "dict":
    """The growth-stage rate the DCF uses, and where it came from.

    EBITDA per share over the longest window that yields a rate (5, then 3
    years — one year is too noisy to project a decade on), falling back to
    revenue per share — EBITDA is the steadier of
    the profit lines, and revenue is defined for a company with no profit yet.
    Clamped to [:data:`GROWTH_FLOOR`, :data:`GROWTH_CAP`]; ``raw`` keeps the
    unclamped figure so the page can say it was capped.
    """
    table = growth_table(annual, None)["rows"]
    for metric in ("ebitda", "revenue"):
        for n in (w for w in GROWTH_WINDOWS if w >= 3):
            raw = table[metric]["cagr"][n]
            if raw is not None:
                return {"rate": _clamp(raw, GROWTH_FLOOR, GROWTH_CAP),
                        "raw": raw, "metric": metric, "years": n}
    return {"rate": GROWTH_FLOOR, "raw": None, "metric": None, "years": None}


# ── DCF ──────────────────────────────────────────────────────────────────────
def dcf(base: "float | None", growth: float,
        discount: float = DISCOUNT_RATE,
        growth_years: int = GROWTH_YEARS,
        terminal_years: int = TERMINAL_YEARS,
        terminal_growth: float = TERMINAL_GROWTH) -> "dict | None":
    """Two-stage earnings-power DCF on a per-share ``base``.

    growth value   = base · Σ xⁿ,            n = 1…growth_years,   x = (1+g)/(1+d)
    terminal value = base · x^G · Σ yⁿ,      n = 1…terminal_years, y = (1+gₜ)/(1+d)

    i.e. each year's earnings, grown and discounted back to today. None for a
    non-positive base.
    """
    if base is None or base <= 0:
        return None
    x = (1.0 + growth) / (1.0 + discount)
    y = (1.0 + terminal_growth) / (1.0 + discount)
    growth_value = base * sum(x ** n for n in range(1, growth_years + 1))
    terminal_value = (base * x ** growth_years
                      * sum(y ** n for n in range(1, terminal_years + 1)))
    return {"growth_value": growth_value, "terminal_value": terminal_value,
            "fair_value": growth_value + terminal_value}


def margin_of_safety(fair: "float | None", price: "float | None") -> "float | None":
    """(fair − price) ÷ fair, in percent. Negative means priced above fair value."""
    if fair is None or price is None or fair <= 0:
        return None
    return (fair - price) / fair * 100.0


def implied_growth(base: "float | None", price: "float | None",
                   discount: float = DISCOUNT_RATE,
                   lo: float = -0.5, hi: float = 1.0) -> "float | None":
    """Reverse DCF: the growth-stage rate at which :func:`dcf` equals ``price``.

    The fair value rises monotonically with growth, so bisection converges.
    None when the price lies outside what ``lo``…``hi`` can produce — a price so
    high that 100% a year for a decade does not justify it is reported as such
    by the page, not as a number.
    """
    if base is None or base <= 0 or price is None or price <= 0:
        return None

    def value(g):
        return dcf(base, g, discount)["fair_value"]

    if not value(lo) <= price <= value(hi):
        return None
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if value(mid) < price:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2.0, 6)


def sensitivity(base: "float | None", growth: float,
                discount: float = DISCOUNT_RATE,
                d_steps: "tuple[float, ...]" = (-0.02, -0.01, 0.0, 0.01, 0.02),
                g_steps: "tuple[float, ...]" = (-0.04, -0.02, 0.0, 0.02, 0.04)
                ) -> "dict | None":
    """Fair value over a grid of discount × growth rates around the base case.

    Rows are discount rates, columns growth rates; the centre cell is the base
    case. Growth points are clamped to a band four points wider than the base
    case's own [GROWTH_FLOOR, GROWTH_CAP], so a capped base case still shows
    what slightly more (or less) growth would be worth; a duplicate that
    clamping produces is dropped.
    """
    if base is None or base <= 0:
        return None
    rates = [round(discount + s, 4) for s in d_steps if discount + s > 0]
    growths = sorted({round(_clamp(growth + s, GROWTH_FLOOR - 0.04, GROWTH_CAP + 0.04), 4)
                      for s in g_steps})
    return {
        "discount_rates": rates,
        "growth_rates": growths,
        "values": [[round(dcf(base, g, d)["fair_value"], 2) for g in growths]
                   for d in rates],
    }


# ── WACC ─────────────────────────────────────────────────────────────────────
def wacc(entry: "dict", price: "float | None",
         beta: "float | None") -> "dict | None":
    """Weighted average cost of capital for one TTM or annual entry.

    cost of equity = risk-free + β · equity risk premium      (CAPM)
    cost of debt   = interest expense ÷ total debt, after tax
    weights        = market cap and total debt

    A company with no debt is all equity, and WACC is its cost of equity. A
    cost of debt above :data:`MAX_COST_OF_DEBT` (interest tagged against a
    sliver of debt) falls back to the risk-free rate. None without a beta or a
    market cap — the equity side is most of the answer.
    """
    cap = fa.market_cap(entry, price)
    if beta is None or cap is None or cap <= 0:
        return None
    debt = fa.total_debt(entry) or 0.0
    interest = entry.get("interest_expense")
    cost_debt = interest / debt if interest and debt else None
    if cost_debt is None or not 0 < cost_debt <= MAX_COST_OF_DEBT:
        cost_debt = RISK_FREE_RATE
    tax = fa.tax_rate(entry)
    cost_equity = RISK_FREE_RATE + beta * EQUITY_RISK_PREMIUM
    we = cap / (cap + debt)
    wd = 1.0 - we
    return {
        "wacc": we * cost_equity + wd * cost_debt * (1.0 - tax),
        "beta": beta, "cost_equity": cost_equity,
        "cost_debt": cost_debt, "tax_rate": tax,
        "weight_equity": we, "weight_debt": wd,
        "risk_free": RISK_FREE_RATE, "erp": EQUITY_RISK_PREMIUM,
    }


def roic_wacc_series(annual: "list[dict]", bars: "list[dict]",
                     market: "list[dict]") -> "list[dict]":
    """After-tax ROIC against WACC, one point per fiscal year.

    Each year's WACC uses the beta measured up to that year end and the market
    cap at that year's closing price, so the spread is what an analyst would
    have computed at the time rather than today's WACC painted backwards.
    Values are percentages; a year missing either side is omitted.
    """
    out = []
    for e in annual:
        roic = fa.returns_on_capital(e)["roic"]
        price = fa._close_on_or_before(bars, e["period_end"])
        w = wacc(e, price, pa.beta(bars, market, as_of=e["period_end"]))
        if roic is None or w is None:
            continue
        out.append({"fy": e["fy"], "t": e["period_end"],
                    "roic": round(roic, 2), "wacc": round(w["wacc"] * 100, 2),
                    "spread": round(roic - w["wacc"] * 100, 2)})
    return out


# ── the whole model ──────────────────────────────────────────────────────────
VERDICT_BANDS = (  # price ÷ fair value → verdict key
    (0.7, "sig_under"), (1.0, "under"), (1.3, "over"), (float("inf"), "sig_over"),
)


def verdict(price: "float | None", fair: "float | None") -> "str | None":
    """Which of four bands price ÷ fair value falls in."""
    if price is None or fair is None or fair <= 0:
        return None
    ratio = price / fair
    return next(key for edge, key in VERDICT_BANDS if ratio < edge)


def model(rows: "list[dict]", bars: "list[dict]",
          market: "list[dict] | None" = None) -> "dict | None":
    """Everything the Intrinsic value tab draws, in one dict.

    Returns None without both four quarters of filings and a price: there is
    nothing to value, or nothing to compare the value against.
    """
    t = fa.ttm(rows)
    if not t or not bars:
        return None
    price = float(bars[-1]["close"])
    annual = fa.annual_series(rows)
    growth = default_growth(annual)
    ps = per_share(t)

    bases = {}
    for basis, base in (("eps", ps["eps"]), ("fcf", ps["fcf"])):
        v = dcf(base, growth["rate"])
        bases[basis] = {
            "base": base,
            "fair_value": v and v["fair_value"],
            "growth_value": v and v["growth_value"],
            "terminal_value": v and v["terminal_value"],
            "margin_of_safety": margin_of_safety(v and v["fair_value"], price),
            "implied_growth": implied_growth(base, price),
            "verdict": verdict(price, v and v["fair_value"]),
        }
    primary = next((b for b in ("eps", "fcf") if bases[b]["fair_value"]), None)

    b = pa.beta(bars, market) if market else None
    return {
        "price": price,
        "price_date": bars[-1]["date"],
        "ttm_period": t["period_end"],
        "assumptions": {
            "discount_rate": DISCOUNT_RATE, "growth_years": GROWTH_YEARS,
            "terminal_years": TERMINAL_YEARS, "terminal_growth": TERMINAL_GROWTH,
            "growth_cap": GROWTH_CAP, "growth_floor": GROWTH_FLOOR,
        },
        "growth": growth,
        "bases": bases,
        "primary": primary,
        "sensitivity": (sensitivity(bases[primary]["base"], growth["rate"])
                        if primary else None),
        "wacc": wacc(t, price, b),
        "per_share": growth_table(annual, t, bars),
    }


__all__ = [
    "DISCOUNT_RATE", "GROWTH_YEARS", "TERMINAL_YEARS", "TERMINAL_GROWTH",
    "GROWTH_CAP", "GROWTH_FLOOR", "RISK_FREE_RATE", "EQUITY_RISK_PREMIUM",
    "PER_SHARE", "GROWTH_WINDOWS", "VERDICT_BANDS",
    "cagr", "per_share", "growth_table", "default_growth",
    "dcf", "margin_of_safety", "implied_growth", "sensitivity",
    "wacc", "roic_wacc_series", "verdict", "model",
]
