"""MkDocs hook: expose the release version and commit to the templates.

The version shown in the header pill and the footer used to be a hardcoded
"v1.0.0" in docs/overrides/main.html, unrelated to `[project].version` in
pyproject.toml (then 0.1.0). It is now read from pyproject.toml, the single
source of truth, and published as `config.extra.release`:

    version     "1.1.0" (from pyproject.toml; "dev" if it cannot be read)
    commit      short SHA — $GITHUB_SHA in CI, `git rev-parse` locally, else ""
    commit_url  <repo_url>/commit/<sha>, or "" without a commit

Every lookup fails soft: a missing git binary or a shallow checkout must never
break the site build.
"""
from __future__ import annotations

import os
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_version(pyproject: Path = ROOT / "pyproject.toml") -> str:
    try:
        with pyproject.open("rb") as fh:
            return str(tomllib.load(fh)["project"]["version"])
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "dev"


def read_commit() -> str:
    sha = os.environ.get("GITHUB_SHA", "").strip()
    if not sha:
        try:
            sha = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                text=True, timeout=5, check=True,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            sha = ""
    return sha[:7]


def release_info(repo_url: str | None) -> dict:
    commit = read_commit()
    repo = (repo_url or "").rstrip("/")
    return {
        "version": read_version(),
        "commit": commit,
        "commit_url": f"{repo}/commit/{commit}" if commit and repo else "",
    }


def on_config(config):
    config.extra["release"] = release_info(config.repo_url)
    return config
