"""
context_store.py — P0: persist the retrieval context next to each report.

Today only the final Markdown report is saved, so groundedness/precision are
uncomputable after the fact. This module writes a `<report>.context.json`
sidecar capturing exactly what was fed to the LLM (financial context and/or
retrieved news docs), so the eval layer has a "ground truth context" to judge
against.

Writing a sidecar must NEVER break report generation — every failure is caught
and downgraded to a warning.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional


def context_sidecar_path(report_path: Path | str) -> Path:
    """`foo/bar.md` -> `foo/bar.context.json` (also handles `bar-2.md`)."""
    return Path(report_path).with_suffix(".context.json")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_context_sidecar(
    report_path: Path | str,
    *,
    ticker: str,
    analysis_type: str,
    provider: str,
    model: str,
    date: str,
    context_text: str = "",
    retrieved_docs: Optional[list[dict]] = None,
    extra: Optional[dict[str, Any]] = None,
) -> Optional[Path]:
    """
    Write a context sidecar next to *report_path*.

    context_text   : the unstructured text actually given to the model
                     (financial_context for analysis, news_block for market-news).
                     This is what groundedness/context-relevance judge against.
    retrieved_docs : structured list of retrieved items (news rows). Used by the
                     precision/recall layer.

    Returns the sidecar path, or None on failure (never raises).
    """
    try:
        payload: dict[str, Any] = {
            "schema_version": 1,
            "ticker": ticker,
            "date": date,
            "analysis_type": analysis_type,
            "provider": provider,
            "model": model,
            "context_sha256": _sha256(context_text) if context_text else None,
            "context_chars": len(context_text or ""),
            "context_text": context_text or "",
            "retrieved_docs": retrieved_docs or [],
        }
        if extra:
            payload.update(extra)

        path = context_sidecar_path(report_path)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  🗂  context sidecar → {path.name}")
        return path
    except Exception as exc:  # never break generation
        print(f"  [WARN] failed to write context sidecar: {exc}")
        return None


def read_context_sidecar(report_path: Path | str) -> Optional[dict]:
    """Load the sidecar for a report, or None if missing/unreadable."""
    path = context_sidecar_path(report_path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
