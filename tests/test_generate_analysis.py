"""Integration tests for the generate_analysis CLI entry script."""

import pytest

import generate_analysis as ga

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
    assert args.provider == "openai"


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
    monkeypatch.setattr(ga, "fetch_data", lambda ticker: {"hist": None})
    monkeypatch.setattr(ga, "build_context", lambda data, atype: "CONTEXT")
    captured = {}

    def fake_llm(ticker, context, atype, provider, model, max_tokens):
        captured.update(ticker=ticker, context=context, atype=atype, provider=provider)
        return "# Report\nbody"

    monkeypatch.setattr(ga, "call_llm", fake_llm)
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
