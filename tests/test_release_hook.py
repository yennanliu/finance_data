"""`scripts/mkdocs_release_hook.py` puts the release version on every page.

The header pill and footer read `config.extra.release`; the version must come
from pyproject.toml (it used to be a hardcoded "v1.0.0" that disagreed with
it), and no lookup may break the site build when git or the file is missing.
"""

import importlib.util
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "mkdocs_release_hook", ROOT / "scripts" / "mkdocs_release_hook.py")
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)


def test_version_comes_from_pyproject():
    text = (ROOT / "pyproject.toml").read_text()
    expected = re.search(r'^version = "([^"]*)"', text, re.MULTILINE).group(1)
    assert hook.read_version() == expected


PYPROJECT = (
    '[build]\nversion = "0.0.1"\n\n'
    '[project]\nname = "finance-data"\nversion = "1.4.2"\n\n'
    '[tool.x]\nversion = "9.9.9"\n'
)


@pytest.mark.parametrize("use_tomllib", [True, False], ids=["tomllib", "py310-fallback"])
def test_project_field_reads_only_the_project_table(monkeypatch, use_tomllib):
    if not use_tomllib:
        monkeypatch.setattr(hook, "tomllib", None)
    elif hook.tomllib is None:
        pytest.skip("tomllib needs Python 3.11+")
    assert hook.project_field(PYPROJECT, "version") == "1.4.2"
    assert hook.project_field(PYPROJECT, "name") == "finance-data"
    with pytest.raises(KeyError):
        hook.project_field(PYPROJECT, "description")


def test_unreadable_pyproject_falls_back_to_dev(tmp_path):
    assert hook.read_version(tmp_path / "missing.toml") == "dev"
    (tmp_path / "pyproject.toml").write_text("[tool.x]\n")
    assert hook.read_version(tmp_path / "pyproject.toml") == "dev"


def test_github_sha_wins_and_is_shortened(monkeypatch):
    monkeypatch.setenv("GITHUB_SHA", "0123456789abcdef0123456789abcdef01234567")
    assert hook.read_commit() == "0123456"


def test_missing_git_gives_empty_commit(monkeypatch):
    monkeypatch.delenv("GITHUB_SHA", raising=False)

    def boom(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", boom)
    info = hook.release_info("https://github.com/o/r")
    assert info["commit"] == "" and info["commit_url"] == ""


def test_on_config_publishes_release(monkeypatch):
    monkeypatch.setenv("GITHUB_SHA", "abcdef1234")
    config = SimpleNamespace(extra={}, repo_url="https://github.com/o/r/")
    hook.on_config(config)
    assert config.extra["release"] == {
        "version": hook.read_version(),
        "commit": "abcdef1",
        "commit_url": "https://github.com/o/r/commit/abcdef1",
    }


def test_hook_is_registered_and_template_has_no_hardcoded_version():
    assert "scripts/mkdocs_release_hook.py" in (ROOT / "mkdocs.yml").read_text()
    main = (ROOT / "docs" / "overrides" / "main.html").read_text()
    assert "v1.0.0" not in main and "config.extra.release" in main


# ── scripts/release_version.py (used by .github/workflows/release.yml) ────────

_rspec = importlib.util.spec_from_file_location(
    "release_version", ROOT / "scripts" / "release_version.py")
rv = importlib.util.module_from_spec(_rspec)
_rspec.loader.exec_module(rv)


@pytest.mark.parametrize("bump,expected", [
    ("patch", "1.4.3"), ("minor", "1.5.0"), ("major", "2.0.0"),
    ("current", "1.4.2"), ("2.0.0rc1", "2.0.0rc1"),
])
def test_next_version(bump, expected):
    assert rv.next_version("1.4.2", bump) == expected


@pytest.mark.parametrize("bad", ["latest", "v1.2.3", "1.2"])
def test_next_version_rejects_junk(bad):
    with pytest.raises(ValueError):
        rv.next_version("1.4.2", bad)


def test_write_version_touches_only_the_project_lines(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "finance-data"\nversion = "1.4.2"\n'
        '[tool.x]\nversion = "9.9.9"\n')
    lock = ('[[package]]\nname = "other"\nversion = "1.4.2"\n\n'
            '[[package]]\nname = "finance-data"\nversion = "1.4.2"\n')
    (tmp_path / "uv.lock").write_text(lock)
    rv.write_version("1.5.0", tmp_path)
    py = (tmp_path / "pyproject.toml").read_text()
    assert 'version = "1.5.0"' in py and 'version = "9.9.9"' in py
    assert (tmp_path / "uv.lock").read_text() == lock.replace(
        'name = "finance-data"\nversion = "1.4.2"', 'name = "finance-data"\nversion = "1.5.0"')


def test_repo_lockfile_carries_the_pyproject_version():
    """release.yml rewrites both; they must agree or `uv sync --locked` fails."""
    lock = (ROOT / "uv.lock").read_text()
    assert f'name = "finance-data"\nversion = "{hook.read_version()}"' in lock
