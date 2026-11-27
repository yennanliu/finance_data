"""Check the price a report was built on against the market record (QA stage 1).

Every report since #84 records the close it was given in its front matter
(``price`` / ``price_date``). Three things can still go wrong, each seen in
``docs/FUNDAMENTAL_REPORT_REVIEW.md`` §12 / ``docs/TECHNICAL_REPORT_REVIEW.md`` §7:

* the report quotes a different price from the one it was given (0050 wrote
  NT$195 for an ETF trading at NT$107) — :func:`quote_mismatch`;
* the pipeline was given the wrong close (a fetch bug) — :func:`store_mismatch`
  compares it with the committed store, ``data/prices/<key>.csv``;
* the store itself stopped updating (SNDK's ended on 2026-11-19 for a week
  while its reports carried newer closes), which leaves the two checks above
  silent because they have no bar to compare with — :func:`store_behind`;
* the close was a session old (79 October technical reports, all committed in
  the 00:00–01:59 UTC window when Yahoo's newest bar is still empty) —
  :func:`stale_sessions`.

The store keeps split-adjusted, *not* dividend-adjusted closes, so an old
report is comparable once later splits are undone. Pure standard library.
"""

from __future__ import annotations

from pathlib import Path

from ..data.prices import load_store, report_key

PRICE_TOLERANCE = 0.005   # relative; prices are quoted to the cent
# Calendar days a report's close may run ahead of the store's newest bar. The
# store updates once a day after report generation, so one session plus a
# weekend (Fri close → Mon report, store still on Thu) is normal.
STORE_LAG_DAYS = 4


def quote_mismatch(stated, price) -> "dict | None":
    """The price a report quotes against the close it was given."""
    if stated is None or not price:
        return None
    diff = stated / price - 1
    if abs(diff) <= PRICE_TOLERANCE:
        return None
    return {"stated": stated, "price": price, "diff_pct": round(diff * 100, 2)}


def recorded_close(bars: list, on: str) -> "float | None":
    """The store's close on ``on``, as it was quoted that day (later splits undone)."""
    for i, bar in enumerate(bars):
        if bar["date"] == on:
            close = bar["close"]
            for later in bars[i + 1:]:
                if later["split"]:
                    close *= later["split"]
            return close
    return None


def store_mismatch(price, price_date: str, bars: list) -> "dict | None":
    """The recorded close against the store. Silent when the store has no bar
    for that date yet (the nightly store update runs after report generation)."""
    close = recorded_close(bars, price_date)
    if close is None or not price or abs(price / close - 1) <= PRICE_TOLERANCE:
        return None
    return {"price": price, "store": round(close, 4),
            "diff_pct": round((price / close - 1) * 100, 2)}


def store_behind(price_date: str, bars: list) -> "dict | None":
    """The store's newest bar when it is more than ``STORE_LAG_DAYS`` older
    than the close a report was given: the store has stopped updating."""
    from datetime import date

    if not bars:
        return None
    last = bars[-1]["date"]
    try:
        lag = (date.fromisoformat(price_date) - date.fromisoformat(last)).days
    except ValueError:
        return None
    if lag <= STORE_LAG_DAYS:
        return None
    return {"price_date": price_date, "store_last": last, "lag_days": lag}


def stale_sessions(price_date: str, report_date: str, bars: list) -> "list[str]":
    """Completed sessions newer than the close used and older than the report.

    The report date is the run's UTC date, so a session dated the same day may
    not have closed yet and is never counted; one dated strictly between the
    two had.
    """
    return [b["date"] for b in bars if price_date < b["date"] < report_date]


def check(fm: dict, ticker: str, report_date: str,
          store_dir: "Path | None" = None) -> dict:
    """Store and freshness checks for one report; empty values mean pass or n/a."""
    out = {"store": None, "stale": [], "behind": None}
    try:
        price = float(fm.get("price") or "")
    except ValueError:
        return out
    price_date = fm.get("price_date", "")
    if len(price_date) != 10:          # "unknown", or no provenance at all
        return out
    bars = load_store(report_key(ticker), store_dir)
    out["store"] = store_mismatch(price, price_date, bars)
    out["behind"] = store_behind(price_date, bars)
    if report_date:
        out["stale"] = stale_sessions(price_date, report_date, bars)
    return out


__all__ = ["PRICE_TOLERANCE", "quote_mismatch", "recorded_close",
           "store_mismatch", "store_behind", "stale_sessions", "check",
           "STORE_LAG_DAYS"]
