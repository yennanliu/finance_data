"""Tests for scripts/check_provider_keys.py.

The script gates every report-generating workflow: it must fail when a provider
in the fallback chain has no key, and must not fail when they all do.
"""

import pytest

import check_provider_keys
from check_provider_keys import PROVIDER_KEYS, main
from scripts.analysis.config.providers import PROVIDER_DEFAULTS


ALL_ENV_VARS = ["OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"]


@pytest.fixture(autouse=True)
def _clear_keys(monkeypatch):
    """Start every test with no provider keys and no PROVIDER/MODEL set."""
    for var in ALL_ENV_VARS + ["PROVIDER", "MODEL"]:
        monkeypatch.delenv(var, raising=False)


def _run(argv, monkeypatch):
    """Invoke the script's ``main()`` with ``argv`` and return its exit code."""
    monkeypatch.setattr("sys.argv", ["check_provider_keys.py", *argv])
    return main()


def test_every_provider_has_a_key_mapping():
    """A provider the chain can select but PROVIDER_KEYS does not cover would
    raise KeyError mid-check instead of reporting a missing secret."""
    assert set(PROVIDER_KEYS) == set(PROVIDER_DEFAULTS)


def test_passes_when_the_whole_chain_has_keys(monkeypatch):
    """Every level of the chain has its key, so the check clears the run."""
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "y")
    assert _run(["--provider", "gemini", "--model", "gemini-3.8-flash"], monkeypatch) == 0


def test_fails_when_no_keys_are_set(monkeypatch):
    """No key anywhere: fail before the install/fetch steps, not after."""
    assert _run(["--provider", "gemini"], monkeypatch) == 1


def test_fails_when_only_the_primary_has_a_key(monkeypatch):
    """The point of the script: a run whose primary works but whose fallback
    has no key is doomed the moment the primary rate-limits, so refuse it up
    front rather than after paying for the data fetch."""
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert _run(["--provider", "gemini"], monkeypatch) == 1


def test_fails_when_only_the_fallback_has_a_key(monkeypatch):
    """The mirror case: the primary's own key missing is just as fatal."""
    monkeypatch.setenv("OPENAI_API_KEY", "y")
    assert _run(["--provider", "gemini"], monkeypatch) == 1


def test_explicit_claude_primary_also_requires_the_chain(monkeypatch):
    """An explicit primary is checked in addition to FALLBACK_CHAIN, not
    instead of it."""
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "y")
    assert _run(["--provider", "claude"], monkeypatch) == 1

    monkeypatch.setenv("ANTHROPIC_API_KEY", "z")
    assert _run(["--provider", "claude"], monkeypatch) == 0


def test_reads_provider_and_model_from_the_environment(monkeypatch):
    """How the workflows actually invoke it — via env, with no CLI args."""
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "y")
    monkeypatch.setenv("PROVIDER", "gemini")
    monkeypatch.setenv("MODEL", "gemini-3.8-flash")
    assert _run([], monkeypatch) == 0


def test_no_arguments_at_all_checks_the_default_chain(monkeypatch):
    """A scheduled run passes nothing, so the bare invocation must still cover
    gemini and openai."""
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert _run([], monkeypatch) == 1
    monkeypatch.setenv("OPENAI_API_KEY", "y")
    assert _run([], monkeypatch) == 0


def test_a_mismatched_model_does_not_raise(monkeypatch):
    """The workflows no longer pre-correct the provider/model pair, so the
    script has to tolerate one straight off a stale dropdown."""
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "y")
    assert _run(["--provider", "gemini", "--model", "gpt-4o"], monkeypatch) == 0


def test_missing_secret_is_reported_by_its_repo_name(capsys, monkeypatch):
    """OpenAI's key lives in a secret named OPEN_KEY_API; naming the env var
    instead would send someone looking for a secret that does not exist."""
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    _run(["--provider", "gemini"], monkeypatch)
    out = capsys.readouterr().out
    assert "::error::OPEN_KEY_API secret is not set" in out
    assert "OPENAI_API_KEY secret is not set" not in out


def test_error_annotations_name_the_provider(capsys, monkeypatch):
    """Each ::error:: says which chain level needs the secret, so the run
    summary is actionable without opening the log."""
    _run(["--provider", "gemini"], monkeypatch)
    out = capsys.readouterr().out
    assert "::error::" in out
    assert "'gemini'" in out
    assert "'openai'" in out


def test_module_exposes_main_for_the_cli(monkeypatch):
    """The workflows call the module as a script; keep main() importable."""
    assert callable(check_provider_keys.main)
