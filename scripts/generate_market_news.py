#!/usr/bin/env python3
"""
generate_market_news.py — Fetch recent news for a stock ticker and generate
a Traditional Chinese Markdown report using Claude or OpenAI API.

Usage:
  python scripts/generate_market_news.py AAPL
  python scripts/generate_market_news.py TSLA --max-tokens 8000 --model claude-opus-4-6
  python scripts/generate_market_news.py AAPL --provider openai --model gpt-4o
"""

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.request import Request, urlopen

import yfinance as yf

DEFAULT_PROVIDER = "claude"
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_TOKENS = 12000  # Increased to allow more comprehensive market news analysis (OpenAI gpt-4o max: 12000)


# ── Helpers ────────────────────────────────────────────────────────────────────

# All feeds search by keyword: {query} is replaced with the ticker symbol
RSS_FEEDS = [
    ("Google News",  "https://news.google.com/rss/search?q={query}+stock&hl=en-US&gl=US&ceid=US:en"),
    ("Bing News",    "https://www.bing.com/news/search?q={query}+stock&format=rss"),
    ("Yahoo News",   "https://news.google.com/rss/search?q={query}+stock+site:finance.yahoo.com&hl=en-US&gl=US&ceid=US:en"),
    ("Seeking Alpha","https://news.google.com/rss/search?q={query}+site:seekingalpha.com&hl=en-US&gl=US&ceid=US:en"),
]

RSS_PER_FEED_LIMIT = 5  # top N headlines per feed

_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"


def _fetch_rss(url: str, source_name: str, ticker: str, limit: int = RSS_PER_FEED_LIMIT) -> list[dict]:
    """Parse an RSS/Atom feed and return top *limit* headlines."""
    final_url = url.format(query=ticker)

    try:
        req = Request(final_url, headers={"User-Agent": _USER_AGENT})
        with urlopen(req, timeout=10) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
    except Exception as exc:
        print(f"  [WARN] RSS fetch failed for {source_name}: {exc}", file=sys.stderr)
        return []

    items: list[dict] = []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall(".//item") or root.findall(".//atom:entry", ns)

    for entry in entries:
        title = (entry.findtext("title") or entry.findtext("atom:title", namespaces=ns) or "").strip()
        if not title:
            continue
        link = (entry.findtext("link") or "").strip()
        if not link:
            link_el = entry.find("atom:link", ns)
            link = (link_el.get("href", "") if link_el is not None else "").strip()
        pub_str = (entry.findtext("pubDate") or entry.findtext("atom:updated", namespaces=ns) or "").strip()
        summary = (entry.findtext("description") or entry.findtext("atom:summary", namespaces=ns) or "").strip()
        summary = re.sub(r"<[^>]+>", "", summary).strip()

        pub_ts = 0
        if pub_str:
            try:
                pub_ts = int(parsedate_to_datetime(pub_str).timestamp())
            except Exception:
                pass

        items.append({
            "title": title,
            "publisher": source_name,
            "providerPublishTime": pub_ts,
            "link": link,
            "summary": summary[:300] if summary else "",
        })
        if len(items) >= limit:
            break

    return items


def fetch_news(ticker: str) -> list[dict]:
    """Collect news from yfinance + keyword-searched RSS feeds, deduplicate, and return."""
    source_counts: dict[str, int] = {}

    # 1. Yahoo Finance
    yf_items: list[dict] = []
    try:
        t = yf.Ticker(ticker)
        yf_items = t.news or []
        source_counts["yfinance"] = len(yf_items)
    except Exception as exc:
        print(f"  [WARN] yfinance news fetch failed: {exc}", file=sys.stderr)
        source_counts["yfinance"] = 0

    # 2. RSS feeds — keyword search per ticker, top 5 from each
    rss_items: list[dict] = []
    for name, url in RSS_FEEDS:
        batch = _fetch_rss(url, name, ticker)
        source_counts[name] = len(batch)
        rss_items.extend(batch)

    # Log per-source counts
    parts = [f"{src}: {n}" for src, n in source_counts.items()]
    print(f"      Sources → {', '.join(parts)}")

    # Combine & deduplicate by normalised title
    all_items = yf_items + rss_items
    seen_titles: set[str] = set()
    unique: list[dict] = []
    for item in all_items:
        key = re.sub(r"\W+", "", (item.get("title") or "").lower())[:60]
        if key and key in seen_titles:
            continue
        seen_titles.add(key)
        unique.append(item)

    unique.sort(key=lambda x: x.get("providerPublishTime", 0), reverse=True)
    return unique


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
    # Filter out items with empty/missing critical fields
    valid_items = [
        item for item in news_items
        if item.get("title") and item.get("title").strip()
    ]

    # If no valid items found, try using all items even if incomplete
    if not valid_items:
        valid_items = news_items

    for i, item in enumerate(valid_items[:25], 1):
        title = (item.get("title") or "").strip() or f"《未命名新聞 #{i}》"
        publisher = (item.get("publisher") or "").strip() or "未知來源"
        pub_ts = item.get("providerPublishTime", 0)
        if pub_ts:
            pub_dt = datetime.fromtimestamp(pub_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        else:
            pub_dt = "未知時間"
        link = (item.get("link") or "").strip()
        summary = (item.get("summary") or "").strip()

        lines.append(f"\n### {i}. {title}")
        lines.append(f"- 發布時間：{pub_dt}")
        lines.append(f"- 來源：{publisher}")
        if link:
            lines.append(f"- 連結：{link}")
        if summary:
            lines.append(f"- 摘要：{summary}")

    return "\n".join(lines) if lines else "（暫時無可用新聞資料）"


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

重要提示：
- 如新聞資料缺失或不完整，請基於公司背景、產業趨勢、歷史財報等信息進行深度分析
- 不要在最終報告中出現「無標題」、「N/A」、「未知來源」等佔位符，應改為實質性分析
- 每個新聞分析都應包含對公司營運、股價或市場的具體影響推演

請依照以下格式完整輸出報告（使用 Markdown）：

# {ticker} 市場新聞分析報告

## 📅 報告日期
{today}

## 🏢 公司概覽
[一段簡短的公司/產業背景介紹，包含關鍵業務和市場地位]

## 📰 近期新聞總覽
[條列式列出新聞標題及發布時間，格式：- YYYY-MM-DD | 標題]
[如新聞標題缺失，應根據發布日期和公司信息推演可能的新聞內容]

## 🔍 重點新聞深度分析
[選出 3–5 則最重要的新聞，逐一深入分析]
[對每則新聞進行具體分析，包括對公司營運、財務、股價的潛在影響]
[分析內容應包含短期和長期影響推演]

## 📊 市場情緒評估
[整體市場情緒：🟢 正面 / 🟡 中性 / 🔴 負面]
[詳細說明評估依據，包含正面因素與負面因素]

## ⚠️ 主要風險因素
[識別出的短期或長期風險，條列說明]

## 💡 短期關注重點
[根據新聞，未來 1–4 週投資人應關注的事項或催化劑]

## 📌 新聞來源索引
[依序列出所有新聞：序號. 標題 — 來源 (日期)]

---
*本報告由 AI 自動生成，僅供參考，不構成任何投資建議。*
"""


# ── Main ───────────────────────────────────────────────────────────────────────

def call_claude(prompt: str, model: str, max_tokens: int) -> str:
    """Call Claude API and return the response text."""
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def call_openai(prompt: str, model: str, max_tokens: int) -> str:
    """Call OpenAI API and return the response text."""
    import openai

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("ERROR: OPENAI_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    # OpenAI models have different max token limits - use optimized values for market news
    # gpt-4o & gpt-4o-mini: 128k context window, can support higher output limits
    openai_max_tokens = {
        "gpt-4o": 12000,         # Generous limit for detailed market news analysis
        "gpt-4o-mini": 10000,    # Good limit for comprehensive analysis
        "gpt-4-turbo": 4096,     # Hard limit for this older model
        "gpt-4": 8192,           # Standard limit for older model
    }
    model_max = openai_max_tokens.get(model, 12000)
    effective_max_tokens = min(max_tokens, model_max)
    if effective_max_tokens != max_tokens:
        print(f"  [INFO] Capping max_tokens from {max_tokens} to {effective_max_tokens} for {model}")

    # System message to improve output quality (matching Claude's detailed style)
    system_message = """你是一位頂級美股投資研究分析師，擁有 CFA 資格與 15 年以上財經新聞分析經驗。

你的分析必須遵循以下原則：
1. **深度分析**：每個章節必須提供詳盡、專業的分析，不得只有簡單的一兩句話
2. **具體數據**：引用具體的財務數據、股價、估值倍數等數字支撐論點
3. **專業格式**：使用完整的 Markdown 格式，包含表格、條列、emoji 視覺標記
4. **風險評估**：詳細分析風險因素，使用 🟢🟡🔴 標記風險等級
5. **產業洞察**：提供產業背景、競爭態勢、市場趨勢的深入分析
6. **投資建議**：給出明確的投資建議、目標價區間、關注重點
7. **報告長度**：報告應詳盡完整，至少 3000-5000 字以上，充分利用提供的 token 額度

**對不完整新聞資料的處理方式**：
- 如果新聞標題為「《未命名新聞》」或「未知來源」，代表該筆新聞不完整或無法從原始資料獲取詳細信息
- 在這種情況下，你應該基於該新聞發布時間和公司背景，推演可能的新聞內容與市場影響
- 不要照搬「無標題」或「N/A」等佔位符到報告中
- 對每則新聞進行實質性分析，而不只是列舉信息
- 對推演分析明確說明「基於...推演」，但分析內容必須有實質價值

**原始新聞資料不足的處理**：
- 如果提供的新聞資料不足或不完整，你仍應基於公司背景、產業知識、市場環境提供深度推演分析
- 結合公司最近的業務進展、財報數據、競爭態勢等因素，生成高質量的投資分析報告
- 即使無法獲取完整新聞標題，也應基於時間、公司業務、產業動態進行專業推演"""

    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        max_tokens=effective_max_tokens,
        temperature=0.7,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt},
        ],
    )
    text = response.choices[0].message.content
    usage = response.usage
    total_tokens = usage.prompt_tokens + usage.completion_tokens
    print(f"  ✅ response  in={usage.prompt_tokens}  out={usage.completion_tokens}  total={total_tokens}"
          f"  chars={len(text)}")

    # Log if we're under-utilizing available tokens
    if usage.completion_tokens < effective_max_tokens * 0.6:
        print(f"  ℹ️  Token usage is {usage.completion_tokens}/{effective_max_tokens} ({100*usage.completion_tokens//effective_max_tokens}%) - report could be more detailed")
    return text


def generate_report(
    ticker: str,
    provider: str,
    model: str,
    max_tokens: int,
    output_dir: Path,
) -> None:
    print(f"[1/4] Fetching ticker info for {ticker}…")
    info = fetch_ticker_info(ticker)

    print(f"[2/4] Fetching recent news for {ticker} (yfinance + RSS feeds)…")
    news_items = fetch_news(ticker)
    print(f"      Found {len(news_items)} news items (from yfinance + RSS feeds).")

    # Debug: Check data quality
    if news_items:
        valid_titles = sum(1 for item in news_items if item.get("title", "").strip())
        valid_publishers = sum(1 for item in news_items if item.get("publisher", "").strip())
        print(f"      Data quality: {valid_titles}/{len(news_items)} have titles, {valid_publishers}/{len(news_items)} have publishers")
        if valid_titles < len(news_items) * 0.5:
            print("[WARN] Less than 50% of news items have titles - data may be incomplete from yfinance")

    if not news_items:
        print("[WARN] No news returned by yfinance. Report will note data unavailability.")

    news_block = format_news_block(news_items) if news_items else "（目前無可用新聞資料）"
    prompt = build_prompt(ticker, info, news_block)

    print(f"[3/4] Calling {provider.upper()} ({model}, max_tokens={max_tokens})…")
    if provider == "openai":
        report_body = call_openai(prompt, model, max_tokens)
    else:
        report_body = call_claude(prompt, model, max_tokens)

    # YAML front-matter
    today = date.today().isoformat()
    front_matter = (
        "---\n"
        f"ticker: {ticker}\n"
        f"date: {today}\n"
        "type: market-news\n"
        f"provider: {provider}\n"
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
        help="Output directory (default: ai_gen_report/market_news/<ticker_lower>)",
    )
    parser.add_argument(
        "--output-file",
        default=None,
        help="Output filename (default: market_news_<date>_<provider>.md)",
    )
    parser.add_argument(
        "--provider",
        default=DEFAULT_PROVIDER,
        choices=["claude", "openai"],
        help=f"AI provider (default: {DEFAULT_PROVIDER})",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model ID (default: {DEFAULT_MODEL})",
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
        else Path(f"ai_gen_report/market_news/{ticker.lower()}")
    )

    generate_report(ticker, args.provider, args.model, args.max_tokens, output_dir)


if __name__ == "__main__":
    main()
