#!/usr/bin/env python3
"""
generate_analysis.py
====================
Fetches live financial data from yfinance, then calls the Claude or OpenAI API
to produce an investment analysis report in Traditional Chinese (Markdown).

Supported analysis types
-------------------------
  fundamental-analysis      Deep fundamental analysis using financial statements
  technical-analysis        Technical chart and indicator analysis
  stock-eval                Comprehensive stock evaluation (fundamental + valuation)
  economics-analysis        US economic indicators and macro environment
  portfolio-review          Portfolio performance and optimization review
  sector-analysis           US market sector rotation and analysis
  financial-report-analyst  8-phase SEC filing analysis with accounting quality score
  stock-valuation           Multi-method valuation (DCF/CCA/EV/EBITDA/P/E) + football field

Usage
-----
  python scripts/generate_analysis.py                          # AAPL fundamental (Claude)
  python scripts/generate_analysis.py TSLA --analysis-type technical-analysis
  python scripts/generate_analysis.py SPY  --analysis-type sector-analysis
  python scripts/generate_analysis.py      --analysis-type economics-analysis
  python scripts/generate_analysis.py AAPL --model claude-opus-4-6 --max-tokens 10000
  python scripts/generate_analysis.py AAPL --provider openai --model gpt-4o

Same-day runs: if fundamental_analysis_2026-02-22.md already exists,
the next run creates fundamental_analysis_2026-02-22-2.md, then -3, etc.

Requirements
------------
  pip install anthropic openai yfinance

Environment
-----------
  ANTHROPIC_API_KEY   (required for Claude provider - default)
  OPENAI_API_KEY      (required for OpenAI provider)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from analysis import ANALYSIS_TYPES, DEFAULT_MODEL, DEFAULT_TOKENS, TODAY
from analysis.config.providers import PROVIDER_DEFAULTS
from analysis.pipeline import run_analysis, save_analysis_report


def save_report(ticker: str, content: str, output_dir: Path,
                analysis_type: str, provider: str = "claude",
                model: str = "") -> Path:
    """Save report with YAML frontmatter and same-day deduplication.

    Thin wrapper over :func:`analysis.pipeline.save_analysis_report`.
    """
    return save_analysis_report(ticker, content, output_dir, analysis_type,
                                provider=provider, model=model)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate a Traditional-Chinese investment analysis report via Claude or OpenAI API."
    )
    p.add_argument(
        "ticker", nargs="?", default="AAPL",
        help="Stock ticker symbol (default: AAPL)",
    )
    p.add_argument(
        "--analysis-type", default="fundamental-analysis",
        choices=list(ANALYSIS_TYPES.keys()),
        help="Type of analysis to run (default: fundamental-analysis)",
    )
    p.add_argument(
        "--output-dir", type=Path, default=None,
        help="Directory to save the report (default: ai_gen_report/<fundamental|technical|stock>/<ticker>/)",
    )
    p.add_argument(
        "--provider", default="openai",
        choices=["claude", "openai", "gemini"],
        help="AI provider (default: openai)",
    )
    p.add_argument(
        "--model", default=None,
        help="Model ID (default: the selected provider's default model)",
    )
    p.add_argument(
        "--max-tokens", type=int, default=DEFAULT_TOKENS,
        help=f"Max output tokens (default: {DEFAULT_TOKENS})",
    )
    args = p.parse_args()
    # Resolve the model from the selected provider's default when not given
    # explicitly, so `--provider claude/gemini` doesn't inherit an OpenAI model.
    if args.model is None:
        args.model = PROVIDER_DEFAULTS.get(args.provider, {}).get("default_model", DEFAULT_MODEL)
    return args


def main() -> None:
    args = parse_args()
    ticker = args.ticker.upper()
    analysis_type = args.analysis_type
    provider = args.provider
    if args.output_dir:
        output_dir = args.output_dir
    elif analysis_type == "fundamental-analysis":
        output_dir = Path("ai_gen_report/fundamental") / ticker.lower()
    elif analysis_type == "technical-analysis":
        output_dir = Path("ai_gen_report/technical") / ticker.lower()
    else:
        output_dir = Path("ai_gen_report/stock") / ticker.lower()

    label = ANALYSIS_TYPES[analysis_type]["label"]
    banner = f"  {ticker}  |  {label}  |  provider: {provider}  |  model: {args.model}  |  out: {output_dir}"
    sep = "=" * max(70, len(banner) + 4)
    print(f"\n{sep}\n{banner}\n{sep}\n")

    run_analysis(ticker, analysis_type, provider, args.model, args.max_tokens, output_dir)

    print(f"\n{sep}\n  Done!\n{sep}\n")


if __name__ == "__main__":
    main()
