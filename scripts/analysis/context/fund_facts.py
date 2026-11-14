"""The ETF report's VERIFIED FUND FIGURES block.

A fund has no income statement, cash flow or WACC, so the company template had
nothing to fill: the eight ETF reports of 2026-11-13 each ran to about 1,000
lines carrying 417–461 ``N/A``, and QQQ was rated "Hold, margin of safety 0%"
by taking its own price as its fair value (``docs/REPORT_REVIEW.md`` F4).

What a fund *can* be judged on is computed here: cost, size, what it holds and
how concentrated that is, and how it has performed against the market, from the
fund profile (:func:`analysis.data.report_inputs.fund_profile`) and the price
store. Pure: plain data in, text out.
"""

from __future__ import annotations

from ..config.benchmarks import BENCHMARK_NAMES, market_benchmark
from ..data import price_analytics as pa
from ..data import prices
from ..utils.formatting import money

WINDOWS = (("1 個月", "1m"), ("3 個月", "3m"), ("6 個月", "6m"),
           ("1 年", "1y"), ("3 年", "3y"), ("5 年", "5y"))
# Share of assets in the ten largest holdings above which a fund is concentrated.
CONCENTRATED_TOP10 = 0.50


def concentration(holdings: "list[dict]") -> "dict | None":
    """Weight of the largest and of the listed holdings (Yahoo gives the top
    ten), and the Herfindahl index over them."""
    weights = [h["weight"] for h in holdings or [] if h.get("weight")]
    if not weights:
        return None
    return {"count": len(weights), "largest": max(weights), "total": sum(weights),
            "hhi": sum(w * w for w in weights)}


def performance(bars: "list[dict]", bench: "list[dict]") -> "list[dict]":
    """Price return per window for the fund and the benchmark, on the dates
    both have a bar for, so a store one session behind does not skew it."""
    if bench:
        common = {b["date"] for b in bars} & {b["date"] for b in bench}
        bars = [b for b in bars if b["date"] in common]
        bench = [b for b in bench if b["date"] in common]
    out = []
    for label, key in WINDOWS:
        days = pa.TRADING_DAYS[key]
        f = pa.period_return(bars, days)
        m = pa.period_return(bench, days) if bench else None
        out.append({"label": label, "fund": f, "benchmark": m,
                    "excess": f - m if f is not None and m is not None else None})
    return out


def compute(data: dict, profile: "dict | None", bars: "list[dict]",
            bench_bars: "list[dict] | None" = None, bench_key: "str | None" = None) -> dict:
    profile = profile or {}
    price, nav = data.get("price_now"), profile.get("nav")
    dd = pa.max_drawdown(bars) if bars else None
    return {
        "ticker": data.get("ticker"), "price": price, "price_date": data.get("price_date"),
        "currency": (data.get("info") or {}).get("currency"),
        "profile": profile,
        "premium": (price / nav - 1) if price and nav else None,
        "concentration": concentration(profile.get("holdings") or []),
        "performance": performance(bars, bench_bars or []) if bars else [],
        "benchmark": bench_key,
        "as_of": bars[-1]["date"] if bars else None,
        "volatility_1y": pa.annualised_volatility(bars) if bars else None,
        "max_drawdown": dd,
        "cagr": pa.cagr(bars) if bars else None,
        "history_years": (pa._year_fraction(bars[0]["date"], bars[-1]["date"]) if len(bars) > 1 else None),
    }


def gather(data: dict, profile: "dict | None") -> dict:
    """:func:`compute` with the fund's and its benchmark's bars read from the
    price store."""
    key = prices.report_key(data.get("ticker") or "")
    bench = market_benchmark(key)
    return compute(data, profile, prices.load_store(key),
                   prices.load_store(bench) if bench else [], bench)


def _p(v, digits=2) -> str:
    return "N/A" if v is None else f"{v * 100:.{digits}f}%"


def _r(v) -> str:
    return "N/A" if v is None else f"{v:+.1f}%"


def _x(v) -> str:
    return "N/A" if v is None else f"{v:.1f}x"


def render(f: dict) -> str:
    p, ccy = f["profile"], f.get("currency") or ""
    price = "N/A" if f.get("price") is None else f"{f['price']:.2f} {ccy}"
    nav = "N/A" if p.get("nav") is None else f"{p['nav']:.2f} {ccy}"
    assets = money(p["total_assets"], prefix="") + " " + ccy if p.get("total_assets") else "N/A"
    category_avg = (f"   (category average {_p(p.get('expense_ratio_category'))})"
                    if p.get("expense_ratio_category") else "")
    lines = [
        "",
        "━━ VERIFIED FUND FIGURES (computed in Python — quote these exactly; do not recompute or replace) ━━",
        f"Price (last completed session close, {f.get('price_date') or 'date N/A'}): {price}",
        "Instrument: fund / ETF. It has no income statement, cash flow, WACC, DCF or margin of safety.",
        "",
        "Fund profile (Yahoo Finance):",
        f"  Fund family / category:     {p.get('family') or 'N/A'} / {p.get('category') or 'N/A'}",
        f"  Net expense ratio:          {_p(p.get('expense_ratio'))}{category_avg}",
        f"  Net assets:                 {assets}",
        f"  Annual holdings turnover:   {_p(p.get('turnover'), 1)}",
        f"  Distribution yield:         {_p(p.get('yield'))}",
        f"  NAV:                        {nav}   → price premium (+) / discount (−) to NAV: {_p(f.get('premium'))}",
        f"  Portfolio P/E / P/B:        {_x(p.get('pe'))} / {_x(p.get('pb'))}   (weighted, as Yahoo reports them)",
    ]
    holdings = p.get("holdings") or []
    if holdings:
        lines += ["", f"Largest holdings ({len(holdings)} listed):"]
        lines += [f"  {h['symbol']:<10} {h.get('name', '')[:38]:<38} {_p(h['weight'])}" for h in holdings]
        c = f["concentration"]
        lines.append(f"  → The {c['count']} listed sum to {_p(c['total'], 1)} of assets; the largest is "
                     f"{_p(c['largest'], 1)}. " + ("Concentrated: more than half the fund is in these names."
                                                  if c["total"] > CONCENTRATED_TOP10 else
                                                  "Diversified: these names are less than half the fund."))
    else:
        lines += ["", "Largest holdings: N/A (not provided). Do not list holdings from memory."]
    sectors = sorted((p.get("sectors") or {}).items(), key=lambda kv: -kv[1])
    if sectors:
        lines += ["", "Sector weights:"] + [f"  {name:<24} {_p(w, 1)}" for name, w in sectors if w]
    perf = f.get("performance") or []
    if perf:
        bench = BENCHMARK_NAMES.get(f.get("benchmark"), f.get("benchmark"))
        lines += ["", f"Price return (price store, to {f.get('as_of')}; distributions not included)"
                      + (f", against {bench}:" if bench else ":"),
                  "  期間       本基金" + ("     基準      超額" if bench else "")]
        for row in perf:
            lines.append(f"  {row['label']:<8} {_r(row['fund']):>8}"
                         + (f"  {_r(row['benchmark']):>8}  {_r(row['excess']):>8}" if bench else ""))
        dd = f.get("max_drawdown")
        vol = "N/A" if f.get("volatility_1y") is None else f"{f['volatility_1y']:.1f}%"
        growth = "N/A" if f.get("cagr") is None else f"{f['cagr']:.1f}%"
        span = f", {f['history_years']:.1f} years" if f.get("history_years") else ""
        worst = "N/A" if not dd else f"{dd['pct']:.1f}% (trough {dd['date']})"
        lines += [
            f"  Annualised volatility (1Y): {vol}",
            f"  Maximum drawdown (stored history{span}): {worst}",
            f"  CAGR over the stored history: {growth}",
        ]
    lines += ["", "→ A figure shown as N/A is unavailable: say so. Never fill it from memory, and never "
                  "invent tracking error, index methodology details or holdings that are not listed above."]
    return "\n".join(lines)


__all__ = ["compute", "gather", "render", "concentration", "performance"]
