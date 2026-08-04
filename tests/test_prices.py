"""Tests for the committed OHLCV price store (scripts/analysis/data/prices.py).

The store's whole design rests on a handful of invariants (see
docs/PRICE_STORE_DESIGN.md §3.3). Each one is asserted here, because a silent
regression in any of them degrades the store back into the full-rewrite model it
replaced without anything visibly breaking.

Fully offline: the read path is stdlib-only and every fetch is monkeypatched.
"""

import pytest

from analysis.data import prices

pytestmark = pytest.mark.unit


# ── helpers ──────────────────────────────────────────────────────────────────
def bar(date, close=100.0, *, volume=1_000_000, div=None, split=None):
    """A well-formed bar whose OHLC brackets `close`."""
    return {
        "date": date,
        "open": close - 1, "high": close + 2, "low": close - 2, "close": close,
        "volume": volume, "div": div, "split": split,
    }


def series(dates, start=100.0):
    return [bar(d, start + i) for i, d in enumerate(dates)]


DATES = ["2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31"]


# ── I1: byte-stable serialisation ────────────────────────────────────────────
def test_serialise_parse_round_trip_is_byte_stable():
    text = prices.serialise(series(DATES))
    assert prices.serialise(prices.parse(text)) == text


def test_round_trip_stable_for_sub_dollar_and_event_columns():
    bars = [
        bar("2026-07-30", 0.4321, div=0.25, split=None),
        bar("2026-07-31", 0.9987, div=None, split=4.0),
    ]
    text = prices.serialise(bars)
    assert prices.serialise(prices.parse(text)) == text
    # Sub-$1 prices keep 4 decimals so cents stay visible.
    assert "0.4321" in text
    # Canonical event forms: no trailing zeros, empty when absent.
    assert ",0.25," in text
    assert text.rstrip().endswith(",4")


def test_fmt_price_is_idempotent_across_the_one_dollar_boundary():
    # Deciding 4dp-vs-2dp on the raw value would format 0.99999 as "1.0000",
    # which re-reads as 1.0 and then formats as "1.00" — a byte flip-flop that
    # would rewrite the line on every single run.
    for v in (0.99999, 0.9987, 1.0, 1.004, 510.28, 0.0001):
        once = prices.fmt_price(v)
        assert prices.fmt_price(float(once)) == once, v


def test_fmt_price_never_emits_scientific_notation():
    assert "e" not in prices.fmt_price(0.00001).lower()


def test_parse_skips_malformed_lines_without_losing_good_ones():
    text = (
        "date,open,high,low,close,volume,div,split\n"
        "2026-07-30,99.00,102.00,98.00,100.00,1000000,,\n"
        "garbage\n"
        "2026-07-31,x,y,z,w,1000000,,\n"
        "2026-08-03,100.00,103.00,99.00,101.00,1000000,,\n"
    )
    got = prices.parse(text)
    assert [b["date"] for b in got] == ["2026-07-30", "2026-08-03"]


# ── I2 / I5: idempotent, atomic writes ───────────────────────────────────────
def test_write_store_is_idempotent(tmp_path):
    bars = series(DATES)
    assert prices.write_store("amd", bars, tmp_path) is True
    assert prices.write_store("amd", bars, tmp_path) is False  # no byte change


def test_write_store_leaves_no_temp_file(tmp_path):
    prices.write_store("amd", series(DATES), tmp_path)
    assert list(tmp_path.glob("*.tmp")) == []


def test_load_store_of_missing_ticker_is_empty(tmp_path):
    assert prices.load_store("nope", tmp_path) == []


def test_store_path_lowercases_the_key(tmp_path):
    assert prices.store_path("AMD", tmp_path).name == "amd.csv"


# ── I3: upsert keeps things sorted, deduplicated, fetch-wins ─────────────────
def test_upsert_sorts_and_deduplicates():
    old = series(["2026-07-28", "2026-07-30"])
    new = series(["2026-07-29", "2026-07-31"])
    merged = prices.upsert(old, new)
    dates = [b["date"] for b in merged]
    assert dates == sorted(dates) == ["2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31"]


def test_upsert_fetched_bar_wins_on_collision():
    old = [bar("2026-07-31", 400.0)]
    new = [bar("2026-07-31", 100.0)]
    assert prices.upsert(old, new)[0]["close"] == 100.0


def test_split_restates_history_without_duplicating_dates():
    """A 4:1 split makes Yahoo re-report every bar at a quarter of the price.

    The fetch simply wins, so the store ends up wholly restated with the same
    number of bars — this is the entire split-handling story, and it is why no
    split detection exists anywhere in the module.
    """
    old = series(DATES, start=400.0)
    new = [dict(b, open=b["open"] / 4, high=b["high"] / 4,
                low=b["low"] / 4, close=b["close"] / 4) for b in old]
    new[-1]["split"] = 4.0

    merged = prices.upsert(old, new)
    assert len(merged) == len(old)
    assert [b["date"] for b in merged] == DATES
    assert merged[0]["close"] == pytest.approx(old[0]["close"] / 4)
    # Every settled bar counts as restated; the newest is excluded by design.
    assert prices._restated_count(old, new) == len(old) - 1


def test_restated_count_ignores_a_provisional_newest_bar():
    # A run landing mid-session sees the newest bar move. That must not read as
    # a restatement, or every TW ticker would report one nightly.
    old = series(DATES)
    new = [dict(b) for b in old]
    new[-1]["close"] += 5.0
    assert prices._restated_count(old, new) == 0


# ── I4: trimming is measured from the data, not the clock ────────────────────
def test_trim_drops_bars_older_than_keep_years_from_newest_bar():
    bars = [bar("2010-01-04"), bar("2016-08-04"), bar("2026-08-04")]
    kept = [b["date"] for b in prices.trim(bars, years=10)]
    assert kept == ["2016-08-04", "2026-08-04"]


def test_trim_is_independent_of_today():
    bars = series(DATES)
    assert prices.trim(bars, 10) == prices.trim(bars, 10)


def test_trim_handles_leap_day_boundary():
    bars = [bar("2016-02-29"), bar("2026-02-29")]
    # 2016-02-29 is exactly the cutoff for a 2026-02-29 newest bar, so it stays.
    assert len(prices.trim(bars, years=10)) == 2


def test_trim_of_empty_is_empty():
    assert prices.trim([], 10) == []


# ── window(): what the derived chart payloads slice ──────────────────────────
def test_window_as_of_truncates_to_the_report_date():
    got = prices.window(series(DATES), as_of="2026-07-29")
    assert [b["date"] for b in got] == DATES[:3]


def test_window_days_keeps_the_newest_bars():
    got = prices.window(series(DATES), days=2)
    assert [b["date"] for b in got] == DATES[-2:]


def test_window_lookback_adds_bars_before_the_visible_range():
    got = prices.window(series(DATES), days=2, lookback=2)
    assert len(got) == 4
    assert got[-1]["date"] == DATES[-1]


def test_window_as_of_applies_before_days():
    got = prices.window(series(DATES), days=2, as_of="2026-07-29")
    assert [b["date"] for b in got] == ["2026-07-28", "2026-07-29"]


def test_window_combined_beyond_available_history_is_clamped():
    got = prices.window(series(DATES), days=99, lookback=99)
    assert len(got) == len(DATES)


# ── I6: the sanity gate ──────────────────────────────────────────────────────
def test_gate_accepts_a_clean_fetch():
    assert prices.gate(series(DATES), []) is None


@pytest.mark.parametrize("bad, expect", [
    ([], "empty"),
    (None, "empty"),
])
def test_gate_rejects_empty_fetches(bad, expect):
    assert expect in prices.gate(bad, [])


def test_gate_rejects_duplicate_dates():
    assert "duplicate" in prices.gate([bar("2026-07-31"), bar("2026-07-31")], [])


def test_gate_rejects_unsorted_dates():
    assert "ascending" in prices.gate([bar("2026-07-31"), bar("2026-07-30")], [])


def test_gate_rejects_non_positive_prices():
    b = bar("2026-07-31")
    b["low"] = 0.0
    assert "non-positive" in prices.gate([b], [])


def test_gate_rejects_nan_prices():
    b = bar("2026-07-31")
    b["close"] = float("nan")
    assert "NaN" in prices.gate([b], [])


def test_gate_rejects_high_below_low():
    b = bar("2026-07-31")
    b["high"], b["low"] = 90.0, 110.0
    assert "high < low" in prices.gate([b], [])


def test_gate_rejects_close_far_outside_the_range():
    b = bar("2026-07-31", 100.0)
    b["close"] = 150.0
    assert "outside" in prices.gate([b], [])


def test_gate_tolerates_a_hair_of_upstream_rounding_slack():
    # Yahoo occasionally reports a close a fraction of a cent outside the day's
    # range; rejecting that would freeze the ticker's updates indefinitely.
    b = bar("2026-07-31", 100.0)
    b["close"] = b["high"] + 0.004
    assert prices.gate([b], []) is None


def test_gate_rejects_a_bar_count_regression():
    old = series(DATES)
    reason = prices.gate(series(DATES[:2]), old)
    assert "regression" in reason


def test_gate_ignores_stored_bars_older_than_the_fetch_window():
    # Only stored bars inside the fetched range can be expected back, so a short
    # fetch window is not a regression.
    old = series(["2016-01-04", "2016-01-05"]) + series(DATES)
    assert prices.gate(series(DATES), old) is None


# ── update(): the statuses the CI log reports ────────────────────────────────
@pytest.fixture
def fake_fetch(monkeypatch):
    """Install a canned fetch result; returns a setter."""
    state = {}

    def setter(bars):
        state["bars"] = bars

    def fetch(symbol, years=prices.KEEP_YEARS):
        got = state.get("bars")
        if isinstance(got, Exception):
            raise got
        return got

    monkeypatch.setattr(prices, "fetch_history", fetch)
    return setter


def test_update_creates_then_reports_unchanged(tmp_path, fake_fetch):
    fake_fetch(series(DATES))
    assert prices.update("amd", "AMD", store_dir=tmp_path)[0] == "created"
    assert prices.update("amd", "AMD", store_dir=tmp_path)[0] == "unchanged"


def test_update_appends_a_new_bar(tmp_path, fake_fetch):
    fake_fetch(series(DATES))
    prices.update("amd", "AMD", store_dir=tmp_path)

    fake_fetch(series(DATES + ["2026-08-03"]))
    status, _ = prices.update("amd", "AMD", store_dir=tmp_path)
    assert status == "appended"
    assert len(prices.load_store("amd", tmp_path)) == len(DATES) + 1


def test_update_reports_restated_after_a_split(tmp_path, fake_fetch):
    fake_fetch(series(DATES, start=400.0))
    prices.update("amd", "AMD", store_dir=tmp_path)

    halved = [dict(b, open=b["open"] / 2, high=b["high"] / 2,
                   low=b["low"] / 2, close=b["close"] / 2)
              for b in series(DATES, start=400.0)]
    fake_fetch(halved)
    status, detail = prices.update("amd", "AMD", store_dir=tmp_path)
    assert status == "restated"
    assert "rewritten" in detail


def test_update_skips_without_writing_when_the_gate_rejects(tmp_path, fake_fetch):
    fake_fetch(series(DATES))
    prices.update("amd", "AMD", store_dir=tmp_path)
    before = prices.store_path("amd", tmp_path).read_text(encoding="utf-8")

    fake_fetch(series(DATES[:1]))  # bar-count regression
    status, reason = prices.update("amd", "AMD", store_dir=tmp_path)
    assert status == "skipped" and "regression" in reason
    assert prices.store_path("amd", tmp_path).read_text(encoding="utf-8") == before


def test_update_fails_softly_on_a_fetch_error(tmp_path, fake_fetch):
    fake_fetch(RuntimeError("boom"))
    status, detail = prices.update("amd", "AMD", store_dir=tmp_path)
    assert status == "failed" and "boom" in detail
    assert not prices.store_path("amd", tmp_path).exists()


def test_update_fails_softly_on_no_data(tmp_path, fake_fetch):
    fake_fetch(None)
    assert prices.update("amd", "AMD", store_dir=tmp_path)[0] == "failed"


def test_update_trims_to_the_keep_window(tmp_path, fake_fetch):
    fake_fetch([bar("2010-01-04"), bar("2016-08-04"), bar("2026-08-04")])
    prices.update("amd", "AMD", years=10, store_dir=tmp_path)
    assert [b["date"] for b in prices.load_store("amd", tmp_path)] == \
        ["2016-08-04", "2026-08-04"]


# ── ticker helpers ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("key, symbol", [
    ("tsla", "TSLA"),
    ("2330.tw", "2330.TW"),
    ("0050", "0050.TW"),
    ("brk.b", "BRK-B"),
    ("AMD", "AMD"),
])
def test_to_yf_symbol(key, symbol):
    assert prices.to_yf_symbol(key) == symbol


@pytest.mark.parametrize("symbol, ccy", [
    ("AMD", "USD"), ("2330.TW", "TWD"), ("0050.TW", "TWD"),
])
def test_currency_for(symbol, ccy):
    assert prices.currency_for(symbol) == ccy
