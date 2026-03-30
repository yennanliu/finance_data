#!/usr/bin/env python3
"""
generate_analysis_openai.py
===========================
OpenAI-specific wrapper for generate_analysis.py.
Generates investment analysis reports using OpenAI API.

Usage
-----
  python scripts/generate_analysis_openai.py                          # AAPL fundamental
  python scripts/generate_analysis_openai.py TSLA --analysis-type technical-analysis
  python scripts/generate_analysis_openai.py SPY  --analysis-type sector-analysis
  python scripts/generate_analysis_openai.py AAPL --model gpt-4-turbo

Requirements
------------
  pip install openai yfinance

Environment
-----------
  OPENAI_API_KEY   (required)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add script directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Import shared functionality from the main script
from generate_analysis import (
    ANALYSIS_TYPES,
    TODAY,
    fetch_data,
    build_context,
    call_openai,
    save_report,
)

DEFAULT_MODEL = "gpt-4o"
DEFAULT_TOKENS = 20000  # Increased to allow more comprehensive analysis


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate a Traditional-Chinese investment analysis report via OpenAI API."
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
        help="Directory to save the report (default: ai_gen_report/stock/<ticker>/)",
    )
    p.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"OpenAI model ID (default: {DEFAULT_MODEL})",
    )
    p.add_argument(
        "--max-tokens", type=int, default=DEFAULT_TOKENS,
        help=f"Max output tokens (default: {DEFAULT_TOKENS})",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    ticker = args.ticker.upper()
    analysis_type = args.analysis_type
    output_dir = args.output_dir or (Path("ai_gen_report/stock") / ticker.lower())

    label = ANALYSIS_TYPES[analysis_type]["label"]
    banner = f"  {ticker}  |  {label}  |  OpenAI  |  model: {args.model}  |  out: {output_dir}"
    sep = "=" * max(70, len(banner) + 4)
    print(f"\n{sep}\n{banner}\n{sep}\n")

    print("[1/3] Fetching financial data from Yahoo Finance …")
    data = fetch_data(ticker)
    context = build_context(data, analysis_type)

    print("[2/3] Calling OpenAI API …")
    report = call_openai(ticker, context, analysis_type, args.model, args.max_tokens)

    print("[3/3] Saving report …")
    save_report(ticker, report, output_dir, analysis_type, provider="openai")

    print(f"\n{sep}\n  Done!\n{sep}\n")


if __name__ == "__main__":
    main()
