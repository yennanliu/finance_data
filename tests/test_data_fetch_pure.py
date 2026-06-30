"""Unit tests for the pure (no-network) helpers in analysis.utils.data_fetch."""

import pandas as pd
import pytest
from bs4 import BeautifulSoup

from scripts.analysis.utils.data_fetch import (
    price_ascii_chart,
    compute_moving_average_charts,
    compute_technicals,
    _parse_finviz_number,
    _merge_finviz_into_info,
    _html_table_to_text,
    _format_finviz,
    _format_stockanalysis,
    _format_roic,
)

pytestmark = pytest.mark.unit


# ── price_ascii_chart ────────────────────────────────────────────────────────

def test_price_ascii_chart_empty():
    assert price_ascii_chart({}) == "  (no price history)"


def test_price_ascii_chart_renders_months():
    out = price_ascii_chart({"2024-01": 100.0, "2024-02": 110.0, "2024-03": 105.0})
    assert "月份" in out
    assert "2024-01" in out and "2024-03" in out
    assert "█" in out  # at least the max month draws bars


# ── compute_moving_average_charts ────────────────────────────────────────────

def test_ma_charts_none_and_empty():
    assert compute_moving_average_charts(None) == ""
    assert compute_moving_average_charts(pd.DataFrame()) == ""


def test_ma_charts_with_data(sample_hist):
    out = compute_moving_average_charts(sample_hist)
    assert "移動平均線" in out
    assert "MA  5" in out
    assert "MA240" in out


def test_ma_charts_insufficient_data():
    short = pd.DataFrame({"Close": [100, 101, 102]})
    out = compute_moving_average_charts(short)
    assert "資料不足" in out  # not enough rows for MA5


# ── compute_technicals ───────────────────────────────────────────────────────

def test_compute_technicals_none_and_empty():
    assert "no ohlc data" in compute_technicals(None).lower()
    assert compute_technicals(pd.DataFrame())  # returns a message, no crash


def test_compute_technicals_contains_indicators(sample_hist):
    out = compute_technicals(sample_hist)
    assert isinstance(out, str) and out
    assert "RSI" in out
    assert "MA" in out


# ── _parse_finviz_number ─────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("1.5T", 1.5e12),
    ("1.23B", 1.23e9),
    ("456.7M", 456.7e6),
    ("12.3K", 12.3e3),
    ("12.34%", pytest.approx(0.1234)),
    ("1,234", 1234.0),
    ("12.5", 12.5),
    ("-50.0%", pytest.approx(-0.5)),
])
def test_parse_finviz_number_valid(raw, expected):
    assert _parse_finviz_number(raw) == expected


@pytest.mark.parametrize("raw", ["-", "", None, "abc", "N/A"])
def test_parse_finviz_number_invalid(raw):
    assert _parse_finviz_number(raw) is None


# ── _merge_finviz_into_info ──────────────────────────────────────────────────

def test_merge_backfills_missing_field():
    info = {}
    out = _merge_finviz_into_info(info, {"P/E": "15.2"})
    assert out["trailingPE"] == pytest.approx(15.2)


def test_merge_does_not_overwrite_existing():
    info = {"trailingPE": 20.0}
    _merge_finviz_into_info(info, {"P/E": "15.2"})
    assert info["trailingPE"] == 20.0


def test_merge_percentage_field_converted_to_decimal():
    info = {}
    _merge_finviz_into_info(info, {"ROE": "12.3%"})
    assert info["returnOnEquity"] == pytest.approx(0.123)


def test_merge_empty_finviz_returns_info_unchanged():
    info = {"a": 1}
    assert _merge_finviz_into_info(info, {}) is info


def test_merge_skips_dash_values():
    info = {}
    _merge_finviz_into_info(info, {"P/E": "-"})
    assert "trailingPE" not in info


# ── _html_table_to_text ──────────────────────────────────────────────────────

def test_html_table_to_text():
    html = """
    <table>
      <tr><th>Year</th><th>Revenue</th></tr>
      <tr><td>2023</td><td>100</td></tr>
      <tr><td>2022</td><td>90</td></tr>
    </table>
    """
    table = BeautifulSoup(html, "html.parser").find("table")
    out = _html_table_to_text(table)
    assert "Year" in out and "Revenue" in out
    assert "2023" in out and "100" in out


def test_html_table_to_text_respects_max_rows():
    rows = "".join(f"<tr><td>{i}</td></tr>" for i in range(50))
    table = BeautifulSoup(f"<table>{rows}</table>", "html.parser").find("table")
    out = _html_table_to_text(table, max_rows=5)
    # header + max_rows data lines = 6
    assert len(out.splitlines()) == 6


# ── formatters ───────────────────────────────────────────────────────────────

def test_format_finviz_empty():
    assert "no Finviz data" in _format_finviz({})


def test_format_finviz_groups_known_keys():
    out = _format_finviz({"P/E": "15", "ROE": "12%", "Beta": "1.1"})
    assert "[Valuation]" in out
    assert "P/E" in out
    assert "[Profitability]" in out


def test_format_finviz_skips_dash():
    out = _format_finviz({"P/E": "-"})
    assert "no Finviz data" in out  # only dash → nothing to show


def test_format_stockanalysis_empty():
    assert "no StockAnalysis data" in _format_stockanalysis({})


def test_format_stockanalysis_sections():
    out = _format_stockanalysis({"financials_annual": "ROW1", "balance_sheet": "BS"})
    assert "Annual Income Statement" in out
    assert "Balance Sheet" in out


def test_format_roic_empty():
    assert "no Roic.ai data" in _format_roic({})


def test_format_roic_table():
    data = {"table_0": {"headers": ["Year", "ROIC"], "rows": [["2023", "15%"], ["2022", "12%"]]}}
    out = _format_roic(data)
    assert "Year" in out and "ROIC" in out
    assert "2023" in out
