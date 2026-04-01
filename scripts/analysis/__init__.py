"""
Analysis package for generating investment analysis reports.

This package provides modular components for financial analysis report generation.

Modules:
    config: Configuration constants (ANALYSIS_TYPES, DEFAULT_MODEL, etc.)
    prompts: Prompt templates loaded from text files
    utils.formatting: Data formatting utilities
    utils.data_fetch: Yahoo Finance data fetching (requires yfinance)
    utils.context: Context builders for different analysis types
    utils.llm: LLM API wrappers (requires anthropic/openai)
"""

from .config import ANALYSIS_TYPES, DEFAULT_MODEL, DEFAULT_TOKENS, TODAY
from .utils.formatting import safe, pct, money, fmt_price, df_to_text
from .prompts import PROMPT_MAP, load_prompt

# Lazy imports for functions requiring external dependencies
def fetch_data(ticker: str) -> dict:
    """Fetch financial data from Yahoo Finance."""
    from .utils.data_fetch import fetch_data as _fetch
    return _fetch(ticker)


def build_context(data: dict, analysis_type: str) -> str:
    """Build context for analysis type."""
    from .utils.context import build_context as _build
    return _build(data, analysis_type)


def call_llm(ticker: str, context: str, analysis_type: str,
             provider: str, model: str, max_tokens: int) -> str:
    """Call the appropriate LLM provider."""
    from .utils.llm import call_llm as _call
    return _call(ticker, context, analysis_type, provider, model, max_tokens)


def call_claude(ticker: str, context: str, analysis_type: str,
                model: str, max_tokens: int) -> str:
    """Call Claude API."""
    from .utils.llm import call_claude as _call
    return _call(ticker, context, analysis_type, model, max_tokens)


def call_openai(ticker: str, context: str, analysis_type: str,
                model: str, max_tokens: int) -> str:
    """Call OpenAI API."""
    from .utils.llm import call_openai as _call
    return _call(ticker, context, analysis_type, model, max_tokens)


__all__ = [
    "ANALYSIS_TYPES",
    "DEFAULT_MODEL",
    "DEFAULT_TOKENS",
    "TODAY",
    "safe",
    "pct",
    "money",
    "fmt_price",
    "df_to_text",
    "fetch_data",
    "build_context",
    "call_llm",
    "call_claude",
    "call_openai",
    "PROMPT_MAP",
    "load_prompt",
]
