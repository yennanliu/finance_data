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
    "PROMPT_MAP",
    "load_prompt",
]
