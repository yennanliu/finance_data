"""Technical-report data integrity: bars, indicators, the run guard, the
front matter, the QA checks and the stale-report notice.

Background: docs/TECHNICAL_REPORT_REVIEW.md — eight 2026-10-23 reports were
written on a ``$nan`` close from an empty last bar, 0050 was modelled from an
empty history all October, and "RSI(14)" was Cutler's, not Wilder's.
"""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

import build_docs as bd
from analysis import pipeline
from analysis.data.sources import complete_bars
from analysis.data.technicals import (compute_technicals, key_levels, levels_summary,
                                      weekly_bars)
from analysis.exceptions import DataFetchError
from analysis.prompts import load_prompt
from analysis.validate import parse_file
from analysis.validate import technical as tq

NY = ZoneInfo("America/New_York")


def bars(n=260, start="2025-10-01", tz="America/New_York"):
    """Business-day OHLCV with swings, so pivots and both RSI legs exist."""
    idx = pd.date_range(start, periods=n, freq="B", tz=tz)
    i = np.arange(n)
    close = 100 + 0.1 * i + 8 * np.sin(i / 6)
    return pd.DataFrame({"Open": close - 0.3, "High": close + 1.5, "Low": close - 1.5,
                         "Close": close, "Volume": 1_000_000.0 + i}, index=idx)


def with_empty_last_bar(h):
    """What Yahoo serves for a while after the close: volume, NaN prices."""
    nxt = h.index[-1] + pd.offsets.BDay(1)
    row = pd.DataFrame({"Open": [np.nan], "High": [np.nan], "Low": [np.nan],
                        "Close": [np.nan], "Volume": [48_658_900.0]}, index=[nxt])
    return pd.concat([h, row])


def quote(price, day, hour=16, minute=0):
    stamp = datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}").replace(tzinfo=NY)
    return {"regularMarketPrice": price, "regularMarketTime": int(stamp.timestamp()),
            "exchangeTimezoneName": "America/New_York", "regularMarketOpen": 258.18,
            "regularMarketDayHigh": 258.41, "regularMarketDayLow": 249.80}


# ── complete_bars ────────────────────────────────────────────────────────────

def test_empty_last_bar_is_dropped_without_a_quote():
    h = bars()
    out, source = complete_bars(with_empty_last_bar(h), {}, now=datetime(2027, 1, 1, tzinfo=NY))
    assert source == "daily_bar"
    assert out.index[-1] == h.index[-1] and out["Close"].notna().all()


def test_empty_last_bar_is_replaced_by_the_official_close():
    h = with_empty_last_bar(bars())
    day = str(h.index[-1])[:10]
    out, source = complete_bars(h, quote(250.38, day, 16, 1), now=datetime(2027, 1, 1, tzinfo=NY))
    assert source == "quote"
    last = out.iloc[-1]
    assert str(out.index[-1])[:10] == day
    assert (last["Close"], last["Open"], last["High"], last["Low"]) == (250.38, 258.18, 258.41, 249.80)
    # No volume in the quote: the empty bar's own volume is kept.
    assert last["Volume"] == 48_658_900.0


def test_intraday_quote_and_open_session_bar_are_ignored():
    h = bars()
    day = str(h.index[-1])[:10]
    now = datetime.fromisoformat(f"{day}T11:00").replace(tzinfo=NY)
    out, source = complete_bars(h, quote(1.0, day, 11, 0), now=now)
    # The bar dated today before 16:00 is a session in progress.
    assert source == "daily_bar" and out.index[-1] == h.index[-2]


def test_no_bars_left():
    h = bars(5)
    h["Close"] = np.nan
    out, source = complete_bars(h, {})
    assert source is None and out.empty
    assert complete_bars(None, {}) == (None, None)


# ── indicators ───────────────────────────────────────────────────────────────

def test_empty_last_bar_no_longer_blanks_the_context():
    out = compute_technicals(with_empty_last_bar(bars()))
    assert "nan" not in out.lower().replace("nan%", "")
    assert "$N/A" not in out
    assert "R1:" in out or "S1:" in out


def test_rsi_and_atr_use_wilder_smoothing():
    h = bars()
    delta = h["Close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    wilder = 100 - 100 / (1 + gain.iloc[-1] / loss.iloc[-1])
    assert f"RSI(14):      {wilder:.2f}  (Wilder)" in compute_technicals(h)


def test_weeks_are_labelled_by_their_last_trading_day():
    h = bars(12, start="2026-10-05")          # Mon 10-05 … Tue 10-20
    weekly = weekly_bars(h)
    labels = [str(i)[:10] for i in weekly.index]
    assert labels == ["2026-10-09", "2026-10-16", "2026-10-20"]   # never a Sunday
    assert weekly["High"].iloc[0] == h["High"].iloc[:5].max()
    out = compute_technicals(bars())
    assert "2026-10-25" not in out


def test_context_carries_daily_and_weekly_ohlc():
    out = compute_technicals(bars())
    assert "近10根日K (開高低收)" in out and "近8根週K" in out
    daily = out.split("近10根日K")[1].split("近8根週K")[0]
    assert len([ln for ln in daily.splitlines() if ln.strip()[:4].isdigit()]) == 10


def test_levels_summary_matches_the_context_block():
    h = bars()
    lv = key_levels(h)
    summary = levels_summary(lv)
    assert summary.startswith("R1 ") or summary.startswith("S1 ")
    for label, value in tq.parse_levels(summary).items():
        assert f"{label}:  ${value:8.2f}" in compute_technicals(h)
    assert key_levels(None) == {} and levels_summary({}) == ""


# ── run guard and front matter ───────────────────────────────────────────────

@pytest.mark.parametrize("data", [
    {"hist": None, "price_now": None},
    {"hist": pd.DataFrame(), "price_now": 108.15},
    {"hist": bars(), "price_now": None},
])
def test_technical_run_refuses_without_history_or_price(monkeypatch, tmp_path, data):
    called = []
    monkeypatch.setattr(pipeline, "fetch_data", lambda ticker: data)
    monkeypatch.setattr(pipeline, "call_llm", lambda *a, **k: called.append(1) or "# r")
    with pytest.raises(DataFetchError):
        pipeline.run_analysis("0050", "technical-analysis", "gemini", "g", 32000, tmp_path)
    assert not called and not list(tmp_path.iterdir())


def test_technical_front_matter_records_price_source_and_levels(monkeypatch, tmp_path):
    h = bars()
    monkeypatch.setattr(pipeline, "fetch_data", lambda ticker: {
        "hist": h, "price_now": float(h["Close"].iloc[-1]), "price_date": "2026-10-22",
        "close_source": "quote", "source_status": {"yfinance_prices": True}})
    monkeypatch.setattr(pipeline, "build_context", lambda data, atype: "CONTEXT")
    monkeypatch.setattr(pipeline, "call_llm", lambda *a, **k: "# AMZN\nbody")
    text = pipeline.run_analysis("AMZN", "technical-analysis", "gemini", "g", 32000,
                                 tmp_path).read_text(encoding="utf-8")
    fm = tq.front_matter(text)
    assert fm["price_date"] == "2026-10-22" and fm["close_source"] == "quote"
    assert tq.parse_levels(fm["levels"]) == tq.parse_levels(levels_summary(key_levels(h)))


# ── QA stage-1 checks ────────────────────────────────────────────────────────

REPORT = """---
ticker: TSM
analysis_type: technical-analysis
price: 412.35
levels: "R1 434.74; R2 450.61; S1 402.11"
---

# TSM 技術分析報告

> **報告日期**：2026-10-23 ｜ **當前價格**：${headline}

## 4. 支撐與阻力

| 阻力級別 | 價位 | 形成原因 |
|----------|------|----------|
| **阻力 R1** | **${r1}** | 波段高點 |
| **阻力 R2** | **$450.61** | 波段高點 |
| **支撐 S3** | **$375.75** | 自行推算（未計算的標籤不比對） |

## 8. 交易策略建議

| 觸發條件 | 下一目標 | 止損 |
|----------|----------|------|
| **跌破 S1 止損** | $380.00 | $399.00 |

| 策略要素 | 策略 A | 策略 B |
|----------|--------|--------|
| **進場價格** | **$435.50** | **$413.00** |
| **目標價 T1** | **$450.61** | **$434.74** |
| **目標價 T2** | **$487.47** | **$450.61** |
| **止損價格** | **$424.00** | **$399.00** |
| **風險報酬比** | **1 : {rr}** | **1 : 1.55（以 T1 計）** |

## 9. 風險提示與監控

{tail}
"""


def report(headline="412.35", r1="434.74", rr="1.31（以 T1 計）", tail="結束。"):
    return REPORT.format(headline=headline, r1=r1, rr=rr, tail=tail)


def test_clean_report_passes():
    assert tq.check(report()) == {"nan": [], "price": None, "levels": [], "rr": []}


def test_rr_to_t2_is_accepted_but_wrong_arithmetic_is_not():
    assert tq.rr_mismatches(report(rr="4.52（以 T2 計）")) == []
    # TSM 2026-10-23: 1 : 3.48 beside its own risk $11.5 / reward $51.97.
    assert tq.rr_mismatches(report(rr="3.48")) == [
        {"column": 1, "stated": 3.48, "recomputed": [1.31, 4.52]}]


def test_rr_written_reward_first():
    assert tq._ratio("**2.81 : 1** 🟢") == 2.81 and tq._ratio("1:3.48") == 3.48


def test_headline_price_and_levels_are_compared_with_the_front_matter():
    out = tq.check(report(headline="431.89", r1="435.10"))
    assert out["price"] == {"stated": 431.89, "price": 412.35, "diff_pct": 4.74}
    assert out["levels"] == [{"label": "R1", "stated": 435.10, "computed": 434.74}]


def test_nan_values_are_flagged():
    text = report(tail="RSI(14) | 33.0 (前週) / nan (當週)\n收盤價 $nan，ATR nan%")
    assert len(tq.check(text)["nan"]) == 3
    assert tq.nan_values("Fernando nano") == []


def test_parse_file_reports_each_technical_issue(tmp_path):
    f = tmp_path / "tsm" / "technical_analysis_2026-10-23_gemini.md"
    f.parent.mkdir()
    f.write_text(report(headline="431.89", r1="435.10", rr="3.48", tail="收盤價 $nan") + "\n" * 90,
                 encoding="utf-8")
    issues = parse_file(f).issues
    for code in ("NAN_VALUE", "PRICE_MISMATCH", "LEVEL_MISMATCH", "RR_MISMATCH"):
        assert code in issues


def test_reports_without_recorded_price_or_levels_skip_those_checks():
    text = report(headline="431.89", r1="435.10").replace("price: 412.35\n", "").replace(
        'levels: "R1 434.74; R2 450.61; S1 402.11"\n', "")
    out = tq.check(text)
    assert out["price"] is None and out["levels"] == []


# ── prompt ───────────────────────────────────────────────────────────────────

def test_prompt_defines_na_rr_composite_and_candles():
    p = load_prompt("technical")
    assert "16. **數據缺漏（N/A）規則**" in p and "不得自行估算" in p
    assert "(目標價 T1 − 進場價) ÷ (進場價 − 止損價)" in p
    assert "六項子評分" in p and "算術平均" in p
    assert "近10根日K" in p and "近8根週K" in p
    assert "500–700 行" in p and "300–500" not in p
    assert "| 月份 | 收盤價 | K線形態 |" not in p


# ── stale-report notice ──────────────────────────────────────────────────────

def test_dropped_ticker_says_no_longer_updated(monkeypatch):
    monkeypatch.setattr(bd, "TODAY_DATE", datetime(2026, 10, 23).date())
    f = Path("technical_analysis_2026-07-18_gemini.md")
    note = bd.stale_notice("mrvl", f, "en")
    assert "No longer updated" in note and "97 days ago" in note
    assert "已停止更新" in bd.stale_notice("mrvl", f, "zh")


def test_scheduled_ticker_gets_the_age_only(monkeypatch):
    monkeypatch.setattr(bd, "TODAY_DATE", datetime(2026, 10, 23).date())
    note = bd.stale_notice("amd", Path("technical_analysis_2026-10-01_gemini.md"), "en")
    assert "No longer updated" not in note and "22 days ago" in note


def test_recent_or_non_daily_reports_get_no_notice(monkeypatch):
    monkeypatch.setattr(bd, "TODAY_DATE", datetime(2026, 10, 23).date())
    assert bd.stale_notice("mrvl", Path("technical_analysis_2026-10-20_gemini.md"), "en") == ""
    assert bd.stale_notice("mrvl", Path("stock_eval_2026-01-01_gemini.md"), "en") == ""


def test_notice_only_on_the_newest_report(monkeypatch):
    monkeypatch.setattr(bd, "TODAY_DATE", datetime(2026, 10, 23).date())
    f = Path("technical_analysis_2026-07-18_gemini.md")
    newer = Path("technical_analysis_2026-07-19_gemini.md")
    meta = bd.get_meta("mrvl")
    assert "rmeta__stale" in bd.report_meta_block("mrvl", meta, f, {}, "en")
    assert "rmeta__stale" not in bd.report_meta_block("mrvl", meta, f, {}, "en", nxt=newer)


def test_rsi_warm_up_is_printed_as_na_not_nan():
    out = compute_technicals(bars(30))            # a recent listing: 6 weeks
    assert "nan" not in out.lower().replace("nan%", "") and "N/A" in out
