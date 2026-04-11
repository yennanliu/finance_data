"""Tests for LLM utilities."""

import pytest
from unittest.mock import patch, MagicMock
from scripts.analysis.utils.llm import call_llm
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
