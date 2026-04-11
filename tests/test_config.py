"""Tests for analysis package configuration."""

import pytest
from scripts.analysis.config import ANALYSIS_TYPES, TODAY
from scripts.analysis.config.providers import PROVIDER_DEFAULTS


def test_analysis_types_keys():
    """Verify ANALYSIS_TYPES contains all expected analysis type keys."""
    expected_keys = {
        "fundamental-analysis",
        "technical-analysis",
        "stock-eval",
        "economics-analysis",
        "portfolio-review",
        "sector-analysis",
        "earnings-call-analysis",
        "insider-trading",
        "institutional-ownership",
        "report-generator",
        "financial-report-analyst",
        "stock-valuation",
    }
    assert set(ANALYSIS_TYPES.keys()) == expected_keys, \
        f"Missing or extra analysis types. Expected {expected_keys}, got {set(ANALYSIS_TYPES.keys())}"


def test_analysis_type_has_required_fields():
    """Verify each analysis type has required configuration fields."""
    for analysis_type, config in ANALYSIS_TYPES.items():
        assert "filename_prefix" in config, f"{analysis_type} missing 'filename_prefix'"
        assert "label" in config, f"{analysis_type} missing 'label'"
        assert isinstance(config.get("ext", ".md"), str), \
            f"{analysis_type} has invalid 'ext' field"


def test_provider_defaults_structure():
    """Verify provider defaults have correct structure."""
    assert "claude" in PROVIDER_DEFAULTS
    assert "openai" in PROVIDER_DEFAULTS

    for provider, defaults in PROVIDER_DEFAULTS.items():
        assert "default_model" in defaults, f"{provider} missing 'default_model'"
        assert "default_tokens" in defaults, f"{provider} missing 'default_tokens'"
        assert isinstance(defaults["default_model"], str)
        assert isinstance(defaults["default_tokens"], int)
        assert defaults["default_tokens"] > 0


def test_today_is_valid_date():
    """Verify TODAY is a valid date string in YYYY-MM-DD format."""
    import re
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", TODAY), \
        f"TODAY format invalid: {TODAY}, expected YYYY-MM-DD"
