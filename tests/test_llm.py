"""Tests for LLM utilities."""

import pytest
from unittest.mock import patch, MagicMock
from scripts.analysis.utils.llm import call_llm, run_with_fallback
from scripts.analysis.exceptions import LLMError


def test_call_llm_dispatches_to_openai():
    """Verify call_llm dispatches to OpenAI for openai provider."""
    with patch("scripts.analysis.utils.llm.call_openai") as mock_openai:
        mock_openai.return_value = "mocked response"
        result = call_llm("TEST", "context", "fundamental-analysis",
                         "openai", "gpt-4o", 16000)
        mock_openai.assert_called_once()
        assert result == "mocked response"


def test_call_llm_dispatches_to_claude():
    """Verify call_llm dispatches to Claude for claude provider."""
    with patch("scripts.analysis.utils.llm.call_claude") as mock_claude:
        mock_claude.return_value = "mocked response"
        result = call_llm("TEST", "context", "fundamental-analysis",
                         "claude", "claude-sonnet-4-6", 8000)
        mock_claude.assert_called_once()
        assert result == "mocked response"


def test_call_llm_default_dispatch_is_claude():
    """Verify call_llm defaults to Claude for unknown providers."""
    with patch("scripts.analysis.utils.llm.call_claude") as mock_claude:
        mock_claude.return_value = "mocked response"
        result = call_llm("TEST", "context", "fundamental-analysis",
                         "unknown", "some-model", 8000)
        mock_claude.assert_called_once()


def test_call_llm_passes_parameters_correctly():
    """Verify call_llm passes all parameters to dispatched function."""
    with patch("scripts.analysis.utils.llm.call_openai") as mock_openai:
        mock_openai.return_value = "response"
        call_llm("TSLA", "test context", "technical-analysis",
                "openai", "gpt-4o-mini", 12000)

        # Verify all parameters were passed
        call_args = mock_openai.call_args
        assert call_args[0][0] == "TSLA"  # ticker
        assert call_args[0][1] == "test context"  # context
        assert call_args[0][2] == "technical-analysis"  # analysis_type
        assert call_args[0][3] == "gpt-4o-mini"  # model
        assert call_args[0][4] == 12000  # max_tokens


# ── run_with_fallback ────────────────────────────────────────────────────────

def test_run_with_fallback_returns_first_success():
    """The first successful attempt short-circuits; later providers aren't tried."""
    tried = []

    def run_one(provider, model):
        tried.append(provider)
        return f"report-from-{provider}"

    result, provider, model = run_with_fallback(
        [("gemini", "gemini-3.6-flash"), ("openai", "gpt-4o")], run_one)

    assert result == "report-from-gemini"
    assert (provider, model) == ("gemini", "gemini-3.6-flash")
    assert tried == ["gemini"]   # openai never attempted


def test_run_with_fallback_falls_through_on_failure():
    """A failing primary falls through to the next provider in the chain."""
    tried = []

    def run_one(provider, model):
        tried.append(provider)
        if provider == "gemini":
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return "report-from-openai"

    result, provider, model = run_with_fallback(
        [("gemini", "gemini-3.6-flash"), ("openai", "gpt-4o")], run_one)

    assert result == "report-from-openai"
    assert (provider, model) == ("openai", "gpt-4o")
    assert tried == ["gemini", "openai"]


def test_run_with_fallback_raises_last_error_when_all_fail():
    """When every provider fails, the last exception propagates."""
    def run_one(provider, model):
        raise RuntimeError(f"{provider} down")

    with pytest.raises(RuntimeError, match="openai down"):
        run_with_fallback([("gemini", "gemini-3.6-flash"), ("openai", "gpt-4o")], run_one)


def test_run_with_fallback_rejects_empty_chain():
    with pytest.raises(ValueError):
        run_with_fallback([], lambda p, m: "x")
