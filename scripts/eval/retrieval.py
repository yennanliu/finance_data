"""
retrieval.py — P3: precision / recall / F1 over a labelled eval set.

An eval-set sample (see qa/eval_set/<TICKER>_<DATE>.json) looks like:

{
  "ticker": "AAPL",
  "date": "2026-06-16",
  "analysis_type": "market-news",
  "retrieved_docs": [{"id": "n1", "title": "...", ...}, ...],
  "relevance_labels": {"n1": 1, "n2": 0, ...},   # precision: is each retrieved doc relevant?
  "gold_events": ["Q3 earnings beat", "new iPhone launch"]  # recall: what SHOULD be covered
}

`report_md` may be attached to the sample (or passed in) so gold-event coverage can
be checked against the actual report text.
"""

from __future__ import annotations

import re
from typing import Optional


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def precision(sample: dict) -> Optional[float]:
    """relevant retrieved / total retrieved (needs relevance_labels)."""
    retrieved = sample.get("retrieved_docs") or []
    labels = sample.get("relevance_labels") or {}
    if not retrieved or not labels:
        return None
    rel = 0
    counted = 0
    for i, d in enumerate(retrieved):
        did = str(d.get("id", i))
        if did in labels:
            counted += 1
            rel += int(bool(labels[did]))
    return (rel / counted) if counted else None


def _event_covered(event: str, haystack: str) -> bool:
    """A gold event is covered if its salient tokens all appear in the text."""
    tokens = [t for t in re.findall(r"[a-z0-9]+", _norm(event)) if len(t) > 2]
    if not tokens:
        return False
    hay = _norm(haystack)
    hits = sum(1 for t in tokens if t in hay)
    return hits >= max(1, int(round(0.6 * len(tokens))))  # 60% of salient tokens


def recall(sample: dict, report_md: Optional[str] = None) -> Optional[float]:
    """gold events covered by report/context / total gold events (needs gold_events)."""
    gold = sample.get("gold_events") or []
    if not gold:
        return None
    haystack = report_md or sample.get("report_md") or ""
    # also let coverage match against retrieved doc titles/summaries
    for d in sample.get("retrieved_docs") or []:
        haystack += "\n" + (d.get("title") or "") + " " + (d.get("summary") or "")
    hit = sum(1 for e in gold if _event_covered(e, haystack))
    return hit / len(gold)


def f1(p: Optional[float], r: Optional[float]) -> Optional[float]:
    if p is None or r is None or (p + r) == 0:
        return None
    return 2 * p * r / (p + r)


def evaluate_sample(sample: dict, report_md: Optional[str] = None) -> dict:
    p = precision(sample)
    r = recall(sample, report_md)
    return {
        "ticker": sample.get("ticker"),
        "date": sample.get("date"),
        "precision": p,
        "recall": r,
        "f1": f1(p, r),
        "n_retrieved": len(sample.get("retrieved_docs") or []),
        "n_gold": len(sample.get("gold_events") or []),
    }


__all__ = ["precision", "recall", "f1", "evaluate_sample"]
