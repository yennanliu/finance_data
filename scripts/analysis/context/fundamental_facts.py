"""The fundamental report's VERIFIED FIGURES block: computed here, quoted there.

The 37-report fact-check (``docs/FUNDAMENTAL_REPORT_REVIEW.md`` §12) found that
the model copies figures reliably and derives them badly: TTM growth taken from
a quarterly field, FCF from Yahoo's "levered" figure, WACC from the prompt's own
example, peer multiples from memory. So every figure the report needs that can
be computed is computed here, from the SEC-sourced fundamentals store and the
price store, and handed to the model with its period, source and formula.

Pure: ``compute_facts`` takes the ``fetch_data`` dict plus
:func:`analysis.data.report_inputs.gather`'s output and returns plain data;
``render_facts`` turns that into context text.
"""

from __future__ import annotations

from datetime import date

from ..config.valuation import (
    DEFAULT_CREDIT_SPREAD, DEFAULT_TAX_RATE, EQUITY_RISK_PREMIUM, FCFF_GROWTH_BOUNDS, FCFF_TERMINAL_CAPEX_TO_DA,
    HISTORY_YEARS, MAX_STATEMENT_AGE_DAYS, TAX_RATE_BOUNDS, WACC_BOUNDS,
)
from ..data import fundamental_analytics as fa
from ..data import prices
from ..utils.formatting import money
from . import valuation as val

FUND_TYPES = ("ETF", "MUTUALFUND")


# ── helpers ──────────────────────────────────────────────────────────────────
def _f(v) -> "float | None":
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def _add(*values) -> "float | None":
    """Sum of the present parts (a company with no short-term investments does
    not tag them), or None if every part is missing."""
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def _pct_change(now, then) -> "float | None":
    if now is None or then is None or then <= 0:
        return None
    return (now - then) / then


def _days_between(a: str, b: str) -> int:
    return abs((date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days)


def _frame_value(df, row: str):
    """Newest value of ``row`` in a newest-first yfinance frame, or None."""
    try:
        if df is None or row not in df.index:
            return None
        return _f(df.loc[row].iloc[0])
    except (IndexError, KeyError):
        return None


def _year_ago_index(rows: "list[dict]") -> "int | None":
    """Index of the row ~one year before the newest, checked by date (the store
    has gaps, so four rows back is not always a year back)."""
    if len(rows) < 5:
        return None
    lo, hi = fa.YEAR_APART_DAYS
    i = len(rows) - 5
    if lo <= _days_between(rows[i]["period_end"], rows[-1]["period_end"]) <= hi:
        return i
    return None


# ── statements ───────────────────────────────────────────────────────────────
def statement_facts(rows: "list[dict]", as_of: "str | None") -> "dict | None":
    """TTM and latest-quarter figures from the SEC-sourced store, or None when
    the store is empty or its newest quarter is stale."""
    t = fa.ttm(rows)
    if not t:
        return None
    if as_of and _days_between(t["period_end"], as_of) > MAX_STATEMENT_AGE_DAYS:
        return None
    latest = rows[-1]
    prev_i = _year_ago_index(rows)
    prev = fa.ttm(rows, prev_i) if prev_i is not None else None
    q_prev = rows[prev_i] if prev_i is not None else None

    m_ttm = fa.margins(t)
    m_q = fa.margins(latest)
    ret = fa.returns_on_capital(t)
    cash = _add(t.get("cash_and_equiv"), t.get("short_term_investments"))
    debt = fa.total_debt(t)
    return {
        "source": f"SEC {latest['form']} filed {latest['filed']}".strip(),
        "period_end": latest["period_end"],
        "fiscal_label": f"FY{latest['fy']} {latest['fp']}",
        "revenue_ttm": t.get("revenue"),
        "revenue_ttm_prior": prev and prev.get("revenue"),
        "revenue_growth_ttm": _pct_change(t.get("revenue"), prev and prev.get("revenue")),
        "revenue_q": latest.get("revenue"),
        "revenue_growth_q": _pct_change(latest.get("revenue"), q_prev and q_prev.get("revenue")),
        "operating_income_ttm": t.get("operating_income"),
        "op_margin_ttm": m_ttm["operating"] / 100 if m_ttm["operating"] is not None else None,
        "op_margin_q": m_q["operating"] / 100 if m_q["operating"] is not None else None,
        "gross_margin_ttm": m_ttm["gross"] / 100 if m_ttm["gross"] is not None else None,
        "net_income_ttm": t.get("net_income"),
        "eps_ttm": t.get("eps_diluted"),
        "ocf_ttm": t.get("ocf"),
        "capex_ttm": t.get("capex"),
        "fcf_ttm": fa.free_cash_flow(t),
        "da_ttm": t.get("dep_amort"),
        "ebitda_ttm": fa.ebitda(t),
        # Complete fiscal years, oldest first, for the DCF's normalised margin.
        "op_margin_history": [m["operating"] / 100 for m in map(fa.margins, fa.annual_series(rows))
                              if m["operating"] is not None],
        "cash": cash,
        "debt": debt,
        "net_cash": (cash or 0.0) - (debt or 0.0) if cash is not None or debt is not None else None,
        "roic_ttm": ret["roic"] / 100 if ret["roic"] is not None else None,
        "roe_ttm": ret["roe"] / 100 if ret["roe"] is not None else None,
        "_ttm_row": t,
    }


def history_multiples(rows, bars, ttm_row, price) -> "dict":
    """Each multiple now (at the current price) vs its own trailing history."""
    out = {}
    if not rows or not bars or not ttm_row:
        return out
    series = fa.valuation_series(rows, bars)
    now = fa.multiples(ttm_row, price)
    cutoff = f"{int(ttm_row['period_end'][:4]) - HISTORY_YEARS}{ttm_row['period_end'][4:]}"
    for key in ("pe", "ps", "ev_ebitda"):
        hist = sorted(p["v"] for p in series.get(key, []) if p["t"] >= cutoff)
        if len(hist) < 4 or now.get(key) is None:
            continue
        cur = now[key]
        out[key] = {
            "current": cur,
            "median": hist[len(hist) // 2],
            "low": hist[0],
            "high": hist[-1],
            "percentile": sum(1 for v in hist if v <= cur) / len(hist),
            "points": len(hist),
        }
    return out


# ── cost of capital ──────────────────────────────────────────────────────────
def wacc_inputs(info: dict, data: dict, stmt: "dict | None", risk_free,
                fx: "float | None" = None) -> "dict":
    """CAPM cost of equity and a reference WACC, every component exposed.

    ``fx`` (quote-currency units per statement-currency unit) converts debt so
    an ADR's market cap and debt can be weighted; without it they cannot.
    """
    beta_raw = _f(info.get("beta"))
    beta, beta_note = val.adjusted_beta(beta_raw)
    ke = risk_free + beta * EQUITY_RISK_PREMIUM if risk_free is not None else None

    income = data.get("income")
    interest = _frame_value(income, "Interest Expense")
    pretax = _frame_value(income, "Pretax Income")
    tax = _frame_value(income, "Tax Provision")
    tax_rate, tax_source = DEFAULT_TAX_RATE, "default"
    if pretax and pretax > 0 and tax is not None:
        rate = tax / pretax
        lo, hi = TAX_RATE_BOUNDS
        if lo <= rate <= hi:
            tax_rate, tax_source = rate, "effective (latest annual)"

    debt = stmt["debt"] if stmt and stmt.get("debt") is not None else _f(info.get("totalDebt"))
    equity = _f(info.get("marketCap"))
    kd = abs(interest) / debt if interest and debt else None
    kd_source = "interest ÷ debt"
    if kd is None and debt and risk_free is not None:
        kd, kd_source = risk_free + DEFAULT_CREDIT_SPREAD, "assumed: Rf + credit spread, no interest reported"

    out = {"risk_free": risk_free, "erp": EQUITY_RISK_PREMIUM, "beta": beta,
           "beta_raw": beta_raw, "beta_note": beta_note,
           "cost_of_equity": ke, "pre_tax_cost_of_debt": kd, "kd_source": kd_source,
           "tax_rate": tax_rate, "tax_source": tax_source,
           "equity_value": equity, "debt": debt, "wacc": None, "wacc_raw": None,
           "equity_weight": None, "debt_weight": None}
    if ke is None or not equity:
        return out
    from . import currency_mismatch
    if currency_mismatch(info):
        if not fx:
            return out  # market cap (quote ccy) and debt (statement ccy) can't be weighted
        debt = debt * fx if debt is not None else None
    d = debt or 0.0
    we, wd = equity / (equity + d), d / (equity + d)
    if wd and kd is None:
        return out
    raw = we * ke + wd * (kd or 0.0) * (1 - tax_rate)
    out.update(equity_weight=we, debt_weight=wd, wacc_raw=raw, wacc=val.banded_wacc(raw))
    return out


def _annual_margins(income) -> "list[float]":
    """Operating margin of each fiscal year in a newest-first yfinance frame,
    returned oldest first."""
    out = []
    try:
        if income is None or "Operating Income" not in income.index or "Total Revenue" not in income.index:
            return out
        for col in income.columns:
            op, rev = _f(income.loc["Operating Income", col]), _f(income.loc["Total Revenue", col])
            if op is not None and rev:
                out.append(op / rev)
    except (KeyError, IndexError):
        return []
    return out[::-1]


def _fill_from_yahoo(stmt: dict, data: dict, info: dict) -> None:
    """Fill what the DCF needs and the SEC store could not give.

    AMD, MRVL and WDC tag no depreciation concept the store maps, so D&A comes
    from Yahoo's quarterly cash flow, then from EBITDA − operating income. A
    company with no SEC rows at all (an IFRS filer) gets its margin history
    from Yahoo's annual income statement.
    """
    from . import statement_ttm

    if stmt.get("da_ttm") is None:
        stmt["da_ttm"] = statement_ttm(data).get("da")
    if stmt.get("da_ttm") is None:
        ebitda, revenue, margin = _f(info.get("ebitda")), stmt.get("revenue_ttm"), stmt.get("op_margin_ttm")
        if ebitda is not None and revenue and margin is not None and ebitda > revenue * margin:
            stmt["da_ttm"] = ebitda - revenue * margin
    if stmt.get("ebitda_ttm") is None:
        revenue, margin, da = stmt.get("revenue_ttm"), stmt.get("op_margin_ttm"), stmt.get("da_ttm")
        stmt["ebitda_ttm"] = (revenue * margin + da if None not in (revenue, margin, da)
                              else _f(info.get("ebitda")))
    if not stmt.get("op_margin_history"):
        stmt["op_margin_history"] = _annual_margins(data.get("income"))


# ── assembly ─────────────────────────────────────────────────────────────────
def compute_facts(data: dict, inputs: dict) -> dict:
    """All verified figures for one fundamental report."""
    from . import currency_mismatch, statement_ttm

    info = data.get("info") or {}
    price, price_date = data.get("price_now"), data.get("price_date")
    is_fund = info.get("quoteType") in FUND_TYPES
    rows = inputs.get("store_rows") or []
    stmt = None if is_fund else statement_facts(rows, price_date)

    if stmt is None and not is_fund:
        y = statement_ttm(data)  # Yahoo quarterly fallback: TTM level, no TTM growth
        latest_q = None
        income_q = data.get("income_q")
        if income_q is not None and len(getattr(income_q, "columns", [])):
            latest_q = str(income_q.columns[0])[:10]
        stmt = {
            "source": "Yahoo quarterly statements (no SEC filing data)",
            "period_end": latest_q, "fiscal_label": "TTM = four quarters to this date",
            "revenue_ttm": y["revenue"] or _f(info.get("totalRevenue")),
            "revenue_growth_ttm": None,
            "revenue_q": None,
            "revenue_growth_q": _f(info.get("revenueGrowth")),
            "op_margin_ttm": y["op_margin"],
            "op_margin_q": _f(info.get("operatingMargins")),
            "ocf_ttm": y["ocf"], "capex_ttm": y["capex"], "fcf_ttm": y["fcf"],
            "da_ttm": y["da"],
            "ebitda_ttm": (y["op_income"] + y["da"] if y["op_income"] is not None
                           and y["da"] is not None else _f(info.get("ebitda"))),
            "cash": _f(info.get("totalCash")), "debt": _f(info.get("totalDebt")),
            "_ttm_row": None,
        }
        stmt["net_cash"] = ((stmt["cash"] or 0.0) - (stmt["debt"] or 0.0)
                            if stmt["cash"] is not None or stmt["debt"] is not None else None)

    if stmt is not None:
        _fill_from_yahoo(stmt, data, info)

    mismatch = currency_mismatch(info)
    fx = inputs.get("fx") if mismatch else None
    rate = fx["rate"] if fx else (None if mismatch else 1.0)
    mkt = _f(info.get("marketCap"))
    fcf_yield = None
    if stmt and stmt.get("fcf_ttm") is not None and mkt and rate:
        fcf_yield = stmt["fcf_ttm"] * rate / mkt

    wacc = None if is_fund else wacc_inputs(info, data, stmt, inputs.get("risk_free"),
                                            fx["rate"] if fx else None)
    valuation = None if is_fund else val.build(
        prices.report_key(data.get("ticker") or ""), info, stmt, wacc,
        inputs.get("peers") or [], price, rate)

    return {
        "ticker": data.get("ticker"),
        "price": price,
        "price_date": price_date,
        "currency": info.get("currency"),
        "statement_currency": info.get("financialCurrency") or info.get("currency"),
        "currency_mismatch": mismatch,
        "fx": fx,
        "is_fund": is_fund,
        "statements": stmt,
        "fcf_yield": fcf_yield,
        "history": history_multiples(rows, inputs.get("bars"), stmt and stmt.get("_ttm_row"), price)
        if stmt and not mismatch else {},
        "wacc": wacc,
        "valuation": valuation,
        "peers": inputs.get("peers") or [],
    }


# ── rendering ────────────────────────────────────────────────────────────────
def _p(v, digits=1) -> str:
    return "N/A" if v is None else f"{v * 100:.{digits}f}%"


def _num(v, digits=2) -> str:
    return "N/A" if v is None else f"{v:.{digits}f}"


def _x(v) -> str:
    return "N/A" if v is None else f"{v:.1f}x"


def _peer_line(p: dict) -> str:
    mixed = p.get("currency") and p.get("financialCurrency") and p["currency"] != p["financialCurrency"]
    ps = "N/A (mixed ccy)" if mixed else _x(_f(p.get("priceToSalesTrailing12Months")))
    ev = "N/A (mixed ccy)" if mixed else _x(_f(p.get("enterpriseToEbitda")))
    return (f"  {p['ticker']:<6} P/E(TTM) {_x(_f(p.get('trailingPE')))}  "
            f"P/E(Fwd) {_x(_f(p.get('forwardPE')))}  P/S(TTM) {ps}  EV/EBITDA(TTM) {ev}  "
            f"Rev growth (latest Q YoY) {_p(_f(p.get('revenueGrowth')))}  "
            f"Gross margin (TTM) {_p(_f(p.get('grossMargins')))}")


def _usd(v, ccy: str = "") -> str:
    return "N/A" if v is None else f"{v:,.2f} {ccy}".strip()


def render_dcf(d: dict, ccy: str, sccy: str, price) -> "list[str]":
    """The DCF MODEL block: assumptions, yearly table, bridge, grid, scenarios
    and reverse DCF, every cell computed."""
    if not d.get("available"):
        return ["", "DCF MODEL: N/A — " + d.get("reason", "not available") + ".",
                "  → Write §8.1–8.7 as N/A with this reason. Do not build a DCF of your own."]
    a, m, ps = d["assumptions"], d["model"], d["per_share"]
    bn = lambda v: f"{v / 1e9:,.2f}"
    up = lambda v: "N/A" if v is None or not price else f"{(v / price - 1) * 100:+.1f}%"
    lines = [
        "",
        f"DCF MODEL (computed in Python; amounts in {sccy} billions unless per share) — copy §8.1–8.7 from here:",
        "  Assumptions (the house base case; explain and criticise them, do not change a number):",
        f"    Forecast length N:                {a['years']} years",
        f"    Revenue base (TTM):               {bn(a['revenue'])}",
        f"    Revenue growth, year 1:           {_p(a['start_growth'])}   ← {a['growth_source']} {_p(a['raw_growth'])}, "
        f"held inside {_p(FCFF_GROWTH_BOUNDS[0], 0)}–{_p(FCFF_GROWTH_BOUNDS[1], 0)}",
        f"    Revenue growth, year {a['years']}:          {_p(a['terminal_growth'])}   ← fades linearly from year 1",
        f"    Operating margin (GAAP EBIT):     {_p(a['op_margin'])} in year 1 → {_p(a['op_margin_end'])} in year {a['years']}   ← "
        + (f"TTM, fading to the median of the last {a['margin_years']} fiscal years (TTM included)"
           if a["margin_years"] else "TTM, held constant (too little history for a median, or a median that is not positive)"),
        f"    Tax rate:                         {_p(a['tax_rate'])}",
        f"    D&A ÷ revenue:                    {_p(a['da_pct'])}   ← TTM, held constant",
        f"    Capex ÷ revenue:                  {_p(a['capex_start'])} in year 1 → {_p(a['capex_end'])} in year {a['years']}"
        f"   ← TTM, fading to {FCFF_TERMINAL_CAPEX_TO_DA:.1f} × D&A if above it",
        f"    WACC:                             {_p(a['wacc'], 2)}",
        f"    Terminal growth g:                {_p(a['terminal_growth'])}",
        "    FCFF = NOPAT + D&A − Capex. Working capital is not modelled. EBIT is GAAP, so SBC is already",
        "    an expense and the share count is not diluted further (prompt combination A).",
        "",
        "  Year  Growth   Revenue  Margin      EBIT       Tax     NOPAT      D&A     Capex      FCFF   Disc.f        PV",
    ]
    for y in m["years"]:
        lines.append(f"  FY+{y['year']:<2} {_p(y['growth']):>7} {bn(y['revenue']):>9} {_p(y['op_margin']):>7} {bn(y['ebit']):>9} "
                     f"{bn(y['tax']):>9} {bn(y['nopat']):>9} {bn(y['da']):>8} {bn(y['capex']):>9} "
                     f"{bn(y['fcff']):>9}   {y['discount_factor']:.3f} {bn(y['pv']):>9}")
    last = m["years"][-1]
    lines += [
        f"  Sum of PV (forecast):               {bn(m['pv_sum'])}",
        f"  Terminal value = {bn(last['fcff'])} × (1 + {_p(m['terminal_growth'])}) ÷ ({_p(m['wacc'], 2)} − {_p(m['terminal_growth'])})"
        f" = {bn(m['terminal_value'])}",
        f"  PV of terminal value = {bn(m['terminal_value'])} × {last['discount_factor']:.3f} = {bn(m['pv_terminal'])}"
        f"   ({_p(m['terminal_share'])} of enterprise value)",
        f"  Enterprise value:                   {bn(m['enterprise_value'])}",
        f"  + Net cash (− = net debt):          {bn(m['net_cash'])}",
        f"  = Equity value:                     {bn(m['equity_value'])}",
        f"  Per share = equity value × price ÷ market cap (in {ccy}) = {_usd(d['value'], ccy)}"
        f"   ({up(d['value'])} vs price)   ← the DCF base value for §8.5 and §8.8",
        "",
        "  Sensitivity, value per share (rows: terminal growth g; columns: WACC):",
        "      g \\ WACC " + "".join(f"{_p(w, 2):>12}" for w in d["sensitivity"]["waccs"]),
    ]
    for g, row in zip(d["sensitivity"]["growths"], d["sensitivity"]["values"]):
        lines.append(f"      {_p(g, 1):>8}  " + "".join(
            f"{'N/A (WACC ≤ g)' if v is None else f'{v:,.2f}':>12}" for v in row))
    lines += ["", "  Scenarios (growth, margin and WACC all move; value per share):"]
    names = {"bear": "悲觀", "base": "基準", "bull": "樂觀"}
    for sc in d["scenarios"]:
        lines.append(f"    {names[sc['name']]}  year-1 growth {_p(sc['start_growth'])}, year-{a['years']} operating margin {_p(sc['op_margin'])}, "
                     f"WACC {_p(sc['wacc'], 2)} → {_usd(sc['value'], ccy)} ({up(sc['value'])})   probability {_p(sc['probability'], 0)}")
    lines.append(f"    Probability-weighted: {_usd(d['scenario_weighted'], ccy)} ({up(d['scenario_weighted'])})"
                 "   ← context only; §8.8 uses the base value")
    ig, im = d["implied_growth"], d["implied_margin"]
    lines += [
        "",
        "  Reverse DCF (one variable solved at a time, the rest at the base case, so that value = price):",
        "    Year-1 revenue growth the price implies: "
        + ("no solution between −10% and 100%" if ig is None else f"{_p(ig)} (base case {_p(a['start_growth'])})"),
        "    Constant operating margin the price implies: "
        + ("no solution between 0.5% and 95%" if im is None
           else f"{_p(im)} (base case {_p(a['op_margin'])} → {_p(a['op_margin_end'])})"),
    ]
    return lines


def render_valuation(f: dict) -> "list[str]":
    """DCF model, §8.8 method table and the rating that follows from it."""
    v = f.get("valuation")
    if not v:
        return []
    ccy = f.get("currency") or ""
    price = f.get("price")
    lines = render_dcf(v["dcf"], ccy, f.get("statement_currency") or ccy, price)
    lines += ["", f"VALUATION METHODS for §7.4 and §8.8 (company type: {v['archetype']}; weights are fixed "
                  "by type — copy values and weights unchanged, add no method and drop none):"]
    if not v["methods"]:
        lines.append("  None could be computed. Write §8.8 as N/A, give no weighted fair value, no MOS and "
                     "no MOS-based rating; say which inputs are missing.")
        return lines
    for r in v["methods"]:
        up = f"{(r['value'] / price - 1) * 100:+.1f}%" if price else "N/A"
        lines.append(f"  {r['label']:<14} {r['value']:>12,.2f} {ccy}   {up:>8}   weight {r['weight_pct']:>3}%   ← {r['basis']}")
    terms = " + ".join(f"{r['value']:,.2f} × {r['weight_pct']}%" for r in v["methods"])
    lines += [
        f"  加權合理價值 = {terms} = {v['fair_value']:,.2f} {ccy}",
    ]
    if v["mos_pct"] is None:
        # No price to measure against (Yahoo and the price store both failed).
        lines.append("  MOS / 上行空間 / 評級: N/A — no price. Give no MOS and no MOS-based rating.")
    else:
        lines.append(f"  MOS = {v['mos_pct']:+.1f}%   上行空間 = {v['upside_pct']:+.1f}%   "
                     f"評級（規則 20）= {v['rating']}")
    if v["unavailable"]:
        lines.append("  Not computable, so left out and its weight shared among the rest: "
                     + "、".join(v["unavailable"]))
    lines.append("  Relative methods use the peers' median multiple, never this company's own current multiple.")
    return lines


def render_facts(f: dict) -> str:
    """The VERIFIED FIGURES context block."""
    ccy = f.get("currency") or ""
    sccy = f.get("statement_currency") or ccy
    lines = [
        "",
        "━━ VERIFIED FIGURES (computed in Python — quote these exactly; do not recompute, round differently or replace) ━━",
        f"Price (last completed session close, {f.get('price_date') or 'date N/A'}): "
        f"{_num(f.get('price'), 2)} {ccy}",
        "  → Use this price and say its date. Do not call it the report-date close unless the dates match.",
    ]
    fx = f.get("fx")
    if f.get("currency_mismatch"):
        q, s = f["currency_mismatch"]
        if fx:
            lines.append(f"Currency: quoted in {q}, statements in {s}. FX ({fx['pair']}, {fx['date']} close): "
                         f"1 {q} = {1 / fx['rate']:,.2f} {s}. Use this rate for every conversion and "
                         f"do not assume another; converted amounts are shown as (≈ … {q}).")
        else:
            lines.append(f"Currency: quoted in {q}, statements in {s}. No FX rate is available: never divide "
                         f"a {s} figure by a {q} price or market cap (FCF yield, EV/EBITDA, P/S), and do not "
                         f"convert with an assumed rate.")
    if f.get("is_fund"):
        lines.append("Instrument: fund/ETF — it has no income statement, cash flow or WACC. "
                     "Do not invent company financials; analyse holdings, fees, tracking and valuation of the index.")
    def amt(v) -> str:
        if v is None:
            return "N/A"
        text = f"{money(v, prefix='')} {sccy}"
        if fx:
            text += f" (≈ {money(v * fx['rate'], prefix='')} {ccy})"
        return text

    s = f.get("statements")
    if s:
        lines += [
            "",
            f"Statements: {s['source']}" + (f", latest quarter {s['period_end']} ({s['fiscal_label']})"
                                            if s.get("period_end") else ""),
            f"  Revenue (TTM):                         {amt(s.get('revenue_ttm'))}",
            f"  Revenue growth (TTM vs prior TTM):     {_p(s.get('revenue_growth_ttm'))}",
            f"  Revenue growth (LATEST QUARTER YoY):   {_p(s.get('revenue_growth_q'))}"
            "   ← a quarterly rate; never label it TTM",
            f"  Operating margin (TTM):                {_p(s.get('op_margin_ttm'))}",
            f"  Operating margin (LATEST QUARTER):     {_p(s.get('op_margin_q'))}",
            f"  Operating cash flow (TTM):             {amt(s.get('ocf_ttm'))}",
            f"  Capital expenditure (TTM):             {amt(s.get('capex_ttm'))}",
            f"  Free cash flow (TTM) = OCF − capex:    {amt(s.get('fcf_ttm'))}",
            f"  FCF yield (TTM FCF ÷ market cap):      {_p(f.get('fcf_yield'), 2)}",
            f"  Cash + short-term investments:         {amt(s.get('cash'))}",
            f"  Total debt:                            {amt(s.get('debt'))}",
            f"  Net cash (− = net debt):               {amt(s.get('net_cash'))}",
        ]
        if s.get("roic_ttm") is not None:
            lines.append(f"  ROIC (TTM, after-tax operating income ÷ (equity + debt − cash)): {_p(s['roic_ttm'])}")
        if s.get("roe_ttm") is not None:
            lines.append(f"  ROE (TTM):                             {_p(s['roe_ttm'])}")
        lines.append("  → If a figure above is N/A, say it is unavailable. Never back out a missing"
                     " figure (e.g. capex) so that a table adds up.")
    w = f.get("wacc")
    if w:
        lines += ["", "Cost of capital (use these; WACC is the discount rate of §6.2 and §8):",
                  f"  Risk-free rate (10Y Treasury):  {_p(w['risk_free'], 2)}",
                  f"  Equity risk premium (assumed):  {_p(w['erp'], 2)}",
                  f"  Beta (raw, Yahoo):              {_num(w.get('beta_raw'), 2)}",
                  f"  Beta used (adjusted):           {_num(w['beta'], 2)}   ← {w.get('beta_note', '')}",
                  f"  Cost of equity = Rf + β × ERP:  {_p(w['cost_of_equity'], 2)}",
                  f"  Pre-tax cost of debt ({w.get('kd_source', 'interest ÷ debt')}): {_p(w['pre_tax_cost_of_debt'], 2)}",
                  f"  Tax rate ({w['tax_source']}):   {_p(w['tax_rate'], 1)}",
                  f"  Weights E / D (market cap / debt): {_p(w['equity_weight'])} / {_p(w['debt_weight'])}",
                  f"  WACC:                           {_p(w['wacc'], 2)}"]
        raw = w.get("wacc_raw")
        if raw is not None and w["wacc"] is not None and abs(raw - w["wacc"]) > 1e-9:
            lo, hi = WACC_BOUNDS
            lines.append(f"    (computed {_p(raw, 2)}; held at the {_p(lo, 0)}–{_p(hi, 0)} band — say so in §8.2)")
    h = f.get("history")
    if h:
        lines += ["", f"Valuation vs own {HISTORY_YEARS}-year history (TTM multiples, price store × SEC statements):"]
        names = {"pe": "P/E", "ps": "P/S", "ev_ebitda": "EV/EBITDA"}
        for k, v in h.items():
            lines.append(f"  {names[k]:<10} now {_x(v['current'])}   median {_x(v['median'])}   "
                         f"range {_x(v['low'])}–{_x(v['high'])}   percentile rank now {v['percentile'] * 100:.0f}%")
    peers = f.get("peers")
    lines.append("")
    if peers:
        lines.append("Peer multiples (Yahoo; use these for §7.1, do not substitute remembered figures):")
        lines += [_peer_line(p) for p in peers]
    else:
        lines.append("Peer multiples: not provided. Any peer multiple you cite must be marked 「估計值」.")
    lines += render_valuation(f)
    lines += [
        "",
        "MOS / upside definitions (Python re-checks §8.8 after generation):",
        "  加權合理價值 = Σ(方法價值 × 權重)，權重合計 100%；寫出完整算式，總和必須等於各項相加。",
        f"  MOS = (加權合理價值 − 價格) ÷ 加權合理價值；上行空間 = (加權合理價值 − 價格) ÷ 價格；價格 = 上方 {f.get('price_date') or ''} 收盤價。",
    ]
    return "\n".join(lines)


__all__ = ["compute_facts", "render_facts", "render_valuation", "render_dcf",
           "statement_facts", "history_multiples", "wacc_inputs"]
