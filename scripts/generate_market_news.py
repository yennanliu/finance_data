#!/usr/bin/env python3
"""
generate_market_news.py — Fetch recent news for a stock ticker and generate
a Traditional Chinese Markdown report using the Claude AI API.

Usage:
  python scripts/generate_market_news.py AAPL
  python scripts/generate_market_news.py TSLA --max-tokens 8000 --model claude-opus-4-6
"""

import argparse
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import anthropic
import yfinance as yf

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_TOKENS = 8000


# ── Helpers ────────────────────────────────────────────────────────────────────

def fetch_news(ticker: str) -> list[dict]:
    """Return up to 30 recent news items from yfinance."""
    t = yf.Ticker(ticker)
    return t.news or []


def fetch_ticker_info(ticker: str) -> dict:
    """Return basic info dict (price, sector, name…) from yfinance."""
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        return {
            "name": info.get("longName") or info.get("shortName", ticker),
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice", "N/A"),
            "currency": info.get("currency", "USD"),
            "market_cap": info.get("marketCap", "N/A"),
        }
    except Exception as exc:
        print(f"[WARN] Could not fetch ticker info: {exc}", file=sys.stderr)
        return {"name": ticker}


def format_news_block(news_items: list[dict]) -> str:
    """Convert yfinance news list to a readable text block for the prompt."""
    lines = []
    for i, item in enumerate(news_items[:25], 1):
        title = item.get("title", "（無標題）")
        publisher = item.get("publisher", "N/A")
        pub_ts = item.get("providerPublishTime", 0)
        if pub_ts:
            pub_dt = datetime.fromtimestamp(pub_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        else:
            pub_dt = "N/A"
        link = item.get("link", "")
        summary = item.get("summary", "")

        lines.append(f"\n### {i}. {title}")
        lines.append(f"- 發布時間：{pub_dt}")
        lines.append(f"- 來源：{publisher}")
        if link:
            lines.append(f"- 連結：{link}")
        if summary:
            lines.append(f"- 摘要：{summary}")
    return "\n".join(lines)


def build_prompt(ticker: str, info: dict, news_block: str) -> str:
    today = date.today().isoformat()
    name = info.get("name", ticker)
    sector = info.get("sector", "N/A")
    price = info.get("current_price", "N/A")
    currency = info.get("currency", "USD")

    return f"""你是一位專業的財經分析師，請根據以下 {ticker}（{name}）的最新新聞，
用**繁體中文**撰寫一份詳盡的市場新聞分析報告。

## 股票基本資訊
- 代碼：{ticker}
- 名稱：{name}
- 產業：{sector}
- 最新股價：{price} {currency}
- 報告日期：{today}

## 最新新聞資料
{news_block}

---

請依照以下格式完整輸出報告（使用 Markdown）：

# {ticker} 市場新聞分析報告

## 📅 報告日期
{today}

## 🏢 公司概覽
[一段簡短的公司/產業背景介紹]

## 📰 近期新聞總覽
[條列式列出所有新聞標題及發布時間，格式：- YYYY-MM-DD | 標題]

## 🔍 重點新聞深度分析
[選出 3–5 則最重要的新聞，逐一深入分析對公司營運、股價或產業的潛在影響]

## 📊 市場情緒評估
[整體市場情緒：🟢 正面 / 🟡 中性 / 🔴 負面]
[說明評估依據，包含正面因素與負面因素]

## ⚠️ 主要風險因素
[從新聞中識別出的短期或長期風險，條列說明]

## 💡 短期關注重點
[根據新聞，未來 1–4 週投資人應關注的事項或催化劑]

## 📌 新聞來源索引
[依序列出所有新聞：序號. 標題 — 來源 (日期)]

---
*本報告由 AI 自動生成，僅供參考，不構成任何投資建議。*
"""


# ── Main ───────────────────────────────────────────────────────────────────────

def generate_report(
    ticker: str,
    model: str,
    max_tokens: int,
    output_dir: Path,
) -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    print(f"[1/4] Fetching ticker info for {ticker}…")
    info = fetch_ticker_info(ticker)

    print(f"[2/4] Fetching recent news for {ticker}…")
    news_items = fetch_news(ticker)
    print(f"      Found {len(news_items)} news items.")

    if not news_items:
        print("[WARN] No news returned by yfinance. Report will note data unavailability.")

    news_block = format_news_block(news_items) if news_items else "（目前無可用新聞資料）"
    prompt = build_prompt(ticker, info, news_block)

    print(f"[3/4] Calling Claude ({model}, max_tokens={max_tokens})…")
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    report_body = message.content[0].text

    # YAML front-matter
    today = date.today().isoformat()
    front_matter = (
        "---\n"
        f"ticker: {ticker}\n"
        f"date: {today}\n"
        "type: market-news\n"
        f"model: {model}\n"
        "---\n\n"
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "README.md"
    output_file.write_text(front_matter + report_body, encoding="utf-8")

    print(f"[4/4] Report saved → {output_file}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a market-news report for a stock ticker (Traditional Chinese Markdown)."
    )
    parser.add_argument("ticker", help="Stock ticker symbol, e.g. AAPL, TSLA, NVDA")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: claude_code/market_news/<ticker_lower>)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Claude model ID (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_TOKENS,
        help=f"Max output tokens (default: {DEFAULT_TOKENS})",
    )

    args = parser.parse_args()
    ticker = args.ticker.upper()
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path(f"claude_code/market_news/{ticker.lower()}")
    )

    generate_report(ticker, args.model, args.max_tokens, output_dir)


if __name__ == "__main__":
    main()
