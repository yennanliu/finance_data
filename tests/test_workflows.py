"""Invariants for the GitHub Actions workflows in .github/workflows/.

A scheduled run knows only its own cron string, so each cron entry has to be
mapped back to a ticker by a shell `case` arm. Nothing at runtime pairs the two
lists, which is how CLAUDE.md ended up documenting "add a ticker" as an edit in
two places: miss the case arm and the run used to publish a duplicate TSLA
report instead of failing. The workflow now errors on an unmapped cron; these
tests catch the same mistake before it is ever pushed.

Parsed with regex rather than a YAML library on purpose — the repo ships no
YAML dependency, and the two constructs under test are single-line forms.
"""

import re
from pathlib import Path

import pytest

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"

# Workflows that fan a single job out over one cron slot per ticker.
SCHEDULED_FANOUT = ["daily_analysis.yml", "daily_market_news.yml"]

CRON_RE = re.compile(r'^\s*- cron:\s*"([^"]+)"', re.MULTILINE)
CASE_ARM_RE = re.compile(r'^\s*"([^"]+)"\)\s+TICKER=', re.MULTILINE)
# The whole right-hand side of an arm, i.e. what the slot actually generates:
# TICKER alone is not it — daily_analysis maps each ticker twice, once per
# ANALYSIS_TYPE.
CASE_TARGET_RE = re.compile(
    r'^\s*"([^"]+)"\)\s+(TICKER=.*?)\s*;;\s*$', re.MULTILINE
)


def _read(name):
    """Return the text of a workflow file under .github/workflows/."""
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def _targets(name):
    """Map each cron to its normalised case-arm assignment (whitespace in the
    arms is column alignment, so it must not make two equal targets differ)."""
    return {
        cron: " ".join(rhs.split())
        for cron, rhs in CASE_TARGET_RE.findall(_read(name))
    }


def test_workflow_dir_exists():
    """Guard the path these tests parse: an empty glob would make every other
    assertion here vacuously pass."""
    assert WORKFLOWS.is_dir(), f"missing {WORKFLOWS}"
    assert list(WORKFLOWS.glob("*.yml")), "no workflows found"


@pytest.mark.parametrize("name", SCHEDULED_FANOUT)
def test_every_cron_slot_has_a_ticker_mapping(name):
    """A cron with no case arm hits the loud-fail default and generates
    nothing — the report for that ticker is silently missing for the day."""
    text = _read(name)
    crons = set(CRON_RE.findall(text))
    arms = set(CASE_ARM_RE.findall(text))

    assert crons, f"{name}: no cron entries parsed"
    assert arms, f"{name}: no case arms parsed"

    unmapped = sorted(crons - arms)
    assert not unmapped, (
        f"{name}: {len(unmapped)} cron slot(s) have no `case` arm and would "
        f"fail at runtime: {unmapped}"
    )


@pytest.mark.parametrize("name", SCHEDULED_FANOUT)
def test_no_unreachable_ticker_mapping(name):
    """A case arm with no cron is dead weight — usually a cron someone removed
    or retyped, leaving the ticker silently unscheduled."""
    text = _read(name)
    crons = set(CRON_RE.findall(text))
    arms = set(CASE_ARM_RE.findall(text))

    orphans = sorted(arms - crons)
    assert not orphans, (
        f"{name}: {len(orphans)} `case` arm(s) match no cron entry, so those "
        f"tickers are never scheduled: {orphans}"
    )


@pytest.mark.parametrize("name", SCHEDULED_FANOUT)
def test_cron_slots_are_unique(name):
    """Two identical crons fire one run, not two, so the second ticker's report
    never gets written."""
    crons = CRON_RE.findall(_read(name))
    duplicates = sorted({c for c in crons if crons.count(c) > 1})
    assert not duplicates, f"{name}: duplicate cron entries: {duplicates}"


@pytest.mark.parametrize("name", SCHEDULED_FANOUT)
def test_every_cron_slot_generates_a_distinct_report(name):
    """Unique crons are not enough: two slots can both resolve to the same
    ticker (and, in daily_analysis, the same analysis type). That publishes one
    report twice and — since the schedule is written by hand, one line per
    ticker — usually means the ticker the second line meant to add is missing
    entirely. Compares the whole assignment, not TICKER alone: daily_analysis
    maps every ticker twice on purpose, once per ANALYSIS_TYPE."""
    targets = _targets(name)
    arms = set(CASE_ARM_RE.findall(_read(name)))

    assert targets, f"{name}: no case-arm targets parsed"
    assert set(targets) == arms, (
        f"{name}: {sorted(arms - set(targets))} arm(s) did not parse as a "
        f"single-line `TICKER=... ;;` assignment; update CASE_TARGET_RE"
    )

    by_target = {}
    for cron, target in targets.items():
        by_target.setdefault(target, []).append(cron)
    collisions = {t: c for t, c in sorted(by_target.items()) if len(c) > 1}
    assert not collisions, (
        f"{name}: {len(collisions)} target(s) are scheduled by more than one "
        f"cron, so that report is generated twice and whichever ticker the "
        f"duplicate line meant to schedule is never run: {collisions}"
    )


@pytest.mark.parametrize("name", SCHEDULED_FANOUT)
def test_no_silent_catch_all_in_the_schedule_case(name):
    """`*) TICKER="TSLA"` turned an unmapped cron into an unnoticed duplicate
    report. The catch-all must fail the run instead."""
    text = _read(name)
    catch_all = re.search(r'^\s*\*\)(.*?);;', text, re.MULTILINE | re.DOTALL)
    assert catch_all, f"{name}: schedule case has no `*)` catch-all at all"
    body = catch_all.group(1)
    assert "::error::" in body and "exit 1" in body, (
        f"{name}: the `*)` catch-all must emit ::error:: and exit 1, not "
        f"silently pick a ticker. Found: {body.strip()!r}"
    )


def test_no_workflow_does_a_full_history_clone():
    """The pack is ~960 MB. `fetch-depth: 0` on a job that only appends a
    commit costs a deep clone for nothing, ~100 times a day."""
    offenders = [
        p.name for p in sorted(WORKFLOWS.glob("*.yml"))
        if re.search(r"^\s*fetch-depth:\s*0\s*$", p.read_text(encoding="utf-8"),
                     re.MULTILINE)
    ]
    assert not offenders, (
        "fetch-depth: 0 clones the full ~960 MB history. Use the default "
        f"shallow checkout, or a bounded depth if the job reads history: {offenders}"
    )


def test_pip_installs_go_through_the_shared_action():
    """`pip install pytest>=7.0` unquoted makes the shell read `>=7.0` as a
    redirect: the package installs UNPINNED and a junk file named `=7.0`
    appears. .github/actions/python-env passes specifiers via xargs, so route
    installs through it rather than reintroducing that bug per workflow."""
    offenders = []
    for p in sorted(WORKFLOWS.glob("*.yml")):
        for line in p.read_text(encoding="utf-8").splitlines():
            # Comments may legitimately *discuss* pip install (e.g. explaining
            # why a job no longer runs one); only real commands count.
            if line.lstrip().startswith("#"):
                continue
            if "pip install" in line:
                offenders.append(f"{p.name}: {line.strip()}")
    assert not offenders, (
        "use ./.github/actions/python-env (its `packages:` input) instead of a "
        f"raw `pip install` in a run block: {offenders}"
    )


# ── EDGAR filing downloaders (download_10k.yml / download_10q.yml) ────────────
# These two do not fan out over cron slots; they loop over the ticker
# directories already present under 10-k/ and 10-q/, so their invariants are
# about that loop rather than about cron/case pairing.

FILING_JOBS = {
    "download_10k.yml": "10-k",
    "download_10q.yml": "10-q",
}

REPO_ROOT = WORKFLOWS.parent.parent


@pytest.mark.parametrize("name,corpus", sorted(FILING_JOBS.items()))
def test_ticker_directories_are_uppercase(name, corpus):
    """The loop passes each directory name straight to the downloader, which
    saves under `ticker.upper()`. A lowercase directory therefore round-trips
    to a *different* path: `10-q/pl/` was real, and on Linux CI (unlike a
    case-insensitive macOS checkout, where the bug is invisible) the job would
    have created a second `10-q/PL/`, re-downloading every filing into it and
    listing the company twice on the built site."""
    root = REPO_ROOT / corpus
    assert root.is_dir(), f"missing {root}"

    offenders = sorted(
        p.name for p in root.iterdir() if p.is_dir() and p.name != p.name.upper()
    )
    assert not offenders, (
        f"{corpus}/ holds lowercase ticker director(ies) {offenders}; "
        f"{name} would create an uppercase duplicate alongside each on Linux"
    )


@pytest.mark.parametrize("name,corpus", sorted(FILING_JOBS.items()))
def test_filing_job_loops_over_its_own_corpus(name, corpus):
    """Each job must glob the directory it commits. Copy-pasting the 10-K job
    without retargeting the glob would refresh annual reports and then commit
    an empty 10-q/ — a green run that silently downloads nothing new."""
    text = _read(name)
    assert f"for dir in {corpus}/*/" in text, (
        f"{name}: expected a `for dir in {corpus}/*/` loop over its own corpus"
    )
    assert re.search(rf"^\s*paths:\s*{re.escape(corpus)}\s*$", text, re.MULTILINE), (
        f"{name}: commit-and-push must stage `{corpus}`"
    )


@pytest.mark.parametrize("name,corpus", sorted(FILING_JOBS.items()))
def test_filing_job_does_not_swallow_downloader_failures(name, corpus):
    """`python ... || true` made a failed ticker invisible: the loop carried on,
    commit-and-push succeeded (nothing changed is not an error), and the run
    went green while that ticker stayed stale. Collect the failures instead and
    re-raise them after the commit."""
    text = _read(name)
    # Comments may legitimately name `|| true` (these two explain why it was
    # removed); only real commands count.
    offenders = [
        line.strip() for line in text.splitlines()
        if "|| true" in line and not line.lstrip().startswith("#")
    ]
    assert not offenders, (
        f"{name}: `|| true` hides a downloader failure and lets the run finish "
        f"green with a stale ticker; collect failed tickers and fail "
        f"afterwards: {offenders}"
    )
    assert "|| failed=" in text, f"{name}: expected failed-ticker collection"
    assert re.search(r"if:\s*steps\.download\.outputs\.failed\s*!=\s*''", text), (
        f"{name}: no step re-raises the collected failures"
    )


@pytest.mark.parametrize("name,corpus", sorted(FILING_JOBS.items()))
def test_failure_step_runs_after_the_commit(name, corpus):
    """Order matters: a partial refresh is still worth committing. Failing
    before commit-and-push would discard good filings because one ticker's
    EDGAR request timed out."""
    text = _read(name)
    commit = text.index("uses: ./.github/actions/commit-and-push")
    fail = text.index("Fail if any ticker could not be refreshed")
    assert commit < fail, (
        f"{name}: the failure step must come after commit-and-push, or a "
        f"partial refresh is thrown away"
    )


@pytest.mark.parametrize("name,corpus", sorted(FILING_JOBS.items()))
def test_failed_ticker_list_is_not_interpolated_into_the_shell(name, corpus):
    """`ticker` is a workflow_dispatch input and flows into the failed list, so
    `${{ }}` inside a run block would be a script-injection seam. Pass it
    through env."""
    text = _read(name)
    assert "${{ steps.download.outputs.failed }}" in text, "expected the value to be passed at all"
    for line in text.splitlines():
        stripped = line.strip()
        if "steps.download.outputs.failed" in stripped and stripped.startswith("echo"):
            pytest.fail(f"{name}: failed list interpolated into a run script: {stripped!r}")


def test_filing_jobs_do_not_share_a_concurrency_group():
    """Sharing one group makes the later job queue behind the earlier one for
    the length of a full refresh, and `cancel-in-progress: false` means it
    waits rather than replacing it."""
    groups = {}
    for name in FILING_JOBS:
        m = re.search(r"^concurrency:\n(?:\s*#.*\n)*\s*group:\s*(\S+)",
                      _read(name), re.MULTILINE)
        assert m, f"{name}: no concurrency group declared"
        groups.setdefault(m.group(1), []).append(name)

    clashes = {g: n for g, n in sorted(groups.items()) if len(n) > 1}
    assert not clashes, f"filing jobs share a concurrency group: {clashes}"
