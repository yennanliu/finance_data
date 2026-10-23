"""Unit tests for analysis.prompts (template loading + PROMPT_MAP)."""

import pytest

from scripts.analysis.config import ANALYSIS_TYPES
from scripts.analysis.prompts import PROMPT_MAP, load_prompt
from scripts.analysis.prompts import _PROMPT_FILES  # internal map, asserted against config

pytestmark = pytest.mark.unit


def test_load_prompt_returns_content_with_placeholders():
    text = load_prompt("fundamental")
    assert isinstance(text, str) and text
    assert "{ticker}" in text
    assert "{financial_context}" in text
    assert "{today}" in text


def test_load_prompt_caches(monkeypatch):
    # First load populates the cache; a second load must not re-read the file.
    load_prompt("technical")
    import scripts.analysis.prompts as prompts_mod

    def _boom(*a, **k):
        raise AssertionError("file was read again despite cache")

    # Patch Path.read_text so any cache miss would blow up.
    monkeypatch.setattr("pathlib.Path.read_text", _boom)
    assert load_prompt("technical")  # served from cache, no read


def test_load_prompt_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_prompt("definitely_not_a_real_prompt_xyz")


def test_prompt_map_getitem_and_contains():
    assert "fundamental-analysis" in PROMPT_MAP
    assert "bogus-type" not in PROMPT_MAP
    assert isinstance(PROMPT_MAP["fundamental-analysis"], str)


def test_prompt_map_unknown_key_raises():
    with pytest.raises(KeyError):
        PROMPT_MAP["nope"]


def test_prompt_map_keys_match_config():
    assert set(PROMPT_MAP.keys()) == set(_PROMPT_FILES.keys())
    # Every configured analysis type must have a prompt mapping.
    assert set(ANALYSIS_TYPES.keys()) == set(PROMPT_MAP.keys())


@pytest.mark.parametrize("analysis_type", list(ANALYSIS_TYPES.keys()))
def test_every_analysis_type_template_resolves_and_has_placeholders(analysis_type):
    template = PROMPT_MAP[analysis_type]
    assert template.strip()
    for placeholder in ("{ticker}", "{financial_context}", "{today}"):
        assert placeholder in template, f"{analysis_type} missing {placeholder}"


@pytest.mark.parametrize("analysis_type", list(ANALYSIS_TYPES.keys()))
def test_templates_format_cleanly(analysis_type):
    # Guards against stray unescaped braces that would break str.format at runtime.
    rendered = PROMPT_MAP[analysis_type].format(
        ticker="AAPL", financial_context="CTX", today="2026-01-01"
    )
    assert "AAPL" in rendered
    assert "{ticker}" not in rendered


# ── fundamental prompt: rules from the 2026-10-22 fact-check ─────────────────
# docs/FUNDAMENTAL_REPORT_REVIEW.md §2 / §3 / §12.

import re
from pathlib import Path

_PROMPTS = Path(__file__).resolve().parent.parent / "scripts" / "analysis" / "prompts"


def test_fundamental_prompt_has_no_copyable_example_numbers():
    """Its old worked example "WACC = … = 9.41%" reappeared as the WACC of 165
    of 795 October reports. Examples must be symbolic."""
    text = load_prompt("fundamental")
    assert re.findall(r"\d+\.\d+\s*%", text) == []
    assert re.findall(r"\$\d", text) == []


def test_fundamental_toc_template_lists_all_eleven_chapters():
    """The old template elided rows with "...", and reports dropped chapter 11."""
    text = load_prompt("fundamental")
    toc = text[text.index("## 目錄"):text.index("## 1. 執行摘要")]
    rows = re.findall(r"^\| (\d+) \|", toc, re.M)
    assert rows == [str(n) for n in range(1, 12)]


def test_fundamental_prompt_chapters_match_the_stage1_check():
    from scripts.analysis.validate.arithmetic import FUNDAMENTAL_CHAPTERS
    text = load_prompt("fundamental")
    found = [int(n) for n in re.findall(r"^## (\d+)\. ", text, re.M)]
    assert found == list(FUNDAMENTAL_CHAPTERS)


def test_fundamental_prompt_defines_rating_thresholds_and_verified_figures():
    text = load_prompt("fundamental")
    assert "評級門檻" in text and "MOS ≥ 25%" in text and "MOS < −25%" in text
    assert "VERIFIED FIGURES" in text
    assert "取報告日" not in text      # a pre-open slot cannot have the report-date close


@pytest.mark.parametrize("name", ["gemini_system.txt", "openai_system.txt"])
def test_system_messages_defer_structure_to_the_prompt(name):
    """gemini_system.txt said "10 章" and 8000–12000 字 against the prompt's
    11 chapters and 7000–10000 字."""
    text = (_PROMPTS / name).read_text(encoding="utf-8")
    assert "10 章" not in text
    assert "11 章" in text
    assert "7000–10000" in text
    assert "專業推演" not in text        # "fill gaps from your own knowledge" invited fabrication
