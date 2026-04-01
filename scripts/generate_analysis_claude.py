#!/usr/bin/env python3
"""
generate_analysis_claude.py
===========================
Claude-specific wrapper for generate_analysis.py.
Generates investment analysis reports using Claude API.

Usage
-----
  python scripts/generate_analysis_claude.py                          # AAPL fundamental
  python scripts/generate_analysis_claude.py TSLA --analysis-type technical-analysis
  python scripts/generate_analysis_claude.py SPY  --analysis-type sector-analysis
  python scripts/generate_analysis_claude.py AAPL --model claude-opus-4-6

Requirements
------------
  pip install anthropic yfinance

Environment
-----------
  ANTHROPIC_API_KEY   (required)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add script directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from analysis import (
    ANALYSIS_TYPES,
    DEFAULT_MODEL,
    DEFAULT_TOKENS,
    TODAY,
    fetch_data,
    build_context,
    call_claude,
)


def save_report(ticker: str, content: str, output_dir: Path,
                analysis_type: str, provider: str = "claude") -> Path:
    """Save report with YAML frontmatter and same-day deduplication."""
    output_dir.mkdir(parents=True, exist_ok=True)
    meta = ANALYSIS_TYPES[analysis_type]
    prefix = meta["filename_prefix"]
    label = meta["label"]
    ext = meta.get("ext", ".md")

    base = f"{prefix}_{TODAY}_claude"

    # Same-day deduplication
    path = output_dir / f"{base}{ext}"
    counter = 2
    while path.exists():
        path = output_dir / f"{base}-{counter}{ext}"
        counter += 1

    if ext == ".html":
        path.write_text(content, encoding="utf-8")
    else:
        frontmatter = (
            "---\n"
            f'title: "{ticker} {label} {TODAY}"\n'
            f"date: {TODAY}\n"
            f"ticker: {ticker}\n"
            f"analysis_type: {analysis_type}\n"
            f"provider: {provider}\n"
            "language: zh-TW\n"
            "generated_by: Claude AI (scripts/generate_analysis.py)\n"
            "---\n\n"
        )
        path.write_text(frontmatter + content, encoding="utf-8")

    print(f"  ✅ saved → {path}")
    return path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate a Traditional-Chinese investment analysis report via Claude API."
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
        help=f"Claude model ID (default: {DEFAULT_MODEL})",
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
    banner = f"  {ticker}  |  {label}  |  Claude  |  model: {args.model}  |  out: {output_dir}"
    sep = "=" * max(70, len(banner) + 4)
    print(f"\n{sep}\n{banner}\n{sep}\n")

    print("[1/3] Fetching financial data from Yahoo Finance …")
    data = fetch_data(ticker)
    context = build_context(data, analysis_type)

    print("[2/3] Calling Claude API …")
    report = call_claude(ticker, context, analysis_type, args.model, args.max_tokens)

    print("[3/3] Saving report …")
    save_report(ticker, report, output_dir, analysis_type, provider="claude")

    print(f"\n{sep}\n  Done!\n{sep}\n")


if __name__ == "__main__":
    main()
