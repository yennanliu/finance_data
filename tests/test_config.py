"""Tests for analysis package configuration."""

import pytest
from scripts.analysis.config import ANALYSIS_TYPES, TODAY
from scripts.analysis.config.providers import (
    PROVIDER_DEFAULTS, FALLBACK_CHAIN, resolve_chain, resolve_model,
)


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


def test_openai_default_model_is_gpt_4o():
    """OpenAI's default/fallback model is gpt-4o."""
    assert PROVIDER_DEFAULTS["openai"]["default_model"] == "gpt-4o"


def test_fallback_chain_tries_gemini_then_openai():
    """The configured chain leads with gemini and falls back to openai."""
    assert FALLBACK_CHAIN[:2] == ["gemini", "openai"]


def test_resolve_chain_default_order():
    """With no override, attempts follow FALLBACK_CHAIN with each provider's model."""
    attempts = resolve_chain()
    assert attempts[0] == ("gemini", PROVIDER_DEFAULTS["gemini"]["default_model"])
    assert attempts[1] == ("openai", "gpt-4o")


def test_resolve_chain_primary_leads_then_falls_back():
    """An explicit primary provider leads; the rest of the chain follows, deduped."""
    attempts = resolve_chain("openai")
    assert attempts[0] == ("openai", "gpt-4o")
    providers = [p for p, _ in attempts]
    assert providers == list(dict.fromkeys(providers))   # no duplicate providers
    assert "gemini" in providers                          # fallback still present


def test_resolve_chain_honors_explicit_primary_model():
    """A primary model overrides only the first attempt's model."""
    attempts = resolve_chain("gemini", "gemini-2.5-pro")
    assert attempts[0] == ("gemini", "gemini-2.5-pro")


def test_resolve_chain_rejects_model_without_provider():
    """A model override without a provider is ambiguous and rejected, rather
    than silently paired with the default lead provider."""
    with pytest.raises(ValueError):
        resolve_chain(None, "gpt-4o")


def test_every_provider_declares_model_prefixes_its_default_matches():
    """The prefixes are what resolve_model uses to tell a provider's models
    apart, so a provider whose own default fails them would repair correct
    input into a loop."""
    for provider, defaults in PROVIDER_DEFAULTS.items():
        prefixes = defaults["model_prefixes"]
        assert isinstance(prefixes, tuple) and prefixes, \
            f"{provider}: model_prefixes must be a non-empty tuple"
        assert defaults["default_model"].startswith(prefixes), \
            f"{provider}: default_model does not match its own model_prefixes"


def test_resolve_model_keeps_a_model_belonging_to_the_provider():
    """A model the provider can serve is passed through untouched."""
    assert resolve_model("gemini", "gemini-2.5-pro") == "gemini-2.5-pro"
    assert resolve_model("openai", "gpt-5.6-sol") == "gpt-5.6-sol"
    assert resolve_model("claude", "claude-opus-4-6") == "claude-opus-4-6"


def test_resolve_model_keeps_openai_ids_outside_the_gpt_prefix():
    """OpenAI's reasoning families are not named gpt-*. Matching on "gpt-"
    alone made `--provider openai --model o3` resolve to gpt-4o — a model
    nobody asked for, silently stamped on the report's front matter."""
    for model in ("o3", "o3-mini", "o1", "o1-preview", "o4-mini"):
        assert resolve_model("openai", model) == model


def test_resolve_model_replaces_a_model_from_the_wrong_provider():
    """A stale dropdown selection (gpt-4o picked alongside provider: gemini)
    must not reach an SDK that cannot serve it."""
    assert resolve_model("gemini", "o3") == PROVIDER_DEFAULTS["gemini"]["default_model"]
    assert resolve_model("gemini", "gpt-4o") == PROVIDER_DEFAULTS["gemini"]["default_model"]
    assert resolve_model("openai", "gemini-3.8-flash") == "gpt-4o"
    assert resolve_model("claude", "gpt-4o") == PROVIDER_DEFAULTS["claude"]["default_model"]


def test_resolve_model_falls_back_when_no_model_given():
    """No model (or an empty one) means the provider's configured default."""
    for provider, defaults in PROVIDER_DEFAULTS.items():
        assert resolve_model(provider) == defaults["default_model"]
        assert resolve_model(provider, None) == defaults["default_model"]
        assert resolve_model(provider, "") == defaults["default_model"]


def test_resolve_chain_repairs_a_mismatched_primary_pair():
    """The repair the report workflows used to do in a bash `case` block now
    happens once, here, for every entry point."""
    attempts = resolve_chain("gemini", "gpt-4o")
    assert attempts[0] == ("gemini", PROVIDER_DEFAULTS["gemini"]["default_model"])


def test_resolve_chain_never_pairs_a_provider_with_a_foreign_model():
    """Whatever the override, every attempt in the chain must be servable."""
    for provider in PROVIDER_DEFAULTS:
        for model in ("gpt-4o", "o3", "gemini-3.8-flash", "claude-sonnet-4-6", None):
            for attempt_provider, attempt_model in resolve_chain(provider, model):
                prefixes = PROVIDER_DEFAULTS[attempt_provider]["model_prefixes"]
                assert attempt_model.startswith(prefixes), \
                    f"resolve_chain({provider!r}, {model!r}) produced " \
                    f"({attempt_provider}, {attempt_model})"


def test_today_is_valid_date():
    """Verify TODAY is a valid date string in YYYY-MM-DD format."""
    import re
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", TODAY), \
        f"TODAY format invalid: {TODAY}, expected YYYY-MM-DD"
