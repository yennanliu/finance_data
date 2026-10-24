"""Bump the release version for .github/workflows/release.yml.

The site's version is `[project].version` in pyproject.toml (read at build time
by scripts/mkdocs_release_hook.py). uv.lock repeats it in the project's own
`[[package]]` entry, and CI installs with `--locked`, so both are rewritten
together. Only those two lines change: re-running `uv lock` here could also
rewrite unrelated resolution markers under a different uv version.

    python scripts/release_version.py patch     # 1.1.0 -> 1.1.1
    python scripts/release_version.py minor     # 1.1.0 -> 1.2.0
    python scripts/release_version.py major     # 1.1.0 -> 2.0.0
    python scripts/release_version.py current   # release 1.1.0 as-is
    python scripts/release_version.py 2.0.0rc1  # explicit version

Prints the resulting version on stdout and nothing else.
"""
from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUMPS = ("major", "minor", "patch", "current")
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-.]?(?:a|b|rc|alpha|beta)\.?\d*)?$")


def next_version(current: str, bump: str) -> str:
    if bump == "current":
        return current
    if bump not in BUMPS:
        if not SEMVER.match(bump):
            raise ValueError(f"not a version or bump kind: {bump!r}")
        return bump
    m = SEMVER.match(current)
    if not m:
        raise ValueError(f"current version {current!r} is not X.Y.Z")
    major, minor, patch = map(int, m.groups())
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _replace_once(text: str, pattern: str, repl: str, what: str) -> str:
    new, n = re.subn(pattern, repl, text, count=1, flags=re.MULTILINE)
    if n != 1:
        raise ValueError(f"could not find the version line in {what}")
    return new


def write_version(version: str, root: Path = ROOT) -> None:
    pyproject = root / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    name = tomllib.loads(text)["project"]["name"]
    pyproject.write_text(_replace_once(
        text, r'^(version\s*=\s*)"[^"]*"', rf'\g<1>"{version}"', "pyproject.toml"),
        encoding="utf-8")

    lock = root / "uv.lock"
    lock.write_text(_replace_once(
        lock.read_text(encoding="utf-8"),
        rf'^(name = "{re.escape(name)}"\nversion = )"[^"]*"', rf'\g<1>"{version}"',
        "uv.lock"), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("bump", help=f"one of {', '.join(BUMPS)}, or an explicit version")
    args = parser.parse_args(argv)
    with (ROOT / "pyproject.toml").open("rb") as fh:
        current = tomllib.load(fh)["project"]["version"]
    try:
        version = next_version(current, args.bump)
        if version != current:
            write_version(version)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
