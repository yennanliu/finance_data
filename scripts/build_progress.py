#!/usr/bin/env python3
"""Render the daily progress summary from a list of collected files.

Previously daily_progress.yml derived this from `git log --since="12 hours ago"`,
which worked only because every report arrived as its own commit. Now that a
whole cycle lands as one commit, the file list comes from the collector instead
— which is also exact, rather than a guess based on a time window.
"""

from __future__ import annotations

import argparse
from pathlib import Path

ANALYSIS_BASE_URL = "https://yennanliu.github.io/finance_data/reports"
NEWS_BASE_URL = "https://yennanliu.github.io/finance_data/market_news"

ANALYSIS_ROOTS = (
    "ai_gen_report/stock/",
    "ai_gen_report/fundamental/",
    "ai_gen_report/technical/",
)
NEWS_ROOT = "ai_gen_report/market_news/"


def _entry(path: str, root: str, base_url: str) -> tuple[str, str] | None:
    """Return (ticker, markdown link) for a report path, or None if it isn't one."""
    rest = path[len(root) :]
    if "/" not in rest:
        return None
    ticker, _, filename = rest.partition("/")
    if not filename.endswith(".md"):
        return None
    stem = Path(filename).stem
    return ticker, f"- [{ticker.upper()} {stem}]({base_url}/{ticker}/{stem}/)"


def build(paths: list[str]) -> str:
    analysis: set[str] = set()
    news: set[str] = set()

    for path in paths:
        path = path.strip()
        if not path.endswith(".md"):
            continue
        for root in ANALYSIS_ROOTS:
            if path.startswith(root):
                got = _entry(path, root, ANALYSIS_BASE_URL)
                if got:
                    analysis.add(got[1])
                break
        else:
            if path.startswith(NEWS_ROOT):
                got = _entry(path, NEWS_ROOT, NEWS_BASE_URL)
                if got:
                    news.add(got[1])

    lines = ["### Stock Analysis", *sorted(analysis)]
    if news:
        lines += ["", "### Market News", *sorted(news)]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", required=True, help="newline-separated paths")
    parser.add_argument("--out", required=True, help="progress file to write")
    args = parser.parse_args()

    raw = Path(args.files).read_text(encoding="utf-8").splitlines()
    text = build(raw)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
