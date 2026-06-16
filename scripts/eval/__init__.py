"""
RAG evaluation toolkit for the report-generation pipeline.

Implements the metrics described in qa/RAG_EVALUATION.md:
  - context_store : persist the retrieval context next to each report (P0)
  - judges        : LLM-as-judge for groundedness / context & answer relevance (P1/P2)
  - retrieval     : precision / recall / F1 over an eval set (P3)
  - run_eval      : CLI that samples reports, scores them, and writes qa/eval_* (P4)
"""

from .context_store import (
    context_sidecar_path,
    read_context_sidecar,
    write_context_sidecar,
)

__all__ = [
    "context_sidecar_path",
    "read_context_sidecar",
    "write_context_sidecar",
]
