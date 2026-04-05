"""
LLM API wrappers for Claude and OpenAI.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

from ..config import TODAY
from ..prompts import PROMPT_MAP, load_prompt

# Refusal patterns — short responses containing these are likely model refusals
_REFUSAL_PATTERNS = [
    "抱歉", "無法協助", "無法完成", "無法滿足", "無法處理",
    "無法提供", "過於龐大", "I cannot", "I'm unable", "I can't",
]
_MAX_REFUSAL_RETRIES = 3


def _is_refusal(text: str) -> bool:
    """Detect if a response is a model refusal (short + contains refusal phrase)."""
    return len(text) < 500 and any(p in text for p in _REFUSAL_PATTERNS)

# OpenAI model token limits
OPENAI_MAX_TOKENS = {
    "gpt-4o": 16384,
    "gpt-4o-mini": 16384,
    "gpt-4-turbo": 4096,
    "gpt-4": 8192,
}


def _load_openai_system_message() -> str:
    """Load the OpenAI system message template."""
    path = Path(__file__).parent.parent / "prompts" / "openai_system.txt"
    return path.read_text(encoding="utf-8")


def _get_anthropic():
    """Lazy import of anthropic."""
    try:
        import anthropic
        return anthropic
    except ImportError:
        sys.exit("ERROR: 'anthropic' not installed.  Run: pip install anthropic")


def call_claude(ticker: str, context: str, analysis_type: str,
                model: str, max_tokens: int) -> str:
    """Call Claude API and return the response text."""
    anthropic = _get_anthropic()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY environment variable is not set.")

    client = anthropic.Anthropic(api_key=api_key)
    template = PROMPT_MAP[analysis_type]
    prompt = template.format(
        ticker=ticker,
        financial_context=context,
        today=TODAY,
    )

    print(f"  → Claude API  model={model}  max_tokens={max_tokens}")

    max_retries = 5
    base_delay = 30  # seconds
    for attempt in range(1, max_retries + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            break
        except anthropic.RateLimitError:
            if attempt == max_retries:
                raise
            delay = base_delay * (2 ** (attempt - 1))
            print(f"  ⚠️  Rate limit hit (attempt {attempt}/{max_retries})."
                  f" Retrying in {delay}s …")
            time.sleep(delay)

    text = "\n\n".join(b.text for b in response.content if hasattr(b, "text"))
    usage = response.usage
    print(f"  ✅ response  in={usage.input_tokens}  out={usage.output_tokens}"
          f"  chars={len(text)}")

    # Retry on refusal
    for retry in range(1, _MAX_REFUSAL_RETRIES + 1):
        if not _is_refusal(text):
            break
        print(f"  ⚠️  Refusal detected (attempt {retry}/{_MAX_REFUSAL_RETRIES}), retrying …")
        time.sleep(3)
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "\n\n".join(b.text for b in response.content if hasattr(b, "text"))
        usage = response.usage
        print(f"  ✅ retry {retry}  in={usage.input_tokens}  out={usage.output_tokens}"
              f"  chars={len(text)}")

    if _is_refusal(text):
        print(f"  ❌ All {_MAX_REFUSAL_RETRIES} retries returned refusal. Returning last response.")

    return text


def call_openai(ticker: str, context: str, analysis_type: str,
                model: str, max_tokens: int) -> str:
    """Call OpenAI API and return the response text."""
    try:
        import openai
    except ImportError:
        sys.exit("ERROR: 'openai' not installed.  Run: pip install openai")

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        sys.exit("ERROR: OPENAI_API_KEY environment variable is not set.")

    # Apply model-specific token limits
    model_max = OPENAI_MAX_TOKENS.get(model, 16384)
    effective_max_tokens = min(max_tokens, model_max)
    if effective_max_tokens != max_tokens:
        print(f"  [INFO] Capping max_tokens from {max_tokens} to {effective_max_tokens} for {model}")

    # Load and format system message
    system_template = _load_openai_system_message()
    system_message = system_template.format(ticker=ticker)

    client = openai.OpenAI(api_key=api_key)
    template = PROMPT_MAP[analysis_type]
    prompt = template.format(
        ticker=ticker,
        financial_context=context,
        today=TODAY,
    )

    print(f"  → OpenAI API  model={model}  max_tokens={effective_max_tokens}")

    max_retries = 5
    base_delay = 30  # seconds
    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=effective_max_tokens,
                temperature=0.7,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt},
                ],
            )
            break
        except openai.RateLimitError:
            if attempt == max_retries:
                raise
            delay = base_delay * (2 ** (attempt - 1))
            print(f"  ⚠️  Rate limit hit (attempt {attempt}/{max_retries})."
                  f" Retrying in {delay}s …")
            time.sleep(delay)

    text = response.choices[0].message.content
    usage = response.usage
    total_tokens = usage.prompt_tokens + usage.completion_tokens
    print(f"  ✅ response  in={usage.prompt_tokens}  out={usage.completion_tokens}  total={total_tokens}"
          f"  chars={len(text)}")

    # Retry on refusal responses
    for retry in range(1, _MAX_REFUSAL_RETRIES + 1):
        if not _is_refusal(text):
            break
        print(f"  ⚠️  Refusal detected (attempt {retry}/{_MAX_REFUSAL_RETRIES}), retrying …")
        time.sleep(3)
        retry_response = client.chat.completions.create(
            model=model,
            max_tokens=effective_max_tokens,
            temperature=0.7,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
        )
        text = retry_response.choices[0].message.content
        retry_usage = retry_response.usage
        print(f"  ✅ retry {retry}  in={retry_usage.prompt_tokens}  out={retry_usage.completion_tokens}"
              f"  chars={len(text)}")

    if _is_refusal(text):
        print(f"  ❌ All {_MAX_REFUSAL_RETRIES} retries returned refusal. Returning last response.")

    # Log if under-utilizing available tokens
    if usage.completion_tokens < effective_max_tokens * 0.7:
        print(f"  ℹ️  Token usage is {usage.completion_tokens}/{effective_max_tokens} "
              f"({100*usage.completion_tokens//effective_max_tokens}%) - report could be more detailed")
    return text


def call_llm(ticker: str, context: str, analysis_type: str,
             provider: str, model: str, max_tokens: int) -> str:
    """Dispatch to the appropriate LLM provider."""
    if provider == "openai":
        return call_openai(ticker, context, analysis_type, model, max_tokens)
    else:
        return call_claude(ticker, context, analysis_type, model, max_tokens)


__all__ = ["call_claude", "call_openai", "call_llm"]
