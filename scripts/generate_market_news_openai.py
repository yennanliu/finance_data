#!/usr/bin/env python3
"""
generate_market_news_openai.py
==============================
OpenAI-specific wrapper for generate_market_news.py.
Fetches recent news for a stock ticker and generates a Traditional Chinese
Markdown report using OpenAI API.

Usage
-----
  python scripts/generate_market_news_openai.py AAPL
  python scripts/generate_market_news_openai.py TSLA --max-tokens 8000 --model gpt-4-turbo

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
from datetime import date
from pathlib import Path

# Add script directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Import shared functionality from the main script
from generate_market_news import (
    fetch_news,
    fetch_ticker_info,
    format_news_block,
    build_prompt,
    call_openai,
)

DEFAULT_MODEL = "gpt-4o"
DEFAULT_TOKENS = 12000  # Increased to allow more comprehensive market news analysis


def generate_report(
    ticker: str,
    model: str,
    max_tokens: int,
    output_dir: Path,
) -> None:
    print(f"[1/4] Fetching ticker info for {ticker}…")
    info = fetch_ticker_info(ticker)

    print(f"[2/4] Fetching recent news for {ticker}…")
    news_items = fetch_news(ticker)
    print(f"      Found {len(news_items)} news items.")

    if not news_items:
        print("[WARN] No news returned by yfinance. Report will note data unavailability.")

    news_block = format_news_block(news_items) if news_items else "（目前無可用新聞資料）"
    prompt = build_prompt(ticker, info, news_block)

    print(f"[3/4] Calling OpenAI ({model}, max_tokens={max_tokens})…")
    report_body = call_openai(prompt, model, max_tokens)

    # YAML front-matter
    today = date.today().isoformat()
    front_matter = (
        "---\n"
        f"ticker: {ticker}\n"
        f"date: {today}\n"
        "type: market-news\n"
        "provider: openai\n"
        f"model: {model}\n"
        "---\n\n"
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "README.md"
    output_file.write_text(front_matter + report_body, encoding="utf-8")

    print(f"[4/4] Report saved → {output_file}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a market-news report for a stock ticker using OpenAI (Traditional Chinese Markdown)."
    )
    parser.add_argument("ticker", help="Stock ticker symbol, e.g. AAPL, TSLA, NVDA")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: claude_code/market_news/<ticker_lower>/<date>)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenAI model ID (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_TOKENS,
        help=f"Max output tokens (default: {DEFAULT_TOKENS})",
    )

    args = parser.parse_args()
    ticker = args.ticker.upper()
    today = date.today().isoformat()
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path(f"claude_code/market_news/{ticker.lower()}/{today}")
    )

    generate_report(ticker, args.model, args.max_tokens, output_dir)


if __name__ == "__main__":
    main()
