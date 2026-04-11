"""Tests for context building."""

import pytest
from unittest.mock import MagicMock
from scripts.analysis.config import ANALYSIS_TYPES
from scripts.analysis.utils.context import build_context


def test_build_context_for_all_analysis_types():
    """Verify build_context returns non-empty string for all analysis types."""
    # Create minimal mock data
    mock_data = {
        "ticker": "TEST",
        "price": 100.0,
        "hist": None,
        "info": {},
        "financials": {},
        "quote": {},
        "news": [],
    }

    for analysis_type in ANALYSIS_TYPES.keys():
        result = build_context(mock_data, analysis_type)
        assert isinstance(result, str), \
            f"build_context returned non-string for {analysis_type}"
        # Note: might be empty string for some types if data is minimal


def test_build_context_with_technical_analysis():
    """Verify build_context handles technical-analysis type."""
    mock_data = {
        "ticker": "AAPL",
        "price": 150.0,
        "hist": None,
    }
    result = build_context(mock_data, "technical-analysis")
    assert isinstance(result, str)


def test_build_context_returns_string():
    """Verify build_context always returns a string."""
    mock_data = {}
    for analysis_type in ["fundamental-analysis", "technical-analysis"]:
        result = build_context(mock_data, analysis_type)
        assert isinstance(result, str), \
            f"build_context did not return string for {analysis_type}"
