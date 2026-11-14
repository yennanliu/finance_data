"""The fundamental report's valuation, computed in Python: DCF, method values,
weights, weighted fair value and rating.

The 2026-11-14 review of the reports (``docs/REPORT_REVIEW.md``) found that the
conclusion rested on numbers the model chose or estimated:

* the §8.8 weights (the DCF's ran from 10% to 70%), so the weights decided the
  rating — ORCL was a Buy on a DCF 82% below its price;
* methods that returned the price they were meant to test: an EV/EBITDA "held
  at the current multiple", a FCF yield equal to today's, analyst consensus
  counted twice;
* a DCF grid, scenario table and reverse DCF filled in by hand;
* a raw beta that put 12 of 30 discount rates at 15% or more.

Everything here is deterministic. :func:`build` returns plain data that
:mod:`fundamental_facts` renders into the VERIFIED FIGURES block; the model
quotes it and explains it. Pure: no network, no pandas.
"""

from __future__ import annotations

from statistics import median

from ..config.valuation import (
    BETA_BOUNDS, BETA_RAW_WEIGHT, CONSENSUS_WEIGHT, CYCLICAL, DEFAULT_BETA,
    FCFF_GROWTH_BOUNDS, FCFF_MARGIN_MIN_YEARS, FCFF_MARGIN_YEARS, FCFF_SCENARIOS,
    FCFF_TERMINAL_CAPEX_TO_DA, FCFF_TERMINAL_GROWTH, FCFF_YEARS, FINANCIAL_SECTORS, MIN_PEERS, PEER_MULTIPLE_BOUNDS, VALUATION_WEIGHTS,
    WACC_BOUNDS,
)
from ..data import intrinsic_value as iv

# §8.8 row labels, in table order. The report prints these; QA matches on them.
METHOD_LABELS = {
    "dcf": "DCF（基準）",
    "fwd_pe": "同業 Forward P/E",
    "ev_ebitda": "同業 EV/EBITDA",
    "ps": "同業 P/S",
    "pb": "同業 P/B",
    "consensus": "分析師共識目標價",
}
PEER_FIELD = {"fwd_pe": "forwardPE", "ev_ebitda": "enterpriseToEbitda",
              "ps": "priceToSalesTrailing12Months", "pb": "priceToBook"}
# Rule 20 of the prompt: (upper MOS bound in %, rating).
RATINGS = ((-25, "賣出"), (-10, "減碼"), (10, "持有"), (25, "買入"))


def _f(v) -> "float | None":
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def _clamp(v: float, bounds: "tuple[float, float]") -> float:
    return max(bounds[0], min(bounds[1], v))


# ── cost of capital ──────────────────────────────────────────────────────────
def adjusted_beta(raw: "float | None") -> "tuple[float, str]":
    """Blume-adjusted beta inside ``BETA_BOUNDS``, and how it was reached."""
    if raw is None:
        return DEFAULT_BETA, "assumed (no beta available)"
    blume = BETA_RAW_WEIGHT * raw + (1 - BETA_RAW_WEIGHT)
    held = _clamp(blume, BETA_BOUNDS)
    note = f"⅔ × raw {raw:.2f} + ⅓"
    if held != blume:
        note += f" = {blume:.2f}, held at the {BETA_BOUNDS[0]:.1f}–{BETA_BOUNDS[1]:.1f} band"
    return held, note


def banded_wacc(raw: "float | None") -> "float | None":
    return None if raw is None else _clamp(raw, WACC_BOUNDS)


# ── company type ─────────────────────────────────────────────────────────────
def archetype(key: str, info: dict, stmt: "dict | None") -> str:
    """Which row of ``VALUATION_WEIGHTS`` applies."""
    if info.get("sector") in FINANCIAL_SECTORS:
        return "financial"
    if (key or "").lower() in CYCLICAL:
        return "cyclical"
    margin = (stmt or {}).get("op_margin_ttm")
    return "profitable" if margin is not None and margin > 0 else "unprofitable"


# ── DCF ──────────────────────────────────────────────────────────────────────
def build_dcf(stmt: "dict | None", wacc: "float | None", tax_rate: float,
              price: "float | None", market_cap: "float | None",
              rate: "float | None", kind: str) -> dict:
    """The FCFF model for §8, or ``{"available": False, "reason": …}``.

    ``rate`` converts statement currency to quote currency (1.0 when they are
    the same, None when they differ and no FX rate was found). Per-share values
    are ``equity × rate × price ÷ market cap``, which needs no share count and
    so is right for an ADR whatever its ratio.
    """
    def unavailable(reason: str) -> dict:
        return {"available": False, "reason": reason}

    s = stmt or {}
    if kind == "financial":
        return unavailable("a lender's cash flows are its funding, not free cash flow; "
                           "valued on earnings and book value instead")
    revenue, margin = s.get("revenue_ttm"), s.get("op_margin_ttm")
    da, capex = s.get("da_ttm"), s.get("capex_ttm")
    if None in (revenue, margin, da, capex) or not revenue:
        missing = [n for n, v in (("revenue", revenue), ("operating margin", margin),
                                  ("D&A", da), ("capex", capex)) if v is None]
        return unavailable("missing TTM input: " + ", ".join(missing or ["revenue"]))
    if margin <= 0:
        return unavailable("TTM operating income is not positive; a loss discounted "
                           "forward is not a value")
    if wacc is None:
        return unavailable("no WACC (cost of capital inputs missing)")
    if not price or not market_cap or not rate:
        return unavailable("no price, market cap or FX rate to express the value per share")

    raw_growth = s.get("revenue_growth_ttm")
    growth_source = "TTM vs prior TTM"
    if raw_growth is None:
        raw_growth, growth_source = s.get("revenue_growth_q"), "latest quarter YoY (no TTM comparison)"
    if raw_growth is None:
        raw_growth, growth_source = FCFF_TERMINAL_GROWTH, "assumed (no growth figure available)"
    start = _clamp(raw_growth, FCFF_GROWTH_BOUNDS)
    da_pct, capex0 = da / revenue, capex / revenue
    capex_end = min(capex0, da_pct * FCFF_TERMINAL_CAPEX_TO_DA)
    capex_path = iv.fade(capex0, capex_end, FCFF_YEARS)
    net_cash = s.get("net_cash") or 0.0
    per_share = rate * price / market_cap
    # Margin: TTM in year 1, fading to the multi-year median, so neither a
    # cycle peak (SNDK) nor a trough (INTC) is capitalised for ever.
    history = [m for m in (s.get("op_margin_history") or []) if m is not None][-(FCFF_MARGIN_YEARS - 1):]
    normal = median(history + [margin]) if len(history) + 1 >= FCFF_MARGIN_MIN_YEARS else None
    end_margin = normal if normal is not None and normal > 0 else margin

    def run(w=None, g=None, start_growth=start, margin_mult=1.0, flat_margin=None):
        path = ([flat_margin] * FCFF_YEARS if flat_margin is not None else
                [min(m * margin_mult, 0.95) for m in iv.fade(margin, end_margin, FCFF_YEARS)])
        return iv.fcff_dcf(revenue, iv.fade(start_growth, FCFF_TERMINAL_GROWTH, FCFF_YEARS),
                           path, tax_rate, da_pct, capex_path,
                           wacc if w is None else w,
                           FCFF_TERMINAL_GROWTH if g is None else g, net_cash)

    base = run()
    if base is None:
        return unavailable("the forecast's last-year free cash flow is not positive "
                           "(capex above operating profit and D&A)")
    if base["equity_value"] <= 0:
        # Net debt above the enterprise value. A negative "fair value" would
        # give a margin of safety over 100% and a Strong Buy on it.
        return unavailable("net debt exceeds the modelled enterprise value, so the "
                           "equity value is not positive")

    grid = iv.fcff_sensitivity(run)
    grid["values"] = [[None if v is None else v * per_share for v in row]
                      for row in grid["values"]]

    scenarios = []
    for name, ((g_mult, m_mult, w_add), prob) in FCFF_SCENARIOS.items():
        sg = _clamp(start * g_mult, (FCFF_GROWTH_BOUNDS[0], FCFF_GROWTH_BOUNDS[1] * 1.5))
        r = run(w=wacc + w_add, start_growth=sg, margin_mult=m_mult)
        scenarios.append({"name": name, "start_growth": sg,
                          "op_margin": min(end_margin * m_mult, 0.95),
                          "wacc": wacc + w_add, "probability": prob,
                          "value": (r["equity_value"] * per_share
                                    if r and r["equity_value"] > 0 else None)})
    weighted = (sum(sc["value"] * sc["probability"] for sc in scenarios)
                if all(sc["value"] is not None for sc in scenarios) else None)

    target = market_cap / rate        # equity value, in statement currency, the price implies
    equity = lambda r: r["equity_value"] if r else None
    implied_growth = iv.solve(lambda x: equity(run(start_growth=x)), target, -0.10, 1.0)
    implied_margin = iv.solve(lambda x: equity(run(flat_margin=x)), target, 0.005, 0.95)

    return {
        "available": True, "model": base, "per_share": per_share, "rate": rate,
        "value": base["equity_value"] * per_share,
        "assumptions": {
            "years": FCFF_YEARS, "start_growth": start, "raw_growth": raw_growth,
            "growth_source": growth_source, "terminal_growth": FCFF_TERMINAL_GROWTH,
            "op_margin": margin, "op_margin_end": end_margin,
            "margin_years": len(history) + 1 if normal is not None else 0,
            "tax_rate": tax_rate, "da_pct": da_pct,
            "capex_start": capex0, "capex_end": capex_end, "wacc": wacc,
            "revenue": revenue, "net_cash": net_cash,
        },
        "sensitivity": grid, "scenarios": scenarios, "scenario_weighted": weighted,
        "implied_growth": implied_growth, "implied_margin": implied_margin,
    }


# ── relative methods ─────────────────────────────────────────────────────────
def peer_median(peers: "list[dict]", method: str) -> "tuple[float | None, list[str]]":
    """Median of the peers' multiple for ``method`` and the tickers behind it.

    Left out: a value outside ``PEER_MULTIPLE_BOUNDS``, and for the multiples
    that divide a market value by a statement figure, a peer quoted in one
    currency and reporting in another (Yahoo divides one by the other).
    """
    field = PEER_FIELD[method]
    lo, hi = PEER_MULTIPLE_BOUNDS[field]
    used = []
    for p in peers or []:
        v = _f(p.get(field))
        mixed = p.get("currency") and p.get("financialCurrency") and p["currency"] != p["financialCurrency"]
        if v is None or not lo <= v <= hi or (mixed and method in ("ev_ebitda", "ps")):
            continue
        used.append((p["ticker"], v))
    if len(used) < MIN_PEERS:
        return None, [t for t, _ in used]
    return median(v for _, v in used), [t for t, _ in used]


def method_values(info: dict, stmt: "dict | None", peers: "list[dict]", dcf: dict,
                  price: "float | None", market_cap: "float | None",
                  rate: "float | None") -> "dict[str, dict]":
    """Per-share value of every method that can be computed, with its basis.

    Each relative method is the **peers' median** multiple applied to the
    company's own figure. None of them reads the company's own current
    multiple, so none can return the price it is being compared with.
    """
    s = stmt or {}
    out: "dict[str, dict]" = {}
    per_share = rate * price / market_cap if rate and price and market_cap else None

    if dcf.get("available"):
        a = dcf["assumptions"]
        out["dcf"] = {"value": dcf["value"],
                      "basis": f"{a['years']}-year FCFF, WACC {a['wacc'] * 100:.2f}%, "
                               f"terminal growth {a['terminal_growth'] * 100:.1f}%"}

    multiple, used = peer_median(peers, "fwd_pe")
    eps = _f(info.get("forwardEps"))
    if multiple and eps and eps > 0:
        out["fwd_pe"] = {"value": multiple * eps,
                         "basis": f"peer median {multiple:.1f}x ({', '.join(used)}) × forward EPS {eps:.2f}"}

    multiple, used = peer_median(peers, "ev_ebitda")
    ebitda = s.get("ebitda_ttm")
    if multiple and ebitda and ebitda > 0 and per_share:
        equity = multiple * ebitda + (s.get("net_cash") or 0.0)
        if equity > 0:
            out["ev_ebitda"] = {"value": equity * per_share,
                                "basis": f"peer median {multiple:.1f}x ({', '.join(used)}) × TTM EBITDA, "
                                         "plus net cash"}

    multiple, used = peer_median(peers, "ps")
    revenue = s.get("revenue_ttm")
    if multiple and revenue and revenue > 0 and per_share:
        out["ps"] = {"value": multiple * revenue * per_share,
                     "basis": f"peer median {multiple:.1f}x ({', '.join(used)}) × TTM revenue"}

    multiple, used = peer_median(peers, "pb")
    book = _f(info.get("bookValue"))
    same_ccy = not (info.get("currency") and info.get("financialCurrency")
                    and info["currency"] != info["financialCurrency"])
    if multiple and book and book > 0 and same_ccy:
        out["pb"] = {"value": multiple * book,
                     "basis": f"peer median {multiple:.1f}x ({', '.join(used)}) × book value per share {book:.2f}"}

    target = _f(info.get("targetMeanPrice"))
    if target and target > 0:
        n = info.get("numberOfAnalystOpinions")
        out["consensus"] = {"value": target,
                            "basis": f"mean target of {n} analysts" if n else "mean analyst target"}
    return out


def _whole_percents(weights: "dict[str, float]") -> "dict[str, int]":
    """Weights as whole percents that sum to exactly 100 (largest remainder)."""
    scaled = {k: w * 100 for k, w in weights.items()}
    out = {k: int(v) for k, v in scaled.items()}
    short = 100 - sum(out.values())
    for k in sorted(scaled, key=lambda k: scaled[k] - out[k], reverse=True)[:short]:
        out[k] += 1
    return out


def weigh(kind: str, values: "dict[str, dict]") -> "list[dict]":
    """The §8.8 rows: each available method with its weight in whole percent.

    The type's base weights are rescaled over the methods that have a value;
    analyst consensus takes ``CONSENSUS_WEIGHT`` of the total and never more.
    Consensus alone is not a valuation, so with no other method there are no
    rows at all.
    """
    base = {k: w for k, w in VALUATION_WEIGHTS[kind].items() if k in values}
    if not base:
        return []
    consensus = CONSENSUS_WEIGHT if "consensus" in values else 0.0
    total = sum(base.values())
    weights = {k: w / total * (1 - consensus) for k, w in base.items()}
    if consensus:
        weights["consensus"] = consensus
    pct = _whole_percents(weights)
    return [{"key": k, "label": METHOD_LABELS[k], "value": round(values[k]["value"], 2),
             "weight_pct": pct[k], "basis": values[k]["basis"]}
            for k in METHOD_LABELS if k in pct]


def rating(mos_pct: "float | None", roic: "float | None", wacc: "float | None") -> "str | None":
    """Prompt rule 20, applied to the Python margin of safety."""
    if mos_pct is None:
        return None
    for upper, label in RATINGS:
        if mos_pct < upper:
            return label
    return "強烈買入" if roic is not None and wacc is not None and roic > wacc else "買入"


# ── assembly ─────────────────────────────────────────────────────────────────
def build(key: str, info: dict, stmt: "dict | None", wacc: "dict | None",
          peers: "list[dict]", price: "float | None", rate: "float | None") -> dict:
    """Everything §7.4 and §8 quote. ``fair_value`` is None when no method
    other than analyst consensus could be computed."""
    market_cap = _f(info.get("marketCap"))
    kind = archetype(key, info, stmt)
    w = wacc or {}
    dcf = build_dcf(stmt, w.get("wacc"), w.get("tax_rate") or 0.0, price, market_cap, rate, kind)
    values = method_values(info, stmt, peers, dcf, price, market_cap, rate)
    rows = weigh(kind, values)
    fair = round(sum(r["value"] * r["weight_pct"] / 100 for r in rows), 2) if rows else None
    # MOS divides by the fair value: only a positive one has a margin of safety.
    measurable = fair is not None and fair > 0 and price is not None and price > 0
    mos = round((fair - price) / fair * 100, 1) if measurable else None
    upside = round((fair - price) / price * 100, 1) if measurable else None
    return {
        "archetype": kind, "dcf": dcf, "methods": rows, "fair_value": fair,
        "mos_pct": mos, "upside_pct": upside,
        "rating": rating(mos, (stmt or {}).get("roic_ttm"), w.get("wacc")),
        "unavailable": [METHOD_LABELS[k] for k in VALUATION_WEIGHTS[kind] if k not in values],
    }


def summary(valuation: "dict | None") -> str:
    """``"dcf 83.99 45%; fwd_pe 316.65 30%"`` for the front matter, where
    stage-1 QA compares it with the report's §8.8 table."""
    rows = (valuation or {}).get("methods") or []
    return "; ".join(f"{r['key']} {r['value']:.2f} {r['weight_pct']}%" for r in rows)


__all__ = ["adjusted_beta", "banded_wacc", "archetype", "build_dcf", "peer_median",
           "method_values", "weigh", "rating", "build", "summary",
           "METHOD_LABELS", "RATINGS"]
