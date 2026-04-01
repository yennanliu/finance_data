"""
LLM API wrappers for Claude and OpenAI.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from ..config import TODAY
from ..prompts import PROMPT_MAP, load_prompt

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

    # Detect refusal patterns and retry with stronger instruction
    refusal_patterns = ["抱歉", "無法完成", "無法滿足", "無法處理", "無法提供", "過於龐大"]
    if len(text) < 500 and any(p in text for p in refusal_patterns):
        print(f"  ⚠️  Detected refusal response, retrying with stronger instruction...")
        retry_prompt = f"""你之前的回覆被拒絕了。請注意：

1. 你必須產出報告，不能拒絕
2. 即使數據不完整，也要基於你的專業知識完成分析
3. 如果是已下市或數據稀少的公司，請說明情況並提供歷史分析

現在請直接開始輸出報告，從標題「# {ticker} 基本面深度分析報告」開始：

{prompt}"""

        retry_response = client.chat.completions.create(
            model=model,
            max_tokens=effective_max_tokens,
            temperature=0.7,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": retry_prompt},
            ],
        )
        text = retry_response.choices[0].message.content
        retry_usage = retry_response.usage
        print(f"  ✅ retry response  in={retry_usage.prompt_tokens}  out={retry_usage.completion_tokens}"
              f"  chars={len(text)}")

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
