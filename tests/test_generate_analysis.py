"""Integration tests for the generate_analysis CLI entry script."""

import pytest

import generate_analysis as ga
# Patch the SAME pipeline module object generate_analysis imports. The script
# runs with scripts/ on sys.path and imports the bare `analysis.pipeline`, which
# is a distinct module identity from `scripts.analysis.pipeline` under pytest.
from analysis import pipeline

pytestmark = pytest.mark.integration

TODAY = ga.TODAY


@pytest.fixture(autouse=True)
def _offline_report_inputs(monkeypatch):
    """The fundamental pipeline also gathers SEC / price-store / peer inputs;
    tests that stub fetch_data must not reach the network through it."""
    monkeypatch.setattr(pipeline.report_inputs, "gather", lambda ticker, info=None: {
        "store_rows": [], "bars": [], "risk_free": None, "peers": [], "fx": None, "status": {}})


def _bars(n=60):
    """A small daily OHLCV frame: technical runs now refuse to start without one."""
    import pandas as pd
    idx = pd.date_range("2026-07-01", periods=n, freq="B", tz="America/New_York")
    close = pd.Series([100.0 + i * 0.5 for i in range(n)], index=idx)
    return pd.DataFrame({"Open": close - 0.5, "High": close + 1, "Low": close - 1,
                         "Close": close, "Volume": 1_000_000.0})


def _priced(hist):
    return {"hist": hist, "price_now": float(hist["Close"].iloc[-1]),
            "price_date": str(hist.index[-1])[:10]}


# ── save_report ──────────────────────────────────────────────────────────────

def test_save_report_writes_markdown_with_frontmatter(tmp_path):
    path = ga.save_report("AAPL", "# Body\ncontent", tmp_path,
                          "fundamental-analysis", provider="openai")
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "ticker: AAPL" in text
    assert "analysis_type: fundamental-analysis" in text
    assert "provider: openai" in text
    assert "language: zh-TW" in text
    assert "# Body" in text
    assert path.name == f"fundamental_analysis_{TODAY}_openai.md"


def test_save_report_same_day_dedup(tmp_path):
    first = ga.save_report("AAPL", "a", tmp_path, "fundamental-analysis", provider="claude")
    second = ga.save_report("AAPL", "b", tmp_path, "fundamental-analysis", provider="claude")
    third = ga.save_report("AAPL", "c", tmp_path, "fundamental-analysis", provider="claude")
    assert first.name == f"fundamental_analysis_{TODAY}_claude.md"
    assert second.name == f"fundamental_analysis_{TODAY}_claude-2.md"
    assert third.name == f"fundamental_analysis_{TODAY}_claude-3.md"


def test_save_report_sanitizes_mermaid_at_source(tmp_path):
    # LLMs emit unquoted parens in node labels; the saved .md (what GitHub
    # renders directly) must already be valid, not only the docs-site copy.
    body = (
        "# Body\n"
        "```mermaid\n"
        "graph TD\n"
        "    A[ADX(14) = 17.44] --> B{ADX(14) < 25?}\n"
        "    B --> C[樂觀情境 (機率: 40%)]\n"
        "```\n"
        "prose with (parens) stays untouched\n"
    )
    path = ga.save_report("AAPL", body, tmp_path,
                          "technical-analysis", provider="gemini")
    text = path.read_text(encoding="utf-8")
    assert 'A["ADX(14) = 17.44"]' in text
    assert 'B{"ADX(14) < 25?"}' in text
    assert 'C["樂觀情境 (機率: 40%)"]' in text
    # Content outside ```mermaid fences is left exactly as-is.
    assert "prose with (parens) stays untouched" in text


def test_save_report_html_has_no_frontmatter(tmp_path):
    path = ga.save_report("AAPL", "<html>x</html>", tmp_path,
                          "report-generator", provider="claude")
    assert path.suffix == ".html"
    text = path.read_text(encoding="utf-8")
    assert not text.startswith("---")
    assert text == "<html>x</html>"


# ── parse_args ───────────────────────────────────────────────────────────────

def test_parse_args_defaults(monkeypatch):
    monkeypatch.setattr("sys.argv", ["generate_analysis.py"])
    args = ga.parse_args()
    assert args.ticker == "AAPL"
    assert args.analysis_type == "fundamental-analysis"
    # No explicit override → the generator uses the configured fallback chain.
    assert args.provider is None
    assert args.model is None


def test_parse_args_overrides(monkeypatch):
    monkeypatch.setattr("sys.argv", [
        "generate_analysis.py", "TSLA",
        "--analysis-type", "technical-analysis",
        "--provider", "claude", "--max-tokens", "5000",
    ])
    args = ga.parse_args()
    assert args.ticker == "TSLA"
    assert args.analysis_type == "technical-analysis"
    assert args.provider == "claude"
    assert args.max_tokens == 5000


# ── main (wired with mocked layers) ──────────────────────────────────────────

def test_main_writes_report(monkeypatch, tmp_path):
    # Orchestration lives in analysis.pipeline; patch its layer dependencies.
    monkeypatch.setattr(pipeline, "fetch_data", lambda ticker: {"hist": None})
    monkeypatch.setattr(pipeline, "build_context", lambda data, atype: "CONTEXT")
    captured = {}

    def fake_llm(ticker, context, atype, provider, model, max_tokens):
        captured.update(ticker=ticker, context=context, atype=atype, provider=provider)
        return "# Report\nbody"

    monkeypatch.setattr(pipeline, "call_llm", fake_llm)
    monkeypatch.setattr("sys.argv", [
        "generate_analysis.py", "msft",
        "--analysis-type", "fundamental-analysis",
        "--provider", "claude",
        "--output-dir", str(tmp_path),
    ])
    ga.main()

    assert captured["ticker"] == "MSFT"        # uppercased
    assert captured["context"] == "CONTEXT"
    files = list(tmp_path.glob("*.md"))
    assert len(files) == 1
    assert "# Report" in files[0].read_text(encoding="utf-8")


def test_main_sanitizes_broken_mermaid_end_to_end(monkeypatch, tmp_path):
    # Full generate path: an LLM that emits the exact unrenderable Mermaid seen
    # in real Gemini reports must still yield a saved file that (a) has quoted
    # labels and (b) passes the report-quality Mermaid gate — proving the fix
    # holds for every stock / provider / execution, not just at docs-build time.
    from analysis.validate import parse_file
    from analysis.utils.mermaid import mermaid_syntax_issues

    broken = (
        "# PLTR 技術分析\n\n"
        "```mermaid\n"
        "graph TD\n"
        "    A[ADX(14) = 17.44] --> B{ADX(14) < 25?}\n"
        "    B --> C[樂觀情境 (機率: 40%)]\n"
        "```\n"
    )
    monkeypatch.setattr(pipeline, "fetch_data", lambda ticker: _priced(_bars()))
    monkeypatch.setattr(pipeline, "build_context", lambda data, atype: "CONTEXT")
    monkeypatch.setattr(pipeline, "call_llm",
                        lambda *a, **k: broken)
    monkeypatch.setattr("sys.argv", [
        "generate_analysis.py", "pltr",
        "--analysis-type", "technical-analysis",
        "--provider", "gemini",
        "--output-dir", str(tmp_path),
    ])
    ga.main()

    saved = next(tmp_path.glob("*.md"))
    text = saved.read_text(encoding="utf-8")
    assert 'A["ADX(14) = 17.44"]' in text
    assert 'B{"ADX(14) < 25?"}' in text
    assert 'C["樂觀情境 (機率: 40%)"]' in text
    # The saved source is clean per both the detector and the quality scanner.
    assert mermaid_syntax_issues(text) == []
    assert "MERMAID" not in parse_file(saved).issues


# ── reports carry no chart markup ────────────────────────────────────────────
# Charts used to be baked into technical reports at generation time (a static PNG
# plus a full inline Plotly document, ~46 KB per report). They are now rendered
# client-side from the price store by build_docs.py, so a generated report must
# come out as pure LLM output — for *every* analysis type, technical included.

def _run_generate(monkeypatch, tmp_path, analysis_type, hist=None):
    data = {"hist": hist}
    if analysis_type == "technical-analysis":
        data = _priced(hist if hist is not None else _bars())
    monkeypatch.setattr(pipeline, "fetch_data", lambda ticker: data)
    monkeypatch.setattr(pipeline, "build_context", lambda data, atype: "CONTEXT")
    monkeypatch.setattr(
        pipeline, "call_llm",
        lambda ticker, context, atype, provider, model, max_tokens: "# Report\nbody",
    )
    monkeypatch.setattr("sys.argv", [
        "generate_analysis.py", "amd",
        "--analysis-type", analysis_type,
        "--provider", "claude",
        "--output-dir", str(tmp_path),
    ])
    ga.main()
    files = list(tmp_path.glob("*.md"))
    assert len(files) == 1
    return files[0]


@pytest.mark.parametrize("analysis_type", ["technical-analysis", "fundamental-analysis"])
def test_generated_report_has_no_chart_markup(monkeypatch, tmp_path, analysis_type):
    text = _run_generate(monkeypatch, tmp_path, analysis_type).read_text(encoding="utf-8")
    for marker in ("candlestick-chart", "plot.ly", "plotly", "technical_chart_",
                   "<details", "靜態圖表"):
        assert marker not in text, f"{analysis_type} report still contains {marker!r}"
    assert text.rstrip().endswith("body")   # LLM output is the whole body


def test_technical_report_writes_no_png(monkeypatch, tmp_path):
    """The PNG path is gone, so a technical run must leave no image behind — even
    when price history is present, which is what used to trigger it."""
    _run_generate(monkeypatch, tmp_path, "technical-analysis", hist=_bars())
    assert list(tmp_path.glob("*.png")) == []


def test_pipeline_no_longer_exposes_a_chart_builder():
    # A stale re-export would let the old embed creep back in unnoticed.
    assert not hasattr(pipeline, "build_technical_chart_embed")
    assert "build_technical_chart_embed" not in pipeline.__all__


# ── §8.8 re-check ────────────────────────────────────────────────────────────

S88 = """# TSLA 基本面深度分析報告

## 1. 執行摘要

### 8.8 估值三角驗證

| **加權合理價值** | **$334.34** |

`$328.25×45% + $164.25×10% + $283.50×15% + $382.40×15% + $401.40×15%`

### 8.9 局限
"""


def test_fundamental_run_rechecks_8_8_and_records_it(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "fetch_data", lambda ticker: {"hist": None, "price_now": 374.58})
    monkeypatch.setattr(pipeline, "build_context", lambda data, atype: "CONTEXT")
    monkeypatch.setattr(pipeline, "call_llm", lambda *a, **k: S88)
    path = pipeline.run_analysis("TSLA", "fundamental-analysis", "gemini", "g", 100, tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "arithmetic_check: corrected" in text
    assert "weighted_fair_value_stated: 334.34" in text      # the model's, kept
    assert "weighted_fair_value_recomputed: 324.23" in text
    assert "mos_recomputed_pct: -15.5" in text
    assert "程式複算更正" in text
    # The table now carries the sum of its own terms; $334.34 survives only in
    # the notices that say what was changed.
    assert "| **加權合理價值** | **$324.23** |" in text
    body = text.split("### 8.8", 1)[1].split("🔎", 1)[0]
    assert "334.34" not in body


def test_a_rewrite_that_does_not_recheck_clean_is_not_marked_corrected():
    """A total printed to one decimal ("$334.3") is not matched by correct(),
    which would still rewrite MOS around it; that must stay a mismatch."""
    report = S88.replace("**$334.34**", "**$334.3**") + "\n| **安全邊際（MOS）** | **-12.0%** |\n"
    out, fields = pipeline.recheck_valuation(report, {"price": 374.58})
    assert fields["arithmetic_check"] == "mismatch"
    assert "-12.0%" in out and "應為" in out


def test_other_types_are_not_rechecked(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "fetch_data", lambda ticker: {"hist": None})
    monkeypatch.setattr(pipeline, "build_context", lambda data, atype: "CONTEXT")
    monkeypatch.setattr(pipeline, "call_llm", lambda *a, **k: S88)
    path = pipeline.run_analysis("TSLA", "stock-eval", "gemini", "g", 100, tmp_path)
    assert "arithmetic_check" not in path.read_text(encoding="utf-8")


# ── provenance ───────────────────────────────────────────────────────────────

HEADER = ("# TSLA 基本面深度分析報告\n> **報告日期**：2026-10-22 ｜ **語言**：繁體中文 ｜ "
          "**數據來源**：Yahoo Finance, Finviz, StockAnalysis, Roic.ai ｜ **分析師**：CFA\n")


def test_front_matter_records_prompt_params_price_and_sources(tmp_path, monkeypatch):
    status = {"yfinance_info": True, "sec_live": True, "finviz": False, "roic": False}
    monkeypatch.setattr(pipeline, "fetch_data", lambda ticker: {
        "hist": None, "price_now": 374.58, "price_date": "2026-10-22", "source_status": status})
    monkeypatch.setattr(pipeline, "build_context", lambda data, atype: "CONTEXT")
    monkeypatch.setattr(pipeline, "call_llm", lambda *a, **k: HEADER)
    path = pipeline.run_analysis("TSLA", "fundamental-analysis", "gemini", "g", 32000, tmp_path)
    text = path.read_text(encoding="utf-8")
    fm = text.split("---")[1]
    assert f"prompt_sha256: {pipeline.prompt_fingerprint('fundamental-analysis', 'gemini')}" in fm
    assert f"temperature: {pipeline.REPORT_TEMPERATURE}" in fm
    assert "max_tokens: 32000" in fm
    assert "price: 374.58" in fm and "price_date: 2026-10-22" in fm
    assert "data_sources_failed: finviz, roic" in fm


def test_header_lists_only_the_sources_that_answered():
    out = pipeline.stamp_sources(HEADER, {"yfinance_info": True, "sec_live": True,
                                          "finviz": False, "stockanalysis": False, "roic": False})
    assert "**數據來源**：SEC 申報資料 (XBRL)、Yahoo Finance ｜ **分析師**" in out
    assert "Finviz" not in out and "Roic.ai" not in out


def test_header_left_alone_without_status():
    assert pipeline.stamp_sources(HEADER, {}) == HEADER
