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
import re
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.request import Request, urlopen

import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))

from analysis.config.providers import resolve_chain
from analysis.llm import run_claude, run_openai, run_gemini, run_with_fallback
from analysis.publish import GENERATED_BY, frontmatter

DEFAULT_PROVIDER = "gemini"
DEFAULT_MODEL = "gemini-3.6-flash"
DEFAULT_TOKENS = 12000

# Hard cap for Gemini to prevent runaway multi-hundred-KB outputs
_GEMINI_MAX_TOKENS = 8000


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


def fetch_news(ticker: str, ticker_obj: yf.Ticker | None = None) -> list[dict]:
    """Collect news from yfinance + keyword-searched RSS feeds, deduplicate, and return."""
    source_counts: dict[str, int] = {}

    yf_items: list[dict] = []
    try:
        t = ticker_obj or yf.Ticker(ticker)
        yf_items = t.news or []
        source_counts["yfinance"] = len(yf_items)
    except Exception as exc:
        print(f"  [WARN] yfinance news fetch failed: {exc}", file=sys.stderr)
        source_counts["yfinance"] = 0

    rss_items: list[dict] = []
    with ThreadPoolExecutor(max_workers=len(RSS_FEEDS)) as pool:
        futures = {pool.submit(_fetch_rss, url, name, ticker): name for name, url in RSS_FEEDS}
        for fut in as_completed(futures):
            name = futures[fut]
            batch = fut.result()
            source_counts[name] = len(batch)
            rss_items.extend(batch)

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


def fetch_ticker_info(ticker: str, ticker_obj: yf.Ticker | None = None) -> dict:
    """Return basic info dict (price, sector, name…) from yfinance."""
    try:
        t = ticker_obj or yf.Ticker(ticker)
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
    """Convert news list to a readable text block for the prompt."""
    lines = []
    for i, item in enumerate(news_items[:25], 1):
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
- **只分析上方實際提供的新聞**，不要憑空捏造或推測不存在的新聞標題與事件
- 如新聞數量較少，深度分析現有的 3–5 則重點新聞即可，無需填充虛假內容
- 不使用 "$XXX"、"N/A"、"TBD" 等佔位符；若某數值未知，直接跳過該細節
- 每個新聞分析應包含對公司營運或股價的具體影響說明

請依照以下格式完整輸出報告（使用 Markdown）：

# {ticker} 市場新聞分析報告 ({today})

## 📅 報告日期
{today}

## 🏢 公司概覽
[一段簡短的公司/產業背景介紹，包含關鍵業務和市場地位]

## 📝 新聞摘要總覽
[400–600 字的完整摘要，整合所有新聞的核心內容。涵蓋：近期重大事件、公司動態、
產業趨勢、市場反應。此段應讓讀者在不閱讀後續細節的情況下，完整掌握當前全貌。]

## 💡 關鍵洞察
[條列 5–8 點深度洞察，每點 2–4 句話，格式如下：]
- **洞察標題**：[具體說明該洞察的意義、背後驅動因素、以及對投資決策的啟示]
[洞察應涵蓋：競爭優勢變化、財務健康度信號、產業拐點、管理層行動、技術/監管趨勢等]

## 📰 近期新聞總覽
[條列式列出新聞標題及發布時間，格式：- YYYY-MM-DD | 標題 — 來源]
[只列出實際提供的新聞，不添加推測或憑空捏造的標題]

## 🔍 重點新聞深度分析
[從上方實際提供的新聞中選出 3–5 則最重要的，逐一深入分析]
[對每則新聞進行具體分析，包括對公司營運、財務、股價的潛在影響]

## 📊 市場情緒評估
[整體市場情緒：🟢 正面 / 🟡 中性 / 🔴 負面]
[詳細說明評估依據，包含正面因素與負面因素]

## ⚠️ 主要風險因素
[識別出的短期或長期風險，條列說明]

## 🔮 短期關注重點
[根據新聞，未來 1–4 週投資人應關注的事項或催化劑]

## 📌 新聞來源索引
[依序列出所有新聞：序號. 標題 — 來源 (日期)]

---
*本報告由 AI 自動生成，僅供參考，不構成任何投資建議。*
"""


# ── Main ───────────────────────────────────────────────────────────────────────

# News-specific system messages (differ from the analysis-report PROMPT_MAP).
_OPENAI_SYSTEM_MESSAGE = """你是一位頂級美股投資研究分析師，擁有 CFA 資格與 15 年以上財經新聞分析經驗。

你的分析必須遵循以下原則：
1. **新聞摘要總覽**：必須撰寫 400–600 字的完整摘要，整合所有新聞核心內容，讓讀者一覽全局
2. **關鍵洞察**：提供 5–8 點深度洞察，每點須有具體說明與投資啟示，不得流於表面
3. **深度分析**：每個章節必須提供詳盡、專業的分析，不得只有簡單的一兩句話
4. **數據準確性**：只引用可從提供新聞中確認的數據；不使用 "$XXX"、"N/A"、"TBD" 等佔位符
5. **專業格式**：使用完整的 Markdown 格式，包含表格、條列、emoji 視覺標記
6. **風險評估**：詳細分析風險因素，使用 🟢🟡🔴 標記風險等級
7. **產業洞察**：提供產業背景、競爭態勢、市場趨勢的深入分析
8. **報告長度**：目標 1500–2500 字，精簡有力，不重複鋪墊

**新聞資料處理原則**：
- **只分析實際提供的新聞**，不捏造或推測不存在的新聞標題與事件
- 跳過標題為「未命名」或「N/A」的條目，不對其進行內容推演
- 若新聞數量有限，深度分析現有重點新聞即可，無需填充虛假內容"""


_GEMINI_SYSTEM_MESSAGE = """你是一位頂級美股投資研究分析師，擁有 CFA 資格與 15 年以上財經新聞分析經驗。

你的分析必須遵循以下原則：
1. **新聞摘要總覽**：必須撰寫 400–600 字的完整摘要，整合所有新聞核心內容，讓讀者一覽全局
2. **關鍵洞察**：提供 5–8 點深度洞察，每點須有具體說明與投資啟示，不得流於表面
3. **深度分析**：每個章節必須提供詳盡、專業的分析，不得只有簡單的一兩句話
4. **數據準確性**：只引用可從提供新聞中確認的數據；不使用 "$XXX"、"N/A"、"TBD" 等佔位符
5. **專業格式**：使用完整的 Markdown 格式，包含表格、條列、emoji 視覺標記
6. **風險評估**：詳細分析風險因素，使用 🟢🟡🔴 標記風險等級
7. **報告長度**：目標 1500–2500 字，精簡有力，不重複鋪墊
8. **新聞誠信**：只分析實際提供的新聞，不捏造或推測不存在的新聞標題與事件"""


def call_claude(prompt: str, model: str, max_tokens: int) -> str:
    """Generate a market-news report via Claude (no refusal retry, no system msg)."""
    return run_claude("", prompt, None, model=model, max_tokens=max_tokens,
                      refusal_retry=False)


def call_openai(prompt: str, model: str, max_tokens: int) -> str:
    """Generate a market-news report via OpenAI (news system msg, no refusal retry)."""
    return run_openai("", prompt, _OPENAI_SYSTEM_MESSAGE, model=model,
                      max_tokens=max_tokens, refusal_retry=False)


def call_gemini(prompt: str, model: str, max_tokens: int) -> str:
    """Generate a market-news report via Gemini (8k cap, no recovery/refusal retry)."""
    return run_gemini("", prompt, _GEMINI_SYSTEM_MESSAGE, model=model,
                      max_tokens=max_tokens, token_ceiling=_GEMINI_MAX_TOKENS,
                      recover_truncation=False, refusal_retry=False)


def generate_report(
    ticker: str,
    provider: str,
    model: str,
    max_tokens: int,
    output_dir: Path,
    output_filename: str | None = None,
) -> None:
    print(f"[1/4] Fetching ticker info for {ticker}…")
    ticker_obj = yf.Ticker(ticker)
    info = fetch_ticker_info(ticker, ticker_obj)

    print(f"[2/4] Fetching recent news for {ticker} (yfinance + RSS feeds)…")
    news_items = fetch_news(ticker, ticker_obj)
    print(f"      Found {len(news_items)} news items (from yfinance + RSS feeds).")

    if news_items:
        valid_titles = sum(1 for item in news_items if item.get("title", "").strip())
        valid_publishers = sum(1 for item in news_items if item.get("publisher", "").strip())
        print(f"      Data quality: {valid_titles}/{len(news_items)} have titles, {valid_publishers}/{len(news_items)} have publishers")
        if valid_titles < len(news_items) * 0.5:
            print("[WARN] Less than 50% of news items have titles - data may be incomplete from yfinance")

    if not news_items:
        print("[WARN] No news found. Report will note data unavailability.")

    news_block = format_news_block(news_items) if news_items else "（目前無可用新聞資料）"
    prompt = build_prompt(ticker, info, news_block)

    def dispatch(prov: str, mdl: str) -> str:
        if prov == "openai":
            return call_openai(prompt, mdl, max_tokens)
        elif prov == "gemini":
            return call_gemini(prompt, mdl, max_tokens)
        return call_claude(prompt, mdl, max_tokens)

    attempts = resolve_chain(provider, model)
    print(f"[3/4] Generating report (chain: {' → '.join(p for p, _ in attempts)}, "
          f"max_tokens={max_tokens})…")
    report_body, provider, model = run_with_fallback(attempts, dispatch)

    today = date.today().isoformat()
    front_matter = frontmatter({
        "title": f'"{ticker} 市場新聞分析 {today}"',
        "ticker": ticker,
        "date": today,
        "type": "market-news",
        "provider": provider,
        "model": model,
        "language": "zh-TW",
        "generated_by": f"{GENERATED_BY.get(provider, 'Claude AI')} (scripts/generate_market_news.py)",
    })

    output_dir.mkdir(parents=True, exist_ok=True)
    filename = output_filename or f"market_news_{today}_{provider}.md"
    output_file = output_dir / filename
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
        default=None,
        choices=["claude", "openai", "gemini"],
        help="Primary AI provider; leads the fallback chain "
             "(default: the configured chain, currently gemini → openai)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model ID for the primary provider (default: that provider's default model)",
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

    generate_report(ticker, args.provider, args.model, args.max_tokens, output_dir, args.output_file)


if __name__ == "__main__":
    main()
