"""
judges.py — P1/P2: LLM-as-judge metrics.

`call_llm` in the analysis package is bound to the analysis prompt templates, so
judges use their own lightweight raw-completion helper `judge_complete`, which
mirrors the provider calls in generate_market_news.py.

Metrics:
  groundedness(report, context)          -> faithfulness, the core hallucination metric
  context_relevance(docs, ticker)        -> retriever quality
  answer_relevance(report, ticker, type) -> generator quality

All judges return a dict and degrade gracefully (score=None) if the judge output
cannot be parsed, so a batch run never crashes on one bad response.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

_PROMPT_DIR = Path(__file__).parent / "prompts"

# Default judge model per provider. Use a DIFFERENT model from the generator to
# reduce self-preference bias (see qa/RAG_EVALUATION.md §2.3).
DEFAULT_JUDGE_MODELS = {
    "openai": "gpt-4o",
    "gemini": "gemini-2.5-flash",
    "claude": "claude-opus-4-6",
}


class JudgeError(RuntimeError):
    pass


def _load_prompt(name: str) -> str:
    return (_PROMPT_DIR / name).read_text(encoding="utf-8")


# ── raw completion ───────────────────────────────────────────────────────────

def judge_complete(prompt: str, provider: str = "openai",
                   model: Optional[str] = None, max_tokens: int = 3000,
                   temperature: float = 0.0) -> str:
    """Single-shot raw completion for judging. Returns response text."""
    provider = provider.lower()
    model = model or DEFAULT_JUDGE_MODELS.get(provider, "gpt-4o")

    if provider == "openai":
        import openai
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise JudgeError("OPENAI_API_KEY not set")
        client = openai.OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model=model, max_tokens=max_tokens, temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""

    if provider == "gemini":
        from google import genai
        from google.genai import types
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise JudgeError("GEMINI_API_KEY not set")
        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model=model, contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=max_tokens, temperature=temperature),
        )
        return resp.text or ""

    if provider == "claude":
        import anthropic
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise JudgeError("ANTHROPIC_API_KEY not set")
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=model, max_tokens=max_tokens, temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return "\n".join(b.text for b in resp.content if hasattr(b, "text"))

    raise JudgeError(f"unknown provider: {provider}")


# ── JSON extraction ──────────────────────────────────────────────────────────

def extract_json(text: str) -> Any:
    """Best-effort parse of a JSON object/array from a model response."""
    if not text:
        raise JudgeError("empty judge response")
    s = text.strip()
    # strip ```json ... ``` fences
    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.S)
    if fence:
        s = fence.group(1).strip()
    # locate first opening bracket
    starts = [i for i in (s.find("{"), s.find("[")) if i != -1]
    if not starts:
        raise JudgeError("no JSON found in judge response")
    start = min(starts)
    opener = s[start]
    closer = "}" if opener == "{" else "]"
    end = s.rfind(closer)
    if end == -1 or end < start:
        raise JudgeError("unbalanced JSON in judge response")
    return json.loads(s[start:end + 1])


# ── truncation (keep judge cost/context bounded) ─────────────────────────────

_MAX_CTX = 24000
_MAX_REPORT = 24000


def _clip(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "\n…[truncated]"


# ── metrics ──────────────────────────────────────────────────────────────────

def groundedness(report_md: str, context_text: str, *, provider: str = "openai",
                 model: Optional[str] = None, max_claims: int = 40) -> dict:
    """Fraction of report claims supported by the context. Core hallucination metric."""
    if not context_text:
        return {"groundedness": None, "error": "no_context", "n_claims": 0,
                "n_unsupported": 0, "unsupported_claims": []}
    prompt = _load_prompt("groundedness.txt").format(
        context=_clip(context_text, _MAX_CTX),
        report=_clip(report_md, _MAX_REPORT),
        max_claims=max_claims,
    )
    try:
        raw = judge_complete(prompt, provider, model, max_tokens=3500)
        data = extract_json(raw)
        claims = data.get("claims", []) if isinstance(data, dict) else (data or [])
        total = len(claims)
        supported = sum(1 for c in claims if c.get("supported"))
        unsupported = [c for c in claims if not c.get("supported")]
        return {
            "groundedness": (supported / total) if total else None,
            "n_claims": total,
            "n_unsupported": total - supported,
            "unsupported_claims": unsupported[:10],
        }
    except Exception as exc:
        return {"groundedness": None, "error": str(exc), "n_claims": 0,
                "n_unsupported": 0, "unsupported_claims": []}


def context_relevance(docs: list[dict], ticker: str, *, provider: str = "openai",
                      model: Optional[str] = None) -> dict:
    """Fraction of retrieved docs judged relevant to analysing the ticker."""
    if not docs:
        return {"context_relevance": None, "error": "no_docs", "n_docs": 0, "per_doc": []}
    lines = []
    for i, d in enumerate(docs):
        did = str(d.get("id", i))
        title = (d.get("title") or "").strip()
        summary = (d.get("summary") or "").strip()
        pub = (d.get("publisher") or "").strip()
        lines.append(f"[{did}] ({pub}) {title} — {summary[:200]}")
    prompt = _load_prompt("context_relevance.txt").format(
        ticker=ticker, docs="\n".join(lines))
    try:
        raw = judge_complete(prompt, provider, model, max_tokens=2000)
        data = extract_json(raw)
        rows = data.get("docs", []) if isinstance(data, dict) else (data or [])
        rel = [int(bool(r.get("relevant"))) for r in rows]
        return {
            "context_relevance": (sum(rel) / len(rel)) if rel else None,
            "n_docs": len(rows),
            "per_doc": rows,
        }
    except Exception as exc:
        return {"context_relevance": None, "error": str(exc), "n_docs": len(docs), "per_doc": []}


def answer_relevance(report_md: str, ticker: str, analysis_type: str, *,
                     provider: str = "openai", model: Optional[str] = None) -> dict:
    """1-5 score of whether the report actually answers the analysis question."""
    prompt = _load_prompt("answer_relevance.txt").format(
        ticker=ticker, analysis_type=analysis_type,
        report=_clip(report_md, _MAX_REPORT))
    try:
        raw = judge_complete(prompt, provider, model, max_tokens=500)
        data = extract_json(raw)
        score = data.get("answer_relevance")
        return {"answer_relevance": float(score) if score is not None else None,
                "reason": data.get("reason", "")}
    except Exception as exc:
        return {"answer_relevance": None, "error": str(exc), "reason": ""}


__all__ = [
    "judge_complete", "extract_json",
    "groundedness", "context_relevance", "answer_relevance",
    "DEFAULT_JUDGE_MODELS", "JudgeError",
]
