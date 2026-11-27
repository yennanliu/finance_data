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
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from functools import partial
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))

from analysis.config.providers import resolve_chain
from analysis.data.prices import to_yf_symbol
from analysis.data.sources import last_completed_close, quote_close, yahoo_news
from analysis.llm import run_claude, run_openai, run_gemini, run_with_fallback
from analysis.publish import GENERATED_BY, frontmatter

DEFAULT_TOKENS = 20000

# Hard cap for Gemini against runaway output. It was 8000 after a prompt that
# told the model to invent missing news produced 200-270 KB reports; that
# prompt is fixed, and at 8000 about 4% of reports (68 of 1,759 by 2026-11)
# were cut off mid-line, because Gemini's thinking tokens share this budget.
# 20000 matches the workflow's DEFAULT_MAX_TOKENS and still bounds a runaway
# at roughly 40k characters. Real runs at 20000 used ~5k and finished (STOP).
_GEMINI_MAX_TOKENS = 20000


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

# Sites with no keyless feed, read through a Google News site: search instead.
# Perplexity Discover sits behind Cloudflare; X's API is paid. Google News
# indexes both, titling each item "<headline or post> - <name>". A site: search
# matches the ticker anywhere on a page (sidebars, quote widgets, a post's list
# of ten cashtags), so the whole feed is scanned and only titles naming the
# company are kept. On X a stock is its cashtag: bare "ANT" is also a crypto
# token, "$ANT" is Anthropic.
SITE_SEARCHES = {  # name: (domain, regex required before the ticker)
    "Perplexity": ("perplexity.ai", ""),
    "X":          ("x.com", r"\$"),
}
SITE_FEED = "https://news.google.com/rss/search?q={query}+site:{site}+when:7d&hl=en-US&gl=US&ceid=US:en"
SITE_SCAN_LIMIT = 100

_CORP_SUFFIX = re.compile(r",?\s+(?:inc|corp|corporation|co|company|ltd|limited|plc|holdings?|group)\.?$", re.I)
_QUOTE_PAGE = re.compile(r"\bPrice: Quote\b")

# ── News selection ─────────────────────────────────────────────────────────────
# What reaches the prompt. The 2026-11-27 QA review failed or warned market-news
# reports for news dated 2017-2025 presented as current (6206.tw's newest item
# was 2025-07-09) and for headlines about other companies (Domino's, FiscalNote,
# Wells Fargo in 4766.tw). Both came from the keyword feeds: a search for
# "4766.TW stock" returns old quote pages and unrelated Seeking Alpha articles.
NEWS_MAX_AGE_DAYS = 14
# The keyword-search feeds. Yahoo's own search (yfinance) is per-symbol and the
# site searches already filter on the company, so only these are re-checked.
KEYWORD_FEEDS = frozenset(name for name, _ in RSS_FEEDS)
# Quote, profile and options pages: titles of a page about a ticker, not news.
_LISTING_PAGE = re.compile(
    r"stock price,? (?:news,? )?quote|price,? quote|company profile|options chain"
    r"|stock price and chart|META_TITLE|^[^|]*\([0-9A-Z.\-]+\)\s*$", re.I)


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


def _short_name(company: str) -> str:
    """'Tesla, Inc.' → 'Tesla', 'NVIDIA Corporation' → 'NVIDIA'."""
    while (stripped := _CORP_SUFFIX.sub("", company).strip().rstrip(",")) != company:
        company = stripped  # "Nan Pao Resins Chemical Co., Ltd." leaves "… Co.," after one pass
    return company


def _fetch_site(name: str, site: str, ticker: str, company: str = "",
                ticker_prefix: str = "") -> list[dict]:
    """Items from *site* (via Google News) whose title names *ticker* or *company*."""
    names = [rf"{ticker_prefix}\b(?-i:{re.escape(ticker)})\b"]  # case-sensitive: tickers like ON, IT
    # fetch_ticker_info() falls back to the ticker as the name; matching that
    # case-insensitively would bypass the cashtag and case rules above.
    # Compare the raw name: "Arm Holdings plc" shortens to "Arm" and is real.
    if company.upper() != ticker.upper() and (short := _short_name(company)):
        # Case-sensitive like the ticker: "Grab" the company, not a "40-yard grab".
        names.append(rf"\b(?-i:{re.escape(short)})\b")
    about_company = re.compile("|".join(names), re.I)

    feed = SITE_FEED.format(query="{query}", site=site)
    kept = []
    for item in _fetch_rss(feed, name, ticker, limit=SITE_SCAN_LIMIT):
        item["title"] = item["title"].removesuffix(f" - {name}")
        if about_company.search(item["title"]) and not _QUOTE_PAGE.search(item["title"]):
            kept.append(item)
    return kept[:RSS_PER_FEED_LIMIT]


def _names_company(ticker: str, company: str) -> re.Pattern:
    """Pattern for text that names the stock: its ticker or its short name.

    A Taiwan listing is named by its bare code ("南寶(4766)", "TWSE:4766");
    a US ticker is matched case-sensitively, as in :func:`_fetch_site`.
    """
    code = ticker.upper().removesuffix(".TW")
    names = [rf"(?<![0-9A-Za-z])(?-i:{re.escape(code)})(?![0-9A-Za-z])"]
    if company.upper() != ticker.upper() and (short := _short_name(company)):
        # Headlines shorten long names: "Nan Pao Resins Chemical" is "Nan Pao".
        words = short.split()
        lead = " ".join(words[:2]) if len(words) > 2 else short
        names.append(rf"\b(?-i:{re.escape(lead)})\b")
    return re.compile("|".join(names), re.I)


def select_news(items: list[dict], ticker: str, company: str = "",
                now: datetime | None = None) -> list[dict]:
    """Keep the items a news report may treat as current news about *ticker*.

    Drops items older than NEWS_MAX_AGE_DAYS or with no publish time, quote and
    profile pages, and keyword-feed items whose title and summary do not name
    the company. Fewer items is the intended outcome: the prompt already says
    to analyse only what is provided.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=NEWS_MAX_AGE_DAYS)).timestamp()
    about = _names_company(ticker, company)
    kept = []
    for item in items:
        title = item.get("title") or ""
        if (item.get("providerPublishTime") or 0) < cutoff:
            continue
        if _LISTING_PAGE.search(title):
            continue
        if (item.get("publisher") in KEYWORD_FEEDS
                and not about.search(f"{title} {item.get('summary') or ''}")):
            continue
        kept.append(item)
    return kept


def fetch_news(ticker: str, company: str = "") -> list[dict]:
    """Collect news from yfinance + RSS feeds + site searches, deduplicate, and return.

    Every web source fails soft (returns []), so one going down narrows the
    report instead of aborting it.
    """
    yf_items = yahoo_news(ticker)
    source_counts: dict[str, int] = {"yfinance": len(yf_items)}

    web_sources = {name: partial(_fetch_rss, url, name, ticker) for name, url in RSS_FEEDS}
    web_sources |= {name: partial(_fetch_site, name, site, ticker, company, prefix)
                    for name, (site, prefix) in SITE_SEARCHES.items()}

    web_items: list[dict] = []
    with ThreadPoolExecutor(max_workers=len(web_sources)) as pool:
        futures = {pool.submit(fetch): name for name, fetch in web_sources.items()}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                batch = fut.result()
            except Exception as exc:  # a fetcher bug must not abort the report
                print(f"  [WARN] {name} failed: {exc!r}", file=sys.stderr)
                batch = []
            source_counts[name] = len(batch)
            web_items.extend(batch)

    parts = [f"{src}: {n}" for src, n in source_counts.items()]
    print(f"      Sources → {', '.join(parts)}")

    # Combine & deduplicate by normalised title
    all_items = yf_items + web_items
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
    """Return basic info dict (price, sector, name…) from yfinance.

    ``price_date`` is the session the price closed on (None when the quote is
    intraday or undated). A report dated on a market holiday was otherwise
    handed a bare price and wrote it up as that day's close: qqq and soxx on
    2026-11-26, Thanksgiving.
    """
    try:
        t = ticker_obj or yf.Ticker(ticker)
        info = t.info or {}
        close, close_date = quote_close(info)
        if close_date is None:  # mid-session: the last finished session instead
            try:
                close, close_date = last_completed_close(t.history(period="5d"))
            except Exception:
                close, close_date = None, None
        summary = (info.get("longBusinessSummary") or "").strip()
        return {
            "name": info.get("longName") or info.get("shortName") or ticker,
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "current_price": close or info.get("currentPrice") or info.get("regularMarketPrice", "N/A"),
            "price_date": close_date,
            "timezone": info.get("exchangeTimezoneName") or "",
            "currency": info.get("currency", "USD"),
            "market_cap": info.get("marketCap", "N/A"),
            "business_summary": summary[:BUSINESS_SUMMARY_CHARS],
            "target_mean": info.get("targetMeanPrice"),
            "analyst_count": info.get("numberOfAnalystOpinions"),
        }
    except Exception as exc:
        print(f"[WARN] Could not fetch ticker info: {exc}", file=sys.stderr)
        return {"name": ticker}


# Yahoo's own profile, so the overview is not written from the model's memory:
# wdc was still described as a flash-memory maker after the SanDisk split.
BUSINESS_SUMMARY_CHARS = 800


def analyst_upside(info: dict) -> str | None:
    """'+63.0%' from the consensus target to the price, computed here.

    amd's report paired a 662 target with headline upside figures ("about 57%"
    to the record high, "58%" to another target) that do not recompute from it.
    """
    try:
        price, target = float(info["current_price"]), float(info["target_mean"])
    except (KeyError, TypeError, ValueError):
        return None
    if price <= 0 or target <= 0:
        return None
    return f"{(target / price - 1) * 100:+.1f}%"


def format_news_block(news_items: list[dict], tzname: str = "") -> str:
    """Convert news list to a readable text block for the prompt.

    Times are in the exchange's zone when known: a story filed on the US
    evening of 11-25 is 11-26 in UTC, and the model wrote it up as 11-26 news.
    """
    try:
        tz = ZoneInfo(tzname) if tzname else timezone.utc
    except Exception:
        tz = timezone.utc
    lines = []
    for i, item in enumerate(news_items[:25], 1):
        title = (item.get("title") or "").strip() or f"《未命名新聞 #{i}》"
        publisher = (item.get("publisher") or "").strip() or "未知來源"
        pub_ts = item.get("providerPublishTime", 0)
        if pub_ts:
            pub_dt = datetime.fromtimestamp(pub_ts, tz=tz).strftime("%Y-%m-%d %H:%M %Z")
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
    price_date = info.get("price_date")
    if price_date:
        price_line = f"{price} {currency}（{price_date} 收盤）"
        if price_date != today:
            price_line += (f"\n- 交易狀態：{today} 沒有已完成的交易日收盤（休市或尚未收盤）。"
                           f"不得描述 {today} 的收盤價、漲跌或盤勢")
    else:
        price_line = f"{price} {currency}（盤中報價，非收盤價）"
    summary = info.get("business_summary")
    profile = f"\n- 公司簡介（Yahoo Finance）：{summary}" if summary else ""
    upside = analyst_upside(info)
    target = (f"\n- 分析師共識目標價：{float(info['target_mean']):.2f} {currency}"
              f"（{info.get('analyst_count') or '?'} 位分析師），相對現價 {upside}（程式計算）"
              if upside else "")

    return f"""你是一位專業的財經分析師，請根據以下 {ticker}（{name}）的最新新聞，
用**繁體中文**撰寫一份詳盡的市場新聞分析報告。

## 股票基本資訊
- 代碼：{ticker}
- 名稱：{name}
- 產業：{sector}
- 最新股價：{price_line}{target}
- 報告日期：{today}{profile}

## 最新新聞資料
{news_block}

---

重要提示：
- **只分析上方實際提供的新聞**，不要憑空捏造或推測不存在的新聞標題與事件
- 如新聞數量較少，深度分析現有的 3–5 則重點新聞即可，無需填充虛假內容
- 不使用 "$XXX"、"N/A"、"TBD" 等佔位符；若某數值未知，直接跳過該細節
- 每個新聞分析應包含對公司營運或股價的具體影響說明
- 「🏢 公司概覽」以上方公司簡介為準，不要用你記憶中的業務描述（公司可能已分拆、併購或轉型）
- 不要自行計算百分比、漲跌幅或上行空間。只引用新聞或上方資料中已有的數字，並註明出處
  （例如「據 Yahoo Finance 報導，股價需上漲約 57% 才能回到歷史高點」），不要把不同來源的價格與百分比湊在一起
- 分析師共識目標價只是背景資訊：可以引用，但不得單憑它推論估值支撐、低估或營運前景
- 若上方沒有提供任何新聞，各章節只需簡短說明本期無可用新聞，不得用一般產業知識推演公司近況
- 區分事實與推論：新聞報導的事件寫成事實；你的推論要寫成「可能」「或將」，不得把推測寫成已確定的因果或結果
- 「創歷史紀錄」「自某年以來最大」等歷史比較，只有新聞明確這樣寫時才可引用，並註明出處
- 新聞的發布時間是其報導時間；描述事件日期時以新聞內容為準，不要把發布日期當成事件發生日
- 來源為「X」的條目是社群貼文，不是新聞報導：只可作為市場情緒的參考，不得當作已證實的事實引用。
  引用 X 貼文中的任何數字或說法時，必須在同一句註明「據 X 貼文」；不得把未經新聞證實的 X 數字寫成一般事實
  （例如「散戶單日買入逾 1 億美元」應寫成「據 X 貼文，散戶單日買入逾 1 億美元（未經證實）」）。
  同一事件若有新聞報導，以新聞內容為準

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
    """Generate a market-news report via Gemini (20k cap, no recovery/refusal retry)."""
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
    symbol = to_yf_symbol(ticker)  # a bare "0050" is a 404 on Yahoo
    print(f"[1/4] Fetching ticker info for {symbol}…")
    info = fetch_ticker_info(symbol)

    print(f"[2/4] Fetching recent news for {symbol} (yfinance + RSS feeds + Perplexity + X)…")
    fetched = fetch_news(symbol, info.get("name", ""))
    news_items = select_news(fetched, symbol, info.get("name", ""))
    print(f"      Found {len(fetched)} unique news items; {len(news_items)} recent and about "
          f"{symbol} (last {NEWS_MAX_AGE_DAYS} days).")

    if news_items:
        valid_titles = sum(1 for item in news_items if item.get("title", "").strip())
        valid_publishers = sum(1 for item in news_items if item.get("publisher", "").strip())
        print(f"      Data quality: {valid_titles}/{len(news_items)} have titles, {valid_publishers}/{len(news_items)} have publishers")
        if valid_titles < len(news_items) * 0.5:
            print("[WARN] Less than 50% of news items have titles - data may be incomplete from yfinance")

    if not news_items:
        print("[WARN] No news found. Report will note data unavailability.")

    news_block = (format_news_block(news_items, info.get("timezone", ""))
                  if news_items else "（目前無可用新聞資料）")
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
        **({"price": info["current_price"], "price_date": info["price_date"]}
           if info.get("price_date") else {}),
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
