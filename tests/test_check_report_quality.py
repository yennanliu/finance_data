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
    """A well-formed fundamental report: chapters ## 1. … ## 11. plus prose."""
    chapters = "\n".join(f"## {n}. 章節 {n}\n內容。" for n in range(1, 12))
    return FM + chapters + "\n" + "\n".join(
        f"### 段落 {i}\n這是分析內容第 {i} 行。" for i in range(lines))


S88_BAD = """
### 8.8 估值三角驗證與安全邊際

| 估值方法 | 隱含每股價值 | 權重 |
|---|---|---|
| **加權合理價值** | **$334.34** | **100%** |

`加權合理價值 = $328.25×45% + $164.25×10% + $283.50×15% + $382.40×15% + $401.40×15%`
`= $147.71 + $16.43 + $42.53 + $57.36 + $60.21 = $334.34`

### 8.9 局限
"""


def test_missing_chapters_are_flagged_for_fundamental_reports(tmp_path):
    body = _good_body().replace("## 11. 章節 11\n", "")
    p = _write(tmp_path, "aapl", "fundamental_analysis_2026-01-01_claude.md", body)
    issue = crq.parse_file(p)
    assert "MISSING_SECTIONS" in issue.issues and "[11]" in issue.note


def test_chapters_are_not_required_of_other_report_types(tmp_path):
    body = FM + "\n".join(f"## 段落 {i}\n內容第 {i} 行。" for i in range(90))
    p = _write(tmp_path, "aapl", "technical_analysis_2026-01-01_claude.md", body)
    assert crq.parse_file(p).issues == []


def test_a_mis_added_weighted_fair_value_is_flagged(tmp_path):
    """TSLA 2026-10-22: the terms add up to $324.23, the report says $334.34."""
    p = _write(tmp_path, "tsla", "fundamental_analysis_2026-01-01_claude.md",
               _good_body() + S88_BAD)
    issue = crq.parse_file(p)
    assert "ARITHMETIC" in issue.issues
    assert "terms_sum=324.23" in issue.note


def test_a_correct_weighted_fair_value_passes(tmp_path):
    body = _good_body() + S88_BAD.replace("$334.34", "$324.23")
    p = _write(tmp_path, "tsla", "fundamental_analysis_2026-01-01_claude.md", body)
    assert crq.parse_file(p).issues == []


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


def test_a_fundamental_report_quoting_another_price_is_flagged(tmp_path):
    """0050 2026-10: 「現價 NT$195.00」 22 times while it was given NT$106.90."""
    fm = "---\ntitle: x\nprice: 106.90\nprice_date: 2026-01-01\n---\n\n"
    body = fm + _good_body()[len(FM):] + "\n現價 NT$195.00\n"
    p = _write(tmp_path, "0050", "fundamental_analysis_2026-01-01_gemini.md", body)
    issue = crq.parse_file(p)
    assert "PRICE_MISMATCH" in issue.issues and "stated=195.0" in issue.note


def test_copied_template_figures_are_placeholders(tmp_path):
    """INTC 2026-10-20 printed 「加權合理價值 $XXX」 from the prompt's example."""
    p = _write(tmp_path, "intc", "fundamental_analysis_2026-01-01_openai.md",
               _good_body() + "\n| **安全邊際（MOS）** | -15%＝(加權合理價值 $XXX − 現價) |\n")
    assert "PLACEHOLDER" in crq.parse_file(p).issues


def test_every_emitted_issue_code_is_documented(tmp_path):
    """The CLI prints ISSUE_TYPES beside each count; an undocumented code
    would print with no description."""
    import re
    from pathlib import Path
    src = (Path(crq.__file__).parent / "analysis/validate/__init__.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'(?:issues\.append|out\.append)\(\(?"([A-Z_]+)"', src))
    assert emitted and emitted <= set(crq.ISSUE_TYPES)


def test_a_duplicate_suffix_after_the_provider_is_still_parsed(tmp_path):
    """skhy/…_2026-10-23_gemini-2.md was read as type 'unknown' and skipped
    every type-specific check."""
    p = _write(tmp_path, "skhy", "fundamental_analysis_2026-10-23_gemini-2.md", _good_body())
    issue = crq.parse_file(p)
    assert (issue.analysis_type, issue.provider) == ("fundamental_analysis", "gemini")
    assert "DUPLICATE" in issue.issues


def test_recent_dates_cover_one_generation_cycle():
    from datetime import date
    assert crq.recent_dates(2, today=date(2026, 10, 24)) == {"2026-10-24", "2026-10-23"}


def test_summary_leads_with_the_recent_slice(tmp_path, capsys, monkeypatch):
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date().isoformat()
    _write(tmp_path, "aapl", f"fundamental_analysis_{today}_gemini.md", FM + "短")
    _write(tmp_path, "aapl", "fundamental_analysis_2020-01-01_gemini.md", FM + "短")
    monkeypatch.setattr("sys.argv", ["x", "--root", str(tmp_path), "--summary"])
    crq.main()
    out = capsys.readouterr().out
    recent, everything = out.split("All scanned reports")
    assert "Recent — last 2 UTC days" in recent and "Total scanned : 1" in recent
    assert "Total scanned : 2" in everything
