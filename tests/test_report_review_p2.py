"""P2 of the 2026-11-14 report review (docs/REPORT_REVIEW.md F8–F10, T3, T5–T8).

A machine-readable verdict in the front matter and a 資料與來源 block written
by the pipeline; one scorecard whose composite Python computes; quality
figures (F-Score, DuPont, working-capital days, lender metrics) and technical
studies (wider level lookback, pivots, Ichimoku, volume profile, anchored
VWAP, A/D, base rates) computed instead of estimated.
"""

import numpy as np
import pandas as pd
import pytest

from analysis import pipeline
from analysis.context import quality
from analysis.data import technical_studies as ts
from analysis.data.technicals import (bars_frame, compute_technicals, key_levels,
                                      levels_summary, pivot_points)
from analysis.prompts import load_prompt
from analysis.validate import content_findings, scorecard as sc
from analysis.validate import technical as tq


def bars(n=260, start="2025-10-01", base=100.0, slope=0.1, amp=8.0):
    idx = pd.date_range(start, periods=n, freq="B")
    i = np.arange(n)
    close = base + slope * i + amp * np.sin(i / 6)
    return pd.DataFrame({"Open": close - 0.3, "High": close + 1.5, "Low": close - 1.5,
                         "Close": close, "Volume": 1_000_000.0 + i}, index=idx)


def store_rows(frame):
    return [{"date": str(ts_)[:10], "open": r.Open, "high": r.High, "low": r.Low,
             "close": r.Close, "volume": int(r.Volume)} for ts_, r in frame.iterrows()]


# ── T5: levels when the price is at a low ────────────────────────────────────

def falling_year_after_a_range():
    """Four years in a 60–80 range, then a year sliding from 140 to a new low at 90."""
    old = bars(1000, "2021-01-01", base=70, slope=0.0, amp=10)
    i = np.arange(260)
    close = 140 - 50 * i / 259
    recent = pd.DataFrame({"Open": close + 0.2, "High": close + 1.0, "Low": close - 1.0,
                           "Close": close, "Volume": 1e6},
                          index=pd.date_range(old.index[-1] + pd.offsets.BDay(1), periods=260, freq="B"))
    return recent, pd.concat([old, recent])


def test_no_support_in_the_last_year_widens_the_lookback():
    recent, full = falling_year_after_a_range()
    alone = key_levels(recent)
    assert alone["support"] == []                       # the review's NVDA case
    wide = key_levels(recent, bars_frame(store_rows(full)))
    assert len(wide["support"]) >= 2 and all(s < wide["last"] for s in wide["support"])
    assert wide["support"] == sorted(wide["support"], reverse=True)      # nearest first
    assert wide["lookback"]["support"] == 504             # two years were enough; five were not read
    assert "S1 " in levels_summary(wide)


def test_a_side_with_enough_levels_keeps_its_one_year_lookback():
    h = bars()
    lv = key_levels(h, bars_frame(store_rows(pd.concat([bars(900, "2021-01-01", base=20), h]))))
    assert lv["lookback"]["support"] == 252 and lv["support"] == key_levels(h)["support"]


def test_widening_stops_at_the_bars_that_exist():
    recent, _ = falling_year_after_a_range()
    lv = key_levels(recent)
    assert lv["lookback"]["support"] == len(recent)      # 260 bars, not "two years"
    assert f"近 {len(recent)} 個交易日" in compute_technicals(recent)


def test_pivot_points_use_the_last_completed_month():
    h = bars(60, "2026-09-01")
    pv = pivot_points(h)
    month = h[h.index.to_period("M") == h.index[-1].to_period("M") - 1]
    hi, lo, c = month["High"].max(), month["Low"].min(), month["Close"].iloc[-1]
    p = (hi + lo + c) / 3
    assert pv["P"] == pytest.approx(p) and pv["PR1"] == pytest.approx(2 * p - lo)
    assert pv["PS2"] == pytest.approx(p - (hi - lo))
    assert pivot_points(h.tail(5)) is None or pivot_points(h.tail(5))["period_end"] < str(h.index[-1])[:10]


def test_pivot_points_use_the_month_that_just_closed_on_its_last_session():
    """On a month's last session that month is complete: its bar, not the one
    before it, is what the coming month's pivots are built from."""
    h = bars(80, "2026-08-03")
    h = h[h.index <= "2026-10-30"]                       # Friday, October's last weekday
    month = h[h.index.to_period("M") == pd.Period("2026-10")]
    pv = pivot_points(h)
    assert pv["period_end"] == "2026-10-30" and pv["high"] == pytest.approx(month["High"].max())
    day_before = pivot_points(h.iloc[:-1])               # Thursday: October still in progress
    assert day_before["period_end"] == "2026-09-30"
    assert pivot_points(h.tz_localize("America/New_York"))["period_end"] == "2026-10-30"


def test_pivot_labels_are_not_read_as_swing_levels():
    """A report that lists 樞軸 PS1 in chapter 4 must not trip LEVEL_MISMATCH."""
    assert tq.LABEL_RE.search("樞軸 PS1") is None and tq.LABEL_RE.search("S1 近期支撐")


# ── T7: studies ──────────────────────────────────────────────────────────────

def test_ichimoku_reads_the_cloud_at_the_last_bar():
    h = bars(200, slope=0.5, amp=0.0)                    # a steady climb
    ich = ts.ichimoku(h)
    high, low = h["High"], h["Low"]
    assert ich["tenkan"] == pytest.approx((high.tail(9).max() + low.tail(9).min()) / 2)
    assert ich["position"] == "雲層上方" and ich["span_a"] < ich["lead_a"]
    assert ts.ichimoku(h.tail(77)) is None               # needs 52 + 26 bars


def test_volume_profile_finds_the_busiest_price():
    h = bars(120, slope=0.0, amp=10)
    h.loc[(h["Close"] > 104) & (h["Close"] < 106), "Volume"] = 5e7
    vp = ts.volume_profile(h)
    assert 103 < vp["poc"] < 107 and vp["val"] <= vp["poc"] <= vp["vah"]
    assert vp["share"] >= ts.VALUE_AREA
    flat = h.assign(High=100.0, Low=100.0, Close=100.0)
    assert ts.volume_profile(flat) is None                # no range, no profile


def test_anchored_vwap_and_ad_line():
    h = bars(60, slope=0.0, amp=0.0)                     # every bar the same
    assert ts.anchored_vwap(h, h.index[10]) == pytest.approx(100.0)
    assert {a["name"] for a in ts.vwap_anchors(h)} == {"52 週高點", "52 週低點"}
    up = bars(60, slope=1.0, amp=0.0).assign(High=lambda d: d["Close"], Low=lambda d: d["Close"] - 2)
    ad = ts.accumulation_distribution(up)                # closes on the high: accumulation
    assert ad["ad_up"] and ad["price_up"] and "確認" in ad["relation"]
    assert ts.accumulation_distribution(h.tail(10)) is None


def test_studies_block_reports_short_history_as_na():
    out = ts.studies_block(bars(30))
    assert "一目均衡表: N/A" in out and "成交量分布" in out


# ── T3: base rates ───────────────────────────────────────────────────────────

def test_base_rates_measure_what_followed_the_same_state():
    close = bars(900, slope=0.2, amp=0.0)["Close"]       # rises every session
    br = ts.base_rates(close)
    assert "MA200 上方" in br["state"] and br["sessions"] == 900
    for row in br["rows"]:
        assert row["same"]["up"] == 1.0 and row["all"]["up"] == 1.0
        assert row["same"]["p25"] <= row["same"]["median"] <= row["same"]["p75"]
        assert row["episodes"] == 1                       # one unbroken run, however many days
    assert ts.base_rates(close.tail(200)) is None        # no 200-day average yet


def test_a_rare_state_has_no_rate():
    i = np.arange(600)
    close = pd.Series(100 + 0.2 * i, index=pd.date_range("2024-01-01", periods=600, freq="B"))
    close.iloc[-12:] = close.iloc[-13] - 2.5 * np.arange(1, 13)     # a sudden slide: RSI < 30
    br = ts.base_rates(close)
    assert "RSI(14) < 30" in br["state"]
    assert all(row["same"] is None for row in br["rows"])
    block = ts.base_rate_block(pd.DataFrame({"Close": close}))
    assert f"少於 {ts.BASE_RATE_MIN_SAMPLES} 個" in block and "不是預測" in block


def test_context_carries_the_new_blocks():
    out = compute_technicals(bars())
    for title in ("進階指標", "歷史基準機率", "經典樞軸點"):
        assert title in out
    assert "technical indicator error" not in out


# ── scorecard ────────────────────────────────────────────────────────────────

FUND = """# X 基本面深度分析報告
## 1. 執行摘要
| 項目 | 內容 |
|---|---|
| **估值** | Forward P/E 30x |
| **綜合評分** | 7.5/10（引用 1.1） |
| **評級 + 信心度** | 🟢 買入 ｜ 信心：中 |
### 1.1 綜合評分卡
| 維度 | 評分（1–10） | 主要依據 |
|---|---|---|
| 成長性 | 9 | TTM 營收成長 7.5% |
| 獲利能力 | **8** | b |
| 財務健康 | 7/10 | c |
| 估值 | 4 | d |
| 護城河 | 8 | e |
| 管理層與資本配置 | 7 | f |
| **綜合評分** | **7.5** | 六項平均 |
## 2. 公司概覽
綜合評分 7.5/10，營收成長 7.5%。
"""

TECH_CARD = """## 1. 技術面概覽
| 維度 | 評分（0–100） | 訊號 | 依據 |
|---|---|---|---|
| 趨勢強度 | 30 | 🔴 | a |
| 動能指標 | 25 | 🔴 | b |
| 支撐穩定度 | 40 | 🟡 | c |
| 成交量配合 | 55 | 🟡 | d |
| 形態完整度 | 35 | 🔴 | e |
| 均線排列 | 20 | 🔴 | f |
| **綜合評分** | **40** | 偏空 | 六項平均 |
## 8. 交易策略建議
當前主策略方向 = 偏空（依評分 40/100），日線 RSI 40。
"""


def test_composite_is_the_mean_of_the_sub_scores_and_is_written_back():
    text, card = sc.fix(FUND, sc.FUNDAMENTAL)
    assert card["total"] == 7.2 and card["stated"] == 7.5 and card["corrected"]
    assert "| **綜合評分** | **7.2** |" in text and "| **綜合評分** | 7.2/10（引用 1.1） |" in text
    assert "綜合評分 7.2/10，營收成長 7.5%。" in text      # the other 7.5 on that line is not a score
    assert "TTM 營收成長 7.5%" in text
    assert sc.fix(text, sc.FUNDAMENTAL)[1]["corrected"] is False


def test_technical_composite_and_signal():
    text, card = sc.fix(TECH_CARD, sc.TECHNICAL)
    assert card["total"] == 34 and isinstance(card["total"], int)
    assert "| **綜合評分** | **34** |" in text and "依評分 34/100），日線 RSI 40" in text
    assert [sc.signal(v) for v in (34, 40, 41, 59, 60, None)] == [
        "bearish", "bearish", "neutral", "neutral", "bullish", None]


def test_a_half_rounds_up():
    card = TECH_CARD.replace("| 均線排列 | 20 |", "| 均線排列 | 22 |")     # mean 34.5
    assert sc.read(card, sc.TECHNICAL)["total"] == 35


def test_an_incomplete_scorecard_has_no_composite():
    text, card = sc.fix(FUND.replace("| 估值 | 4 | d |\n", ""), sc.FUNDAMENTAL)
    assert card["total"] is None and text.count("7.5") == FUND.count("7.5")
    assert pipeline.score_fields(card) == {}


def test_the_old_ascii_scorecard_is_still_read():
    old = "## 1. 技術面概覽\n```\n" + "\n".join(
        f"{label}      ████  {v}/100  🔴" for label, v in zip(sc.TECHNICAL["labels"], (30, 25, 40, 55, 35, 20))
    ) + "\n綜合評分      ████  34/100  偏空\n```\n"
    assert sc.read(old, sc.TECHNICAL) == {
        "scores": dict(zip(sc.TECHNICAL["labels"], (30.0, 25.0, 40.0, 55.0, 35.0, 20.0))),
        "stated": 34.0, "total": 34}


def test_stated_rating_and_its_distance_from_the_computed_one():
    assert sc.stated_rating(FUND) == "買入"
    adjusted = FUND.replace("🟢 買入 ｜ 信心：中", "依 MOS 應為 買入，調整為 持有，因為估值偏高")
    assert sc.stated_rating(adjusted) == "持有"
    template = FUND.replace("🟢 買入 ｜ 信心：中", "強烈買入/買入/持有/減碼/賣出")
    assert sc.stated_rating(template) is None            # the template's own list is not a rating
    assert sc.rating_gap("強烈買入", "持有") == 2 and sc.rating_gap("賣出", "減碼") == -1
    assert sc.rating_gap("買入", None) is None


def test_qa_flags_a_rating_two_notches_from_the_computed_one():
    def codes(computed):
        fm = f"---\nrating_computed: {computed}\n---\n"
        return [c for c, _ in content_findings("fundamental_analysis", fm + FUND, FUND, "X", "2026-11-14")]
    assert "RATING_GAP" in codes("減碼") and "RATING_GAP" not in codes("持有")


# ── F10 / T8: front matter and the sources block ─────────────────────────────

def test_verdict_prefers_the_reports_rating_and_rechecked_fair_value():
    _, card = sc.fix(FUND, sc.FUNDAMENTAL)
    facts = {"valuation": {"rating": "持有", "fair_value": 120.0}}
    ok = pipeline.verdict(FUND, card, facts, {"arithmetic_check": "ok",
                                              "weighted_fair_value_recomputed": 118.5})
    assert ok == {"score": 7.2, "score_stated": 7.5, "rating": "買入", "fair_value": 118.5}
    bad = pipeline.verdict("## 1. 執行摘要\n", {"total": None}, facts, {"arithmetic_check": "mismatch",
                                                                      "weighted_fair_value_recomputed": 99.0})
    assert bad == {"rating": "持有", "fair_value": 120.0}


def test_technical_front_matter_carries_score_and_signal(monkeypatch, tmp_path):
    h = bars().tz_localize("America/New_York")
    monkeypatch.setattr(pipeline, "fetch_data", lambda ticker: {
        "hist": h, "price_now": float(h["Close"].iloc[-1]), "price_date": "2026-09-29",
        "close_source": "daily_bar", "info": {"currency": "USD"}, "earnings_date": "2026-11-20",
        "source_status": {"yfinance_prices": True, "finviz": False}})
    monkeypatch.setattr(pipeline, "long_history", lambda key: None)
    monkeypatch.setattr(pipeline, "build_context", lambda data, atype: "CONTEXT")
    monkeypatch.setattr(pipeline, "call_llm", lambda *a, **k: "# AMZN\n" + TECH_CARD)
    text = pipeline.run_analysis("AMZN", "technical-analysis", "gemini", "g", 32000,
                                 tmp_path).read_text(encoding="utf-8")
    fm = tq.front_matter(text)
    assert fm["score"] == "34" and fm["score_stated"] == "40.0" and fm["signal"] == "bearish"
    tail = text.split(pipeline.SOURCES_HEADING)[1]
    assert "USD，2026-09-29 收盤（Yahoo Finance 日線）" in tail and f"{len(h)} 根日線" in tail
    assert "| 有回應的資料來源 | Yahoo Finance |" in tail and "| 未回應的資料來源 | Finviz |" in tail
    assert "2026-11-20" in tail and "gemini / g" in tail
    assert text.rstrip().endswith("。")                   # not read as a cut-off report


def test_fundamental_sources_block_names_the_filing():
    data = {"price_now": 162.85, "price_date": "2026-11-13", "info": {"currency": "USD"},
            "source_status": {"fundamentals_store": True, "yfinance_info": True, "roic": False},
            "report_facts": {"statements": {"source": "SEC 10-Q filed 2026-08-27",
                                            "period_end": "2026-07-26", "fiscal_label": "FY2027 Q2"}}}
    block = pipeline.data_sources_block(data, "fundamental-analysis", "openai", "gpt-6-luna")
    assert "SEC 10-Q filed 2026-08-27，最新季度 2026-07-26（FY2027 Q2）" in block
    assert "SEC 申報資料 (XBRL)、Yahoo Finance" in block and "| 未回應的資料來源 | Roic.ai |" in block
    assert "F-Score" in block and "資料包" not in block
    fund = pipeline.data_sources_block({**data, "fund_facts": {"x": 1}}, "fundamental-analysis", "openai")
    assert "基金資料" in fund and "DCF" not in fund


# ── F8: quality figures ──────────────────────────────────────────────────────

def ttm(period_end, **kw):
    row = {"period_end": period_end, "revenue": 1000.0, "gross_profit": 600.0, "net_income": 200.0,
           "total_assets": 2000.0, "total_equity": 1000.0, "ocf": 300.0, "long_term_debt": 100.0,
           "current_assets": 800.0, "current_liabilities": 400.0, "shares_diluted": 100.0}
    return {**row, **kw}


def statements(dates, **rows):
    return pd.DataFrame(rows, index=pd.to_datetime(dates)).T


def test_dupont_factors_multiply_to_roe():
    d = quality.dupont(ttm("2026-06-30"))
    assert d["net_margin"] * d["asset_turnover"] * d["equity_multiplier"] == pytest.approx(d["roe"])
    assert d["roe"] == pytest.approx(0.2)
    assert quality.dupont(ttm("2026-06-30", total_equity=-5.0)) is None
    assert quality.dupont(None) is None


def test_f_score_counts_only_the_tests_it_can_run():
    cur = ttm("2026-06-30", net_income=260.0, gross_profit=None)
    fs = quality.f_score(cur, ttm("2025-06-30"))
    assert fs["tested"] == 8 and fs["tests"]["gross_margin_improving"] is None
    assert fs["tests"]["roa_improving"] is True and fs["prior_period_end"] == "2025-06-30"
    assert quality.f_score(cur, None) is None


def test_working_capital_days_from_matching_balance_columns():
    data = {"balance_q": statements(
        ["2026-06-30", "2026-03-31", "2025-06-30"],
        **{"Accounts Receivable": [100.0, 90.0, 80.0], "Inventory": [40.0, 50.0, 60.0],
           "Accounts Payable": [20.0, 20.0, 40.0]})}
    wc = quality.working_capital(data, ttm("2026-06-30"), ttm("2025-06-30"))
    now, prior = wc["now"], wc["prior"]
    assert now["dso"] == pytest.approx(100 / 1000 * 365) and now["dio"] == pytest.approx(40 / 400 * 365)
    assert now["ccc"] == pytest.approx(now["dso"] + now["dio"] - now["dpo"])
    assert prior["dpo"] == pytest.approx(40 / 400 * 365)
    # A balance sheet a quarter off the flows describes a different period.
    assert quality.working_capital(data, ttm("2026-09-30"), None) is None


def test_missing_inventory_is_na_not_zero():
    data = {"balance_q": statements(["2026-06-30"], **{"Accounts Receivable": [100.0],
                                                      "Accounts Payable": [20.0]})}
    now = quality.working_capital(data, ttm("2026-06-30"), None)["now"]
    assert now["dio"] is None and now["ccc"] is None and now["dso"] is not None
    text = "\n".join(quality.render({"working_capital": {"now": now, "prior": None}}))
    assert "DIO N/A" in text and "CCC N/A" in text


def test_lender_gets_bank_metrics_and_no_f_score():
    q_dates = ["2026-09-30", "2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"]
    data = {
        "income_q": statements(q_dates, **{"Net Interest Income": [90.0, 80.0, 70.0, 60.0, 50.0],
                                           "Total Revenue": [150.0, 130.0, 120.0, 100.0, 90.0],
                                           "Pretax Income": [30.0, 20.0, 20.0, 10.0, 5.0],
                                           "Net Income": [24.0, 16.0, 16.0, 8.0, 4.0]}),
        "balance_q": statements(q_dates, **{"Total Assets": [6000.0, 5800.0, 5600.0, 5200.0, 5000.0],
                                            "Tangible Book Value": [800.0, 780.0, 760.0, 740.0, 700.0],
                                            "Net Loan": [4500.0, 4300.0, 4100.0, 3900.0, 3700.0]}),
    }
    stmt = {"_ttm_row": ttm("2026-09-30"), "_ttm_prior_row": ttm("2025-09-30")}
    q = quality.build(data, {"marketCap": 2000.0}, stmt, lender=True)
    b = q["bank"]
    assert q["f_score"] is None and q["working_capital"] is None
    assert b["nim_proxy"] == pytest.approx(300 / 5500) and b["cost_to_income"] == pytest.approx(420 / 500)
    assert b["rotce"] == pytest.approx(64 / 800) and b["p_tbv"] == pytest.approx(2.5)
    text = "\n".join(quality.render(q))
    assert "LENDER METRICS" in text and "not applied to a lender" in text and "CET1: N/A" in text
    assert quality.bank_metrics({"income_q": None, "balance_q": None}, {}) is None


def test_company_quality_block_is_in_the_verified_figures():
    stmt = {"_ttm_row": ttm("2026-06-30", net_income=260.0), "_ttm_prior_row": ttm("2025-06-30")}
    text = "\n".join(quality.render(quality.build({}, {}, stmt, lender=False)))
    assert "Piotroski F-Score:" in text and "DuPont (TTM" in text
    assert "Working-capital days: N/A" in text
    assert quality.render(None) == []


# ── F9 / T6: prompts ─────────────────────────────────────────────────────────

def test_technical_prompt_asks_for_tables_not_drawings():
    p = load_prompt("technical")
    assert "必須繪製" not in p and "必須大量使用" not in p and "║" not in p
    assert p.count("```mermaid") == 0 and "最多 1 個 Mermaid 圖" in p
    assert "每個數字只完整陳述一次" in p
    assert "機率只能來自歷史基準" in p and "| 成功機率 |" not in p and "信心度百分比" not in p
    assert "進階指標" in p and "樞軸" in p
    assert "題示" in p and "不得**出現「題示」" in p     # named only to forbid it
    for row in ("進場價格", "目標價 T1", "目標價 T2", "止損價格", "風險報酬比"):
        assert f"| {row} |" in p                          # the rows stage-1 QA reads


def test_technical_prompt_scorecard_is_the_one_the_parser_reads():
    p = load_prompt("technical")
    card = p[p.index("### 🏆 技術評分卡"):p.index("## 2. 趨勢分析")]
    assert all(f"| {label} |" in card for label in sc.TECHNICAL["labels"])
    assert f"≥{sc.BULLISH_AT}" in card and f"≤{sc.BEARISH_AT}" in card
    assert f"綜合評分偏多（≥{sc.BULLISH_AT}）" in p and f"綜合評分偏空（≤{sc.BEARISH_AT}）" in p


def test_fundamental_prompt_has_one_scorecard_and_conditional_sections():
    p = load_prompt("fundamental")
    card = p[p.index("### 1.1 綜合評分卡"):p.index("### 1.2 ")]
    assert all(f"| {label} |" in card for label in sc.FUNDAMENTAL["labels"])
    for gone in ("多維度評分儀表板", "護城河強度評分", "最終綜合評級雷達圖", "S&P 500 均值 |", "| 營業利潤率 | 退出倍數 |"):
        assert gone not in p
    assert "有資料才寫" in p and "不得畫「示意」「估算」數字的圖表" in p
    assert "唯一的評分卡與綜合評分" in p and "QUALITY FIGURES" in p and "LENDER METRICS" in p
    assert "不得**使用「資料包」" in p
    assert "照抄 DCF MODEL 的 Scenarios" in p


# ── review of #108 ───────────────────────────────────────────────────────────

def test_a_missing_debt_figure_is_not_a_leverage_pass():
    """fa.piotroski reads a missing debt as zero, which "improves" on last year's debt."""
    fs = quality.f_score(ttm("2026-06-30", long_term_debt=None), ttm("2025-06-30", long_term_debt=20.0))
    assert fs["tests"]["leverage_falling"] is None and fs["tested"] == 8
    assert fs["score"] == sum(1 for v in fs["tests"].values() if v)
    zero = quality.f_score(ttm("2026-06-30", long_term_debt=0.0), ttm("2025-06-30", long_term_debt=20.0))
    assert zero["tests"]["leverage_falling"] is True and zero["tested"] == 9     # a reported zero counts


def test_lender_ratios_use_the_balance_sheet_of_the_income_period():
    income_dates = ["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30"]
    income = statements(income_dates, **{"Net Interest Income": [80.0, 70.0, 60.0, 50.0, 40.0],
                                         "Total Revenue": [130.0, 120.0, 100.0, 90.0, 80.0],
                                         "Pretax Income": [20.0, 20.0, 10.0, 5.0, 5.0],
                                         "Net Income": [16.0, 16.0, 8.0, 4.0, 4.0]})
    # Yahoo has published September's balance sheet; income still ends in June.
    newer = statements(["2026-09-30", "2026-06-30", "2025-06-30"],
                       **{"Total Assets": [9000.0, 5800.0, 5000.0],
                          "Tangible Book Value": [999.0, 780.0, 700.0]})
    b = quality.bank_metrics({"income_q": income, "balance_q": newer}, {"marketCap": 1560.0})
    assert b["period_end"] == "2026-06-30" and b["tangible_book"] == 780.0
    assert b["nim_proxy"] == pytest.approx(260 / 5400) and b["p_tbv"] == pytest.approx(2.0)
    # No balance sheet for June at all: nothing is formed across two periods.
    only_new = statements(["2026-09-30"], **{"Total Assets": [9000.0], "Tangible Book Value": [999.0]})
    gone = quality.bank_metrics({"income_q": income, "balance_q": only_new}, {"marketCap": 1560.0})
    assert gone["nim_proxy"] is None and gone["rotce"] is None and gone["p_tbv"] is None
    assert gone["nii_share"] == pytest.approx(260 / 440)          # income-only ratios still stand
    assert "no balance sheet dated 2026-06-30" in "\n".join(quality.render({"bank": gone, "lender": True}))


def test_an_unchanged_ad_line_is_flat_not_falling():
    flat = bars(60, slope=0.0, amp=0.0)                  # constant close, symmetric range
    ad = ts.accumulation_distribution(flat)
    assert ad["ad"] == 0 and ad["price"] == 0 and "持平" in ad["relation"]
    out = ts.studies_block(flat)
    assert "A/D 持平、價格持平" in out and "下降" not in out.split("A/D 線")[1]


def test_base_rate_state_is_read_from_the_newest_fetched_session():
    """The store ends a session early; the session it lacks is the one that changes the state."""
    i = np.arange(700)
    full = pd.DataFrame({"Close": 100 + 0.2 * i}, index=pd.date_range("2024-01-01", periods=700, freq="B"))
    full.iloc[-1] = 60.0                                  # today's close breaks below the MA200
    for col in ("Open", "High", "Low"):
        full[col] = full["Close"]
    full["Volume"] = 1e6
    store = full.iloc[:-1]                                # the committed store has not seen today
    fetched = full.tail(300).tz_localize("America/New_York")
    closes = ts.history_closes(fetched, store)
    assert len(closes) == 700 and closes.iloc[-1] == 60.0 and closes.index.is_monotonic_increasing
    assert "MA200 下方" in ts.base_rates(closes)["state"]
    assert "MA200 上方" in ts.base_rates(store["Close"])["state"]      # what was read before
    assert "MA200 下方" in ts.base_rate_block(fetched, store)
    assert len(ts.history_closes(fetched, None)) == 300


def test_a_widened_side_is_on_one_price_basis():
    """The store is not dividend-adjusted and the fetched bars are, so the same
    swing sits at two prices; merged, it would be listed twice."""
    from analysis.data.technicals import _cluster_levels, swing_points
    recent, full = falling_year_after_a_range()
    store = bars_frame(store_rows(full))
    store[["Open", "High", "Low", "Close"]] *= 1.03      # the store's basis, 3% above the fetched one
    lv = key_levels(recent, store)
    assert lv["basis"]["support"] == "store"
    window = store.tail(lv["lookback"]["support"])
    _, lows = swing_points(window["High"], window["Low"])
    from_store = sorted((x for x in _cluster_levels(lows) if x <= lv["last"]), reverse=True)[:3]
    assert lv["support"] == from_store                    # every level from the one series
    gaps = [abs(a - b) / b for a, b in zip(lv["support"], lv["support"][1:])]
    assert all(g > 0.015 for g in gaps)                   # no near-duplicate pair


def test_widened_levels_say_where_they_came_from():
    from analysis.data.technicals import compute_levels
    recent, full = falling_year_after_a_range()
    store = bars_frame(store_rows(full))
    assert key_levels(recent, store)["basis"]["support"] == "store"
    note = compute_levels(recent, store)
    assert "價位取自價格資料庫" in note and "支撐" in note.split("放寬後的")[1].split("價位取自")[0]
    assert key_levels(bars())["basis"] == {"resistance": "fetched", "support": "fetched"}
    assert "取自價格資料庫" not in compute_levels(bars())


def test_a_dashboard_total_above_the_card_does_not_absorb_the_correction():
    report = FUND.replace("| **綜合評分** | 7.5/10（引用 1.1） |", "| **綜合評分** | 7.5 |")
    text, card = sc.fix(report, sc.FUNDAMENTAL)
    assert card["corrected"] and text.count("| **綜合評分** | 7.2 |") == 1
    assert "| **綜合評分** | **7.2** | 六項平均 |" in text      # the card's own total, too
    assert sc.read(text, sc.FUNDAMENTAL)["stated"] == 7.2


def test_a_correction_across_a_signal_band_is_recorded_and_flagged(monkeypatch, tmp_path):
    h = bars().tz_localize("America/New_York")
    monkeypatch.setattr(pipeline, "fetch_data", lambda ticker: {
        "hist": h, "price_now": float(h["Close"].iloc[-1]), "price_date": "2026-09-29",
        "info": {"currency": "USD"}, "source_status": {"yfinance_prices": True}})
    monkeypatch.setattr(pipeline, "long_history", lambda key: None)
    monkeypatch.setattr(pipeline, "build_context", lambda data, atype: "CONTEXT")
    card = TECH_CARD.replace("**40**", "**45**").replace("40/100", "45/100")   # says neutral; mean is 34
    monkeypatch.setattr(pipeline, "call_llm", lambda *a, **k: "# AMZN\n" + card)
    path = pipeline.run_analysis("AMZN", "technical-analysis", "gemini", "g", 32000, tmp_path)
    text = path.read_text(encoding="utf-8")
    fm = tq.front_matter(text)
    assert fm["signal"] == "bearish" and fm["signal_stated"] == "neutral"
    assert "評分覆核" in text and "重算為 34（偏空）" in text
    content = text.split("---\n\n", 1)[1]
    codes = [c for c, _ in content_findings("technical_analysis", text, content, "AMZN", "2026-11-14")]
    assert "SIGNAL_CHANGED" in codes


def test_a_correction_inside_one_band_is_not_a_signal_change(monkeypatch, tmp_path):
    h = bars().tz_localize("America/New_York")
    monkeypatch.setattr(pipeline, "fetch_data", lambda ticker: {
        "hist": h, "price_now": float(h["Close"].iloc[-1]), "price_date": "2026-09-29",
        "info": {}, "source_status": {"yfinance_prices": True}})
    monkeypatch.setattr(pipeline, "long_history", lambda key: None)
    monkeypatch.setattr(pipeline, "build_context", lambda data, atype: "CONTEXT")
    monkeypatch.setattr(pipeline, "call_llm", lambda *a, **k: "# AMZN\n" + TECH_CARD)   # 40 → 34, both bearish
    text = pipeline.run_analysis("AMZN", "technical-analysis", "gemini", "g", 32000,
                                 tmp_path).read_text(encoding="utf-8")
    assert "signal_stated" not in tq.front_matter(text) and "評分覆核" not in text


def test_overview_table_leaves_values_to_the_owning_chapter():
    p = load_prompt("technical")
    table = p[p.index("### 📊 核心指標速覽表"):p.index("### 🏆 技術評分卡")]
    assert table.count("| 數值 |") == 1 and "| 當前價格 | 數值 |" in table
    assert "見第 5 章" in table and "見第 2 章" in table and "見第 6 章" in table
