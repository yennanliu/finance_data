"""`scripts/mkdocs_release_hook.py` puts the release version on every page.

The header pill and footer read `config.extra.release`; the version must come
from pyproject.toml (it used to be a hardcoded "v1.0.0" that disagreed with
it), and no lookup may break the site build when git or the file is missing.
"""

import importlib.util
import subprocess
import tomllib
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
    with (ROOT / "pyproject.toml").open("rb") as fh:
        expected = tomllib.load(fh)["project"]["version"]
    assert hook.read_version() == expected


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
