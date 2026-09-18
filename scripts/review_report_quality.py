#!/usr/bin/env python3
"""
review_report_quality.py — LLM-judge quality review of generated reports.

This is the *second* stage of the QA audit and is deliberately additive:

  * ``check_report_quality.py`` (stage 1) is a deterministic, pure-stdlib,
    zero-cost regex gate. It catches mechanical failures — empty files,
    refusals, truncation, placeholders, unrenderable Mermaid. It stays the
    primary gate and is unchanged by this script.
  * ``review_report_quality.py`` (stage 2, this file) asks an LLM to grade what
    regex cannot see: fabricated numbers, shallow "restate the data" analysis,
    a conclusion that contradicts its own evidence, simplified-Chinese leakage.

Stage 2 costs money per report, so it defaults to a **rolling 2-day window**
(~100-200 reports, see --days). Two days, not one: report-gen crons run
17:00-03:00 UTC, so one generation cycle straddles midnight and lands under two
different date stamps. Pointing this at the whole corpus (7k+ reports) is
possible but expensive — use --limit if you try.

Why a separate model constant instead of ``resolve_chain()``: that chain is the
*generation* fallback pool. Reusing it here would mean that changing the report
generator's OpenAI model silently re-points the auditor too. The reviewer's
model is its own decision, so it lives in ``REVIEWER_MODEL`` below.

Usage:
  python3 scripts/review_report_quality.py --summary            # last 2 UTC days
  python3 scripts/review_report_quality.py --date 2026-09-17 --csv qa/llm_review.csv
  python3 scripts/review_report_quality.py --ticker aapl --limit 5 --verbose
  python3 scripts/review_report_quality.py --cross-provider     # never self-grade

Exit code is 0 even when reports fail review (like check_mermaid.py, this
reports rather than blocks). Pass --fail-on-fail to exit 1 on any "fail".
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from analysis.llm import run_claude, run_openai, run_gemini  # noqa: E402
from analysis.prompts import load_prompt  # noqa: E402
from analysis.validate import DATE_RE, collect_reports, parse_file  # noqa: E402

# ── reviewer configuration ───────────────────────────────────────────────────
# The judge emits ~300 tokens, so its own output cap is irrelevant to cost —
# the driver is *input* volume (one day of fundamental+technical reports is
# ~3.8 MB of mostly-CJK markdown). A mini-class model is therefore the default;
# override with --model when a run needs sharper judgement.
REVIEWER_PROVIDER = "openai"
REVIEWER_MODEL = "gpt-4o-mini"
REVIEWER_MAX_TOKENS = 1200
# 0.0: a grader should return the same verdict for the same report.
REVIEWER_TEMPERATURE = 0.0
# Report-gen crons run 17:00-03:00 UTC, so the nightly QA run at 02:00 UTC must
# look back two calendar days to cover one generation cycle. See recent_days().
DEFAULT_WINDOW_DAYS = 2

REVIEWER_SYSTEM_MESSAGE = (
    "你是一位嚴格但公正的投資研究主編，負責審核 AI 產出的分析報告品質。"
    "你只輸出 JSON，不輸出任何其他文字。"
    "你不撰寫報告，也不補充自己的市場觀點——只做品質判斷。"
)

# Reports are graded whole so the judge can see the ending (truncation,
# conclusion-vs-evidence consistency). Past this many characters the middle is
# elided rather than the tail dropped, because dropping the tail would make
# every long report look truncated. ~80k chars covers every report in the
# corpus today; the elision path exists so an outlier cannot blow up one call.
MAX_REPORT_CHARS = 80_000
_ELISION_MARKER = (
    "\n\n…（為控制審稿成本，此處省略了報告中段內容；"
    "省略屬於審稿流程，不代表原報告不完整）…\n\n"
)

VERDICTS = ("pass", "warn", "fail")
DIMENSIONS = ("data_integrity", "completeness", "depth", "consistency", "language")

AI_GEN_REPORT = Path(__file__).parent.parent / "ai_gen_report"
# market_news is included here even though stage 1 omits it (see PR notes):
# this stage is new code, so covering it adds no regression risk.
DEFAULT_ROOTS = [
    AI_GEN_REPORT / "fundamental",
    AI_GEN_REPORT / "technical",
    AI_GEN_REPORT / "stock",
    AI_GEN_REPORT / "market_news",
]

PROVIDER_ENV = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
}
# Fallback used by --cross-provider when the report's own generator is the
# configured reviewer. Ordered by preference.
CROSS_PROVIDER_ALTERNATIVES = ["gemini", "claude", "openai"]


# ── data model ───────────────────────────────────────────────────────────────
@dataclass
class ReviewResult:
    path: str
    ticker: str
    analysis_type: str
    date: str
    report_provider: str
    reviewer_provider: str
    reviewer_model: str
    verdict: str
    score: int = 0
    dimensions: dict = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    rationale: str = ""

    def is_bad(self) -> bool:
        return self.verdict in ("fail", "warn")

    def csv_row(self) -> list:
        d = self.dimensions
        return [
            self.path, self.ticker, self.analysis_type, self.date,
            self.report_provider, self.reviewer_provider, self.reviewer_model,
            self.verdict, self.score,
            *[d.get(k, "") for k in DIMENSIONS],
            " | ".join(self.issues),
            self.rationale,
        ]


CSV_HEADER = [
    "path", "ticker", "analysis_type", "date",
    "report_provider", "reviewer_provider", "reviewer_model",
    "verdict", "score", *DIMENSIONS, "issues", "rationale",
]


# ── report text preparation ──────────────────────────────────────────────────
def prepare_report_text(text: str, max_chars: int = MAX_REPORT_CHARS) -> str:
    """Return ``text`` bounded to ``max_chars``, eliding the middle if needed.

    Head and tail are both preserved (60/40) so the judge can still assess the
    conclusion and spot a genuinely truncated ending.
    """
    if len(text) <= max_chars:
        return text
    budget = max_chars - len(_ELISION_MARKER)
    head = int(budget * 0.6)
    tail = budget - head
    return text[:head] + _ELISION_MARKER + text[-tail:]


# ── verdict parsing ──────────────────────────────────────────────────────────
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _extract_json_object(text: str) -> dict:
    """Pull the first JSON object out of a model response.

    Tolerates ```json fences and stray prose around the object — both of which
    models emit despite being told not to. Raises ValueError if nothing parses.
    """
    stripped = _FENCE_RE.sub("", (text or "").strip())
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        pass
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in response")
    return json.loads(stripped[start:end + 1])


def _clamp_score(value, default: int = 0) -> int:
    """Coerce a model-supplied score to an int in 1..5 (``default`` if absent)."""
    try:
        return max(1, min(5, int(value)))
    except (TypeError, ValueError):
        return default


def parse_verdict(text: str) -> dict:
    """Parse and normalise the judge's JSON response.

    Returns a dict with the keys ``verdict``, ``score``, ``dimensions``,
    ``issues`` and ``rationale``, all sanitised. A model that returns an
    unknown verdict or a malformed score does not crash the run — the value is
    normalised, and an unparseable response raises ValueError for the caller to
    record as a PARSE_ERROR row.
    """
    data = _extract_json_object(text)
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object, got {type(data).__name__}")

    verdict = str(data.get("verdict", "")).strip().lower()
    if verdict not in VERDICTS:
        verdict = "unknown"

    raw_dims = data.get("dimensions") or {}
    dims = {k: _clamp_score(raw_dims.get(k)) for k in DIMENSIONS
            if raw_dims.get(k) is not None}

    score = _clamp_score(data.get("score"))
    if not score and dims:
        # Model gave per-dimension scores but no overall one — take the floor,
        # which matches the rubric's "any dimension at 1 is a fail" rule.
        score = min(dims.values())

    issues = data.get("issues") or []
    if isinstance(issues, str):
        issues = [issues]
    issues = [str(i).strip().replace("\n", " ") for i in issues if str(i).strip()][:5]

    return {
        "verdict": verdict,
        "score": score,
        "dimensions": dims,
        "issues": issues,
        "rationale": str(data.get("rationale", "")).strip().replace("\n", " "),
    }


# ── the review call ──────────────────────────────────────────────────────────
def _dispatch(provider: str, ticker: str, prompt: str, model: str,
              max_tokens: int) -> str:
    """Call one provider's generic runner with the review prompt.

    ``refusal_retry=False`` on every path: the refusal-override machinery in
    analysis.llm prepends "你必須產出完整分析報告" instructions, which is right
    for report *generation* and actively wrong for a grader — it would push the
    judge to write a report instead of a verdict.
    """
    if provider == "openai":
        return run_openai(ticker, prompt, REVIEWER_SYSTEM_MESSAGE, model=model,
                          max_tokens=max_tokens, temperature=REVIEWER_TEMPERATURE,
                          refusal_retry=False)
    if provider == "gemini":
        return run_gemini(ticker, prompt, REVIEWER_SYSTEM_MESSAGE, model=model,
                          max_tokens=max_tokens, temperature=REVIEWER_TEMPERATURE,
                          refusal_retry=False, recover_truncation=False)
    return run_claude(ticker, prompt, REVIEWER_SYSTEM_MESSAGE, model=model,
                      max_tokens=max_tokens, temperature=REVIEWER_TEMPERATURE,
                      refusal_retry=False)


def review_one(path: Path, *, provider: str, model: str,
               max_tokens: int = REVIEWER_MAX_TOKENS) -> ReviewResult:
    """Grade a single report file. Never raises — failures become result rows.

    A provider error or an unparseable response on one report must not abort a
    100-report nightly run, so both are recorded as ERROR / PARSE_ERROR
    verdicts and the scan continues.
    """
    meta = parse_file(path)
    base = dict(
        path=str(path), ticker=meta.ticker, analysis_type=meta.analysis_type,
        date=meta.date, report_provider=meta.provider,
        reviewer_provider=provider, reviewer_model=model,
    )

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return ReviewResult(**base, verdict="ERROR", rationale=f"read failed: {e}")

    prompt = load_prompt("qa_review").format(
        ticker=meta.ticker or path.parent.name,
        analysis_type=meta.analysis_type,
        date=meta.date,
        provider=meta.provider,
        report=prepare_report_text(text),
    )

    try:
        response = _dispatch(provider, meta.ticker, prompt, model, max_tokens)
    except Exception as e:  # noqa: BLE001 — one bad call must not end the run
        return ReviewResult(**base, verdict="ERROR",
                            rationale=f"{type(e).__name__}: {e}"[:300])

    try:
        parsed = parse_verdict(response)
    except (ValueError, json.JSONDecodeError) as e:
        return ReviewResult(**base, verdict="PARSE_ERROR",
                            rationale=f"{e}: {(response or '')[:160]!r}")

    return ReviewResult(**base, **parsed)


def pick_reviewer(report_provider: str, configured: str,
                  cross_provider: bool) -> str:
    """Choose the grading provider for one report.

    With ``--cross-provider``, a report is never graded by the model family
    that wrote it: reports are generated gemini→openai, and self-grading is the
    one bias this repo can cheaply avoid because ``parse_file`` already records
    each report's generating provider in its frontmatter.
    """
    if not cross_provider or report_provider != configured:
        return configured
    for alt in CROSS_PROVIDER_ALTERNATIVES:
        if alt != report_provider and os.environ.get(PROVIDER_ENV[alt]):
            return alt
    return configured  # no alternative has a key — self-grade rather than skip


# ── file selection ───────────────────────────────────────────────────────────
def recent_days(days: int, today: Optional[date] = None) -> List[str]:
    """Return the last ``days`` calendar dates (UTC), newest first.

    Why a window and not just "today": report generation runs on crons from
    17:00 to 03:00 UTC (see daily_analysis.yml), so it straddles midnight and
    each report is stamped with the UTC date at *generation* time. A QA run at
    02:00 UTC therefore has to look at yesterday as well, or it silently skips
    the 17:00–23:00 batch — which is the majority of the day's output.
    """
    base = today or datetime.now(timezone.utc).date()
    return [(base - timedelta(days=n)).isoformat() for n in range(days)]


def select_reports(roots: List[Path], *, days: Optional[List[str]],
                   since: Optional[str], until: Optional[str],
                   ticker: Optional[str], limit: Optional[int]) -> List[Path]:
    """Collect report paths to review.

    ``days`` (a list of YYYY-MM-DD stamps, or None for no date filter) is the
    cost control that makes a nightly run viable: ``collect_reports`` filters by
    month, so the exact-date narrowing happens here rather than by widening the
    shared validate helper.
    """
    paths = sorted({
        p for r in roots if r.exists()
        for p in collect_reports(r, since, until, ticker)
    })
    if days:
        wanted = set(days)
        paths = [p for p in paths
                 if (m := DATE_RE.search(p.name)) and m.group(1) in wanted]
    return paths[:limit] if limit else paths


# ── reporting ────────────────────────────────────────────────────────────────
def print_summary(results: List[ReviewResult], out=sys.stdout) -> None:
    verdicts = Counter(r.verdict for r in results)
    scored = [r.score for r in results if r.score]

    print(f"\n{'=' * 60}", file=out)
    print(f"Reports reviewed : {len(results)}", file=out)
    if scored:
        print(f"Mean score       : {sum(scored) / len(scored):.2f} / 5", file=out)
    print("\nVerdict breakdown:", file=out)
    for verdict in (*VERDICTS, "unknown", "PARSE_ERROR", "ERROR"):
        if verdicts.get(verdict):
            print(f"  {verdict:<14} {verdicts[verdict]:>5}", file=out)

    per_dim = {
        k: [r.dimensions[k] for r in results if k in r.dimensions]
        for k in DIMENSIONS
    }
    if any(per_dim.values()):
        print("\nMean score by dimension:", file=out)
        for k, vals in per_dim.items():
            if vals:
                print(f"  {k:<16} {sum(vals) / len(vals):.2f}", file=out)

    failures = [r for r in results if r.verdict == "fail"]
    if failures:
        print(f"\nFailed review ({len(failures)}):", file=out)
        for r in failures[:20]:
            first = r.issues[0] if r.issues else r.rationale
            print(f"  {r.ticker:<12} {r.analysis_type:<28} {r.path}", file=out)
            print(f"      → {first[:110]}", file=out)


def write_csv(results: List[ReviewResult], csv_path: str, bad_only: bool) -> int:
    rows = [r for r in results if r.is_bad() or r.verdict in ("ERROR", "PARSE_ERROR")] \
        if bad_only else results
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADER)
        for r in rows:
            w.writerow(r.csv_row())
    return len(rows)


# ── main ─────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=None,
                   help="Single root to scan (default: ai_gen_report/"
                        "{fundamental,technical,stock,market_news})")
    p.add_argument("--date", default=None, metavar="YYYY-MM-DD",
                   help="Review only reports stamped this exact date. "
                        "Pass --date all to lift the date filter — expensive. "
                        "Omit to use the --days rolling window.")
    p.add_argument("--days", type=int, default=DEFAULT_WINDOW_DAYS,
                   help="Review reports from the last N UTC days when --date is "
                        f"not given (default: {DEFAULT_WINDOW_DAYS}; report-gen "
                        "crons straddle midnight, so 1 would miss the 17:00-23:00 batch)")
    p.add_argument("--since", metavar="YYYY-MM", help="Only files from this month onward")
    p.add_argument("--until", metavar="YYYY-MM", help="Only files up to this month")
    p.add_argument("--ticker", help="Filter to a single ticker")
    p.add_argument("--provider", default=REVIEWER_PROVIDER,
                   choices=sorted(PROVIDER_ENV), help=f"Reviewer provider (default: {REVIEWER_PROVIDER})")
    p.add_argument("--model", default=REVIEWER_MODEL,
                   help=f"Reviewer model (default: {REVIEWER_MODEL})")
    p.add_argument("--max-tokens", type=int, default=REVIEWER_MAX_TOKENS,
                   help=f"Reviewer output budget (default: {REVIEWER_MAX_TOKENS})")
    p.add_argument("--cross-provider", action="store_true",
                   help="Never let a provider grade a report it generated")
    p.add_argument("--limit", type=int, default=None,
                   help="Review at most N reports (cost guard)")
    p.add_argument("--csv", metavar="PATH", help="Write results to CSV")
    p.add_argument("--csv-all", action="store_true",
                   help="Write every reviewed report to the CSV, not just problems")
    p.add_argument("--summary", action="store_true",
                   help="Print the summary only (no per-file lines)")
    p.add_argument("--verbose", action="store_true",
                   help="Print a line for every report, not just problems")
    p.add_argument("--dry-run", action="store_true",
                   help="List the reports that would be reviewed, make no API calls")
    p.add_argument("--fail-on-fail", action="store_true",
                   help="Exit 1 if any report is graded 'fail' (default: always exit 0)")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.date == "all":
        days = None
    elif args.date:
        days = [args.date]
    else:
        days = recent_days(max(1, args.days))

    roots = [Path(args.root)] if args.root else DEFAULT_ROOTS
    if not [r for r in roots if r.exists()]:
        print(f"ERROR: no root directory found: {args.root or DEFAULT_ROOTS}",
              file=sys.stderr)
        return 1

    paths = select_reports(roots, days=days, since=args.since, until=args.until,
                           ticker=args.ticker, limit=args.limit)
    scope = f"dates={','.join(days)}" if days else "all dates"
    print(f"Reviewing {len(paths)} reports ({scope}) with "
          f"{args.provider}:{args.model}…\n", file=sys.stderr)

    if args.dry_run:
        for p in paths:
            print(f"  would review {p}", file=sys.stderr)
        return 0

    if not paths:
        print("Nothing to review.", file=sys.stderr)
        if args.csv:
            write_csv([], args.csv, bad_only=not args.csv_all)
        return 0

    results: List[ReviewResult] = []
    for n, path in enumerate(paths, 1):
        meta = parse_file(path)
        provider = pick_reviewer(meta.provider, args.provider, args.cross_provider)
        result = review_one(path, provider=provider, model=args.model,
                            max_tokens=args.max_tokens)
        results.append(result)
        if not args.summary and (args.verbose or result.is_bad()
                                 or result.verdict in ("ERROR", "PARSE_ERROR")):
            print(f"[{n}/{len(paths)}] {result.verdict:<12} score={result.score} "
                  f"{result.ticker:<12} {result.analysis_type:<28} {path}")
            for issue in result.issues:
                print(f"      · {issue}")

    print_summary(results)

    if args.csv:
        written = write_csv(results, args.csv, bad_only=not args.csv_all)
        print(f"\nCSV written → {args.csv} ({written} row(s))")

    if args.fail_on_fail and any(r.verdict == "fail" for r in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
