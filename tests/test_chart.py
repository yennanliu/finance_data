"""Tests for chart generation functions."""

import pandas as pd
import pytest
from scripts.analysis.utils.data_fetch import generate_plotly_candlestick_chart


@pytest.fixture
def sample_ohlcv_data():
    """Create sample OHLCV data for testing."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    prices = [100 + i + (i % 3 - 1) * 0.5 for i in range(100)]  # Trending up with noise
    return pd.DataFrame({
        "Open": prices,
        "High": [p + 1 for p in prices],
        "Low": [p - 1 for p in prices],
        "Close": [p + 0.5 for p in prices],
        "Volume": [1000000] * 100,
    }, index=dates)


def test_generate_plotly_candlestick_chart_returns_html(sample_ohlcv_data):
    """Verify chart generation returns non-empty HTML."""
    html = generate_plotly_candlestick_chart(sample_ohlcv_data, "MSFT")
    assert isinstance(html, str)
    assert len(html) > 0
    assert "html" in html.lower()


def test_generate_plotly_candlestick_chart_includes_plotly_cdn(sample_ohlcv_data):
    """Verify generated chart includes Plotly.js CDN."""
    html = generate_plotly_candlestick_chart(sample_ohlcv_data, "MSFT")
    assert "cdn.plot.ly/plotly" in html or "plotly" in html.lower()


def test_generate_plotly_candlestick_chart_includes_ticker(sample_ohlcv_data):
    """Verify chart HTML contains the ticker name."""
    html = generate_plotly_candlestick_chart(sample_ohlcv_data, "MSFT")
    assert "MSFT" in html


def test_generate_plotly_candlestick_chart_with_empty_data():
    """Verify chart generation gracefully handles empty DataFrame."""
    empty_df = pd.DataFrame()
    html = generate_plotly_candlestick_chart(empty_df, "TEST")
    assert html == ""  # Should return empty string on failure


def test_generate_plotly_candlestick_chart_with_none():
    """Verify chart generation gracefully handles None."""
    html = generate_plotly_candlestick_chart(None, "TEST")
    assert html == ""  # Should return empty string on failure


def test_generate_plotly_candlestick_chart_includes_ma_lines(sample_ohlcv_data):
    """Verify chart includes moving average traces."""
    html = generate_plotly_candlestick_chart(sample_ohlcv_data, "MSFT")
    # Check for MA indicators (may appear in JSON data within script)
    assert "MA" in html or "moving" in html.lower()
