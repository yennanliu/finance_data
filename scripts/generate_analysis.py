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

# Add script directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from analysis import (
    ANALYSIS_TYPES,
    DEFAULT_MODEL,
    DEFAULT_TOKENS,
    TODAY,
    fetch_data,
    build_context,
    call_llm,
)
from analysis.utils.data_fetch import generate_plotly_candlestick_chart


def save_report(ticker: str, content: str, output_dir: Path,
                analysis_type: str, provider: str = "claude") -> Path:
    """Save report with YAML frontmatter and same-day deduplication."""
    output_dir.mkdir(parents=True, exist_ok=True)
    meta = ANALYSIS_TYPES[analysis_type]
    prefix = meta["filename_prefix"]
    label = meta["label"]
    ext = meta.get("ext", ".md")

    # Map provider to simple suffix
    model_suffix = "openai" if provider == "openai" else "claude"
    base = f"{prefix}_{TODAY}_{model_suffix}"

    # Same-day deduplication: base.ext → base-2.ext → base-3.ext …
    path = output_dir / f"{base}{ext}"
    counter = 2
    while path.exists():
        path = output_dir / f"{base}-{counter}{ext}"
        counter += 1

    if ext == ".html":
        # HTML output: write as-is
        path.write_text(content, encoding="utf-8")
    else:
        # Markdown: prepend YAML frontmatter
        generated_by = "OpenAI API" if provider == "openai" else "Claude AI"
        frontmatter = (
            "---\n"
            f'title: "{ticker} {label} {TODAY}"\n'
            f"date: {TODAY}\n"
            f"ticker: {ticker}\n"
            f"analysis_type: {analysis_type}\n"
            f"provider: {provider}\n"
            "language: zh-TW\n"
            f"generated_by: {generated_by} (scripts/generate_analysis.py)\n"
            "---\n\n"
        )
        path.write_text(frontmatter + content, encoding="utf-8")

    print(f"  ✅ saved → {path}")
    return path


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
        help="Directory to save the report (default: ai_gen_report/stock/<ticker>/)",
    )
    p.add_argument(
        "--provider", default="claude",
        choices=["claude", "openai"],
        help="AI provider (default: claude)",
    )
    p.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Model ID (default: {DEFAULT_MODEL})",
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
    provider = args.provider
    output_dir = args.output_dir or (Path("ai_gen_report/stock") / ticker.lower())

    label = ANALYSIS_TYPES[analysis_type]["label"]
    banner = f"  {ticker}  |  {label}  |  provider: {provider}  |  model: {args.model}  |  out: {output_dir}"
    sep = "=" * max(70, len(banner) + 4)
    print(f"\n{sep}\n{banner}\n{sep}\n")

    print("[1/3] Fetching financial data from Yahoo Finance …")
    data = fetch_data(ticker)
    context = build_context(data, analysis_type)

    # Generate interactive candlestick chart for technical analysis (before LLM call for efficiency)
    chart_embed = ""
    if analysis_type == "technical-analysis" and data.get("hist") is not None:
        print("  Generating interactive candlestick chart with MA30/60/200 …")
        chart_html = generate_plotly_candlestick_chart(data["hist"], ticker)
        if chart_html:
            chart_embed = chart_html + "\n\n"

    print(f"[2/3] Calling {provider.upper()} API …")
    report = call_llm(ticker, context, analysis_type, provider, args.model, args.max_tokens)

    print("[3/3] Saving report …")
    final_report = chart_embed + report
    save_report(ticker, final_report, output_dir, analysis_type, provider=provider)

    print(f"\n{sep}\n  Done!\n{sep}\n")


if __name__ == "__main__":
    main()
