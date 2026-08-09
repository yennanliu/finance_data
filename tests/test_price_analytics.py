"""Tests for the derived price statistics (scripts/analysis/data/price_analytics.py).

Every number the Price Data pages show is computed here rather than in the
browser, precisely so it can be asserted against hand-worked arithmetic. The
cases below are chosen so the expected value is checkable by hand — a regression
in, say, the monthly-return chaining or the drawdown baseline would otherwise
only ever show up as a plausible-looking wrong number on the site.

Fully offline: pure stdlib in, plain data out.
"""

import math

import pytest

from analysis.data import price_analytics as pa

pytestmark = pytest.mark.unit


# ── helpers ──────────────────────────────────────────────────────────────────
def bar(date, close, *, volume=1_000_000):
    """A well-formed bar whose OHLC brackets `close`."""
    return {"date": date, "open": close, "high": close + 1, "low": close - 1,
            "close": close, "volume": volume, "div": None, "split": None}


def ramp(n, start=100.0, step=1.0, year=2026, month=1):
    """`n` consecutive daily bars stepping by `step` (dates need not be sessions)."""
    out = []
    for i in range(n):
        day = i + 1
        m, d = month + (day - 1) // 28, (day - 1) % 28 + 1
        out.append(bar(f"{year}-{m:02d}-{d:02d}", start + i * step))
    return out


# ── period returns ───────────────────────────────────────────────────────────
def test_period_return_counts_bars_not_calendar_days():
    bars = [bar("2026-01-01", 100.0), bar("2026-01-02", 110.0), bar("2026-01-05", 121.0)]
    assert pa.period_return(bars, 1) == pytest.approx(10.0)
    assert pa.period_return(bars, 2) == pytest.approx(21.0)


def test_period_return_is_none_when_history_is_shorter_than_the_window():
    """A 1Y return off nine months of data would understate a young ticker."""
    bars = ramp(10)
    assert pa.period_return(bars, 10) is None   # needs 11 bars for a 10-bar look-back
    assert pa.period_return(bars, 9) is not None


def test_ytd_is_measured_from_the_previous_year_final_close():
    bars = [bar("2025-12-30", 50.0), bar("2025-12-31", 100.0), bar("2026-01-02", 150.0)]
    # Anchored on 2025-12-31, so January's first session is part of the move.
    assert pa.ytd_return(bars) == pytest.approx(50.0)


def test_ytd_is_none_without_a_previous_year():
    assert pa.ytd_return([bar("2026-01-02", 100.0), bar("2026-01-05", 110.0)]) is None


# ── range / risk ─────────────────────────────────────────────────────────────
def test_high_low_uses_intraday_extremes_and_locates_the_close_in_the_band():
    bars = [bar("2026-01-01", 100.0), bar("2026-01-02", 200.0), bar("2026-01-03", 150.0)]
    band = pa.high_low(bars, days=3)
    assert band["high"] == pytest.approx(201.0)   # high = close + 1
    assert band["low"] == pytest.approx(99.0)     # low  = close - 1
    assert band["position"] == pytest.approx((150.0 - 99.0) / (201.0 - 99.0) * 100)
    assert band["from_high"] == pytest.approx((150.0 - 201.0) / 201.0 * 100)


def test_high_low_position_is_none_on_a_flat_band():
    """'We cannot say' is not the same as 'mid-range'."""
    bars = [{"date": "2026-01-01", "open": 10.0, "high": 10.0, "low": 10.0,
             "close": 10.0, "volume": 1, "div": None, "split": None}]
    assert pa.high_low(bars, days=1)["position"] is None


def test_drawdown_is_measured_against_the_running_peak():
    bars = [bar("2026-01-01", 100.0), bar("2026-01-02", 200.0),
            bar("2026-01-03", 150.0), bar("2026-01-04", 250.0)]
    series = pa.drawdown_series(bars)
    assert [p["v"] for p in series] == [0.0, 0.0, -25.0, 0.0]
    worst = pa.max_drawdown(bars)
    assert worst == {"pct": -25.0, "date": "2026-01-03"}


def test_drawdown_never_recovers_above_zero_on_a_falling_series():
    series = pa.drawdown_series(ramp(20, start=200.0, step=-5.0))
    assert all(p["v"] <= 0 for p in series)
    assert series[-1]["v"] < series[0]["v"]


# ── volatility ───────────────────────────────────────────────────────────────
def test_annualised_volatility_matches_the_textbook_formula():
    # Alternating ±10% moves: the daily returns are +11.11…% / -10%.
    closes = [100.0, 110.0, 99.0, 108.9, 98.01]
    bars = [bar(f"2026-01-{i + 1:02d}", c) for i, c in enumerate(closes)]
    rets = pa.daily_returns(bars)
    mean = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))
    assert pa.annualised_volatility(bars) == pytest.approx(sd * math.sqrt(252))


def test_volatility_of_a_constant_series_is_zero():
    bars = [bar(f"2026-01-{i + 1:02d}", 100.0) for i in range(40)]
    assert pa.annualised_volatility(bars) == pytest.approx(0.0)


def test_volatility_series_starts_only_once_the_window_is_full():
    bars = ramp(60)
    series = pa.volatility_series(bars, window=30)
    # 59 returns, 30-wide window → 30 points, the first dated at bar index 30.
    assert len(series) == 30
    assert series[0]["t"] == bars[30]["date"]
    assert series[-1]["t"] == bars[-1]["date"]


def test_volatility_series_is_empty_when_history_is_shorter_than_the_window():
    assert pa.volatility_series(ramp(10), window=30) == []


# ── CAGR ─────────────────────────────────────────────────────────────────────
def test_cagr_of_a_doubling_over_two_years_is_about_41_percent():
    bars = [bar("2024-01-01", 100.0), bar("2026-01-01", 200.0)]
    assert pa.cagr(bars) == pytest.approx(41.4, abs=0.2)


def test_cagr_is_none_on_a_corrupt_date_rather_than_raising():
    """prices.parse doesn't validate dates, and this runs inside the docs build —
    one bad store line must cost a statistic, not the whole site."""
    assert pa.cagr([bar("2026-01-40", 100.0), bar("2026-02-01", 200.0)]) is None


def test_cagr_is_none_for_a_span_too_short_to_annualise():
    """Annualising three months of data invents a trend that isn't there."""
    assert pa.cagr([bar("2026-01-01", 100.0), bar("2026-03-01", 200.0)]) is None


# ── distribution ─────────────────────────────────────────────────────────────
def test_histogram_counts_every_session_including_the_open_ended_tails():
    closes = [100.0, 130.0, 100.0, 100.5, 99.0]  # +30%, -23%, +0.5%, -1.49%
    bars = [bar(f"2026-01-{i + 1:02d}", c) for i, c in enumerate(closes)]
    buckets = pa.return_histogram(bars)
    assert sum(b["count"] for b in buckets) == len(closes) - 1
    assert buckets[-1]["count"] == 1   # the +30% day lands in "> 10%"
    assert buckets[0]["count"] == 1    # the -23% day lands in "< -10%"


def test_histogram_buckets_are_half_open_on_the_left():
    """A return exactly on an edge belongs to the bucket that edge opens."""
    bars = [bar("2026-01-01", 100.0), bar("2026-01-02", 101.0)]  # exactly +1%
    buckets = {b["label"]: b["count"] for b in pa.return_histogram(bars)}
    assert buckets["1 to 2%"] == 1
    assert buckets["0 to 1%"] == 0


# ── monthly returns ──────────────────────────────────────────────────────────
def test_monthly_return_runs_from_the_previous_month_close():
    bars = [bar("2026-01-30", 100.0), bar("2026-01-31", 200.0),
            bar("2026-02-27", 300.0)]
    rows = pa.monthly_returns(bars)
    assert rows[0]["year"] == 2026
    # February is measured off January's *last* close (200), not its first.
    assert rows[0]["months"][2] == pytest.approx(50.0)
    assert 1 not in rows[0]["months"]   # no December to measure January against


def test_year_total_chains_the_months():
    bars = [bar("2025-12-31", 100.0), bar("2026-01-31", 110.0),
            bar("2026-02-28", 121.0)]
    row = pa.monthly_returns(bars)[0]
    assert row["months"] == {1: 10.0, 2: 10.0}
    assert row["year_pct"] == pytest.approx(21.0)


def test_year_total_is_none_when_january_is_missing():
    bars = [bar("2026-02-27", 100.0), bar("2026-03-31", 110.0)]
    assert pa.monthly_returns(bars)[0]["year_pct"] is None


# ── summary ──────────────────────────────────────────────────────────────────
def test_summary_is_none_for_an_empty_store():
    assert pa.summary([]) is None


def test_summary_reports_the_stored_span_and_latest_bar():
    bars = ramp(300)
    s = pa.summary(bars)
    assert s["bars"] == 300
    assert s["first_date"] == bars[0]["date"]
    assert s["last_date"] == bars[-1]["date"]
    assert s["last_close"] == pytest.approx(bars[-1]["close"])
    assert s["all_time_high"] == pytest.approx(bars[-1]["close"] + 1)


def test_summary_survives_a_one_bar_store():
    """A freshly-added ticker must not crash the whole docs build."""
    s = pa.summary([bar("2026-01-02", 42.0)])
    assert s["bars"] == 1
    assert s["returns"]["1y"] is None
    assert s["volatility_1y"] is None
    assert s["cagr"] is None
    assert s["avg_volume_30d"] == 1_000_000
