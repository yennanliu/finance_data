#!/usr/bin/env python3
"""Verify an API key is present for every provider the generator might use.

A report run is allowed to fall through ``FALLBACK_CHAIN`` (gemini → openai),
so checking only the *primary* provider's key lets a run start that is doomed
the moment the primary 429s. This resolves the same chain the generator will
resolve and fails fast — before the expensive install/fetch steps — if any
level in it is missing its key.

Used by the report-generating workflows in ``.github/workflows/``; it replaces
an inline heredoc that was copy-pasted into three of them. Emits
``::error::`` annotations so a missing secret surfaces on the run summary
rather than only in the log.

Usage:
    python scripts/check_provider_keys.py                    # chain default
    python scripts/check_provider_keys.py --provider gemini --model gemini-3.8-flash

``--provider`` / ``--model`` default to the ``PROVIDER`` / ``MODEL``
environment variables, which is how the workflows pass them.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from analysis.config.providers import resolve_chain  # noqa: E402

# provider → (env var the SDK reads, GitHub secret name that populates it).
# The two differ for OpenAI: the repo's secret is named OPEN_KEY_API, so an
# error message naming OPENAI_API_KEY would send someone looking for a secret
# that does not exist.
PROVIDER_KEYS = {
    "openai": ("OPENAI_API_KEY", "OPEN_KEY_API"),
    "gemini": ("GEMINI_API_KEY", "GEMINI_API_KEY"),
    "claude": ("ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        default=os.environ.get("PROVIDER") or None,
        help="Primary provider leading the chain (default: $PROVIDER)",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("MODEL") or None,
        help="Model for the primary provider (default: $MODEL)",
    )
    args = parser.parse_args()

    missing = []
    for provider, model in resolve_chain(args.provider, args.model):
        env_var, secret = PROVIDER_KEYS[provider]
        if os.environ.get(env_var):
            print(f"OK {provider} ({model}): {secret} is set")
        else:
            print(
                f"::error::{secret} secret is not set "
                f"(required for '{provider}' in the fallback chain)"
            )
            missing.append(secret)

    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
