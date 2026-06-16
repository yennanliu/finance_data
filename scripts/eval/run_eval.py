#!/usr/bin/env python3
"""
run_eval.py — P4: sample generated reports, score RAG quality, write qa/eval_*.

Mirrors the style of scripts/check_report_quality.py. Reads each report's
`.context.json` sidecar (written by context_store at generation time) so it can
judge groundedness/relevance against the exact context the model saw.

Examples
--------
  # Smoke test without any API calls (discovery + sidecar coverage only)
  python3 scripts/eval/run_eval.py --root ai_gen_report/market_news --no-llm --summary

  # Judge a 10% stratified sample of June market-news reports with gpt-4o
  python3 scripts/eval/run_eval.py --root ai_gen_report/market_news \
        --since 2026-06 --sample 0.1 --judge-provider openai --judge-model gpt-4o \
        --csv qa/eval_2026-06-16.csv --summary

  # Retrieval precision/recall from a labelled eval set
  python3 scripts/eval/run_eval.py --eval-set qa/eval_set --summary
"""

from __future__ import annotations

import argparse
import csv
import random
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))  # make `eval` importable

from eval.context_store import read_context_sidecar
from eval import judges as J
from eval import retrieval as R

# Red lines from qa/RAG_EVALUATION.md §4 (trigger review when below).
RED_LINES = {
    "groundedness": 0.90,
    "context_relevance": 0.65,
    "answer_relevance": 3.5,
    "precision": 0.50,
    "recall": 0.50,
}

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


@dataclass
class ReportRow:
    path: str
    ticker: str = ""
    date: str = ""
    analysis_type: str = ""
    provider: str = ""
    has_context: bool = False
    groundedness: Optional[float] = None
    n_unsupported: Optional[int] = None
    context_relevance: Optional[float] = None
    answer_relevance: Optional[float] = None
    notes: list[str] = field(default_factory=list)


def _parse_frontmatter(text: str) -> dict:
    m = _FM_RE.match(text)
    fm: dict[str, str] = {}
    if not m:
        return fm
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"')
    return fm


def _strip_frontmatter(text: str) -> str:
    return _FM_RE.sub("", text, count=1)


def discover(root: Path, since: str, until: str, ticker: str,
             atype: str) -> list[Path]:
    out = []
    for p in sorted(root.rglob("*.md")):
        if p.name.endswith(".context.json"):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        fm = _parse_frontmatter(text)
        d = fm.get("date", "")
        if since and d and d < since:
            continue
        if until and d and d > until + "￿":
            continue
        if ticker and fm.get("ticker", "").upper() != ticker.upper():
            continue
        t = fm.get("analysis_type") or fm.get("type", "")
        if atype and t != atype:
            continue
        out.append(p)
    return out


def sample(paths: list[Path], frac: float, max_n: int, seed: int) -> list[Path]:
    rng = random.Random(seed)
    # stratify by (ticker dir, type) so the sample spans the corpus
    buckets: dict[tuple, list[Path]] = defaultdict(list)
    for p in paths:
        fm = _parse_frontmatter(p.read_text(encoding="utf-8", errors="ignore"))
        buckets[(fm.get("ticker", p.parent.name),
                 fm.get("analysis_type") or fm.get("type", ""))].append(p)
    picked: list[Path] = []
    for items in buckets.values():
        k = max(1, int(round(len(items) * frac))) if frac < 1 else len(items)
        picked.extend(rng.sample(items, min(k, len(items))))
    rng.shuffle(picked)
    if max_n:
        picked = picked[:max_n]
    return picked


def judge_report(path: Path, provider: str, model: Optional[str],
                 no_llm: bool) -> ReportRow:
    text = path.read_text(encoding="utf-8", errors="ignore")
    fm = _parse_frontmatter(text)
    body = _strip_frontmatter(text)
    row = ReportRow(
        path=str(path),
        ticker=fm.get("ticker", path.parent.name).upper(),
        date=fm.get("date", ""),
        analysis_type=fm.get("analysis_type") or fm.get("type", ""),
        provider=fm.get("provider", ""),
    )
    sidecar = read_context_sidecar(path)
    row.has_context = sidecar is not None
    if no_llm:
        if not row.has_context:
            row.notes.append("no_context_sidecar")
        return row
    if not row.has_context:
        row.notes.append("no_context_sidecar→groundedness_skipped")

    context_text = (sidecar or {}).get("context_text", "")
    docs = (sidecar or {}).get("retrieved_docs", [])

    if context_text:
        g = J.groundedness(body, context_text, provider=provider, model=model)
        row.groundedness = g.get("groundedness")
        row.n_unsupported = g.get("n_unsupported")
        if g.get("error"):
            row.notes.append(f"grounded_err:{g['error']}")

    if docs:
        cr = J.context_relevance(docs, row.ticker, provider=provider, model=model)
        row.context_relevance = cr.get("context_relevance")
        if cr.get("error"):
            row.notes.append(f"ctxrel_err:{cr['error']}")

    ar = J.answer_relevance(body, row.ticker, row.analysis_type or "analysis",
                            provider=provider, model=model)
    row.answer_relevance = ar.get("answer_relevance")
    if ar.get("error"):
        row.notes.append(f"ansrel_err:{ar['error']}")
    return row


def _avg(vals: list[Optional[float]]) -> Optional[float]:
    nums = [v for v in vals if v is not None]
    return sum(nums) / len(nums) if nums else None


def run_eval_set(eval_dir: Path) -> list[dict]:
    import json
    results = []
    for p in sorted(eval_dir.glob("*.json")):
        try:
            sample_obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  [WARN] bad eval-set file {p.name}: {exc}")
            continue
        results.append(R.evaluate_sample(sample_obj))
    return results


def write_csv(rows: list[ReportRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path", "ticker", "date", "type", "provider", "has_context",
                    "groundedness", "n_unsupported", "context_relevance",
                    "answer_relevance", "notes"])
        for r in rows:
            w.writerow([r.path, r.ticker, r.date, r.analysis_type, r.provider,
                        int(r.has_context),
                        "" if r.groundedness is None else f"{r.groundedness:.3f}",
                        "" if r.n_unsupported is None else r.n_unsupported,
                        "" if r.context_relevance is None else f"{r.context_relevance:.3f}",
                        "" if r.answer_relevance is None else f"{r.answer_relevance:.2f}",
                        ";".join(r.notes)])
    print(f"  CSV written → {path}")


def _fmt(v: Optional[float], nd: int = 3) -> str:
    return "n/a" if v is None else f"{v:.{nd}f}"


def _flag(metric: str, v: Optional[float]) -> str:
    if v is None:
        return ""
    return "  🔴 BELOW RED LINE" if v < RED_LINES[metric] else "  🟢"


def summarize(rows: list[ReportRow], retr: list[dict]) -> str:
    lines = ["", "=" * 60]
    lines.append(f"Reports scored : {len(rows)}")
    with_ctx = sum(1 for r in rows if r.has_context)
    lines.append(f"With context   : {with_ctx}/{len(rows)} "
                 f"({100*with_ctx//max(len(rows),1)}%)  ← P0 coverage")
    lines.append("")
    g = _avg([r.groundedness for r in rows])
    cr = _avg([r.context_relevance for r in rows])
    ar = _avg([r.answer_relevance for r in rows])
    lines.append("LLM-judge averages:")
    lines.append(f"  Groundedness      : {_fmt(g)}{_flag('groundedness', g)}")
    lines.append(f"  Context Relevance : {_fmt(cr)}{_flag('context_relevance', cr)}")
    lines.append(f"  Answer Relevance  : {_fmt(ar, 2)}{_flag('answer_relevance', ar)}")

    if retr:
        rp = _avg([x["precision"] for x in retr])
        rr = _avg([x["recall"] for x in retr])
        rf = _avg([x["f1"] for x in retr])
        lines.append("")
        lines.append(f"Retrieval (eval set, n={len(retr)}):")
        lines.append(f"  Precision : {_fmt(rp)}{_flag('precision', rp)}")
        lines.append(f"  Recall    : {_fmt(rr)}{_flag('recall', rr)}")
        lines.append(f"  F1        : {_fmt(rf)}")

    worst = sorted([r for r in rows if r.groundedness is not None],
                   key=lambda r: r.groundedness)[:5]
    if worst:
        lines.append("")
        lines.append("Lowest groundedness (potential hallucinations):")
        for r in worst:
            lines.append(f"  {_fmt(r.groundedness)}  {r.n_unsupported} unsupported  "
                         f"{r.ticker} {r.date} ({Path(r.path).name})")
    lines.append("=" * 60)
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate RAG quality of generated reports.")
    p.add_argument("--root", type=Path, default=Path("ai_gen_report"),
                   help="Root dir to scan for reports (default: ai_gen_report)")
    p.add_argument("--since", default="", help="Min date YYYY-MM[-DD] (frontmatter)")
    p.add_argument("--until", default="", help="Max date YYYY-MM[-DD]")
    p.add_argument("--ticker", default="", help="Restrict to one ticker")
    p.add_argument("--type", dest="atype", default="", help="Restrict to one analysis_type")
    p.add_argument("--sample", type=float, default=1.0, help="Sampling fraction (0-1)")
    p.add_argument("--max", type=int, default=0, help="Hard cap on #reports scored")
    p.add_argument("--seed", type=int, default=42, help="Sampling seed")
    p.add_argument("--judge-provider", default="openai", choices=["openai", "gemini", "claude"])
    p.add_argument("--judge-model", default=None, help="Override judge model id")
    p.add_argument("--no-llm", action="store_true",
                   help="Skip judges; only report discovery + sidecar coverage")
    p.add_argument("--eval-set", type=Path, default=None,
                   help="Dir of labelled JSON samples for precision/recall")
    p.add_argument("--csv", type=Path, default=None, help="Write per-report CSV here")
    p.add_argument("--summary", action="store_true", help="Print summary to stdout")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    paths = discover(args.root, args.since, args.until, args.ticker, args.atype)
    print(f"Discovered {len(paths)} reports under {args.root}")
    if args.sample < 1.0 or args.max:
        paths = sample(paths, args.sample, args.max, args.seed)
        print(f"Sampled {len(paths)} reports (frac={args.sample}, max={args.max or '∞'})")

    rows: list[ReportRow] = []
    for i, p in enumerate(paths, 1):
        print(f"[{i}/{len(paths)}] {p.name}")
        rows.append(judge_report(p, args.judge_provider, args.judge_model, args.no_llm))

    retr = run_eval_set(args.eval_set) if args.eval_set and args.eval_set.exists() else []

    if args.csv:
        write_csv(rows, args.csv)
    if args.summary or not args.csv:
        print(summarize(rows, retr))


if __name__ == "__main__":
    main()
