"""Per-provider configuration for LLM models and token limits.

This module is the single source of truth for:
  * ``PROVIDER_DEFAULTS`` — the default model / token budget / model-id prefix
    for each provider.
  * ``FALLBACK_CHAIN``    — the ordered provider pool the report generators try,
    stopping at the first success. Reorder or extend this list to change
    fallback behaviour (e.g. add a third level, or slot a new provider in the
    middle); nothing else needs to change.
"""

# ``default_tokens`` documents each provider's per-report output budget. Only
# ``default_model`` is read by code (see ``resolve_chain``); the budget actually
# handed to the API comes from ``--max-tokens`` (default ``config.DEFAULT_TOKENS``
# = 32000), which CI passes explicitly. So keep these numbers truthful
# about what the paired model can really emit rather than aspirational:
#
#   * A full fundamental report (7000-10000 字, 11 chapters, Ch.8 DCF arithmetic)
#     needs roughly 32k output tokens to finish in one shot.
#   * ``run_openai`` clamps to the model's own ceiling (``OPENAI_MAX_TOKENS``), so
#     the gpt-4o default tops out at 16,384 and will truncate a full-length
#     report's tail chapters. Switch the OpenAI default to a gpt-5.6-* model (32k
#     capable) if the OpenAI fallback needs to produce complete reports.
#   * ``run_gemini`` clamps to 65,536 and auto-retries at that ceiling when it
#     detects truncation, so the primary path self-heals.
PROVIDER_DEFAULTS = {
    "claude": {
        "default_model": "claude-sonnet-4-6",
        "default_tokens": 32000,
        "model_prefix": "claude-",
    },
    "openai": {
        # 16000, not 32000: gpt-4o cannot exceed 16,384 output tokens.
        "default_model": "gpt-4o",
        "default_tokens": 16000,
        "model_prefix": "gpt-",
    },
    "gemini": {
        "default_model": "gemini-3.8-flash",
        "default_tokens": 32000,
        "model_prefix": "gemini-",
    },
}

# Ordered provider fallback chain for automated report generation.
# The generator tries these in order and keeps the first successful result, so
# a transient outage or quota cap on one provider (e.g. Gemini 429) falls
# through to the next. Add levels by appending provider names here.
FALLBACK_CHAIN = ["gemini", "openai"]


def resolve_model(provider, model=None):
    """Return the model id to use for ``provider``.

    ``model`` wins when it actually belongs to ``provider`` (matched on the
    provider's ``model_prefix``); a mismatched or empty id falls back to that
    provider's ``default_model``. This is what keeps a stale dropdown selection
    — say ``gpt-4o`` picked alongside ``provider: gemini`` — from being handed
    to an SDK that cannot serve it.

    Lives here rather than in each caller because ``PROVIDER_DEFAULTS`` is the
    only place that knows which ids belong to which provider.
    """
    config = PROVIDER_DEFAULTS[provider]
    if model and model.startswith(config["model_prefix"]):
        return model
    return config["default_model"]


def resolve_chain(primary_provider=None, primary_model=None):
    """Resolve the ordered list of ``(provider, model)`` attempts to try.

    ``primary_provider`` (optional) leads the chain — an explicit ``--provider``
    override; when omitted the chain starts at ``FALLBACK_CHAIN[0]``.
    ``primary_model`` (optional) overrides the model of that first attempt only,
    and only when it belongs to that provider (see ``resolve_model``); every
    other provider uses its ``PROVIDER_DEFAULTS`` model.

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
        model = resolve_model(
            provider, primary_model if provider == primary_provider else None
        )
        attempts.append((provider, model))
    return attempts
