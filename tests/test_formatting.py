"""Unit tests for analysis.utils.formatting (pure formatters)."""

import pandas as pd
import pytest

from scripts.analysis.utils.formatting import safe, pct, money, fmt_price, df_to_text

pytestmark = pytest.mark.unit


# ── safe ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,default,expected", [
    (None, "N/A", "N/A"),
    ("", "N/A", "N/A"),
    (None, "--", "--"),
    ("hello", "N/A", "hello"),
    (0, "N/A", 0),          # 0 is a real value, not missing
    (0.0, "N/A", 0.0),
    (False, "N/A", False),  # False != "" and is not None
    (123, "N/A", 123),
])
def test_safe(value, default, expected):
    assert safe(value, default) == expected


def test_safe_default_is_na():
    assert safe(None) == "N/A"


# ── pct ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (0.123, "12.3%"),
    (1, "100.0%"),
    (0, "0.0%"),
    (-0.05, "-5.0%"),
    (None, "N/A"),
    ("abc", "N/A"),
    ("", "N/A"),
])
def test_pct(value, expected):
    assert pct(value) == expected


def test_pct_accepts_numeric_string():
    assert pct("0.25") == "25.0%"


# ── money ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (1.5e12, "$1.50T"),
    (2.5e9, "$2.50B"),
    (3.5e6, "$3.50M"),
    (4.5e3, "$4.50K"),
    (123.0, "$123.00"),
    (0, "$0.00"),
    (None, "N/A"),
    ("bad", "N/A"),
])
def test_money(value, expected):
    assert money(value) == expected


def test_money_negative_keeps_sign_and_magnitude():
    assert money(-2e9) == "$-2.00B"


def test_money_custom_prefix():
    assert money(5e3, prefix="") == "5.00K"


# ── fmt_price ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (99.5, "$99.50"),
    (0, "$0.00"),
    (1234.567, "$1234.57"),
    (None, "N/A"),
    ("x", "N/A"),
])
def test_fmt_price(value, expected):
    assert fmt_price(value) == expected


# ── df_to_text ─────────────────────────────────────────────────────────────────

def _sample_df():
    return pd.DataFrame(
        {"2023": [1e9, 2e9], "2022": [1.5e9, 2.5e9]},
        index=["Total Revenue", "Net Income"],
    )


def test_df_to_text_none_and_empty():
    assert df_to_text(None) == "  (no data)"
    assert df_to_text(pd.DataFrame()) == "  (no data)"


def test_df_to_text_renders_requested_rows():
    out = df_to_text(_sample_df(), rows=["Total Revenue"])
    assert "Total Revenue" in out
    assert "$1.00B" in out          # 2023 column
    assert "$1.50B" in out          # 2022 column
    assert "Net Income" not in out  # not requested


def test_df_to_text_all_rows_when_none_requested():
    out = df_to_text(_sample_df())
    assert "Total Revenue" in out
    assert "Net Income" in out


def test_df_to_text_skips_unknown_rows_gracefully():
    out = df_to_text(_sample_df(), rows=["Nonexistent Row"])
    # header still present, no exception
    assert isinstance(out, str)
    assert "Nonexistent Row" not in out
