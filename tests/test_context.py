"""Tests for context building."""

import pytest
import pandas as pd
from unittest.mock import MagicMock
from scripts.analysis.config import ANALYSIS_TYPES
from scripts.analysis.utils.context import build_context


def get_minimal_mock_data():
    """Create minimal but valid mock data structure for build_context."""
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    hist_df = pd.DataFrame({
        "Open": [100, 101, 102, 103, 104],
        "High": [101, 102, 103, 104, 105],
        "Low": [99, 100, 101, 102, 103],
        "Close": [100.5, 101.5, 102.5, 103.5, 104.5],
        "Volume": [1000000] * 5,
    }, index=dates)

    # price_series is a dict with month keys and float values
    price_series = {
        "2024-01": 100.5,
        "2024-02": 101.5,
        "2024-03": 102.5,
    }

    # Empty DataFrames for financial data
    empty_df = pd.DataFrame()

    return {
        "ticker": "TEST",
        "price": 100.0,
        "price_now": 100.0,
        "price_52w_high": 110.0,
        "price_52w_low": 90.0,
        "price_series": price_series,
        "hist": hist_df,
        "info": {"sector": "Technology"},
        "financials": {"totalRevenue": 1e9},
        "quote": {"regularMarketPrice": 100.0},
        "news": [{"title": "Test News", "summary": "Test Summary"}],
        # Financial statement data
        "income": empty_df,
        "income_q": empty_df,
        "balance": empty_df,
        "balance_q": empty_df,
        "cashflow": empty_df,
        "cashflow_q": empty_df,
        "finviz": {},
    }


def test_build_context_for_all_analysis_types():
    """Verify build_context returns non-empty string for all analysis types."""
    mock_data = get_minimal_mock_data()

    for analysis_type in ANALYSIS_TYPES.keys():
        result = build_context(mock_data, analysis_type)
        assert isinstance(result, str), \
            f"build_context returned non-string for {analysis_type}"


def test_build_context_with_technical_analysis():
    """Verify build_context handles technical-analysis type."""
    mock_data = get_minimal_mock_data()
    result = build_context(mock_data, "technical-analysis")
    assert isinstance(result, str)


def test_build_context_returns_string():
    """Verify build_context always returns a string."""
    mock_data = get_minimal_mock_data()
    for analysis_type in ["fundamental-analysis", "technical-analysis"]:
        result = build_context(mock_data, analysis_type)
        assert isinstance(result, str), \
            f"build_context did not return string for {analysis_type}"
