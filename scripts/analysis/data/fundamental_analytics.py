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

from datetime import date, timedelta

from ..config.valuation import DEFAULT_TAX_RATE, TAX_RATE_BOUNDS

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
    "sbc", "dividends_paid", "buybacks",
    "interest_expense", "income_tax", "pretax_income",
)
LEVEL_METRICS = (
    "cash_and_equiv", "short_term_investments",
    "long_term_debt", "short_term_debt", "total_assets", "total_equity",
    "current_assets", "current_liabilities", "total_liabilities",
    "retained_earnings", "goodwill", "intangibles",
)

# The tax rate assumed when a period's own effective rate is unusable — a loss
# year, or a one-off benefit that drives the rate negative — and the bounds on
# an effective rate we will believe (outside them it is a one-off such as a
# valuation-allowance release, not a rate). Shared with the fundamental
# report's fact block via config/valuation.py, so the Market Data pages and the
# LLM reports tax the same company the same way.
STATUTORY_TAX_RATE = DEFAULT_TAX_RATE


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


# ── split adjustment ─────────────────────────────────────────────────────────
PER_SHARE_METRICS = ("eps_basic", "eps_diluted")

# Latest an original 10-Q / 10-K lands after its period end (the 10-K deadline
# for the smallest filers is 90 days).
ORIGINAL_FILING_DAYS = 100


def split_adjust(rows: "list[dict]", bars: "list[dict]") -> "list[dict]":
    """Restate per-share figures onto today's share basis.

    The store keeps figures *as first reported*, so NVDA's quarter to April
    2024 carries EPS of $5.98 on 2.49B shares, and the quarter after it $0.67
    on 24.8B — the 10:1 split in between. The price store is split-adjusted, so
    joining the two unadjusted divided a post-split price by a pre-split EPS
    and put NVDA's historical P/E an order of magnitude too low.

    Every split the price store records *after* a row's filing date multiplies
    that row's share count and divides its EPS. The filing date, not the period
    end, decides the basis: a split between the two is already reflected in the
    filing. Returns new rows; the store's own rows are never mutated, and the
    CSV download stays exactly as filed.

    The ``filed`` column is capped at :data:`ORIGINAL_FILING_DAYS` after the
    period end. It records which filing supplied the *revenue* fact, and for a
    differenced Q4 that can be a comparative column years later: GOOG's
    2020-12-31 row says 2023-02-03, which put its pre-split $22.23 EPS after
    the 2022 20:1 split and left it unadjusted. The EPS itself always comes
    from the original filing, which lands within that window.
    """
    splits = [(b["date"], float(b["split"])) for b in bars or []
              if b.get("split")]
    if not splits:
        return rows
    out = []
    for r in rows:
        cap = (date.fromisoformat(r["period_end"])
               + timedelta(days=ORIGINAL_FILING_DAYS)).isoformat()
        basis = min(r.get("filed") or cap, cap)
        factor = 1.0
        for when, ratio in splits:
            if when > basis and ratio > 0:
                factor *= ratio
        if factor == 1.0:
            out.append(r)
            continue
        r = dict(r)
        if r.get("shares_diluted") is not None:
            r["shares_diluted"] = r["shares_diluted"] * factor
        for m in PER_SHARE_METRICS:
            if r.get(m) is not None:
                r[m] = r[m] / factor
        out.append(r)
    return out


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


def effective_tax_rate(row: "dict") -> "float | None":
    """Income tax ÷ pre-tax income, as a fraction; None when it is not a rate.

    A loss year has no meaningful rate, and a rate outside
    :data:`TAX_RATE_BOUNDS` is a one-off rather than what the business pays.
    """
    tax, pretax = _get(row, "income_tax"), _get(row, "pretax_income")
    if tax is None or pretax is None or pretax <= 0:
        return None
    rate = tax / pretax
    lo, hi = TAX_RATE_BOUNDS
    return rate if lo <= rate <= hi else None


def tax_rate(row: "dict") -> float:
    """The period's effective rate, or the statutory rate when it has none."""
    rate = effective_tax_rate(row)
    return STATUTORY_TAX_RATE if rate is None else rate


def invested_capital(row: "dict") -> "float | None":
    """Equity plus total debt less cash and short-term investments."""
    equity = _get(row, "total_equity")
    if equity is None:
        return None
    cash = _add(_get(row, "cash_and_equiv"), _get(row, "short_term_investments"))
    return equity + (total_debt(row) or 0.0) - (cash or 0.0)


def nopat(row: "dict") -> "float | None":
    """Net operating profit after tax: operating income × (1 − tax rate)."""
    op = _get(row, "operating_income")
    return None if op is None else op * (1.0 - tax_rate(row))


def returns_on_capital(row: "dict") -> "dict":
    """ROE, ROA, ROIC and ROS for one TTM or annual period.

    Computed on closing balances rather than on the average of opening and
    closing. The average is the more defensible denominator, but it needs a
    prior period that the first year of any store does not have; closing
    balances keep the series complete and are what most screeners publish.

    ROIC is *after-tax* operating profit over invested capital — what the
    glossary has always said it was. Until 2026-10 the numerator was pre-tax,
    which overstated ROIC by the tax rate and made it incomparable with a WACC,
    the one thing ROIC exists to be compared with. Invested capital at or below
    zero (a cash pile larger than equity plus debt) yields None: the ratio's
    sign would flip and read as a loss.
    """
    net = _get(row, "net_income")
    equity = _get(row, "total_equity")
    invested = invested_capital(row)
    return {
        "roe": _ratio(net, equity),
        "roa": _ratio(net, _get(row, "total_assets")),
        "roic": (_ratio(nopat(row), invested)
                 if invested is not None and invested > 0 else None),
        "ros": _ratio(net, _get(row, "revenue")),
    }


def free_cash_flow(row: "dict") -> "float | None":
    """Operating cash flow less capital expenditure.

    Capex is tagged as a positive outflow in XBRL, so this subtracts it.
    """
    return _sub(_get(row, "ocf"), _get(row, "capex"))


def ebitda(row: "dict") -> "float | None":
    return _add(_get(row, "operating_income"), _get(row, "dep_amort"))


def total_liabilities(row: "dict") -> "float | None":
    """Reported total liabilities, else assets − equity.

    AMD, AMZN, INTC and ORCL never tag a Liabilities total. Assets − equity is
    the balance-sheet identity rather than an estimate (it folds any
    non-controlling interest into liabilities, which is the conservative side
    for every ratio that uses it).
    """
    reported = _get(row, "total_liabilities")
    if reported is not None:
        return reported
    return _sub(_get(row, "total_assets"), _get(row, "total_equity"))


# ── financial strength ───────────────────────────────────────────────────────
def _div(a: "float | None", b: "float | None") -> "float | None":
    """a / b, None when either side is missing or b is zero."""
    if a is None or b is None or not b:
        return None
    return a / b


def financial_strength(row: "dict") -> "dict":
    """The balance-sheet ratios of GuruFocus's Financial Strength panel.

    ``row`` is a TTM or annual entry, so interest cover divides a year of
    operating income by a year of interest. Each ratio is None when an input is
    absent, and a company with no debt at all has no debt ratio to report
    (cash-to-debt and debt/EBITDA are undefined, not infinite or zero).
    """
    debt = total_debt(row)
    cash = _add(_get(row, "cash_and_equiv"), _get(row, "short_term_investments"))
    eb = ebitda(row)
    interest = _get(row, "interest_expense")
    return {
        "debt": debt,
        "cash_to_debt": _div(cash, debt) if debt else None,
        "equity_to_asset": _div(_get(row, "total_equity"), _get(row, "total_assets")),
        "debt_to_equity": (_div(debt, _get(row, "total_equity"))
                           if (_get(row, "total_equity") or 0) > 0 else None),
        "debt_to_ebitda": _div(debt, eb) if debt and eb and eb > 0 else None,
        "interest_coverage": (_div(_get(row, "operating_income"), interest)
                              if interest and interest > 0 else None),
        "current_ratio": _div(_get(row, "current_assets"),
                              _get(row, "current_liabilities")),
    }


# Where each strength ratio reads as strong / fair / weak: (good edge, weak
# edge, higher_is_better). These are conventional screen thresholds, not
# laws — the page shows the value beside the tone so a reader can disagree.
STRENGTH_ZONES = {
    "cash_to_debt": (1.0, 0.3, True),
    "equity_to_asset": (0.5, 0.3, True),
    "debt_to_equity": (0.5, 1.5, False),
    "debt_to_ebitda": (2.0, 4.0, False),
    "interest_coverage": (8.0, 3.0, True),
    "current_ratio": (1.5, 1.0, True),
    "altman_z": (2.99, 1.81, True),
    # Share of testable criteria passed: 7/9 strong, 3/9 weak, 4–6 fair — the
    # glossary's bands. 0.4 rather than 0.45 so that 4/9 (0.444) reads fair.
    "piotroski": (0.75, 0.4, True),
}


def strength_tone(key: str, value: "float | None") -> "str | None":
    """'good', 'fair' or 'weak' for one ratio; None for a value-less ratio."""
    if value is None or key not in STRENGTH_ZONES:
        return None
    good, weak, higher = STRENGTH_ZONES[key]
    if higher:
        return "good" if value >= good else "weak" if value < weak else "fair"
    return "good" if value <= good else "weak" if value > weak else "fair"


# Altman's zones for the original (public manufacturer) Z-score.
ALTMAN_SAFE, ALTMAN_DISTRESS = 2.99, 1.81


def altman_z(row: "dict", price: "float | None") -> "float | None":
    """Altman Z-score: 1.2·WC/TA + 1.4·RE/TA + 3.3·EBIT/TA + 0.6·MVE/TL + 1.0·S/TA.

    Above 2.99 is Altman's "safe" zone, below 1.81 "distress". EBIT is taken as
    operating income and MVE as market cap at ``price``. Every term is required
    — a Z-score with a term silently dropped is a different, lower number.
    """
    assets = _get(row, "total_assets")
    liabilities = total_liabilities(row)
    wc = _sub(_get(row, "current_assets"), _get(row, "current_liabilities"))
    terms = (wc, _get(row, "retained_earnings"), _get(row, "operating_income"),
             market_cap(row, price), _get(row, "revenue"))
    if not assets or not liabilities or any(v is None for v in terms):
        return None
    wc, re_, ebit, mve, sales = terms
    return (1.2 * wc / assets + 1.4 * re_ / assets + 3.3 * ebit / assets
            + 0.6 * mve / liabilities + 1.0 * sales / assets)


PIOTROSKI_TESTS = (
    "roa_positive", "ocf_positive", "roa_improving", "accruals",
    "leverage_falling", "liquidity_improving", "no_dilution",
    "gross_margin_improving", "asset_turnover_improving",
)


def piotroski(cur: "dict", prev: "dict") -> "dict":
    """Piotroski F-score: nine pass/fail tests, this year against last.

    ``cur`` and ``prev`` are TTM (or annual) entries a year apart. A test whose
    inputs are missing is None rather than a fail, and ``score`` counts passes
    out of ``tested`` — so a filer that does not tag gross profit (AMZN) is
    reported as 6/8, not marked down to 6/9 for something it never said.
    """
    def roa(r):
        return _div(_get(r, "net_income"), _get(r, "total_assets"))

    def lev(r):
        return _div(_get(r, "long_term_debt") or 0.0, _get(r, "total_assets"))

    def cur_ratio(r):
        return _div(_get(r, "current_assets"), _get(r, "current_liabilities"))

    def gm(r):
        return _div(_get(r, "gross_profit"), _get(r, "revenue"))

    def turn(r):
        return _div(_get(r, "revenue"), _get(r, "total_assets"))

    def gt(a, b):
        return None if a is None or b is None else a > b

    def lt(a, b):
        return None if a is None or b is None else a < b

    ocf, net = _get(cur, "ocf"), _get(cur, "net_income")
    sh_now, sh_then = _get(cur, "shares_diluted"), _get(prev, "shares_diluted")
    tests = {
        "roa_positive": gt(roa(cur), 0.0),
        "ocf_positive": gt(ocf, 0.0),
        "roa_improving": gt(roa(cur), roa(prev)),
        "accruals": gt(ocf, net),
        # Untestable without assets on both sides; debt-free in both years
        # counts as a pass (leverage cannot fall below zero).
        "leverage_falling": (None if lev(cur) is None or lev(prev) is None
                             else True if lev(cur) == lev(prev) == 0
                             else lt(lev(cur), lev(prev))),
        "liquidity_improving": gt(cur_ratio(cur), cur_ratio(prev)),
        "no_dilution": None if sh_now is None or sh_then is None
        else sh_now <= sh_then,
        "gross_margin_improving": gt(gm(cur), gm(prev)),
        "asset_turnover_improving": gt(turn(cur), turn(prev)),
    }
    tested = [v for v in tests.values() if v is not None]
    return {"score": sum(1 for v in tested if v), "tested": len(tested),
            "tests": tests}


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


def valuation_ranges(valuation: "dict", current: "dict | None" = None,
                     as_of: "str | None" = None, min_points: int = 4) -> "dict":
    """Where each multiple sits inside its own history.

    For every series in :func:`valuation_series`: the minimum, median and
    maximum over the stored history, the current value, and its percentile
    rank — the share of past periods at or below it. 90 reads "dearer than nine
    periods in ten". Series shorter than ``min_points`` are omitted; a rank
    among three points is noise.

    ``current`` overrides the latest point with a multiple at *today's* price
    (:func:`multiples` on the newest TTM and the last close). The series itself
    prices each period at its own period end, which for a company that last
    reported four months ago is a four-month-old multiple.
    """
    out: "dict[str, dict]" = {}
    for key, points in valuation.items():
        values = [p["v"] for p in points or []]
        if len(values) < min_points:
            continue
        ranked = sorted(values)
        n = len(ranked)
        mid = n // 2
        median = ranked[mid] if n % 2 else (ranked[mid - 1] + ranked[mid]) / 2
        now = (current or {}).get(key)
        if current is not None and now is None:
            continue  # undefined today (a loss, say): no marker to place
        if now is None:
            now, when = values[-1], points[-1]["t"]
        else:
            now, when = round(now, 3), as_of or points[-1]["t"]
        out[key] = {
            "min": ranked[0], "median": round(median, 3), "max": ranked[-1],
            "current": now, "as_of": when,
            "rank": round(sum(1 for v in ranked if v <= now) / n * 100.0, 1),
            "points": n,
        }
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
def _year_ago(rows: "list[dict]") -> "dict | None":
    """The TTM entry four quarters before the newest — if it is a year back.

    Same gap check as :func:`yoy_growth`: four rows back is only a year back in
    a store with no missing quarters.
    """
    if len(rows) < 2 * TTM_QUARTERS:
        return None
    i = len(rows) - 1
    apart = (date.fromisoformat(rows[i]["period_end"])
             - date.fromisoformat(rows[i - TTM_QUARTERS]["period_end"])).days
    lo, hi = YEAR_APART_DAYS
    return ttm(rows, i - TTM_QUARTERS) if lo <= apart <= hi else None



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
        "strength_ttm": financial_strength(t) if t else {},
        "altman_z": altman_z(t, price) if t else None,
        "piotroski": (piotroski(t, prev) if t and (prev := _year_ago(rows))
                      else None),
    }
    growth = yoy_growth(rows, "revenue")
    out["revenue_yoy"] = growth[-1]["v"] if growth else None
    return out


__all__ = [
    "TTM_QUARTERS", "FLOW_METRICS", "LEVEL_METRICS", "STATUTORY_TAX_RATE",
    "split_adjust", "ttm", "ttm_series", "annual_series", "yoy_growth",
    "margins", "total_debt", "returns_on_capital", "free_cash_flow", "ebitda",
    "effective_tax_rate", "tax_rate", "invested_capital", "nopat",
    "total_liabilities", "financial_strength", "altman_z", "piotroski",
    "STRENGTH_ZONES", "strength_tone",
    "PIOTROSKI_TESTS", "ALTMAN_SAFE", "ALTMAN_DISTRESS",
    "market_cap", "enterprise_value", "multiples", "valuation_series",
    "valuation_ranges", "pe_bands", "summary",
]
