"""Per-provider configuration for LLM models and token limits.

This module is the single source of truth for:
  * ``PROVIDER_DEFAULTS`` — the default model / token budget for each provider.
  * ``FALLBACK_CHAIN``    — the ordered provider pool the report generators try,
    stopping at the first success. Reorder or extend this list to change
    fallback behaviour (e.g. add a third level, or slot a new provider in the
    middle); nothing else needs to change.
"""

PROVIDER_DEFAULTS = {
    "claude": {
        "default_model": "claude-sonnet-4-6",
        "default_tokens": 8000,
    },
    "openai": {
        "default_model": "gpt-4o",
        "default_tokens": 16000,
    },
    "gemini": {
        "default_model": "gemini-3.6-flash",
        "default_tokens": 32000,
    },
}

# Ordered provider fallback chain for automated report generation.
# The generator tries these in order and keeps the first successful result, so
# a transient outage or quota cap on one provider (e.g. Gemini 429) falls
# through to the next. Add levels by appending provider names here.
FALLBACK_CHAIN = ["gemini", "openai"]


def resolve_chain(primary_provider=None, primary_model=None):
    """Resolve the ordered list of ``(provider, model)`` attempts to try.

    ``primary_provider`` (optional) leads the chain — an explicit ``--provider``
    override; when omitted the chain starts at ``FALLBACK_CHAIN[0]``.
    ``primary_model`` (optional) overrides the model of that first attempt only;
    every other provider uses its ``PROVIDER_DEFAULTS`` model.

    A model without a provider is rejected: applying it to the default lead
    provider would silently pair, say, ``gpt-4o`` with Gemini. Pass both.

    Fallback levels always come from ``FALLBACK_CHAIN``, so extending the pool is
    a one-line edit there.
    """
    if primary_model and not primary_provider:
        raise ValueError(
            "a model override requires an explicit provider "
            "(which provider is this model for?)"
        )

    order = ([primary_provider] if primary_provider else []) + [
        p for p in FALLBACK_CHAIN if p != primary_provider
    ]

    attempts, seen = [], set()
    for provider in order:
        if provider in seen or provider not in PROVIDER_DEFAULTS:
            continue
        seen.add(provider)
        if provider == primary_provider and primary_model:
            model = primary_model
        else:
            model = PROVIDER_DEFAULTS[provider]["default_model"]
        attempts.append((provider, model))
    return attempts
