"""Tests for data fetching utilities."""

import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from scripts.analysis.utils.data_fetch import compute_technicals


@pytest.fixture
def sample_hist():
    """Create sample historical data."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    prices = [100 + i + (i % 5 - 2) * 0.5 for i in range(100)]
    return pd.DataFrame({
        "Close": prices,
        "High": [p + 1 for p in prices],
        "Low": [p - 1 for p in prices],
        "Open": [p + 0.2 for p in prices],
        "Volume": [1000000 + i * 10000 for i in range(100)],
    }, index=dates)


def test_compute_technicals_with_valid_data(sample_hist):
    """Verify compute_technicals returns a non-empty string."""
    result = compute_technicals(sample_hist)
    assert isinstance(result, str)
    assert len(result) > 0


def test_compute_technicals_with_none():
    """Verify compute_technicals handles None gracefully."""
    result = compute_technicals(None)
    assert "no OHLC data" in result.lower() or result == ""


def test_compute_technicals_with_empty_dataframe():
    """Verify compute_technicals handles empty DataFrame gracefully."""
    empty_df = pd.DataFrame()
    result = compute_technicals(empty_df)
    assert result  # Should return some message


def test_compute_technicals_includes_ma_values(sample_hist):
    """Verify compute_technicals includes moving average data."""
    result = compute_technicals(sample_hist)
    # Should contain MA indicators
    assert "MA" in result or "moving" in result.lower()
