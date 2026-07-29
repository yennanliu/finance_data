"""Publish layer: write generated reports to disk.

Centralises the two output concerns shared by the generator scripts:
  * ``dedup_path`` — same-day filename de-duplication (``-2``, ``-3``, …)
  * ``frontmatter`` — render a YAML frontmatter block from ordered fields

Callers own their field set and filename policy, so per-script output stays
byte-identical while the path/frontmatter mechanics live in one place.
"""

from __future__ import annotations

from pathlib import Path


def dedup_path(output_dir: Path, base: str, ext: str = ".md") -> Path:
    """Return ``output_dir/<base><ext>``, bumping ``-2``, ``-3``… if it exists.

    Creates ``output_dir`` if needed.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{base}{ext}"
    counter = 2
    while path.exists():
        path = output_dir / f"{base}-{counter}{ext}"
        counter += 1
    return path


def frontmatter(fields: dict) -> str:
    """Render an ordered dict of fields into a YAML frontmatter block.

    Values are emitted verbatim, so a caller wanting a quoted string should
    include the quotes in the value (e.g. ``{"title": '"AAPL 2026-01-01"'}``).
    """
    body = "".join(f"{key}: {value}\n" for key, value in fields.items())
    return f"---\n{body}---\n\n"


# Human-readable API label for the `generated_by` front-matter field, shared by
# the analysis pipeline and the market-news generator.
GENERATED_BY = {"openai": "OpenAI API", "gemini": "Google Gemini API"}


__all__ = ["dedup_path", "frontmatter", "GENERATED_BY"]
