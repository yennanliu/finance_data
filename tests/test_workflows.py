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


def _read(name):
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_workflow_dir_exists():
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
