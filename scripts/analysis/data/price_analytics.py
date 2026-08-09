"""price_analytics.py — derived statistics over the committed price store
=========================================================================
Everything the Price Data pages show beyond the raw candles is computed here:
period returns, the 52-week band, drawdown, rolling volatility, the daily-return
histogram and the monthly-return grid.

Two rules shape this module:

  * **Pure standard library.** ``build_docs.py`` imports it at module scope and
    must stay offline and dependency-light, exactly like :mod:`prices` — so no
    pandas, no numpy, no statistics tricks that pull anything in.
  * **Bars in, plain data out.** Every function takes the ``list[dict]`` that
    :func:`prices.load_store` returns (oldest→newest) and returns floats, dicts
    or lists of dicts. Nothing here reads a file, so it is trivially testable
    against a hand-written bar list (see ``tests/test_price_analytics.py``).

Returns are computed on the stored close, which is Yahoo's split- and
dividend-adjusted close (see ``docs/PRICE_STORE_DESIGN.md``) — so a "return"
here is a total return, not a price change.
"""

from __future__ import annotations

import math
from datetime import date

# Trading days per period. Approximations on purpose: the store holds sessions,
# not calendar days, so "1 month ago" is "21 bars back" — close enough for a
# summary table and immune to holidays leaving a calendar lookup empty.
TRADING_DAYS = {
    "1d": 1,
    "1w": 5,
    "1m": 21,
    "3m": 63,
    "6m": 126,
    "1y": 252,
    "3y": 756,
    "5y": 1260,
}
TRADING_DAYS_PER_YEAR = 252

# Rolling window for the volatility series. 30 sessions ≈ six weeks: short
# enough to show an earnings shock, long enough not to be pure noise.
VOL_WINDOW = 30

# Daily-return histogram bucket edges, in percent. Deliberately fixed rather
# than derived per ticker so two tickers' histograms can be compared by eye.
HIST_EDGES = (-10.0, -7.0, -5.0, -3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0)


def closes(bars: "list[dict]") -> "list[float]":
    """The close series, oldest→newest."""
    return [float(b["close"]) for b in bars]


def _pct(new: float, old: float) -> "float | None":
    """Percent change old→new; None when the base is unusable."""
    if not old:
        return None
    return (new - old) / old * 100.0


# ── Period returns ───────────────────────────────────────────────────────────
def period_return(bars: "list[dict]", days: int) -> "float | None":
    """Percent return over the last ``days`` *bars*, or None if history is short.

    Requires the full lookback: reporting a "1Y return" off nine months of data
    would silently understate a young ticker's move.
    """
    if days <= 0 or len(bars) <= days:
        return None
    return _pct(float(bars[-1]["close"]), float(bars[-1 - days]["close"]))


def ytd_return(bars: "list[dict]") -> "float | None":
    """Percent return from the last close of the previous year to the latest.

    Anchored on the previous year's final bar rather than the first bar of this
    year, so the first trading day of January is itself part of the YTD move.
    """
    if not bars:
        return None
    year = bars[-1]["date"][:4]
    base = None
    for b in bars:
        if b["date"][:4] >= year:
            break
        base = b
    if base is None:
        return None
    return _pct(float(bars[-1]["close"]), float(base["close"]))


# ── Range / risk ─────────────────────────────────────────────────────────────
def high_low(bars: "list[dict]", days: int = TRADING_DAYS["1y"]) -> "dict | None":
    """Intraday high/low over the last ``days`` bars, plus where the last close
    sits inside that band (0 = at the low, 100 = at the high)."""
    recent = bars[-days:] if days > 0 else bars
    if not recent:
        return None
    hi = max(float(b["high"]) for b in recent)
    lo = min(float(b["low"]) for b in recent)
    last = float(bars[-1]["close"])
    span = hi - lo
    return {
        "high": hi,
        "low": lo,
        # None rather than 50 on a flat band: "we cannot say" is not "mid-range".
        "position": ((last - lo) / span * 100.0) if span > 0 else None,
        "from_high": _pct(last, hi),
    }


def drawdown_series(bars: "list[dict]") -> "list[dict]":
    """Percent below the running peak close, one point per bar (≤ 0)."""
    out: "list[dict]" = []
    peak = 0.0
    for b in bars:
        c = float(b["close"])
        peak = max(peak, c)
        out.append({"t": b["date"], "v": round((c - peak) / peak * 100.0, 2) if peak else 0.0})
    return out


def max_drawdown(bars: "list[dict]") -> "dict | None":
    """Deepest peak-to-trough close decline, with the date it bottomed."""
    series = drawdown_series(bars)
    if not series:
        return None
    worst = min(series, key=lambda p: p["v"])
    return {"pct": worst["v"], "date": worst["t"]}


def daily_returns(bars: "list[dict]") -> "list[float]":
    """Bar-over-bar percent returns (one shorter than ``bars``)."""
    cs = closes(bars)
    out = []
    for prev, cur in zip(cs, cs[1:]):
        r = _pct(cur, prev)
        if r is not None:
            out.append(r)
    return out


def _stdev(xs: "list[float]") -> "float | None":
    """Sample standard deviation; None for fewer than two points."""
    n = len(xs)
    if n < 2:
        return None
    mean = sum(xs) / n
    return math.sqrt(sum((x - mean) ** 2 for x in xs) / (n - 1))


def annualised_volatility(bars: "list[dict]",
                          days: int = TRADING_DAYS["1y"]) -> "float | None":
    """Annualised stdev of daily returns over the last ``days`` bars, in percent."""
    rets = daily_returns(bars[-(days + 1):] if days > 0 else bars)
    sd = _stdev(rets)
    return sd * math.sqrt(TRADING_DAYS_PER_YEAR) if sd is not None else None


def volatility_series(bars: "list[dict]", window: int = VOL_WINDOW) -> "list[dict]":
    """Rolling annualised volatility, one point per bar once the window fills."""
    rets = daily_returns(bars)
    if len(rets) < window:
        return []
    out: "list[dict]" = []
    for i in range(window, len(rets) + 1):
        sd = _stdev(rets[i - window:i])
        if sd is None:
            continue
        # rets[i-1] is the return *into* bars[i], so that bar dates the window.
        out.append({"t": bars[i]["date"],
                    "v": round(sd * math.sqrt(TRADING_DAYS_PER_YEAR), 2)})
    return out


def cagr(bars: "list[dict]") -> "float | None":
    """Compound annual growth rate over the whole stored history, in percent."""
    if len(bars) < 2:
        return None
    first, last = float(bars[0]["close"]), float(bars[-1]["close"])
    if first <= 0 or last <= 0:
        return None
    years = _year_fraction(bars[0]["date"], bars[-1]["date"])
    if years is None or years < 0.5:  # too short to annualise without inventing a trend
        return None
    return ((last / first) ** (1.0 / years) - 1.0) * 100.0


def _year_fraction(start_iso: str, end_iso: str) -> "float | None":
    """Calendar years between two ISO dates (365.25-day years), None if either
    is unparseable.

    ``prices.parse`` does not validate the date field, so a corrupt store line
    reaches us as a plain string — and this runs inside the docs build, where an
    exception would take down every page, not just one statistic.
    """
    try:
        start = date.fromisoformat(start_iso)
        end = date.fromisoformat(end_iso)
    except (TypeError, ValueError):
        return None
    return (end.toordinal() - start.toordinal()) / 365.25


# ── Distribution / seasonality ───────────────────────────────────────────────
def return_histogram(bars: "list[dict]",
                     edges: "tuple[float, ...]" = HIST_EDGES) -> "list[dict]":
    """Bucket daily returns into fixed bins → ``[{label, count, from, to}]``.

    The outer buckets are open-ended (``< -10%``, ``> +10%``) so nothing is
    dropped however violent a single session was.
    """
    rets = daily_returns(bars)
    buckets = [{"label": f"< {edges[0]:g}%", "from": None, "to": edges[0], "count": 0}]
    for lo, hi in zip(edges, edges[1:]):
        buckets.append({"label": f"{lo:g} to {hi:g}%", "from": lo, "to": hi, "count": 0})
    buckets.append({"label": f"> {edges[-1]:g}%", "from": edges[-1], "to": None, "count": 0})

    for r in rets:
        if r < edges[0]:
            buckets[0]["count"] += 1
        elif r >= edges[-1]:
            buckets[-1]["count"] += 1
        else:
            for i, (lo, hi) in enumerate(zip(edges, edges[1:]), start=1):
                if lo <= r < hi:
                    buckets[i]["count"] += 1
                    break
    return buckets


def monthly_returns(bars: "list[dict]") -> "list[dict]":
    """Per-calendar-month returns → ``[{year, months: {1..12: pct}, year_pct}]``.

    A month's return runs from the previous month's last close to its own, so
    the months of a year chain together into the year's return. January of the
    first stored year therefore has no base and is omitted.
    """
    if not bars:
        return []
    # Last close of each month, in order.
    month_close: "dict[str, float]" = {}
    for b in bars:
        month_close[b["date"][:7]] = float(b["close"])
    months = sorted(month_close)

    rows: "dict[int, dict]" = {}
    for prev, cur in zip(months, months[1:]):
        year, month = int(cur[:4]), int(cur[5:7])
        pct = _pct(month_close[cur], month_close[prev])
        if pct is None:
            continue
        rows.setdefault(year, {"year": year, "months": {}, "year_pct": None})
        rows[year]["months"][month] = round(pct, 2)

    # A year's return chains its months; only complete-from-January years get one.
    for row in rows.values():
        if 1 not in row["months"]:
            continue
        growth = 1.0
        for m in sorted(row["months"]):
            growth *= 1.0 + row["months"][m] / 100.0
        row["year_pct"] = round((growth - 1.0) * 100.0, 2)
    return [rows[y] for y in sorted(rows)]


# ── Summary ──────────────────────────────────────────────────────────────────
def summary(bars: "list[dict]") -> "dict | None":
    """Everything the index table and the per-ticker stat block need.

    Returns None for an empty store so callers can skip the ticker outright.
    """
    if not bars:
        return None
    last = bars[-1]
    band = high_low(bars) or {}
    dd = max_drawdown(bars) or {}
    return {
        "last_close": float(last["close"]),
        "last_date": last["date"],
        "first_date": bars[0]["date"],
        "bars": len(bars),
        "returns": {k: period_return(bars, d) for k, d in TRADING_DAYS.items()},
        "ytd": ytd_return(bars),
        "high_52w": band.get("high"),
        "low_52w": band.get("low"),
        "range_position": band.get("position"),
        "from_52w_high": band.get("from_high"),
        "all_time_high": max(float(b["high"]) for b in bars),
        "max_drawdown": dd.get("pct"),
        "max_drawdown_date": dd.get("date"),
        "volatility_1y": annualised_volatility(bars),
        "cagr": cagr(bars),
        "avg_volume_30d": (sum(int(b["volume"]) for b in bars[-30:]) // min(len(bars), 30)),
    }


__all__ = [
    "TRADING_DAYS", "TRADING_DAYS_PER_YEAR", "VOL_WINDOW", "HIST_EDGES",
    "closes", "period_return", "ytd_return", "high_low",
    "drawdown_series", "max_drawdown", "daily_returns",
    "annualised_volatility", "volatility_series", "cagr",
    "return_histogram", "monthly_returns", "summary",
]
