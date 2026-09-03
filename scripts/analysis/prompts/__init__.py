"""
Prompt templates for analysis generation.

Prompts are stored as text files in this directory and loaded on demand.
"""

from __future__ import annotations

from pathlib import Path

from ..config import ANALYSIS_TYPES

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


# Derived from ANALYSIS_TYPES so the two can never disagree: declaring a new
# analysis type there is all it takes to make its prompt loadable here.
_PROMPT_FILES = {k: v["prompt_file"] for k, v in ANALYSIS_TYPES.items()}


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
