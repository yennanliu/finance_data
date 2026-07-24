"""LLM layer: generic provider runners + analysis-report dispatch.

The canonical implementation lives in :mod:`analysis.utils.llm` (kept there so
``call_llm`` resolves the ``call_*`` functions as its own module globals, which
the test-suite monkeypatches). This package re-exports that surface as the
layer's public API; new code should import from ``analysis.llm``.
"""

from ..utils.llm import (  # noqa: F401
    run_claude, run_openai, run_gemini,
    call_claude, call_openai, call_gemini, call_llm,
    run_with_fallback,
    OPENAI_MAX_TOKENS,
    _is_refusal, _refusal_override_prefix, _repeated_heading, _gemini_finish_reason,
    _load_openai_system_message, _load_gemini_system_message,
)

__all__ = [
    "run_claude", "run_openai", "run_gemini",
    "call_claude", "call_openai", "call_gemini", "call_llm",
    "run_with_fallback",
    "OPENAI_MAX_TOKENS",
]
