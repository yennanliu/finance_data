#!/usr/bin/env python3
"""
recheck_fundamental_reports.py
==============================
Re-run the generation-time arithmetic recheck over fundamental reports that
were written before it existed, or before it learned to correct.

The pipeline now rechecks every new report (``pipeline.recheck_valuation`` and
``derivation.fix``, see docs/REPORT_PIPELINE.md). Reports from before that
carry the model's own §8.8 total, MOS and upside even where the terms add up
to something else: 362 of 762 on 2026-10-30, 316 of them with no recheck at
all and 46 with only the 「應為」 notice. This script gives each report what
the pipeline would give it today:

  * no recheck yet, or ``arithmetic_check: mismatch`` — any earlier notice and
    「程式複算」 block are removed, then ``recheck_valuation`` corrects,
    fixes the product line and annotates, and its fields go into the front
    matter;
  * already consistent (``ok``, ``corrected``, or a §8.8 that adds up) — only
    the product line is re-fixed, so no recap block is added to a report with
    nothing to correct;
  * every report — ``derivation.fix`` repairs broken equation chains
    (``derivation_fixed`` in the front matter).

A file is rewritten only when its body changes. Idempotent: a second run
changes nothing.

Usage
-----
  python scripts/recheck_fundamental_reports.py --dry-run
  python scripts/recheck_fundamental_reports.py
  python scripts/recheck_fundamental_reports.py --ticker MRVL
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from analysis.pipeline import recheck_valuation  # noqa: E402
from analysis.validate import arithmetic, derivation  # noqa: E402

FUNDAMENTAL = ROOT / "ai_gen_report" / "fundamental"

_FRONT = re.compile(r"\A---\n(.*?\n)---\n", re.S)
# What annotate() added on an earlier run: the notice under the title and the
# 「程式複算」 quote at the end of §8.8.
_NOTICE = re.compile(r"\n\*\*(?:⚠️|✏️) 程式複算更正\*\*：[^\n]*\n\n")
_BLOCK = re.compile(r"\n> 🔎 \*\*程式複算[^\n]*\n(?:>[^\n]*\n)*\n?")
_FIELDS = ("arithmetic_check", "weighted_fair_value_stated",
           "weighted_fair_value_recomputed", "mos_recomputed_pct", "derivation_fixed")


def split(text: str) -> "tuple[str, str]":
    """``(front-matter body, report body)``; the first is "" when absent."""
    m = _FRONT.match(text)
    return (m.group(1), text[m.end():]) if m else ("", text)


def merge_front(front: str, fields: dict) -> str:
    """``front`` with ``fields`` set: existing keys replaced in place, new
    ones appended in pipeline order."""
    lines = front.splitlines()
    for key in _FIELDS:
        if key not in fields:
            continue
        line = f"{key}: {fields[key]}"
        at = next((i for i, l in enumerate(lines) if l.split(":", 1)[0] == key), None)
        if at is None:
            lines.append(line)
        else:
            lines[at] = line
    return "\n".join(lines) + "\n"


def recheck(text: str) -> "tuple[str, dict]":
    """The report as the pipeline would write it today, and what changed:
    ``{"arithmetic_check": …, "derivation_fixed": n}`` (only keys that apply)."""
    front, body = split(text)
    fm = dict(l.split(":", 1) for l in front.splitlines() if ":" in l)
    fm = {k.strip(): v.strip() for k, v in fm.items()}
    status = fm.get("arithmetic_check")
    fields: dict = {}

    if status in (None, "mismatch"):
        stripped = _BLOCK.sub("\n", _NOTICE.sub("", body, count=1))
        try:
            price = float(fm["price"]) if fm.get("price") else None
        except ValueError:
            price = None
        rechecked, checks = recheck_valuation(stripped, {"price": price})
        if checks["arithmetic_check"] in ("corrected", "mismatch"):
            body, fields = rechecked, checks
        elif checks["arithmetic_check"] == "ok":
            # Consistent already: no recap block, just the product line.
            body = arithmetic.fix_products(body, arithmetic.check(body, price))
    else:
        price = float(fm["price"]) if fm.get("price") else None
        body = arithmetic.fix_products(body, arithmetic.check(body, price))

    body, repaired = derivation.fix(body)
    if repaired:
        fields["derivation_fixed"] = int(fm.get("derivation_fixed") or 0) + repaired

    if not front:
        return body, fields   # no front matter to record in (none exist today)
    return f"---\n{merge_front(front, fields)}---\n{body}", fields


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--ticker", help="only this ticker's reports")
    ap.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    args = ap.parse_args()

    pattern = f"{args.ticker.lower()}/*.md" if args.ticker else "*/*.md"
    counts: Counter = Counter()
    for path in sorted(FUNDAMENTAL.glob(pattern)):
        if not path.name.startswith("fundamental_analysis_"):
            continue
        text = path.read_text(encoding="utf-8")
        new, fields = recheck(text)
        counts["scanned"] += 1
        if new == text:
            continue
        counts["changed"] += 1
        counts[f"arithmetic_check={fields.get('arithmetic_check', '-')}"] += 1
        if fields.get("derivation_fixed"):
            counts["derivation_fixed"] += 1
        print(f"  {'would fix' if args.dry_run else 'fixed'}  {path.relative_to(ROOT)}  {fields}")
        if not args.dry_run:
            path.write_text(new, encoding="utf-8")
    print(", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
