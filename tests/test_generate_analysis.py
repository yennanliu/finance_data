"""Integration tests for the generate_analysis CLI entry script."""

import pytest

import generate_analysis as ga
# Patch the SAME pipeline module object generate_analysis imports. The script
# runs with scripts/ on sys.path and imports the bare `analysis.pipeline`, which
# is a distinct module identity from `scripts.analysis.pipeline` under pytest.
from analysis import pipeline

pytestmark = pytest.mark.integration

TODAY = ga.TODAY


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
    monkeypatch.setattr(pipeline, "fetch_data", lambda ticker: {"hist": None})
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
