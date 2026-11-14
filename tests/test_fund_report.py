"""A fund is not a company: the ETF branch of the fundamental report.

The eight ETF reports of 2026-11-13 went through the company template and came
out about 1,000 lines long with 417–461 ``N/A`` each (``docs/REPORT_REVIEW.md``
F4). They now get their own figures, context and prompt.
"""

import pytest

from analysis import pipeline
from analysis.config.benchmarks import market_benchmark, sector_benchmark
from analysis.context import build_context, fund_facts
from analysis.prompts import load_prompt
from analysis.validate import parse_file
from analysis.validate import technical as tq

pytestmark = pytest.mark.unit

PROFILE = {
    "family": "Invesco", "category": "Large Growth", "expense_ratio": 0.0018,
    "expense_ratio_category": 0.009, "total_assets": 463.8e9, "turnover": 0.08,
    "yield": 0.0045, "nav": 688.22, "pe": 28.4, "pb": 8.7,
    "holdings": [{"symbol": "AAPL", "name": "Apple Inc", "weight": 0.0816},
                 {"symbol": "NVDA", "name": "NVIDIA Corp", "weight": 0.0800},
                 {"symbol": "MSFT", "name": "Microsoft Corp", "weight": 0.0629}],
    "sectors": {"technology": 0.58, "healthcare": 0.048, "realestate": 0.0},
}


def bars(n, start=100.0, step=1.0, first_day=1):
    """``n`` sessions, one a day, closing ``start``, ``start + step``, …"""
    from datetime import date, timedelta
    d0 = date(2020, 1, first_day)
    return [{"date": (d0 + timedelta(days=i)).isoformat(), "close": start + step * i}
            for i in range(n)]


def data(**kw):
    out = {"ticker": "QQQ", "info": {"currency": "USD", "quoteType": "ETF", "longName": "Invesco QQQ"},
           "price_now": 688.17, "price_date": "2026-11-12", "price_series": {}, "news": []}
    out.update(kw)
    return out


# ── figures ──────────────────────────────────────────────────────────────────
def test_concentration_is_the_weight_of_the_listed_holdings():
    c = fund_facts.concentration(PROFILE["holdings"])
    assert c["count"] == 3 and c["largest"] == 0.0816
    assert c["total"] == pytest.approx(0.2245)
    assert fund_facts.concentration([]) is None


def test_performance_is_measured_on_sessions_both_series_have():
    fund = bars(300)
    bench = bars(299, start=200.0, step=1.0)          # the benchmark store is a session behind
    rows = {r["label"]: r for r in fund_facts.performance(fund, bench)}
    one_month = rows["1 個月"]
    # 21 sessions back from the last common one (index 298): 398 vs 377, 498 vs 477.
    assert one_month["fund"] == pytest.approx((398 / 377 - 1) * 100)
    assert one_month["benchmark"] == pytest.approx((498 / 477 - 1) * 100)
    assert one_month["excess"] == pytest.approx(one_month["fund"] - one_month["benchmark"])
    assert rows["3 年"]["fund"] is None               # not enough history: N/A, not a guess


def test_premium_to_nav_and_the_rendered_block():
    f = fund_facts.compute(data(), PROFILE, bars(300), bars(300, start=200.0), "vti")
    assert f["premium"] == pytest.approx(688.17 / 688.22 - 1)
    text = fund_facts.render(f)
    assert "VERIFIED FUND FIGURES" in text and "0.18%" in text and "category average 0.90%" in text
    assert "AAPL" in text and "8.16%" in text and "VTI（美國整體市場）" in text
    assert "Diversified" in text and "realestate" not in text       # a zero weight is not listed
    assert "no income statement" in text


def test_a_fund_with_no_profile_says_na_and_forbids_memory():
    text = fund_facts.render(fund_facts.compute(data(), None, [], [], None))
    assert "Net expense ratio:          N/A" in text
    assert "Largest holdings: N/A" in text and "Do not list holdings from memory" in text


def test_a_concentrated_fund_is_called_concentrated():
    profile = dict(PROFILE, holdings=[{"symbol": "2330.TW", "name": "TSMC", "weight": 0.5645},
                                      {"symbol": "2454.TW", "name": "MediaTek", "weight": 0.0674}])
    assert "Concentrated" in fund_facts.render(fund_facts.compute(data(), profile, [], [], None))


# ── benchmarks ───────────────────────────────────────────────────────────────
def test_benchmarks_come_from_the_price_store_and_never_compare_a_fund_with_itself():
    assert market_benchmark("nvda") == "vti" and market_benchmark("2330.tw") == "0050"
    assert market_benchmark("vti") is None and market_benchmark("0050") is None
    assert sector_benchmark("nvda") == "smh" and sector_benchmark("vst") is None


# ── context, prompt and pipeline ─────────────────────────────────────────────
def test_fund_context_is_the_fund_block_not_the_company_statements():
    d = data(fund_facts=fund_facts.compute(data(), PROFILE, bars(300), [], None),
             report_facts={"is_fund": True})
    context = build_context(d, "fundamental-analysis")
    assert "VERIFIED FUND FIGURES" in context
    assert "INCOME STATEMENT" not in context and "CASH FLOW STATEMENT" not in context


def test_fund_prompt_has_eight_chapters_and_no_company_valuation():
    prompt = load_prompt("fundamental_etf")
    filled = prompt.format(ticker="QQQ", financial_context="C", today="2026-11-14")
    assert [f"## {n}." in filled for n in range(1, 9)] == [True] * 8 and "## 9." not in filled
    assert "不得" in prompt and "DCF" in prompt and "N/A（資料未提供）" in prompt
    for banned in ("### 8.8", "WACC 推導", "加權合理價值"):
        assert banned not in prompt


def fund_report():
    return "# QQQ ETF 分析報告\n\n> **數據來源**：x ｜ y\n\n" + "\n\n".join(
        f"## {n}. 章節\n\n內容。" for n in range(1, 9)) + "\n" + "內容\n" * 90


def test_a_fund_run_uses_the_fund_prompt_and_skips_the_valuation_recheck(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(pipeline, "fetch_data", lambda ticker: data(source_status={"yfinance_info": True}))
    monkeypatch.setattr(pipeline.report_inputs, "gather", lambda ticker, info=None: {
        "store_rows": [], "bars": [], "risk_free": 0.04, "peers": [], "fx": None, "status": {}})
    monkeypatch.setattr(pipeline.report_inputs, "fund_profile", lambda ticker, info=None: PROFILE)
    monkeypatch.setattr(pipeline.fund_facts, "gather",
                        lambda d, profile: fund_facts.compute(d, profile, bars(300), [], None))

    def fake_llm(ticker, context, atype, provider, model, max_tokens, prompt_file=None):
        seen.update(context=context, prompt_file=prompt_file)
        return fund_report()

    monkeypatch.setattr(pipeline, "call_llm", fake_llm)
    path = pipeline.run_analysis("QQQ", "fundamental-analysis", "openai", "m", 1000, tmp_path)
    fm = tq.front_matter(path.read_text(encoding="utf-8"))
    assert seen["prompt_file"] == pipeline.FUND_PROMPT and "VERIFIED FUND FIGURES" in seen["context"]
    assert fm["instrument"] == "fund" and "fund_profile" in fm["data_sources_ok"]
    assert "arithmetic_check" not in fm and "valuation" not in fm
    assert fm["prompt_sha256"] != pipeline.prompt_fingerprint("fundamental-analysis", "openai")


def test_qa_checks_a_fund_report_against_the_fund_chapters(tmp_path):
    f = tmp_path / "qqq" / "fundamental_analysis_2026-11-14_openai.md"
    f.parent.mkdir()
    head = "---\nticker: QQQ\nanalysis_type: fundamental-analysis\ninstrument: fund\n---\n\n"
    f.write_text(head + fund_report(), encoding="utf-8")
    assert "MISSING_SECTIONS" not in parse_file(f).issues
    f.write_text(head + fund_report().replace("## 8. 章節", "## 八、章節"), encoding="utf-8")
    assert "MISSING_SECTIONS" in parse_file(f).issues
    # Without the marker the same eight chapters are a truncated company report.
    f.write_text(head.replace("instrument: fund\n", "") + fund_report(), encoding="utf-8")
    assert "MISSING_SECTIONS" in parse_file(f).issues
