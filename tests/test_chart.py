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


def test_generate_plotly_candlestick_chart_returns_dict(sample_ohlcv_data):
    """Verify chart generation returns dict with plotly_html and png_filename keys."""
    result = generate_plotly_candlestick_chart(sample_ohlcv_data, "MSFT")
    assert isinstance(result, dict)
    assert "plotly_html" in result
    assert "png_filename" in result
    assert isinstance(result["plotly_html"], str)


def test_generate_plotly_candlestick_chart_includes_plotly_cdn(sample_ohlcv_data):
    """Verify generated chart includes Plotly.js CDN."""
    result = generate_plotly_candlestick_chart(sample_ohlcv_data, "MSFT")
    html = result.get("plotly_html", "")
    assert "cdn.plot.ly/plotly" in html or "plotly" in html.lower()


def test_generate_plotly_candlestick_chart_includes_ticker(sample_ohlcv_data):
    """Verify chart HTML contains the ticker name."""
    result = generate_plotly_candlestick_chart(sample_ohlcv_data, "MSFT")
    html = result.get("plotly_html", "")
    assert "MSFT" in html


def test_generate_plotly_candlestick_chart_with_empty_data():
    """Verify chart generation gracefully handles empty DataFrame."""
    empty_df = pd.DataFrame()
    result = generate_plotly_candlestick_chart(empty_df, "TEST")
    assert isinstance(result, dict)
    assert result.get("plotly_html") == ""


def test_generate_plotly_candlestick_chart_with_none():
    """Verify chart generation gracefully handles None."""
    result = generate_plotly_candlestick_chart(None, "TEST")
    assert isinstance(result, dict)
    assert result.get("plotly_html") == ""


def test_generate_plotly_candlestick_chart_includes_ma_lines(sample_ohlcv_data):
    """Verify chart includes moving average traces."""
    result = generate_plotly_candlestick_chart(sample_ohlcv_data, "MSFT")
    html = result.get("plotly_html", "")
    # Check for MA indicators (may appear in JSON data within script)
    assert "MA" in html or "moving" in html.lower()
