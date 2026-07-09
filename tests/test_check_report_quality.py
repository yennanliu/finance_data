"""Integration tests for the check_report_quality scanner."""

import pytest

import check_report_quality as crq

pytestmark = pytest.mark.integration

FM = "---\ntitle: x\ndate: 2026-01-01\n---\n\n"


def _write(tmp_path, ticker, filename, body):
    d = tmp_path / ticker
    d.mkdir(parents=True, exist_ok=True)
    p = d / filename
    p.write_text(body, encoding="utf-8")
    return p


def _good_body(lines=90):
    return FM + "\n".join(f"## 段落 {i}\n這是分析內容第 {i} 行。" for i in range(lines))


# ── parse_file per issue category ────────────────────────────────────────────

def test_empty(tmp_path):
    p = _write(tmp_path, "aapl", "fundamental_analysis_2026-01-01_claude.md", "   \n  ")
    assert "EMPTY" in crq.parse_file(p).issues


def test_refusal(tmp_path):
    body = FM + "抱歉，我無法完成這個請求。"
    p = _write(tmp_path, "aapl", "fundamental_analysis_2026-01-01_claude.md", body)
    issues = crq.parse_file(p).issues
    assert "REFUSAL" in issues
    assert "TOO_SHORT" not in issues  # refusal takes precedence


def test_too_short(tmp_path):
    body = FM + "## 標題\n簡短內容。\n結束。"
    p = _write(tmp_path, "aapl", "fundamental_analysis_2026-01-01_claude.md", body)
    issues = crq.parse_file(p).issues
    assert "TOO_SHORT" in issues
    assert "REFUSAL" not in issues


def test_no_frontmatter(tmp_path):
    p = _write(tmp_path, "aapl", "fundamental_analysis_2026-01-01_claude.md",
               _good_body().replace(FM, ""))
    assert "NO_FRONTMATTER" in crq.parse_file(p).issues


def test_placeholder(tmp_path):
    body = _good_body() + "\n分析 {ticker} 的表現。"
    p = _write(tmp_path, "aapl", "fundamental_analysis_2026-01-01_claude.md", body)
    assert "PLACEHOLDER" in crq.parse_file(p).issues


def test_html_leak(tmp_path):
    body = FM + "<!DOCTYPE html>\n<script>window.PlotlyConfig={}</script>\n只有一個標題\n## one"
    p = _write(tmp_path, "aapl", "technical_analysis_2026-01-01_claude.md", body)
    assert "HTML_LEAK" in crq.parse_file(p).issues


def test_mermaid_broken_flowchart(tmp_path):
    body = (_good_body()
            + "\n```mermaid\ngraph TD\n    A[ADX(14) = 17.44] --> B{未來 (估)}\n```\n")
    p = _write(tmp_path, "aapl", "technical_analysis_2026-01-01_gemini.md", body)
    issue = crq.parse_file(p)
    assert "MERMAID" in issue.issues
    assert "mermaid=" in issue.note


def test_mermaid_valid_flowchart_not_flagged(tmp_path):
    # Quoted labels (what the generator now emits) must not trip the detector.
    body = (_good_body()
            + '\n```mermaid\ngraph TD\n    A["ADX(14) = 17.44"] --> B{"未來 (估)"}\n```\n')
    p = _write(tmp_path, "aapl", "technical_analysis_2026-01-01_gemini.md", body)
    assert "MERMAID" not in crq.parse_file(p).issues


def test_cutoff_trailing_comma(tmp_path):
    body = _good_body() + "\n因此我們的結論是，"
    p = _write(tmp_path, "aapl", "fundamental_analysis_2026-01-01_claude.md", body)
    assert "CUTOFF" in crq.parse_file(p).issues


def test_duplicate(tmp_path):
    p = _write(tmp_path, "aapl", "fundamental_analysis_2026-01-01-2.md", _good_body())
    assert "DUPLICATE" in crq.parse_file(p).issues


def test_good_report_has_no_issues(tmp_path):
    p = _write(tmp_path, "aapl", "fundamental_analysis_2026-01-01_claude.md", _good_body())
    issue = crq.parse_file(p)
    assert issue.issues == []
    assert issue.is_bad() is False
    assert issue.ticker == "aapl"
    assert issue.provider == "claude"
    assert issue.analysis_type == "fundamental_analysis"


# ── collect_reports filtering ────────────────────────────────────────────────

def test_collect_reports_filters(tmp_path):
    _write(tmp_path, "aapl", "fundamental_analysis_2026-01-15_claude.md", _good_body())
    _write(tmp_path, "aapl", "fundamental_analysis_2026-03-15_claude.md", _good_body())
    _write(tmp_path, "msft", "fundamental_analysis_2026-02-15_claude.md", _good_body())

    # no filters → all 3
    assert len(crq.collect_reports(tmp_path, None, None, None)) == 3
    # ticker filter
    assert len(crq.collect_reports(tmp_path, None, None, "aapl")) == 2
    # since filter (>= 2026-02)
    assert len(crq.collect_reports(tmp_path, "2026-02", None, None)) == 2
    # since + until window (2026-02 only)
    assert len(crq.collect_reports(tmp_path, "2026-02", "2026-02", None)) == 1
