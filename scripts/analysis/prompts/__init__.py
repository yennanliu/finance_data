"""
Prompt templates for analysis generation.

Prompts are stored as text files in this directory and loaded on demand.
"""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent
_CACHE: dict[str, str] = {}


def load_prompt(name: str) -> str:
    """Load a prompt template from file.

    Args:
        name: The prompt name (e.g., 'fundamental', 'technical')

    Returns:
        The prompt template string with {ticker}, {financial_context}, {today} placeholders.
    """
    if name in _CACHE:
        return _CACHE[name]

    path = _PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    content = path.read_text(encoding="utf-8")
    _CACHE[name] = content
    return content


# Map analysis types to their prompt file names
_PROMPT_FILES = {
    "fundamental-analysis": "fundamental",
    "technical-analysis": "technical",
    "stock-eval": "stock_eval",
    "economics-analysis": "economics",
    "portfolio-review": "portfolio",
    "sector-analysis": "sector",
    "earnings-call-analysis": "earnings_call",
    "insider-trading": "insider_trading",
    "institutional-ownership": "institutional",
    "report-generator": "report_generator",
    "financial-report-analyst": "financial_report_analyst",
    "stock-valuation": "stock_valuation",
}


class PromptMap:
    """Lazy-loading prompt map that acts like a dict."""

    def __getitem__(self, key: str) -> str:
        if key not in _PROMPT_FILES:
            raise KeyError(f"Unknown analysis type: {key}")
        return load_prompt(_PROMPT_FILES[key])

    def __contains__(self, key: str) -> bool:
        return key in _PROMPT_FILES

    def keys(self):
        return _PROMPT_FILES.keys()


PROMPT_MAP = PromptMap()

__all__ = ["load_prompt", "PROMPT_MAP"]
