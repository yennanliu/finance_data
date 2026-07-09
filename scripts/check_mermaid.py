#!/usr/bin/env python3
"""
check_mermaid.py — surface reports whose ```mermaid diagrams won't render.

Non-blocking alert (exit code is always 0 unless ``--strict``): it lists every
report file that still contains unrenderable Mermaid syntax and prints the exact
offending snippet, so a broken diagram is visible without failing the pipeline.

Detection mirrors the generation-time repair in ``analysis.utils.mermaid`` —
anything reported here is something ``sanitize_mermaid`` would have fixed, so a
hit means a report slipped through un-sanitized (a regression worth seeing).

When run inside GitHub Actions it also:
  * emits ``::warning file=…,line=…::`` annotations (shown on the run + in PRs)
  * appends a Markdown section to ``$GITHUB_STEP_SUMMARY`` (the run summary page)

Usage:
  python3 scripts/check_mermaid.py [--root PATH] [--strict]

Examples:
  python3 scripts/check_mermaid.py
  python3 scripts/check_mermaid.py --root ai_gen_report/stock --strict
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from analysis.utils.mermaid import mermaid_issue_locations  # noqa: E402

DEFAULT_ROOT = Path(__file__).parent.parent / "ai_gen_report"


def _gha_escape(msg: str) -> str:
    """Escape a message for a GitHub Actions workflow command."""
    return msg.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def scan(root: Path) -> "list[tuple[Path, list[tuple[int, str]]]]":
    """Return [(path, [(line, snippet), …]), …] for every file with issues."""
    out = []
    for p in sorted(root.rglob("*.md")):
        text = p.read_text(encoding="utf-8", errors="replace")
        if "```mermaid" not in text:
            continue
        locs = mermaid_issue_locations(text)
        if locs:
            out.append((p, locs))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=str(DEFAULT_ROOT),
                        help="Directory to scan (default: ai_gen_report)")
    parser.add_argument("--strict", action="store_true",
                        help="Exit non-zero if any broken diagram is found "
                             "(default: alert only, exit 0)")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"ERROR: root not found: {root}", file=sys.stderr)
        sys.exit(1)

    findings = scan(root)
    total_snippets = sum(len(locs) for _, locs in findings)
    in_gha = bool(os.environ.get("GITHUB_ACTIONS"))
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")

    if not findings:
        print("✅ No broken Mermaid diagrams found.")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write("### 🧜 Mermaid check\n\n✅ No broken diagrams found.\n")
        return

    # ── console: list failure places + print the failed part ────────────────
    print(f"⚠️  {total_snippets} broken Mermaid snippet(s) in {len(findings)} file(s):\n")
    for path, locs in findings:
        rel = path.relative_to(root.parent) if root.parent in path.parents else path
        print(f"── {rel}")
        for line, snip in locs:
            print(f"     line {line}: {snip}")
        print()

    # ── GitHub Actions annotations (one per snippet) ─────────────────────────
    if in_gha:
        for path, locs in findings:
            rel = os.path.relpath(path)
            for line, snip in locs:
                msg = _gha_escape(f"Unrenderable Mermaid: {snip}")
                print(f"::warning file={rel},line={line}::{msg}")

    # ── job summary (Markdown) ───────────────────────────────────────────────
    if summary_path:
        lines = ["### 🧜 Mermaid check\n",
                 f"⚠️ **{total_snippets}** broken snippet(s) in **{len(findings)}** file(s). "
                 "These diagrams will not render on GitHub.\n",
                 "| File | Line | Failed snippet |",
                 "|------|-----:|----------------|"]
        for path, locs in findings:
            rel = os.path.relpath(path)
            for line, snip in locs:
                cell = snip.replace("|", "\\|").replace("\n", " ")
                if len(cell) > 120:
                    cell = cell[:117] + "…"
                lines.append(f"| `{rel}` | {line} | `{cell}` |")
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    if args.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
