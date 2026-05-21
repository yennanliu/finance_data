"""Per-provider configuration for LLM models and token limits."""

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
        "default_model": "gemini-2.5-pro",
        "default_tokens": 16000,
    },
}
