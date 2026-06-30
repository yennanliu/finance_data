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
