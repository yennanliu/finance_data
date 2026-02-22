#!/usr/bin/env python3
"""
generate_analysis.py
====================
Fetches live financial data from yfinance, then calls the Claude API
to produce a full fundamental-analysis report in Traditional Chinese
(Markdown format).

Usage
-----
  # default: AAPL → claude_code/aapl/
  python scripts/generate_analysis.py

  # any ticker
  python scripts/generate_analysis.py NVDA
  python scripts/generate_analysis.py TSLA --output-dir claude_code/tsla

  # choose model / token budget
  python scripts/generate_analysis.py AAPL --model claude-opus-4-6 --max-tokens 10000

Requirements
------------
  pip install anthropic yfinance

Environment
-----------
  ANTHROPIC_API_KEY   (required)
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
from datetime import date
from pathlib import Path

# ── dependency guards ─────────────────────────────────────────────────────────
try:
    import anthropic
except ImportError:
    sys.exit("ERROR: 'anthropic' not installed.  Run: pip install anthropic")

try:
    import yfinance as yf
except ImportError:
    sys.exit("ERROR: 'yfinance' not installed.  Run: pip install yfinance")

# ── constants ─────────────────────────────────────────────────────────────────
TODAY          = date.today().isoformat()
DEFAULT_MODEL  = "claude-sonnet-4-6"
DEFAULT_TOKENS = 8000


# ═════════════════════════════════════════════════════════════════════════════
# 1.  DATA COLLECTION
# ═════════════════════════════════════════════════════════════════════════════

def _safe(value, default="N/A"):
    """Return value or default when None / empty."""
    if value is None or value == "":
        return default
    return value


def _pct(value) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "N/A"


def _money(value, prefix="$") -> str:
    try:
        v = float(value)
        for mag, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
            if abs(v) >= mag:
                return f"{prefix}{v / mag:.2f}{suffix}"
        return f"{prefix}{v:.2f}"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_price(value) -> str:
    try:
        return f"${float(value):.2f}"
    except (TypeError, ValueError):
        return "N/A"


def _df_to_text(df, rows: list[str] | None = None, max_cols: int = 4) -> str:
    """Render a subset of a DataFrame as an ASCII table."""
    if df is None or df.empty:
        return "  (no data)"
    try:
        cols = list(df.columns[:max_cols])
        col_labels = [str(c)[:10] for c in cols]
        header = f"{'':30}" + "  ".join(f"{lbl:>14}" for lbl in col_labels)
        sep    = "-" * len(header)
        lines  = [header, sep]
        target = rows if rows else list(df.index)
        for row in target:
            if row in df.index:
                values = [df.loc[row, c] for c in cols]
                fmts   = [_money(v) for v in values]
                label  = str(row)[:28].ljust(30)
                lines.append(label + "  ".join(f"{f:>14}" for f in fmts))
        return "\n".join(lines)
    except Exception as exc:
        return f"  (formatting error: {exc})"


def fetch_data(ticker: str) -> dict:
    """Download fundamentals, price history, and news from Yahoo Finance."""
    print(f"  → yfinance: {ticker}")
    t    = yf.Ticker(ticker)
    info = t.info or {}

    # price history ───────────────────────────────────────────────────────────
    try:
        hist = t.history(period="1y")
        price_now      = float(hist["Close"].iloc[-1]) if not hist.empty else None
        price_52w_high = float(hist["High"].max())     if not hist.empty else None
        price_52w_low  = float(hist["Low"].min())      if not hist.empty else None
        # 1-year price series for ASCII chart (monthly close)
        monthly = hist["Close"].resample("ME").last().dropna()
        price_series = {str(k)[:7]: round(float(v), 2) for k, v in monthly.items()}
    except Exception:
        price_now = price_52w_high = price_52w_low = None
        price_series = {}

    # financial statements ────────────────────────────────────────────────────
    def _safe_df(fn):
        try:
            df = fn()
            return df if df is not None and not df.empty else None
        except Exception:
            return None

    return {
        "ticker":          ticker,
        "info":            info,
        "income":          _safe_df(lambda: t.financials),
        "income_q":        _safe_df(lambda: t.quarterly_financials),
        "balance":         _safe_df(lambda: t.balance_sheet),
        "cashflow":        _safe_df(lambda: t.cashflow),
        "news":            (t.news or [])[:8],
        "price_now":       price_now,
        "price_52w_high":  price_52w_high,
        "price_52w_low":   price_52w_low,
        "price_series":    price_series,
    }


def build_context(data: dict) -> str:
    """Assemble all fetched data into a single readable string for Claude."""
    info   = data["info"]
    ticker = data["ticker"]

    # ── income statement ──────────────────────────────────────────────────────
    inc_rows = [
        "Total Revenue",
        "Gross Profit",
        "Operating Income",
        "Net Income",
        "EBITDA",
        "Research And Development",
        "Selling General Administrative",
    ]
    # ── balance sheet ─────────────────────────────────────────────────────────
    bs_rows = [
        "Total Assets",
        "Total Liabilities Net Minority Interest",
        "Stockholders Equity",
        "Cash And Cash Equivalents",
        "Total Debt",
        "Current Assets",
        "Current Liabilities",
        "Inventory",
        "Accounts Receivable",
    ]
    # ── cash flow ─────────────────────────────────────────────────────────────
    cf_rows = [
        "Operating Cash Flow",
        "Capital Expenditure",
        "Free Cash Flow",
        "Common Stock Repurchased",
        "Cash Dividends Paid",
        "Issuance Of Debt",
        "Repayment Of Debt",
    ]

    # ── recent news ───────────────────────────────────────────────────────────
    news_lines = [
        f"  - {item['title']}"
        for item in data.get("news", [])
        if item.get("title")
    ]

    # ── price series for ASCII chart ──────────────────────────────────────────
    ps = data.get("price_series", {})
    if ps:
        min_p = min(ps.values())
        max_p = max(ps.values())
        rng   = max_p - min_p or 1
        bar_h = 8  # chart height in rows
        chart_lines = [f"  {'月份':>7}  {'收盤價':>8}  {'走勢'}"]
        for month, price in ps.items():
            bars = int((price - min_p) / rng * 30)
            chart_lines.append(f"  {month}  {price:>8.2f}  {'█' * bars}")
        price_chart = "\n".join(chart_lines)
    else:
        price_chart = "  (no price history)"

    ctx = f"""
╔══════════════════════════════════════════════════════════════════╗
║  FINANCIAL DATA PACKAGE  —  {ticker:<6}  —  {TODAY}
╚══════════════════════════════════════════════════════════════════╝

━━ COMPANY OVERVIEW ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ticker:              {ticker}
Full Name:           {_safe(info.get('longName'))}
Sector:              {_safe(info.get('sector'))}
Industry:            {_safe(info.get('industry'))}
Country:             {_safe(info.get('country'))}
Employees:           {_safe(info.get('fullTimeEmployees'))}
Business Summary:
{textwrap.fill(_safe(info.get('longBusinessSummary', ''), ''), width=78, initial_indent='  ', subsequent_indent='  ')[:600]}

━━ MARKET DATA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Current Price:       {_fmt_price(data['price_now'])}
52W High:            {_fmt_price(data['price_52w_high'])}
52W Low:             {_fmt_price(data['price_52w_low'])}
Market Cap:          {_money(info.get('marketCap'))}
Enterprise Value:    {_money(info.get('enterpriseValue'))}
Beta:                {_safe(info.get('beta'))}
Short Ratio:         {_safe(info.get('shortRatio'))}
Shares Outstanding:  {_money(info.get('sharesOutstanding'), prefix='')} shares
Float Shares:        {_money(info.get('floatShares'), prefix='')} shares

━━ 12-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{price_chart}

━━ VALUATION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
P/E  (Trailing):     {_safe(info.get('trailingPE'))}
P/E  (Forward):      {_safe(info.get('forwardPE'))}
PEG  Ratio:          {_safe(info.get('pegRatio'))}
P/S  Ratio:          {_safe(info.get('priceToSalesTrailing12Months'))}
P/B  Ratio:          {_safe(info.get('priceToBook'))}
EV / EBITDA:         {_safe(info.get('enterpriseToEbitda'))}
EV / Revenue:        {_safe(info.get('enterpriseToRevenue'))}
EPS  (TTM):          ${_safe(info.get('trailingEps'))}
EPS  (Forward):      ${_safe(info.get('forwardEps'))}

━━ ANALYST CONSENSUS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Recommendation:      {_safe(info.get('recommendationKey'))}
# of Analysts:       {_safe(info.get('numberOfAnalystOpinions'))}
Target (Low):        {_fmt_price(info.get('targetLowPrice'))}
Target (Mean):       {_fmt_price(info.get('targetMeanPrice'))}
Target (High):       {_fmt_price(info.get('targetHighPrice'))}

━━ PROFITABILITY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Revenue (TTM):       {_money(info.get('totalRevenue'))}
Revenue Growth:      {_pct(info.get('revenueGrowth'))}
Gross Margin:        {_pct(info.get('grossMargins'))}
EBITDA Margin:       {_pct(info.get('ebitdaMargins'))}
Operating Margin:    {_pct(info.get('operatingMargins'))}
Net Profit Margin:   {_pct(info.get('profitMargins'))}
ROE:                 {_pct(info.get('returnOnEquity'))}
ROA:                 {_pct(info.get('returnOnAssets'))}

━━ BALANCE SHEET SNAPSHOT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Cash:          {_money(info.get('totalCash'))}
Total Debt:          {_money(info.get('totalDebt'))}
Debt/Equity:         {_safe(info.get('debtToEquity'))}
Current Ratio:       {_safe(info.get('currentRatio'))}
Quick Ratio:         {_safe(info.get('quickRatio'))}

━━ CASH FLOW ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Operating Cash Flow: {_money(info.get('operatingCashflow'))}
Capital Expenditure: {_money(info.get('capitalExpenditures'))}
Free Cash Flow:      {_money(info.get('freeCashflow'))}

━━ DIVIDENDS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Dividend Yield:      {_pct(info.get('dividendYield'))}
Dividend Rate:       ${_safe(info.get('dividendRate'))}
Payout Ratio:        {_pct(info.get('payoutRatio'))}

━━ INCOME STATEMENT (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{_df_to_text(data['income'], inc_rows)}

━━ BALANCE SHEET (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{_df_to_text(data['balance'], bs_rows)}

━━ CASH FLOW STATEMENT (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{_df_to_text(data['cashflow'], cf_rows)}

━━ RECENT NEWS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{chr(10).join(news_lines) if news_lines else '  (no news)'}
""".strip()

    return ctx


# ═════════════════════════════════════════════════════════════════════════════
# 2.  PROMPT
# ═════════════════════════════════════════════════════════════════════════════

PROMPT_TEMPLATE = """\
你是一位頂級美股投資研究分析師，深度精通基本面分析。
請根據下方提供的即時財務數據，為 **{ticker}** 撰寫一份完整的基本面深度分析報告。

═══════════════════════  嚴格要求  ═══════════════════════
1. 語言：全程使用**繁體中文**（Traditional Chinese）
2. 格式：完整 **Markdown** 格式（# ## ### 層級標題）
3. 圖表：大量使用 ASCII 圖表（折線圖、長條圖）來展示數據趨勢
4. 深度：每個章節需深入分析，直接引用具體財務數字
5. 表格：重要比較數據一律用 Markdown 表格呈現
6. 評分：在適當地方加入 ★☆ 評星
7. 長度：涵蓋下列全部章節，不可省略
═══════════════════════════════════════════════════════════

━━ 財務數據（今日即時）━━
{financial_context}
━━━━━━━━━━━━━━━━━━━━━━━━

請嚴格按照以下架構輸出完整報告：

---

# {ticker} 基本面深度分析報告

> **報告日期**：{today} ｜ **語言**：繁體中文 ｜ **數據來源**：Yahoo Finance

---

## 目錄
（列出所有章節編號與名稱）

---

## 1. 執行摘要

用以下 ASCII 框格呈現核心儀表板：

```
╔══════════════════════════════════════════════════════╗
║  {ticker} 核心投資儀表板
╠════════════════════╦════════════════════════════════╣
║ 當前股價           ║  xxx                           ║
║ 52W 區間           ║  $xxx ─── $xxx                 ║
║ 市值               ║  xxx                           ║
║ 整體評級           ║  ★★★★☆  買入 / 持有 / 賣出     ║
╚════════════════════╩════════════════════════════════╝
```

列出 5 個核心投資論點（表格形式，含訊號 🟢🟡🔴）。

---

## 2. 公司概覽

- 核心業務、市場地位、業務分部
- 競爭優勢簡述

---

## 3. 損益表深度分析

### 3.1 年度收入趨勢（ASCII 折線圖）

用 ASCII 長條圖顯示近 4 年收入，例如：

```
年度收入 ($B)
$400B ┤
$350B ┤  ████
...
```

### 3.2 利潤率趨勢

用 ASCII 折線圖顯示毛利率、營業利潤率、淨利率趨勢。

### 3.3 詳細數據表

用表格列出近 4 年：收入、毛利率、EBITDA、淨利潤、EPS。

### 3.4 費用結構分析

---

## 4. 資產負債表分析

### 4.1 資產結構（ASCII 橫條圖）
### 4.2 負債與流動性
### 4.3 股東權益趨勢

---

## 5. 現金流量分析

### 5.1 現金流瀑布圖（ASCII）
### 5.2 自由現金流趨勢
### 5.3 資本配置策略

---

## 6. 獲利能力指標

### 6.1 ROE / ROA / ROIC 趨勢
### 6.2 與行業均值比較（表格）

---

## 7. 估值分析

### 7.1 估值指標彙整表

| 指標 | {ticker} | 行業均值 | 5年均值 | 評估 |
|------|----------|---------|---------|------|
| P/E  | ...      | ...     | ...     | ...  |
...

### 7.2 情境目標股價

| 情境 | 假設 | 目標股價 | vs 現價 |
|------|------|---------|---------|
...

---

## 8. 競爭護城河

用 ASCII 條形圖顯示各護城河強度評分（0-100）。

---

## 9. 成長催化劑

- 短期（0-12 個月）
- 中期（1-3 年）
- 長期（3 年以上）
- TAM 市場規模估算

---

## 10. 風險分析

### 10.1 風險矩陣（ASCII 表格，影響程度 × 發生概率）
### 10.2 主要風險詳表（含緩解措施）

---

## 11. 公平價值估算

用三種方法估算，並給出目標股價區間。

---

## 12. 投資建議

```
╔══════════════════════════════════════════╗
║  最終評級：★★★★☆  [買入 / 持有 / 賣出]  ║
║  公平價值：$xxx – $xxx                   ║
║  建議倉位：xx%                           ║
║  投資時限：x–x 年                        ║
╚══════════════════════════════════════════╝
```

後續監控指標清單（Markdown checklist）。

---

> **免責聲明**：本報告為 AI 自動生成，僅供研究參考，不構成投資建議。
"""


# ═════════════════════════════════════════════════════════════════════════════
# 3.  CLAUDE API
# ═════════════════════════════════════════════════════════════════════════════

def call_claude(ticker: str, context: str, model: str, max_tokens: int) -> str:
    """Call the Claude Messages API and return the full analysis text."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY environment variable is not set.")

    client = anthropic.Anthropic(api_key=api_key)
    prompt = PROMPT_TEMPLATE.format(
        ticker=ticker,
        financial_context=context,
        today=TODAY,
    )

    print(f"  → Claude API  model={model}  max_tokens={max_tokens}")
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )

    text = "\n\n".join(
        block.text for block in response.content if hasattr(block, "text")
    )
    usage = response.usage
    print(
        f"  ✅ response  in={usage.input_tokens}  out={usage.output_tokens}"
        f"  chars={len(text)}"
    )
    return text


# ═════════════════════════════════════════════════════════════════════════════
# 4.  SAVE
# ═════════════════════════════════════════════════════════════════════════════

def save_report(ticker: str, content: str, output_dir: Path) -> Path:
    """Write the report to a dated .md file with YAML frontmatter."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"fundamental_analysis_{TODAY}.md"
    path     = output_dir / filename

    frontmatter = (
        "---\n"
        f'title: "{ticker} 基本面分析 {TODAY}"\n'
        f"date: {TODAY}\n"
        f"ticker: {ticker}\n"
        "language: zh-TW\n"
        "generated_by: Claude AI (scripts/generate_analysis.py)\n"
        "---\n\n"
    )
    path.write_text(frontmatter + content, encoding="utf-8")
    print(f"  ✅ saved → {path}")
    return path


# ═════════════════════════════════════════════════════════════════════════════
# 5.  CLI
# ═════════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate a Traditional-Chinese fundamental analysis report via Claude API."
    )
    p.add_argument("ticker",       nargs="?",  default="AAPL",
                   help="Stock ticker symbol (default: AAPL)")
    p.add_argument("--output-dir", type=Path,  default=None,
                   help="Directory to save the report (default: claude_code/<ticker>/)")
    p.add_argument("--model",      default=DEFAULT_MODEL,
                   help=f"Claude model ID (default: {DEFAULT_MODEL})")
    p.add_argument("--max-tokens", type=int,   default=DEFAULT_TOKENS,
                   help=f"Max output tokens (default: {DEFAULT_TOKENS})")
    return p.parse_args()


def main() -> None:
    args       = parse_args()
    ticker     = args.ticker.upper()
    output_dir = args.output_dir or (Path("claude_code") / ticker.lower())

    banner = f"  Generating: {ticker}  |  model: {args.model}  |  out: {output_dir}"
    sep    = "=" * max(60, len(banner))
    print(f"\n{sep}\n{banner}\n{sep}\n")

    print("[1/3] Fetching financial data from Yahoo Finance …")
    data    = fetch_data(ticker)
    context = build_context(data)

    print("[2/3] Calling Claude API …")
    report  = call_claude(ticker, context, args.model, args.max_tokens)

    print("[3/3] Saving report …")
    save_report(ticker, report, output_dir)

    print(f"\n{sep}\n  Done!\n{sep}\n")


if __name__ == "__main__":
    main()
