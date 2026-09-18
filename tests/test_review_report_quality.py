"""Tests for the LLM-judge QA stage (scripts/review_report_quality.py).

Fully offline: every provider call is mocked at the ``analysis.llm`` runner
boundary, matching the rest of the suite. No API keys required.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date
from unittest.mock import patch

import pytest

import review_report_quality as rrq

pytestmark = pytest.mark.unit

FM = "---\ntitle: x\ndate: 2026-09-17\nprovider: gemini\n---\n\n"


def _library_stream_handlers():
    """Every ``analysis.*`` StreamHandler that route_library_logs_to_stderr
    would touch (FileHandler excluded, as it subclasses StreamHandler)."""
    for name in list(logging.Logger.manager.loggerDict):
        if "analysis" not in name:
            continue
        logger_obj = logging.getLogger(name)
        for handler in getattr(logger_obj, "handlers", []):
            if isinstance(handler, logging.StreamHandler) \
                    and not isinstance(handler, logging.FileHandler):
                yield logger_obj, handler


@pytest.fixture(autouse=True)
def _isolate_library_log_streams():
    """Undo route_library_logs_to_stderr()'s global mutation after each test.

    The routing rebinds handler streams process-wide. Left alone, a handler
    still pointing at one test's captured stream raises
    ValueError("I/O operation on closed file") from logging's flush in a later
    test — an order-dependent failure, since the suite randomises order.
    """
    before = [(lg, h, h.stream) for lg, h in _library_stream_handlers()]
    known = {id(h) for _, h, _ in before}

    yield

    for _, handler, stream in before:
        # Direct assignment, not setStream(): setStream flushes the *current*
        # stream before swapping, and by teardown that stream is the one
        # pytest just closed — the flush itself would raise.
        handler.stream = stream
    # Handlers created *during* the test (setup_logger caches per name) would
    # otherwise survive holding that test's stream.
    for logger_obj, handler in list(_library_stream_handlers()):
        if id(handler) not in known:
            logger_obj.removeHandler(handler)


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


def test_cross_provider_is_validated_before_any_api_call(monkeypatch, tmp_path):
    """One clear config error beats a hundred identical ERROR rows and the
    tokens spent producing them."""
    for env in rrq.PROVIDER_ENV.values():
        monkeypatch.delenv(env, raising=False)
    _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_openai.md")

    with patch.object(rrq, "run_openai") as m:
        code = rrq.main(["--root", str(tmp_path), "--date", "2026-09-17",
                         "--cross-provider", "--summary"])

    assert code == 1
    assert m.call_count == 0


def test_cross_provider_passes_validation_when_an_alternative_key_exists(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert rrq.validate_cross_provider("openai") is None


def test_validate_cross_provider_names_the_secrets_to_set(monkeypatch):
    for env in rrq.PROVIDER_ENV.values():
        monkeypatch.delenv(env, raising=False)
    msg = rrq.validate_cross_provider("openai")
    assert "GEMINI_API_KEY" in msg and "ANTHROPIC_API_KEY" in msg


# ── reviewer model follows the provider ──────────────────────────────────────

def test_model_override_applies_only_to_the_configured_provider():
    """A --cross-provider switch must not inherit the lead provider's model id:
    Gemini handed "gpt-4o-mini" fails every call."""
    assert rrq.reviewer_model_for("openai", "openai", "gpt-4o") == "gpt-4o"
    assert rrq.reviewer_model_for("gemini", "openai", "gpt-4o") == rrq.REVIEWER_MODELS["gemini"]


def test_every_provider_has_a_reviewer_model():
    assert set(rrq.REVIEWER_MODELS) == set(rrq.PROVIDER_ENV)


def test_cross_provider_switch_uses_the_new_providers_model(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_openai.md")

    with patch.object(rrq, "run_gemini", return_value=_verdict_json()) as gem:
        rrq.main(["--root", str(tmp_path), "--date", "2026-09-17",
                  "--cross-provider", "--summary"])

    assert gem.call_args.kwargs["model"] == rrq.REVIEWER_MODELS["gemini"]


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


def test_cross_provider_refuses_rather_than_self_grading(monkeypatch):
    """Silently self-grading would do the opposite of what --cross-provider
    asks while still reporting a verdict, so there is no reviewer to return."""
    for env in rrq.PROVIDER_ENV.values():
        monkeypatch.delenv(env, raising=False)
    assert rrq.pick_reviewer("openai", "openai", cross_provider=True) is None


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


# ── JSON shape validation (PR #65 review) ────────────────────────────────────
# Syntactically valid JSON says nothing about field types. Each of these used
# to raise from inside parse_verdict with an exception review_one did not
# catch, aborting the whole nightly batch.

@pytest.mark.parametrize("payload", [
    {"verdict": "pass", "dimensions": ["a", "b"]},      # was AttributeError
    {"verdict": "pass", "dimensions": "good"},
    {"verdict": "pass", "dimensions": 5},
    {"verdict": "pass", "issues": 5},                   # was TypeError
    {"verdict": "pass", "issues": {"a": 1}},
    {"verdict": "pass", "rationale": {"text": "x"}},
])
def test_wrong_field_shapes_raise_valueerror(payload):
    with pytest.raises(ValueError):
        rrq.parse_verdict(json.dumps(payload))


@pytest.mark.parametrize("payload", [
    {"verdict": "pass", "dimensions": ["a"]},
    {"verdict": "pass", "issues": 5},
])
def test_wrong_field_shapes_become_parse_error_rows_not_crashes(tmp_path, payload):
    p = _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_gemini.md")
    with patch.object(rrq, "run_openai", return_value=json.dumps(payload)):
        result = rrq.review_one(p, provider="openai", model="gpt-4o-mini")
    assert result.verdict == "PARSE_ERROR"


def test_a_batch_survives_a_malformed_response_in_the_middle(tmp_path):
    """The whole point of the ERROR/PARSE_ERROR rows: one bad response must
    not cost the other 99 reports."""
    for n in (5, 6, 7):
        _write(tmp_path, "aapl", f"fundamental_analysis_2026-09-1{n}_gemini.md")

    responses = [_verdict_json(), json.dumps({"dimensions": [1]}), _verdict_json()]
    with patch.object(rrq, "run_openai", side_effect=responses):
        code = rrq.main(["--root", str(tmp_path), "--date", "all", "--summary",
                         "--csv", str(tmp_path / "r.csv"), "--csv-all"])

    assert code == 0
    body = (tmp_path / "r.csv").read_text(encoding="utf-8")
    assert body.count("PARSE_ERROR") == 1
    assert body.count("pass") == 2


def test_empty_dimensions_object_is_accepted():
    assert rrq.parse_verdict(json.dumps({"verdict": "pass", "score": 4,
                                         "dimensions": {}}))["dimensions"] == {}


# ── verdict enforcement (PR #65 review) ──────────────────────────────────────

def test_a_pass_verdict_is_downgraded_when_a_dimension_fails():
    """verdict="pass" with data_integrity=1 would otherwise be filtered out of
    the problem CSV and never trip --fail-on-fail — exactly the case the
    reviewer exists to catch."""
    parsed = rrq.parse_verdict(_verdict_json(
        verdict="pass", score=5, dimensions={**{k: 5 for k in rrq.DIMENSIONS},
                                             "data_integrity": 1}))
    assert parsed["verdict"] == "fail"


def test_a_pass_verdict_is_downgraded_on_a_low_overall_score():
    assert rrq.parse_verdict(_verdict_json(verdict="pass", score=2))["verdict"] == "fail"


def test_score_three_is_downgraded_to_warn():
    assert rrq.parse_verdict(_verdict_json(verdict="pass", score=3))["verdict"] == "warn"


def test_weak_data_integrity_fails_even_with_a_good_overall_score():
    parsed = rrq.parse_verdict(_verdict_json(
        verdict="pass", score=4, dimensions={"data_integrity": 2, "depth": 5}))
    assert parsed["verdict"] == "fail"


def test_a_harsher_model_verdict_is_never_upgraded():
    """The model may be stricter than its own scores; it may not be laxer."""
    assert rrq.parse_verdict(_verdict_json(verdict="fail", score=5))["verdict"] == "fail"
    assert rrq.parse_verdict(_verdict_json(verdict="warn", score=5))["verdict"] == "warn"


def test_a_clean_pass_is_left_alone():
    assert rrq.parse_verdict(_verdict_json(
        verdict="pass", score=5,
        dimensions={k: 5 for k in rrq.DIMENSIONS}))["verdict"] == "pass"


def test_verdict_is_untouched_when_there_are_no_scores_to_judge():
    assert rrq.parse_verdict(json.dumps({"verdict": "pass"}))["verdict"] == "pass"


def test_a_downgraded_verdict_reaches_the_csv_and_the_exit_code(tmp_path):
    """End-to-end: enforcement has to survive into the artifacts, not just the
    parser's return value."""
    _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_gemini.md")
    out = tmp_path / "r.csv"
    contradictory = _verdict_json(verdict="pass", score=5,
                                  dimensions={"data_integrity": 1})

    with patch.object(rrq, "run_openai", return_value=contradictory):
        code = rrq.main(["--root", str(tmp_path), "--date", "2026-09-17",
                         "--csv", str(out), "--summary", "--fail-on-fail"])

    assert code == 1
    assert "fail" in out.read_text(encoding="utf-8")


# ── is_bad covers everything needing attention ───────────────────────────────

@pytest.mark.parametrize("verdict,bad", [
    ("pass", False), ("warn", True), ("fail", True),
    ("unknown", True), ("ERROR", True), ("PARSE_ERROR", True),
])
def test_is_bad_is_everything_but_a_clean_pass(verdict, bad):
    assert _result(verdict=verdict).is_bad() is bad


def test_an_unknown_verdict_is_not_filtered_out_of_the_csv(tmp_path):
    out = tmp_path / "r.csv"
    assert rrq.write_csv([_result(verdict="unknown")], str(out), bad_only=True) == 1


# ── limit guard (PR #65 review) ──────────────────────────────────────────────

def test_limit_zero_means_zero_reports_not_all_of_them(tmp_path):
    """`--limit 0` is falsy; treating it as "no limit" reviewed the whole
    corpus and billed for it."""
    for n in range(5):
        _write(tmp_path, "aapl", f"fundamental_analysis_2026-09-1{n}_gemini.md")

    picked = rrq.select_reports([tmp_path], days=None, since=None, until=None,
                                ticker=None, limit=0)
    assert picked == []


def test_limit_zero_makes_no_api_calls(tmp_path):
    _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_gemini.md")
    with patch.object(rrq, "run_openai") as m:
        code = rrq.main(["--root", str(tmp_path), "--date", "2026-09-17",
                         "--limit", "0", "--summary"])
    assert code == 0
    assert m.call_count == 0


# ── prompt-injection hardening (PR #65 review) ───────────────────────────────

def test_the_system_message_marks_report_content_as_untrusted():
    """Reports are model output built partly from scraped news/RSS text, so an
    attacker-controlled headline can reach this prompt. The delimiters aid
    clarity; this instruction is the actual boundary."""
    msg = rrq.REVIEWER_SYSTEM_MESSAGE
    assert "<report_data>" in msg
    assert "不可信" in msg
    assert "忽略" in msg


def test_the_report_is_wrapped_in_named_delimiters(tmp_path):
    p = _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_gemini.md")
    with patch.object(rrq, "run_openai", return_value=_verdict_json()) as m:
        rrq.review_one(p, provider="openai", model="gpt-4o-mini")

    prompt = m.call_args.args[1]
    assert "<report_data>" in prompt and "</report_data>" in prompt
    assert prompt.index("<report_data>") < prompt.index("</report_data>")


def test_the_hardened_system_message_is_sent_to_every_provider(tmp_path):
    p = _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_gemini.md")
    runners = {"run_openai": "openai", "run_gemini": "gemini", "run_claude": "claude"}
    for runner, provider in runners.items():
        with patch.object(rrq, runner, return_value=_verdict_json()) as m:
            rrq.review_one(p, provider=provider,
                           model=rrq.REVIEWER_MODELS[provider])
        assert m.call_args.args[2] == rrq.REVIEWER_SYSTEM_MESSAGE, runner


# ── stdout is a data channel, not a log channel ──────────────────────────────
# The first live CI run wrote ~400 lines of per-call INFO logging into the
# committed qa/llm_review_<date>.txt, because analysis.utils.logging_utils
# attaches its handler to stdout and the workflow tees stdout into that file.
# The workflow then embeds the file in qa/README.md, which grew by 432 lines.

def test_library_log_handlers_are_moved_off_stdout():
    import logging
    from analysis.utils.logging_utils import setup_logger

    logger = setup_logger("analysis.test.route", level=logging.INFO)
    handler = logger.handlers[0]
    handler.setStream(sys.stdout)          # the shipped default
    assert handler.stream is sys.stdout

    moved = rrq.route_library_logs_to_stderr()

    assert moved >= 1
    assert handler.stream is sys.stderr


def test_routing_is_idempotent():
    rrq.route_library_logs_to_stderr()
    assert rrq.route_library_logs_to_stderr() == 0


def test_the_llm_modules_own_logger_lands_on_stderr():
    """The noisy one in practice: run_openai logs two INFO lines per report."""
    import analysis.utils.llm as llm_mod

    for h in llm_mod.logger.handlers:
        if isinstance(h, logging.StreamHandler):
            h.setStream(sys.stdout)

    rrq.route_library_logs_to_stderr()

    streams = [h.stream for h in llm_mod.logger.handlers
               if isinstance(h, logging.StreamHandler)]
    assert streams and all(s is sys.stderr for s in streams)


def test_stdout_carries_only_the_summary_not_library_logs(tmp_path, capsys):
    """End-to-end guard on the artifact's contents: what the workflow tees
    must be the summary alone."""
    _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_gemini.md")

    def _logging_runner(ticker, prompt, system_message, **kw):
        # Stand in for run_openai's real per-call INFO logging.
        logging.getLogger("analysis.utils.llm").info(
            "Response: input=26000, output=249, total=26249, chars=409")
        return _verdict_json()

    with patch.object(rrq, "run_openai", side_effect=_logging_runner):
        rrq.main(["--root", str(tmp_path), "--date", "2026-09-17", "--summary"])

    out = capsys.readouterr().out
    assert "Reports reviewed" in out          # the summary is present
    assert "[INFO" not in out                 # the noise is not
    assert "total=26249" not in out


# ── --limit plumbing for cheap model comparisons ─────────────────────────────

def test_limit_selection_is_deterministic_across_runs(tmp_path):
    """Two runs with the same cap must grade the same reports, or a
    model-vs-model comparison is not like-for-like."""
    for t in ("msft", "aapl", "nvda", "goog"):
        _write(tmp_path, t, "fundamental_analysis_2026-09-17_gemini.md")

    kwargs = dict(days=None, since=None, until=None, ticker=None, limit=2)
    first = rrq.select_reports([tmp_path], **kwargs)
    second = rrq.select_reports([tmp_path], **kwargs)

    assert first == second
    assert len(first) == 2


def test_limit_caps_the_api_calls_end_to_end(tmp_path):
    for n in range(5):
        _write(tmp_path, "aapl", f"fundamental_analysis_2026-09-1{n}_gemini.md")

    with patch.object(rrq, "run_openai", return_value=_verdict_json()) as m:
        rrq.main(["--root", str(tmp_path), "--date", "all", "--limit", "2",
                  "--summary"])

    assert m.call_count == 2


# ── grounding filter ─────────────────────────────────────────────────────────
# Two live gpt-4o-mini runs agreed closely on scores, so the judge is
# reproducible — but ~25 rows per run scored 1 on all five dimensions with
# template prose and no citations, and at least one was checkably false. These
# tests pin the split between that boilerplate and the genuinely grounded rows.

ALL_ONES = {k: 1 for k in rrq.DIMENSIONS}
MIXED = {"data_integrity": 2, "completeness": 3, "depth": 2,
         "consistency": 3, "language": 4}


def test_cited_figures_ignores_bare_small_numbers():
    """"1" and "5" occur in every report, so matching them would call any
    complaint grounded."""
    assert rrq.cited_figures(["第 1 章有 5 個問題"]) == []


def test_cited_figures_picks_up_decimals_and_long_integers():
    figures = rrq.cited_figures(["TTM 營收 $90.27B（YoY +345.7%）", "成長 454%"])
    assert "90.27" in figures
    assert "345.7" in figures
    assert "454" in figures


def test_cited_figures_deduplicates_preserving_order():
    assert rrq.cited_figures(["41.31 then 41.31 then 89.10"]) == ["41.31", "89.10"]


def test_a_pass_needs_no_evidence():
    assert rrq.verdict_is_grounded("pass", ALL_ONES, [], "報告內容") is True


@pytest.mark.parametrize("verdict", ["ERROR", "PARSE_ERROR", "unknown"])
def test_non_complaint_verdicts_are_not_held_to_the_bar(verdict):
    assert rrq.verdict_is_grounded(verdict, {}, [], "") is True


def test_all_ones_with_no_citation_is_ungrounded():
    """The boilerplate signature: bottom scores across the board, template
    prose, nothing checkable."""
    issues = ["報告中出現多處捏造數據，例如對於營收和利潤率的數字缺乏來源脈絡。"]
    assert rrq.verdict_is_grounded("fail", ALL_ONES, issues, "報告內容") is False


def test_all_ones_is_kept_when_it_quotes_a_real_figure():
    """About 6 of 25 all-ones rows did cite a real number; those are real
    findings and must survive."""
    issues = ["TTM 營收達 $90.27B 不符合實際情況。"]
    report = "本季 TTM 營收 $90.27B，成長強勁。"
    assert rrq.verdict_is_grounded("fail", ALL_ONES, issues, report) is True


def test_all_ones_quoting_a_figure_absent_from_the_report_is_ungrounded():
    issues = ["營收 $12.34B 無法查證。"]
    assert rrq.verdict_is_grounded("fail", ALL_ONES, issues, "營收 $99.99B") is False


def test_a_graded_verdict_is_kept_even_without_citations():
    """2/3/2/3/4 is a considered judgement; only the degenerate pattern is
    filtered, so prose-only reasoning at mixed scores stays."""
    issues = ["分析深度不足，多處僅重述數據。"]
    assert rrq.verdict_is_grounded("fail", MIXED, issues, "報告內容") is True


def test_partial_dimensions_are_not_treated_as_all_ones():
    """A single reported dimension at 1 is not the all-five pattern."""
    assert rrq.verdict_is_grounded("fail", {"depth": 1}, ["深度不足"], "x") is True


# ── the two real cases from the live runs ────────────────────────────────────

def test_the_real_msft_false_positive_is_quarantined():
    """msft was flagged for "$XXX"/"N/A" placeholders that appear nowhere in
    its 79 KB report, at 1s across all five dimensions."""
    issues = ["報告中出現多處未填值的佔位符，如「$XXX」、「N/A」等。"]
    report = "## 1. 營收分析\nFY26 營收 $331.84B，ROIC 29.58%。\n"
    assert rrq.verdict_is_grounded("fail", ALL_ONES, issues, report) is False


def test_the_real_mu_catch_survives():
    """mu's "$90.27B" TTM revenue is a genuine fabrication (actual ≈ $37B)
    that the rule-based stage passed clean — the whole point of stage 2."""
    issues = ["報告中出現多處捏造數據，例如 TTM 營收達 $90.27B（YoY +345.7%）不符合實際情況。"]
    report = "TTM 營收 $90.27B  (100.0%)，YoY +345.7%。"
    assert rrq.verdict_is_grounded("fail", ALL_ONES, issues, report) is True


# ── plumbing: result, CSV, summary, exit code ────────────────────────────────

def test_review_one_marks_a_boilerplate_verdict_ungrounded(tmp_path):
    p = _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_gemini.md")
    response = _verdict_json(verdict="fail", score=1, dimensions=ALL_ONES,
                             issues=["報告中出現多處捏造數據。"])
    with patch.object(rrq, "run_openai", return_value=response):
        result = rrq.review_one(p, provider="openai", model="gpt-4o-mini")

    assert result.verdict == "fail"
    assert result.grounded is False
    assert result.is_bad() is True                  # still in the CSV
    assert result.counts_against_quality() is False  # but not in the counts


def test_review_one_marks_a_cited_verdict_grounded(tmp_path):
    body = FM + "## 分析\nTTM 營收 $90.27B，成長強勁。\n"
    p = _write(tmp_path, "mu", "fundamental_analysis_2026-09-17_gemini.md", body)
    response = _verdict_json(verdict="fail", score=1, dimensions=ALL_ONES,
                             issues=["TTM 營收 $90.27B 不符合實際情況。"])
    with patch.object(rrq, "run_openai", return_value=response):
        result = rrq.review_one(p, provider="openai", model="gpt-4o-mini")

    assert result.grounded is True
    assert result.counts_against_quality() is True


def test_grounding_uses_the_full_report_not_the_elided_copy(tmp_path):
    """A figure quoted from a section that was elided before sending is still
    a real citation."""
    body = FM + "頭" * 200 + "\n關鍵數字 4321.99\n" + "尾" * 200
    p = _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_gemini.md", body)
    response = _verdict_json(verdict="fail", score=1, dimensions=ALL_ONES,
                             issues=["數字 4321.99 無法查證。"])

    with patch.object(rrq, "MAX_REPORT_CHARS", 120), \
            patch.object(rrq, "run_openai", return_value=response) as m:
        result = rrq.review_one(p, provider="openai", model="gpt-4o-mini")

    assert "4321.99" not in m.call_args.args[1]   # elided out of the prompt
    assert result.grounded is True                # but still grounded


def test_csv_has_a_grounded_column_matching_the_header():
    row = _result(grounded=False).csv_row()
    assert len(row) == len(rrq.CSV_HEADER)
    assert row[rrq.CSV_HEADER.index("grounded")] == "no"
    assert _result(grounded=True).csv_row()[rrq.CSV_HEADER.index("grounded")] == "yes"


def test_ungrounded_rows_stay_in_the_csv_for_auditing(tmp_path):
    out = tmp_path / "r.csv"
    assert rrq.write_csv([_result(verdict="fail", grounded=False)],
                         str(out), bad_only=True) == 1


def test_summary_counts_only_grounded_verdicts(capsys):
    results = [_result(verdict="fail", grounded=True),
               _result(verdict="fail", grounded=False),
               _result(verdict="fail", grounded=False)]
    rrq.print_summary(results)
    out = capsys.readouterr().out

    assert "Reports reviewed : 3" in out
    assert "Ungrounded       : 2" in out
    assert "Verdict breakdown (1 grounded)" in out


def test_summary_omits_the_ungrounded_line_when_there_are_none(capsys):
    rrq.print_summary([_result(verdict="pass", grounded=True)])
    assert "Ungrounded" not in capsys.readouterr().out


def test_fail_on_fail_ignores_an_ungrounded_fail(tmp_path):
    """A bad review must not fail a build; only a bad report may."""
    _write(tmp_path, "aapl", "fundamental_analysis_2026-09-17_gemini.md")
    response = _verdict_json(verdict="fail", score=1, dimensions=ALL_ONES,
                             issues=["報告中出現多處捏造數據。"])
    with patch.object(rrq, "run_openai", return_value=response):
        code = rrq.main(["--root", str(tmp_path), "--date", "2026-09-17",
                         "--summary", "--fail-on-fail"])
    assert code == 0


def test_fail_on_fail_still_trips_on_a_grounded_fail(tmp_path):
    body = FM + "## 分析\nTTM 營收 $90.27B。\n"
    _write(tmp_path, "mu", "fundamental_analysis_2026-09-17_gemini.md", body)
    response = _verdict_json(verdict="fail", score=1, dimensions=ALL_ONES,
                             issues=["TTM 營收 $90.27B 不符合實際情況。"])
    with patch.object(rrq, "run_openai", return_value=response):
        code = rrq.main(["--root", str(tmp_path), "--date", "2026-09-17",
                         "--summary", "--fail-on-fail"])
    assert code == 1


# ── rubric content (PR #68) ──────────────────────────────────────────────────
# The third live run's 54 grounded fails were audited against the reports:
# 38 complained that input figures lack a cited source, which the pipeline can
# never provide (the data context is not reproduced in the report body); 3
# complained that the report's *own* DCF outputs were unsourced (amd's
# "加權合理價值 $619.64" is derived in its Ch.8); and soxq was failed for a
# data anomaly the report itself had correctly flagged and restated. All three
# were rubric defects, so the rubric now rules them out explicitly. These
# tests stop the rules being dropped by a later edit.

def _rubric() -> str:
    from analysis.prompts import load_prompt
    return load_prompt("qa_review")


def test_missing_sources_is_explicitly_not_a_defect():
    """38 of 54 grounded fails cited this; the reports structurally cannot
    satisfy it, so it inflated every fail count."""
    text = _rubric()
    assert "未提供來源" in text
    assert "不是缺陷" in text


def test_self_derived_valuations_count_as_sourced():
    """amd's 加權合理價值 $619.64 is computed in its own DCF chapter, so
    'source unknown' was simply false."""
    text = _rubric()
    assert "加權合理價值" in text
    assert "報告自身的估值模型" in text


def test_self_flagged_anomalies_are_credited_not_penalised():
    """soxq flagged its own distorted 31.0% yield and restated it at 1.15%;
    the judge failed it for the honesty."""
    text = _rubric()
    assert "自行標註的數據異常" in text
    assert "良好實務" in text


def test_low_scores_must_carry_traceable_evidence():
    """States the rule the grounding filter already enforces, so a row is not
    quarantined for breaking a rule it was never told."""
    text = _rubric()
    assert "證據要求" in text
    assert "ungrounded" in text


def test_placeholder_claims_must_be_confirmed_first():
    """msft and wqtm were both flagged for placeholders that were absent or
    near-absent (wqtm: N/A x1, TBD x0)."""
    assert "再寫進 issues" in _rubric()


def test_the_unsatisfiable_criterion_is_gone():
    """The original line asked whether every figure carried source context."""
    assert "具體數字是否有來源脈絡，而非憑空出現" not in _rubric()


def test_genuine_fabrication_is_still_a_fail():
    """The rubric must not become permissive: mu's implausible figures are
    exactly what this stage is for."""
    text = _rubric()
    assert "捏造" in text
    assert "1-2 分" in text


def test_rubric_still_renders_with_every_placeholder():
    from analysis.prompts import load_prompt
    rendered = load_prompt("qa_review").format(
        ticker="AAPL", analysis_type="fundamental_analysis",
        date="2026-09-17", provider="gemini", report="BODY")
    for placeholder in ("{ticker}", "{report}", "{provider}",
                        "{analysis_type}", "{date}"):
        assert placeholder not in rendered
    assert '"verdict"' in rendered      # JSON schema survived {{ }} escaping
    assert '"data_integrity"' in rendered


def test_rubric_overhead_stays_small_next_to_the_report():
    """The prompt is prepended to every ~27k-token report, so its own size is
    a per-report cost multiplied by ~117 reports a night."""
    overhead = len(_rubric()) - len("{report}")
    assert overhead < 6000, f"rubric grew to {overhead} chars"
