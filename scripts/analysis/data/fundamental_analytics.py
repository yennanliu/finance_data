"""fundamental_analytics.py — derived statistics over the fundamentals store
============================================================================
Everything the Financials pages show beyond the reported line items is computed
here: trailing-twelve-month roll-ups, year-on-year growth, the three margins,
ROE / ROA / ROIC / ROS, free cash flow, and the valuation multiples that join
this store against the price store.

Two rules shape this module, the same two that shape :mod:`price_analytics`:

  * **Pure standard library.** ``build_docs.py`` imports it at module scope and
    must stay offline and dependency-light.
  * **Rows in, plain data out.** Every function takes the ``list[dict]`` that
    :func:`fundamentals.load_store` returns (oldest→newest) and returns floats,
    dicts or lists of dicts. Nothing here reads a file, so it is testable
    against a hand-written row list (see ``tests/test_fundamental_analytics.py``).

Nothing derived is ever written back to the store. The store holds what the
filer reported; ratios, growth rates and multiples are functions of it and are
recomputed on every build. That is the same split
``docs/PRICE_STORE_DESIGN.md`` §12 settled for prices, and it is what makes the
valuation charts cost no new data: they are a join of two stores we already have.

**A missing input yields None, not zero.** A company that does not tag gross
profit has no gross margin — printing 0% would assert something false about it.
Every helper here propagates absence rather than substituting a number.
"""

from __future__ import annotations

from datetime import date

# Quarters in a trailing-twelve-month window.
TTM_QUARTERS = 4

# How far apart two period ends may be and still count as a year. Fiscal years
# run 52 or 53 weeks and quarter ends drift, so this is deliberately loose — it
# exists to catch a *gap*, not to police a few days of calendar slack.
YEAR_APART_DAYS = (330, 400)

# Metrics that accumulate over a year and so can be summed into a TTM figure.
# A balance-sheet level (assets, equity, debt, cash) is a point in time and a
# per-share figure is an average — neither is summable, so both are carried from
# the most recent quarter instead.
FLOW_METRICS = (
    "revenue", "gross_profit", "operating_income", "net_income",
    "rnd_expense", "sga_expense", "dep_amort", "ocf", "capex",
)
LEVEL_METRICS = (
    "cash_and_equiv", "short_term_investments",
    "long_term_debt", "short_term_debt", "total_assets", "total_equity",
)


# ── small helpers ────────────────────────────────────────────────────────────
def _get(row: "dict", key: str) -> "float | None":
    v = row.get(key)
    return None if v is None else float(v)


def _ratio(num: "float | None", den: "float | None") -> "float | None":
    """num / den as a percentage; None when either side is unusable."""
    if num is None or den is None or not den:
        return None
    return num / den * 100.0


def _sum(values: "list[float | None]") -> "float | None":
    """Sum, or None if any part is missing — a partial sum is not a TTM figure."""
    if not values or any(v is None for v in values):
        return None
    return sum(values)


def _add(*values: "float | None") -> "float | None":
    """Sum, treating absence as zero but requiring at least one real value.

    Used where the parts are genuinely optional — a company with no short-term
    debt simply does not tag it, and its total debt is its long-term debt.
    """
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def _sub(a: "float | None", b: "float | None") -> "float | None":
    return None if a is None or b is None else a - b


# ── period selection ─────────────────────────────────────────────────────────
def ttm(rows: "list[dict]", end_index: int | None = None) -> "dict | None":
    """Trailing-twelve-month figures as of ``end_index`` (default: newest).

    Flows are summed across four quarters; levels and per-share figures are
    taken from the closing quarter. Returns None when four quarters are not
    available — a TTM figure off three of them would understate the year.
    """
    if not rows:
        return None
    i = len(rows) - 1 if end_index is None else end_index
    if i < TTM_QUARTERS - 1 or i >= len(rows):
        return None

    window = rows[i - TTM_QUARTERS + 1:i + 1]
    close = window[-1]

    out = {"period_end": close["period_end"], "fy": close["fy"], "fp": close["fp"]}
    for m in FLOW_METRICS:
        out[m] = _sum([_get(r, m) for r in window])
    for m in LEVEL_METRICS:
        out[m] = _get(close, m)
    out["shares_diluted"] = _get(close, "shares_diluted")
    # Per-share earnings accumulate like a flow, so the TTM figure is the sum.
    for m in ("eps_basic", "eps_diluted"):
        out[m] = _sum([_get(r, m) for r in window])
    return out


def ttm_series(rows: "list[dict]") -> "list[dict]":
    """A TTM figure at every quarter that has four quarters behind it."""
    return [t for t in (ttm(rows, i) for i in range(len(rows))) if t]


def annual_series(rows: "list[dict]") -> "list[dict]":
    """One entry per complete fiscal year, summed from its four quarters."""
    out: "list[dict]" = []
    by_year: "dict[int, list[dict]]" = {}
    for r in rows:
        by_year.setdefault(r["fy"], []).append(r)
    for fy in sorted(by_year):
        window = by_year[fy]
        if len(window) != TTM_QUARTERS:
            continue  # a partial year would read as a collapse in revenue
        close = window[-1]
        entry = {"period_end": close["period_end"], "fy": fy, "fp": "FY"}
        for m in FLOW_METRICS:
            entry[m] = _sum([_get(r, m) for r in window])
        for m in LEVEL_METRICS:
            entry[m] = _get(close, m)
        entry["shares_diluted"] = _get(close, "shares_diluted")
        for m in ("eps_basic", "eps_diluted"):
            entry[m] = _sum([_get(r, m) for r in window])
        out.append(entry)
    return out


# ── growth ───────────────────────────────────────────────────────────────────
def yoy_growth(rows: "list[dict]", metric: str) -> "list[dict]":
    """Year-on-year percent change for ``metric``, one point per period.

    Compared against the same quarter a year earlier rather than the previous
    quarter, so seasonality does not read as growth. A sign change makes the
    percentage meaningless (a swing from loss to profit is not "+340%"), so
    those points are omitted.

    Stepping back four rows only lands a year earlier in a gapless store, and
    the store has gaps: ``resolve`` writes a row only for a period some revenue
    concept covers, so a quarter nobody tagged is simply absent. PLTR's
    2020-12-31 sits four rows after 2019-09-30 — 458 days, not a year — and
    AVAV has four more like it. The dates are checked rather than assumed.
    """
    out: "list[dict]" = []
    lo, hi = YEAR_APART_DAYS
    for i in range(TTM_QUARTERS, len(rows)):
        apart = (date.fromisoformat(rows[i]["period_end"])
                 - date.fromisoformat(rows[i - TTM_QUARTERS]["period_end"])).days
        if not lo <= apart <= hi:
            continue
        now, then = _get(rows[i], metric), _get(rows[i - TTM_QUARTERS], metric)
        if now is None or then is None or then <= 0:
            continue
        out.append({"t": rows[i]["period_end"],
                    "v": round((now - then) / then * 100.0, 2)})
    return out


# ── profitability ────────────────────────────────────────────────────────────
def margins(row: "dict") -> "dict":
    """Gross, operating and net margin — Growin's 三率圖."""
    rev = _get(row, "revenue")
    return {
        "gross": _ratio(_get(row, "gross_profit"), rev),
        "operating": _ratio(_get(row, "operating_income"), rev),
        "net": _ratio(_get(row, "net_income"), rev),
    }


def total_debt(row: "dict") -> "float | None":
    return _add(_get(row, "long_term_debt"), _get(row, "short_term_debt"))


def returns_on_capital(row: "dict") -> "dict":
    """ROE, ROA, ROIC and ROS for one TTM or annual period.

    Computed on closing balances rather than on the average of opening and
    closing. The average is the more defensible denominator, but it needs a
    prior period that the first year of any store does not have; closing
    balances keep the series complete and are what most screeners publish.
    Invested capital is equity plus total debt less cash.
    """
    net = _get(row, "net_income")
    equity = _get(row, "total_equity")
    debt = total_debt(row)
    cash = _add(_get(row, "cash_and_equiv"), _get(row, "short_term_investments"))
    invested = None
    if equity is not None:
        invested = equity + (debt or 0.0) - (cash or 0.0)
    return {
        "roe": _ratio(net, equity),
        "roa": _ratio(net, _get(row, "total_assets")),
        "roic": _ratio(_get(row, "operating_income"), invested),
        "ros": _ratio(net, _get(row, "revenue")),
    }


def free_cash_flow(row: "dict") -> "float | None":
    """Operating cash flow less capital expenditure.

    Capex is tagged as a positive outflow in XBRL, so this subtracts it.
    """
    return _sub(_get(row, "ocf"), _get(row, "capex"))


def ebitda(row: "dict") -> "float | None":
    return _add(_get(row, "operating_income"), _get(row, "dep_amort"))


# ── valuation: the join against the price store ──────────────────────────────
def _close_on_or_before(bars: "list[dict]", iso: str) -> "float | None":
    """The last close at or before ``iso``.

    A period ends on a fiscal date that may be a weekend or holiday, so an exact
    lookup would miss. Bars are ascending, so a reverse scan finds the session
    that priced the company when the period closed.
    """
    for b in reversed(bars):
        if b["date"] <= iso:
            return float(b["close"])
    return None


def market_cap(row: "dict", price: "float | None") -> "float | None":
    shares = _get(row, "shares_diluted")
    if price is None or shares is None:
        return None
    return price * shares


def enterprise_value(row: "dict", price: "float | None") -> "float | None":
    """Market cap plus total debt less cash and short-term investments."""
    cap = market_cap(row, price)
    if cap is None:
        return None
    cash = _add(_get(row, "cash_and_equiv"), _get(row, "short_term_investments"))
    return cap + (total_debt(row) or 0.0) - (cash or 0.0)


def multiples(row: "dict", price: "float | None") -> "dict":
    """P/E, P/S, P/B, EV/Sales and EV/EBITDA for one TTM period.

    ``row`` must be a TTM or annual entry: a multiple built on a single
    quarter's earnings would be four times too high.
    """
    cap = market_cap(row, price)
    ev = enterprise_value(row, price)
    eps = _get(row, "eps_diluted")
    equity = _get(row, "total_equity")
    revenue = _get(row, "revenue")
    eb = ebitda(row)

    def _div(a, b):
        if a is None or b is None or b <= 0:
            return None
        return a / b

    return {
        "pe": (None if price is None or eps is None or eps <= 0 else price / eps),
        "ps": _div(cap, revenue),
        "pb": _div(cap, equity),
        "ev_sales": _div(ev, revenue),
        "ev_ebitda": _div(ev, eb),
    }


def valuation_series(rows: "list[dict]", bars: "list[dict]") -> "dict":
    """Each multiple as a {t, v} series over every TTM period in the store.

    This is the whole of Growin's 估值 group, and it needs no data beyond the
    two stores: a fundamentals row supplies the denominator, and the price store
    supplies the close on the day the period ended.
    """
    keys = ("pe", "ps", "pb", "ev_sales", "ev_ebitda")
    out: "dict[str, list[dict]]" = {k: [] for k in keys}
    for t in ttm_series(rows):
        price = _close_on_or_before(bars, t["period_end"])
        m = multiples(t, price)
        for k in keys:
            if m[k] is not None:
                out[k].append({"t": t["period_end"], "v": round(m[k], 3)})
    return out


def pe_bands(rows: "list[dict]", bars: "list[dict]",
             percentiles: "tuple[float, ...]" = (0.1, 0.3, 0.5, 0.7, 0.9)) -> "dict":
    """The P/E river chart: price, and what it would be at historical multiples.

    Each band is TTM earnings per share times one percentile of this ticker's
    own historical P/E, so the bands say "this is what the market has actually
    paid for these earnings before" rather than imposing an absolute multiple.
    Returns an empty dict when there is no positive-earnings history to rank.
    """
    series = valuation_series(rows, bars).get("pe") or []
    if len(series) < 4:
        return {}

    ranked = sorted(p["v"] for p in series)
    levels = []
    for q in percentiles:
        idx = min(int(q * (len(ranked) - 1)), len(ranked) - 1)
        levels.append(round(ranked[idx], 1))
    levels = sorted(set(levels))

    eps_at = {t["period_end"]: _get(t, "eps_diluted") for t in ttm_series(rows)}
    ends = sorted(eps_at)

    def eps_on(iso: str) -> "float | None":
        chosen = None
        for e in ends:
            if e <= iso:
                chosen = eps_at[e]
            else:
                break
        return chosen

    price_points, bands = [], {str(lv): [] for lv in levels}
    # Monthly sampling: a 10-year daily series would be 2,500 points per band.
    seen = set()
    for b in bars:
        month = b["date"][:7]
        if month in seen or b["date"] < ends[0]:
            continue
        seen.add(month)
        eps = eps_on(b["date"])
        if eps is None or eps <= 0:
            continue
        price_points.append({"t": b["date"], "v": round(float(b["close"]), 2)})
        for lv in levels:
            bands[str(lv)].append({"t": b["date"], "v": round(eps * lv, 2)})

    if not price_points:
        return {}
    return {"price": price_points, "levels": levels, "bands": bands}


# ── summary ──────────────────────────────────────────────────────────────────
def summary(rows: "list[dict]", bars: "list[dict]" | None = None) -> "dict | None":
    """Everything the index table and the per-ticker stat block need.

    Returns None for an empty store so callers can skip the ticker outright.
    """
    if not rows:
        return None
    latest = rows[-1]
    t = ttm(rows)
    price = _close_on_or_before(bars or [], latest["period_end"]) if bars else None

    out = {
        "periods": len(rows),
        "first_period": rows[0]["period_end"],
        "last_period": latest["period_end"],
        "last_fy": latest["fy"],
        "last_fp": latest["fp"],
        "last_form": latest["form"],
        "last_filed": latest["filed"],
        "revenue_q": _get(latest, "revenue"),
        "net_income_q": _get(latest, "net_income"),
        "revenue_ttm": t and t.get("revenue"),
        "net_income_ttm": t and t.get("net_income"),
        "eps_ttm": t and t.get("eps_diluted"),
        "fcf_ttm": free_cash_flow(t) if t else None,
        "margins_ttm": margins(t) if t else {},
        "returns_ttm": returns_on_capital(t) if t else {},
        "multiples_ttm": multiples(t, price) if t else {},
    }
    growth = yoy_growth(rows, "revenue")
    out["revenue_yoy"] = growth[-1]["v"] if growth else None
    return out


__all__ = [
    "TTM_QUARTERS", "FLOW_METRICS", "LEVEL_METRICS",
    "ttm", "ttm_series", "annual_series", "yoy_growth",
    "margins", "total_debt", "returns_on_capital", "free_cash_flow", "ebitda",
    "market_cap", "enterprise_value", "multiples", "valuation_series",
    "pe_bands", "summary",
]
