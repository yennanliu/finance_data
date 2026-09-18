"""Tests for the LLM-judge QA stage (scripts/review_report_quality.py).

Fully offline: every provider call is mocked at the ``analysis.llm`` runner
boundary, matching the rest of the suite. No API keys required.
"""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import patch

import pytest

import review_report_quality as rrq

pytestmark = pytest.mark.unit

FM = "---\ntitle: x\ndate: 2026-09-17\nprovider: gemini\n---\n\n"


def _write(tmp_path, ticker, filename, body=None):
    d = tmp_path / ticker
    d.mkdir(parents=True, exist_ok=True)
    p = d / filename
    p.write_text(body if body is not None else FM + "## 分析\n內容。\n", encoding="utf-8")
    return p


def _verdict_json(**over):
    payload = {
        "verdict": "pass",
        "score": 4,
        "dimensions": {k: 4 for k in rrq.DIMENSIONS},
        "issues": [],
        "rationale": "整體品質良好。",
    }
    payload.update(over)
    return json.dumps(payload, ensure_ascii=False)


# ── prepare_report_text ──────────────────────────────────────────────────────

def test_short_report_passes_through_unchanged():
    text = "報告內容" * 10
    assert rrq.prepare_report_text(text, max_chars=1000) == text


def test_long_report_elides_the_middle_and_keeps_both_ends():
    text = "頭" * 500 + "中" * 4000 + "尾" * 500
    out = rrq.prepare_report_text(text, max_chars=2000)

    assert len(out) <= 2000
    assert rrq._ELISION_MARKER in out
    # Both ends survive: the tail matters because dropping it would make every
    # long report look truncated to the completeness check.
    assert out.startswith("頭")
    assert out.endswith("尾")


# ── parse_verdict ────────────────────────────────────────────────────────────

def test_parses_plain_json():
    parsed = rrq.parse_verdict(_verdict_json())
    assert parsed["verdict"] == "pass"
    assert parsed["score"] == 4
    assert parsed["dimensions"]["depth"] == 4


def test_parses_json_wrapped_in_a_code_fence():
    parsed = rrq.parse_verdict(f"```json\n{_verdict_json(verdict='fail')}\n```")
    assert parsed["verdict"] == "fail"


def test_parses_json_surrounded_by_prose():
    raw = f"好的，以下是審稿結果：\n{_verdict_json(verdict='warn')}\n希望有幫助。"
    assert rrq.parse_verdict(raw)["verdict"] == "warn"


def test_unknown_verdict_is_normalised_not_raised():
    parsed = rrq.parse_verdict(_verdict_json(verdict="excellent"))
    assert parsed["verdict"] == "unknown"


def test_scores_are_clamped_into_range():
    parsed = rrq.parse_verdict(_verdict_json(score=99, dimensions={"depth": -3}))
    assert parsed["score"] == 5
    assert parsed["dimensions"]["depth"] == 1


def test_missing_overall_score_falls_back_to_the_dimension_floor():
    """The rubric says any dimension at 1 is a fail, so the floor is the
    conservative reading when the model omits the overall score."""
    raw = json.dumps({"verdict": "pass", "dimensions": {"depth": 4, "language": 2}})
    assert rrq.parse_verdict(raw)["score"] == 2


def test_issues_string_is_coerced_to_a_list_and_capped():
    assert rrq.parse_verdict(_verdict_json(issues="單一問題"))["issues"] == ["單一問題"]
    many = rrq.parse_verdict(_verdict_json(issues=[f"問題{i}" for i in range(9)]))
    assert len(many["issues"]) == 5


def test_newlines_are_stripped_so_csv_rows_stay_on_one_line():
    parsed = rrq.parse_verdict(_verdict_json(rationale="第一行\n第二行"))
    assert "\n" not in parsed["rationale"]


@pytest.mark.parametrize("raw", ["", "完全不是 JSON", "抱歉，我無法審核。", None])
def test_unparseable_response_raises_valueerror(raw):
    with pytest.raises(ValueError):
        rrq.parse_verdict(raw)


# ── review_one ───────────────────────────────────────────────────────────────

def test_review_one_returns_the_parsed_verdict(tmp_path):
    p = _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_gemini.md")
    with patch.object(rrq, "run_openai", return_value=_verdict_json()) as m:
        result = rrq.review_one(p, provider="openai", model="gpt-4o-mini")

    assert result.verdict == "pass"
    assert result.ticker == "aapl"
    assert result.report_provider == "gemini"
    assert result.reviewer_provider == "openai"
    assert m.call_count == 1


def test_review_one_disables_refusal_retry(tmp_path):
    """The refusal-override prefix tells the model to WRITE a report; handing
    that to a grader would make it produce analysis instead of a verdict."""
    p = _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_gemini.md")
    with patch.object(rrq, "run_openai", return_value=_verdict_json()) as m:
        rrq.review_one(p, provider="openai", model="gpt-4o-mini")

    assert m.call_args.kwargs["refusal_retry"] is False
    assert m.call_args.kwargs["temperature"] == 0.0


def test_provider_error_becomes_an_error_row_not_an_exception(tmp_path):
    """One failed call must not abort a 100-report nightly run."""
    p = _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_gemini.md")
    with patch.object(rrq, "run_openai", side_effect=RuntimeError("502 upstream")):
        result = rrq.review_one(p, provider="openai", model="gpt-4o-mini")

    assert result.verdict == "ERROR"
    assert "502 upstream" in result.rationale


def test_unparseable_response_becomes_a_parse_error_row(tmp_path):
    p = _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_gemini.md")
    with patch.object(rrq, "run_openai", return_value="not json at all"):
        result = rrq.review_one(p, provider="openai", model="gpt-4o-mini")

    assert result.verdict == "PARSE_ERROR"


def test_review_one_dispatches_to_the_requested_provider(tmp_path):
    p = _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_openai.md")
    with patch.object(rrq, "run_gemini", return_value=_verdict_json()) as gem, \
            patch.object(rrq, "run_openai") as oai:
        result = rrq.review_one(p, provider="gemini", model="gemini-3.8-flash")

    assert gem.call_count == 1
    assert oai.call_count == 0
    assert result.reviewer_provider == "gemini"


def test_prompt_renders_without_stray_braces(tmp_path):
    """qa_review.txt escapes its JSON braces as {{ }}; a regression there would
    raise KeyError/IndexError at .format() time on every single report."""
    p = _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_gemini.md")
    with patch.object(rrq, "run_openai", return_value=_verdict_json()) as m:
        rrq.review_one(p, provider="openai", model="gpt-4o-mini")

    prompt = m.call_args.args[1]
    assert "aapl" in prompt
    assert "{ticker}" not in prompt
    assert "{report}" not in prompt
    assert '"verdict"' in prompt  # the literal JSON schema survived escaping


# ── pick_reviewer ────────────────────────────────────────────────────────────

def test_cross_provider_off_always_uses_the_configured_reviewer():
    assert rrq.pick_reviewer("openai", "openai", cross_provider=False) == "openai"


def test_cross_provider_avoids_self_grading(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert rrq.pick_reviewer("openai", "openai", cross_provider=True) == "gemini"


def test_cross_provider_keeps_the_reviewer_when_report_provider_differs():
    assert rrq.pick_reviewer("gemini", "openai", cross_provider=True) == "openai"


def test_cross_provider_falls_back_to_self_when_no_other_key_exists(monkeypatch):
    """Self-grading beats skipping the report entirely."""
    for env in rrq.PROVIDER_ENV.values():
        monkeypatch.delenv(env, raising=False)
    assert rrq.pick_reviewer("openai", "openai", cross_provider=True) == "openai"


# ── date window ──────────────────────────────────────────────────────────────

def test_recent_days_spans_the_generation_cycle():
    """Report-gen crons run 17:00-03:00 UTC, so one cycle carries two date
    stamps; a 1-day window would silently skip the 17:00-23:00 batch."""
    assert rrq.recent_days(2, today=date(2026, 9, 18)) == ["2026-09-18", "2026-09-17"]


def test_recent_days_crosses_a_month_boundary():
    assert rrq.recent_days(2, today=date(2026, 3, 1))[1] == "2026-02-28"


def test_select_reports_filters_to_the_window(tmp_path):
    _write(tmp_path, "aapl", "fundamental_analysis_2026-09-18_gemini.md")
    _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_gemini.md")
    _write(tmp_path, "aapl", "fundamental_analysis_2026-09-01_gemini.md")

    picked = rrq.select_reports([tmp_path], days=["2026-09-18", "2026-09-17"],
                                since=None, until=None, ticker=None, limit=None)
    names = [p.name for p in picked]

    assert len(names) == 2
    assert not any("2026-09-01" in n for n in names)


def test_select_reports_with_no_window_takes_everything(tmp_path):
    _write(tmp_path, "aapl", "fundamental_analysis_2026-09-18_gemini.md")
    _write(tmp_path, "aapl", "fundamental_analysis_2026-01-01_gemini.md")

    picked = rrq.select_reports([tmp_path], days=None, since=None, until=None,
                                ticker=None, limit=None)
    assert len(picked) == 2


def test_limit_caps_the_number_of_reports(tmp_path):
    for n in range(5):
        _write(tmp_path, "aapl", f"fundamental_analysis_2026-09-1{n}_gemini.md")

    picked = rrq.select_reports([tmp_path], days=None, since=None, until=None,
                                ticker=None, limit=2)
    assert len(picked) == 2


def test_missing_root_is_skipped_not_fatal(tmp_path):
    _write(tmp_path, "aapl", "fundamental_analysis_2026-09-18_gemini.md")
    picked = rrq.select_reports([tmp_path, tmp_path / "nope"], days=None,
                                since=None, until=None, ticker=None, limit=None)
    assert len(picked) == 1


# ── CSV output ───────────────────────────────────────────────────────────────

def _result(**over):
    base = dict(
        path="p", ticker="aapl", analysis_type="fundamental_analysis",
        date="2026-09-17", report_provider="gemini", reviewer_provider="openai",
        reviewer_model="gpt-4o-mini", verdict="pass", score=4,
        dimensions={k: 4 for k in rrq.DIMENSIONS}, issues=[], rationale="ok",
    )
    base.update(over)
    return rrq.ReviewResult(**base)


def test_csv_row_matches_the_header_width():
    assert len(_result().csv_row()) == len(rrq.CSV_HEADER)


def test_csv_writes_only_problem_rows_by_default(tmp_path):
    out = tmp_path / "r.csv"
    results = [_result(verdict="pass"), _result(verdict="fail"),
               _result(verdict="warn"), _result(verdict="ERROR")]

    written = rrq.write_csv(results, str(out), bad_only=True)

    assert written == 3  # fail + warn + ERROR, pass excluded
    assert out.read_text(encoding="utf-8").count("\n") == 4  # header + 3


def test_csv_all_writes_every_row(tmp_path):
    out = tmp_path / "r.csv"
    assert rrq.write_csv([_result(), _result()], str(out), bad_only=False) == 2


def test_issues_are_joined_into_one_cell(tmp_path):
    row = _result(issues=["問題甲", "問題乙"]).csv_row()
    assert "問題甲 | 問題乙" in row


# ── main / exit codes ────────────────────────────────────────────────────────

def test_dry_run_makes_no_api_calls(tmp_path):
    _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_gemini.md")
    with patch.object(rrq, "run_openai") as m:
        code = rrq.main(["--root", str(tmp_path), "--date", "2026-09-17", "--dry-run"])

    assert code == 0
    assert m.call_count == 0


def test_main_exits_zero_even_when_reports_fail(tmp_path):
    """Non-blocking by default, like check_mermaid.py — QA reports, it does not
    gate the nightly commit."""
    _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_gemini.md")
    with patch.object(rrq, "run_openai", return_value=_verdict_json(verdict="fail", score=1)):
        code = rrq.main(["--root", str(tmp_path), "--date", "2026-09-17", "--summary"])
    assert code == 0


def test_fail_on_fail_opts_into_a_nonzero_exit(tmp_path):
    _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_gemini.md")
    with patch.object(rrq, "run_openai", return_value=_verdict_json(verdict="fail", score=1)):
        code = rrq.main(["--root", str(tmp_path), "--date", "2026-09-17",
                         "--summary", "--fail-on-fail"])
    assert code == 1


def test_fail_on_fail_still_exits_zero_when_all_pass(tmp_path):
    _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_gemini.md")
    with patch.object(rrq, "run_openai", return_value=_verdict_json()):
        code = rrq.main(["--root", str(tmp_path), "--date", "2026-09-17",
                         "--summary", "--fail-on-fail"])
    assert code == 0


def test_empty_selection_still_writes_a_csv_with_a_header(tmp_path):
    """The workflow's README step counts CSV lines, so a no-report night must
    still leave a well-formed file rather than none."""
    out = tmp_path / "r.csv"
    code = rrq.main(["--root", str(tmp_path), "--date", "2026-09-17",
                     "--csv", str(out)])

    assert code == 0
    assert out.read_text(encoding="utf-8").strip() == ",".join(rrq.CSV_HEADER)


def test_main_writes_csv_end_to_end(tmp_path):
    _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_gemini.md")
    out = tmp_path / "r.csv"
    with patch.object(rrq, "run_openai", return_value=_verdict_json(verdict="fail", score=1)):
        rrq.main(["--root", str(tmp_path), "--date", "2026-09-17",
                  "--csv", str(out), "--summary"])

    body = out.read_text(encoding="utf-8")
    assert "fail" in body
    assert "aapl" in body
