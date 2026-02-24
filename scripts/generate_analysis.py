#!/usr/bin/env python3
"""
generate_analysis.py
====================
Fetches live financial data from yfinance, then calls the Claude API
to produce an investment analysis report in Traditional Chinese (Markdown).

Supported analysis types
-------------------------
  fundamental-analysis   Deep fundamental analysis using financial statements
  technical-analysis     Technical chart and indicator analysis
  stock-eval             Comprehensive stock evaluation (fundamental + valuation)
  economics-analysis     US economic indicators and macro environment
  portfolio-review       Portfolio performance and optimization review
  sector-analysis        US market sector rotation and analysis

Usage
-----
  python scripts/generate_analysis.py                          # AAPL fundamental
  python scripts/generate_analysis.py TSLA --analysis-type technical-analysis
  python scripts/generate_analysis.py SPY  --analysis-type sector-analysis
  python scripts/generate_analysis.py      --analysis-type economics-analysis
  python scripts/generate_analysis.py AAPL --model claude-opus-4-6 --max-tokens 10000

Same-day runs: if fundamental_analysis_2026-02-22.md already exists,
the next run creates fundamental_analysis_2026-02-22-2.md, then -3, etc.

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

ANALYSIS_TYPES = {
    "fundamental-analysis": {
        "filename_prefix": "fundamental_analysis",
        "label":           "基本面深度分析",
    },
    "technical-analysis": {
        "filename_prefix": "technical_analysis",
        "label":           "技術分析",
    },
    "stock-eval": {
        "filename_prefix": "stock_eval",
        "label":           "綜合股票評估",
    },
    "economics-analysis": {
        "filename_prefix": "economics_analysis",
        "label":           "總體經濟分析",
    },
    "portfolio-review": {
        "filename_prefix": "portfolio_review",
        "label":           "投資組合回顧",
    },
    "sector-analysis": {
        "filename_prefix": "sector_analysis",
        "label":           "產業板塊分析",
    },
}


# ═════════════════════════════════════════════════════════════════════════════
# 1.  DATA COLLECTION
# ═════════════════════════════════════════════════════════════════════════════

def _safe(value, default="N/A"):
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
    if df is None or df.empty:
        return "  (no data)"
    try:
        cols       = list(df.columns[:max_cols])
        col_labels = [str(c)[:10] for c in cols]
        header     = f"{'':30}" + "  ".join(f"{lbl:>14}" for lbl in col_labels)
        sep        = "-" * len(header)
        lines      = [header, sep]
        target     = rows if rows else list(df.index)
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
        hist           = t.history(period="1y")
        price_now      = float(hist["Close"].iloc[-1]) if not hist.empty else None
        price_52w_high = float(hist["High"].max())     if not hist.empty else None
        price_52w_low  = float(hist["Low"].min())      if not hist.empty else None
        monthly        = hist["Close"].resample("ME").last().dropna()
        price_series   = {str(k)[:7]: round(float(v), 2) for k, v in monthly.items()}
    except Exception:
        hist = None
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
        "ticker":         ticker,
        "info":           info,
        "hist":           hist,
        "income":         _safe_df(lambda: t.financials),
        "income_q":       _safe_df(lambda: t.quarterly_financials),
        "balance":        _safe_df(lambda: t.balance_sheet),
        "cashflow":       _safe_df(lambda: t.cashflow),
        "news":           (t.news or [])[:8],
        "price_now":      price_now,
        "price_52w_high": price_52w_high,
        "price_52w_low":  price_52w_low,
        "price_series":   price_series,
    }


# ─── ASCII helpers ────────────────────────────────────────────────────────────

def _price_ascii_chart(price_series: dict) -> str:
    if not price_series:
        return "  (no price history)"
    lines = [f"  {'月份':>7}  {'收盤價':>8}  走勢"]
    min_p = min(price_series.values())
    max_p = max(price_series.values())
    rng   = max_p - min_p or 1
    for month, price in price_series.items():
        bars = int((price - min_p) / rng * 30)
        lines.append(f"  {month}  {price:>8.2f}  {'█' * bars}")
    return "\n".join(lines)


def _compute_technicals(hist) -> str:
    """Compute basic technical indicators from OHLC history DataFrame."""
    if hist is None or hist.empty:
        return "  (no OHLC data)"
    try:
        import pandas as pd

        close  = hist["Close"]
        volume = hist["Volume"]

        # Moving averages
        ma20  = close.rolling(20).mean()
        ma50  = close.rolling(50).mean()
        ma200 = close.rolling(200).mean()

        # RSI-14
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss.replace(0, float("nan"))
        rsi   = 100 - (100 / (1 + rs))

        # MACD (12/26/9)
        ema12  = close.ewm(span=12, adjust=False).mean()
        ema26  = close.ewm(span=26, adjust=False).mean()
        macd   = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        hist_m = macd - signal

        # Bollinger Bands (20, 2σ)
        bb_mid  = close.rolling(20).mean()
        bb_std  = close.rolling(20).std()
        bb_up   = bb_mid + 2 * bb_std
        bb_lo   = bb_mid - 2 * bb_std

        # Last values
        last        = close.iloc[-1]
        last_ma20   = ma20.iloc[-1]
        last_ma50   = ma50.iloc[-1]
        last_ma200  = ma200.iloc[-1] if len(close) >= 200 else float("nan")
        last_rsi    = rsi.iloc[-1]
        last_macd   = macd.iloc[-1]
        last_signal = signal.iloc[-1]
        last_hist_m = hist_m.iloc[-1]
        last_bb_up  = bb_up.iloc[-1]
        last_bb_lo  = bb_lo.iloc[-1]
        avg_vol_20  = volume.rolling(20).mean().iloc[-1]
        last_vol    = volume.iloc[-1]

        # Recent 60-day OHLCV table (weekly)
        recent = hist.tail(60).copy()
        recent.index = recent.index.strftime("%Y-%m-%d")
        weekly = recent["Close"].resample("W").last().dropna()
        ohlcv_lines = ["  日期        收盤     RSI    MACD信號"]
        for dt_str in list(weekly.index.strftime("%Y-%m-%d"))[-12:]:
            try:
                dt     = pd.Timestamp(dt_str)
                c      = close.loc[dt_str] if dt_str in close.index else float("nan")
                r      = rsi.loc[dt_str]   if dt_str in rsi.index   else float("nan")
                m      = macd.loc[dt_str]  if dt_str in macd.index  else float("nan")
                ohlcv_lines.append(f"  {dt_str}  {c:>7.2f}  {r:>5.1f}  {m:>+7.3f}")
            except Exception:
                pass

        na = lambda v: f"{v:.2f}" if v == v else "N/A"  # NaN check

        return f"""
  ── 當前技術指標快照 ──
  收盤價:   ${last:.2f}
  MA20:     ${na(last_ma20)}   {'▲ 上方' if last > last_ma20 else '▼ 下方'}
  MA50:     ${na(last_ma50)}   {'▲ 上方' if last > last_ma50 else '▼ 下方'}
  MA200:    ${na(last_ma200)}  {'▲ 上方' if last_ma200 == last_ma200 and last > last_ma200 else '▼ 下方' if last_ma200 == last_ma200 else 'N/A'}
  RSI(14):  {na(last_rsi)}    {'超買 >70' if last_rsi > 70 else '超賣 <30' if last_rsi < 30 else '中性'}
  MACD:     {last_macd:+.3f}
  MACD信號: {last_signal:+.3f}
  MACD柱:   {last_hist_m:+.3f}  {'看多' if last_hist_m > 0 else '看空'}
  BB上軌:   ${na(last_bb_up)}
  BB下軌:   ${na(last_bb_lo)}
  成交量:   {last_vol:,.0f}  (20日均量: {avg_vol_20:,.0f})

  ── 近12週收盤走勢 ──
{chr(10).join(ohlcv_lines)}
"""
    except Exception as exc:
        return f"  (technical indicator error: {exc})"


# ═════════════════════════════════════════════════════════════════════════════
# 2.  CONTEXT BUILDERS  (one per analysis type)
# ═════════════════════════════════════════════════════════════════════════════

def _market_overview(info: dict, data: dict) -> str:
    return f"""
━━ MARKET DATA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Current Price:       {_fmt_price(data['price_now'])}
52W High:            {_fmt_price(data['price_52w_high'])}
52W Low:             {_fmt_price(data['price_52w_low'])}
Market Cap:          {_money(info.get('marketCap'))}
Enterprise Value:    {_money(info.get('enterpriseValue'))}
Beta:                {_safe(info.get('beta'))}
Short Ratio:         {_safe(info.get('shortRatio'))}
Shares Outstanding:  {_money(info.get('sharesOutstanding'), prefix='')} shares

━━ VALUATION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
P/E  (Trailing):     {_safe(info.get('trailingPE'))}
P/E  (Forward):      {_safe(info.get('forwardPE'))}
PEG  Ratio:          {_safe(info.get('pegRatio'))}
P/S  Ratio:          {_safe(info.get('priceToSalesTrailing12Months'))}
P/B  Ratio:          {_safe(info.get('priceToBook'))}
EV / EBITDA:         {_safe(info.get('enterpriseToEbitda'))}
EPS (TTM):           ${_safe(info.get('trailingEps'))}
EPS (Forward):       ${_safe(info.get('forwardEps'))}

━━ PROFITABILITY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Revenue (TTM):       {_money(info.get('totalRevenue'))}
Revenue Growth:      {_pct(info.get('revenueGrowth'))}
Gross Margin:        {_pct(info.get('grossMargins'))}
Operating Margin:    {_pct(info.get('operatingMargins'))}
Net Profit Margin:   {_pct(info.get('profitMargins'))}
ROE:                 {_pct(info.get('returnOnEquity'))}
ROA:                 {_pct(info.get('returnOnAssets'))}

━━ BALANCE SHEET SNAPSHOT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Cash:          {_money(info.get('totalCash'))}
Total Debt:          {_money(info.get('totalDebt'))}
Debt/Equity:         {_safe(info.get('debtToEquity'))}
Current Ratio:       {_safe(info.get('currentRatio'))}
Operating Cash Flow: {_money(info.get('operatingCashflow'))}
Free Cash Flow:      {_money(info.get('freeCashflow'))}
"""


def build_context(data: dict, analysis_type: str) -> str:
    """Assemble fetched data into context text appropriate for the analysis type."""
    info   = data["info"]
    ticker = data["ticker"]

    company_hdr = f"""
╔══════════════════════════════════════════════════════════════════╗
║  FINANCIAL DATA PACKAGE  —  {ticker:<6}  —  {TODAY}
╚══════════════════════════════════════════════════════════════════╝

━━ COMPANY OVERVIEW ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ticker:    {ticker}
Name:      {_safe(info.get('longName'))}
Sector:    {_safe(info.get('sector'))}
Industry:  {_safe(info.get('industry'))}
Country:   {_safe(info.get('country'))}
Employees: {_safe(info.get('fullTimeEmployees'))}
Summary:
{textwrap.fill(_safe(info.get('longBusinessSummary', ''), ''), width=78, initial_indent='  ', subsequent_indent='  ')[:500]}
""".strip()

    news_lines = [
        f"  - {item['title']}"
        for item in data.get("news", [])
        if item.get("title")
    ]
    news_block = "\n━━ RECENT NEWS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n" + (
        "\n".join(news_lines) if news_lines else "  (no news)"
    )

    # ── technical-analysis: focus on price/indicator data ─────────────────────
    if analysis_type == "technical-analysis":
        price_chart = _price_ascii_chart(data["price_series"])
        technicals  = _compute_technicals(data["hist"])
        analyst = f"""
━━ ANALYST CONSENSUS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Recommendation:  {_safe(info.get('recommendationKey'))}
Target (Mean):   {_fmt_price(info.get('targetMeanPrice'))}
Target (Low):    {_fmt_price(info.get('targetLowPrice'))}
Target (High):   {_fmt_price(info.get('targetHighPrice'))}
"""
        return "\n".join([
            company_hdr,
            f"\n━━ 12-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{price_chart}",
            technicals,
            analyst,
            news_block,
        ])

    # ── economics-analysis: macro proxy via SPY / broad market ────────────────
    if analysis_type == "economics-analysis":
        price_chart = _price_ascii_chart(data["price_series"])
        return "\n".join([
            company_hdr,
            f"\n━━ 12-MONTH PRICE HISTORY ({ticker}) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{price_chart}",
            _market_overview(info, data),
            news_block,
        ])

    # ── all other types: full fundamental context ──────────────────────────────
    inc_rows = [
        "Total Revenue", "Gross Profit", "Operating Income",
        "Net Income", "EBITDA", "Research And Development",
        "Selling General Administrative",
    ]
    bs_rows = [
        "Total Assets", "Total Liabilities Net Minority Interest",
        "Stockholders Equity", "Cash And Cash Equivalents", "Total Debt",
        "Current Assets", "Current Liabilities",
    ]
    cf_rows = [
        "Operating Cash Flow", "Capital Expenditure", "Free Cash Flow",
        "Common Stock Repurchased", "Cash Dividends Paid",
    ]
    analyst_block = f"""
━━ ANALYST CONSENSUS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Recommendation:  {_safe(info.get('recommendationKey'))}
# Analysts:      {_safe(info.get('numberOfAnalystOpinions'))}
Target (Mean):   {_fmt_price(info.get('targetMeanPrice'))}
Target (Low):    {_fmt_price(info.get('targetLowPrice'))}
Target (High):   {_fmt_price(info.get('targetHighPrice'))}
Dividend Yield:  {_pct(info.get('dividendYield'))}
Payout Ratio:    {_pct(info.get('payoutRatio'))}
"""
    price_chart = _price_ascii_chart(data["price_series"])
    return "\n".join([
        company_hdr,
        f"\n━━ 12-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{price_chart}",
        _market_overview(info, data),
        analyst_block,
        f"\n━━ INCOME STATEMENT (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['income'], inc_rows)}",
        f"\n━━ BALANCE SHEET (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['balance'], bs_rows)}",
        f"\n━━ CASH FLOW STATEMENT (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['cashflow'], cf_rows)}",
        news_block,
    ])


# ═════════════════════════════════════════════════════════════════════════════
# 3.  PROMPT TEMPLATES
# ═════════════════════════════════════════════════════════════════════════════

# ── Fundamental Analysis ──────────────────────────────────────────────────────
PROMPT_FUNDAMENTAL = """\
你是一位頂級美股投資研究分析師，深度精通基本面分析。
請根據下方提供的即時財務數據，為 **{ticker}** 撰寫一份完整的基本面深度分析報告。

═══════════════════════  嚴格要求  ═══════════════════════
1. 語言：全程使用**繁體中文**（Traditional Chinese）
2. 格式：完整 **Markdown** 格式（# ## ### 層級標題）
3. 視覺化圖表（必須大量使用）：
   - **Mermaid 圖表**：用於展示流程、關係、趨勢（graph, pie, mindmap, quadrantChart, gantt）
   - **ASCII 圖表**：折線圖、長條圖、進度條來展示數據趨勢
   - 參考範例：使用 ```mermaid 代碼塊創建圖表
4. 圖表範例：
   ```mermaid
   graph TD
       A[收入] --> B[毛利]
       B --> C[營業利益]
   ```
   ```mermaid
   pie title 收入結構
       "產品A" : 45
       "產品B" : 30
       "產品C" : 25
   ```
5. 深度：每個章節需深入分析，直接引用具體財務數字
6. 表格：重要比較數據一律用 Markdown 表格呈現，加入視覺指標 🟢🟡🔴
7. 評分：在適當地方加入 ★☆ 評星
8. Unicode 圖表：使用 ▓░█ 等字符創建視覺化進度條
═══════════════════════════════════════════════════════════

━━ 財務數據（今日即時）━━
{financial_context}
━━━━━━━━━━━━━━━━━━━━━━━━

請按以下架構輸出完整報告，每個章節都要包含豐富的視覺化圖表：

# {ticker} 基本面深度分析報告
> **報告日期**：{today} ｜ **語言**：繁體中文 ｜ **數據來源**：Yahoo Finance

## 目錄
## 1. 執行摘要
   - 使用 Mermaid graph 顯示核心評分（基本面/估值/技術面）
   - 5大投資論點表格 🟢🟡🔴
   - 快速統計卡片（Markdown表格）
## 2. 公司概覽
   - 業務結構 Mermaid graph TD 流程圖
   - 市場地位 Mermaid pie chart
   - 競爭優勢 Mermaid mindmap
## 3. 損益表深度分析
   - 收入成長 Mermaid graph LR 時間軸
   - 年度收入趨勢 Unicode 長條圖 ▓░
   - 利潤率演變 Mermaid graph 或 ASCII 折線圖
   - 詳細數據表（近4年：收入/毛利率/EBITDA/淨利/EPS）
   - 費用結構 Mermaid pie chart
## 4. 資產負債表分析
   - 資產結構 Mermaid graph TD 分解圖
   - 資產配置 Unicode 橫條圖
   - 負債與流動性比率表格
   - 股東權益趨勢 ASCII 圖
## 5. 現金流量分析
   - 現金流瀑布 Mermaid graph LR
   - 自由現金流趨勢 Unicode 進度條
   - 資本配置策略 Mermaid graph
## 6. 獲利能力指標
   - ROE/ROA/ROIC 對比表格（含行業均值）🟢🟡🔴
   - 獲利能力儀表板 Mermaid graph
## 7. 估值分析
   - 估值指標 Mermaid graph TD
   - 估值倍數對比表格（P/E P/B P/S EV/EBITDA PEG）
   - 情境目標股價（樂觀/基準/悲觀）Mermaid graph
   - 同業比較 Markdown 表格
## 8. 競爭護城河
   - Porter's Five Forces Mermaid mindmap
   - 護城河評分 Unicode 條形圖 ▓░
   - 競爭定位矩陣表格
## 9. 成長催化劑
   - 催化劑時間軸 Mermaid gantt
   - 短/中/長期機會 Mermaid graph
   - TAM 市場規模 Unicode 圖表
## 10. 風險分析
   - 風險矩陣 Mermaid quadrantChart
   - 風險評分卡表格（含機率×影響度）🔴🟡🟢
   - 緩解措施列表
## 11. 公平價值估算
   - DCF 模型 Mermaid graph LR
   - 三種估值法比較 Markdown 表格
   - 估值區間視覺化 Unicode 圖
## 12. 投資建議
   - 最終評級 Mermaid graph 或框格
   - 投資人適配度 Mermaid graph TD
   - 監控指標 checklist

> **免責聲明**：本報告為 AI 自動生成，僅供研究參考，不構成投資建議。
"""

# ── Technical Analysis ────────────────────────────────────────────────────────
PROMPT_TECHNICAL = """\
你是一位專業的技術分析師，精通圖表形態識別與技術指標解讀。
請根據下方提供的 {ticker} 技術數據，撰寫一份完整的技術分析報告。

═══════════════════════  嚴格要求  ═══════════════════════
1. 語言：全程使用**繁體中文**
2. 格式：完整 Markdown 格式
3. 視覺化圖表（必須大量使用）：
   - **Mermaid 圖表**：展示技術指標關係、趨勢判斷（graph, quadrantChart）
   - **ASCII 圖表**：繪製關鍵走勢、支撐阻力位示意圖
   - **Unicode 進度條**：顯示指標強度（▓░█）
4. 具體數字：所有支撐/阻力位、目標價需給出具體數值
5. 交易建議：需包含進場點、止損點、目標價及風險報酬比
6. 視覺指標：使用 🟢🟡🔴 表示多空訊號強度
═══════════════════════════════════════════════════════════

━━ 技術數據（今日即時）━━
{financial_context}
━━━━━━━━━━━━━━━━━━━━━━━━

請按以下架構輸出完整報告，每個章節都要包含豐富的視覺化圖表：

# {ticker} 技術分析報告
> **報告日期**：{today} ｜ **語言**：繁體中文 ｜ **數據來源**：Yahoo Finance

## 目錄
## 1. 技術面概覽
   - 技術訊號儀表板 Mermaid graph（買入/中性/賣出）
   - 核心指標速覽表（價格/均線/RSI/MACD）🟢🟡🔴
   - 技術評分卡
## 2. 趨勢分析
   - 多時框趨勢 Mermaid graph TD（月/週/日線）
   - 長期趨勢（週線/月線）Unicode 走勢圖
   - 中期趨勢（日線）
   - 短期趨勢（近期走勢）
   - 趨勢強度評估（ADX 解讀）Mermaid graph
## 3. 圖表形態分析
   - 形態識別 Mermaid graph LR（頭肩頂/底、雙頂/底、三角形等）
   - K線形態（近期重要K線組合）
   - ASCII 走勢示意圖（標注關鍵點位）
   - 形態目標價計算
## 4. 支撐與阻力
   - 關鍵價位分布 Unicode 圖
   - 阻力位（近、中、強）表格
   - 支撐位（近、中、強）表格
   - 支撐阻力位 ASCII 視覺化圖
   - 斐波那契回調位
## 5. 技術指標深度解讀
   - 指標訊號總覽 Mermaid graph TD
   - 移動平均線（MA20/50/200）排列分析 Mermaid graph
   - RSI（14）過買過賣分析 Unicode 進度條
   - MACD（12/26/9）訊號解讀 Mermaid graph
   - 布林通道分析 ASCII 圖
   - 成交量分析（量價配合度）Unicode 圖
## 6. 動能與波動率
   - 動能評估 Mermaid quadrantChart
   - ATR 波動率 Unicode 進度條
   - Beta 與市場相關性表格
## 7. 多時框架總結
   - 時框架評分 Markdown 表格（月線/週線/日線）🟢🟡🔴
   - 綜合訊號矩陣
## 8. 交易策略建議
   - 策略流程圖 Mermaid graph TD
   - 多頭策略（進場/目標/止損/風險報酬比）表格
   - 空頭策略（進場/目標/止損/風險報酬比）表格
   - 整體訊號強度 ★☆ 評星 + Mermaid graph
## 9. 風險提示與監控
   - 關鍵監控指標 checklist
   - 風險場景 Mermaid graph

> **免責聲明**：本報告為 AI 自動生成，僅供研究參考，不構成投資建議。
"""

# ── Stock Evaluation ──────────────────────────────────────────────────────────
PROMPT_STOCK_EVAL = """\
你是一位頂級美股投資評估師，請對 **{ticker}** 進行全方位綜合評估。

═══════════════════════  嚴格要求  ═══════════════════════
1. 語言：全程使用**繁體中文**
2. 格式：完整 Markdown 格式
3. 視覺化圖表（必須大量使用）：
   - **Mermaid 圖表**：雷達圖概念（graph）、決策樹（graph TD）、評分矩陣（quadrantChart）
   - **ASCII 雷達圖**：多維度評分視覺化
   - **Unicode 評分條**：各項指標強度（▓░█）
4. 綜合評分：從多個維度給出量化評分（0-10分）
5. 視覺指標：使用 🟢🟡🔴 表示評級
6. 投資論點：給出清晰、可操作的投資論據
═══════════════════════════════════════════════════════════

━━ 財務數據（今日即時）━━
{financial_context}
━━━━━━━━━━━━━━━━━━━━━━━━

請按以下架構輸出完整報告，每個章節都要包含豐富的視覺化圖表：

# {ticker} 綜合股票評估報告
> **報告日期**：{today} ｜ **語言**：繁體中文 ｜ **數據來源**：Yahoo Finance

## 目錄
## 1. 評估總覽
   - 綜合評分 Mermaid graph（六維度評分）
   - ASCII 雷達圖（多維度視覺化）
   - 買入/持有/賣出 快速結論 Mermaid pie chart
## 2. 六維度評分矩陣
   - Markdown 表格：成長性/獲利能力/財務健康/估值/競爭優勢/管理層（各0-10分）🟢🟡🔴
   - Unicode 評分條視覺化 ▓░
   - Mermaid quadrantChart（風險/報酬矩陣）
## 3. 業務品質評估
   - 商業模式 Mermaid graph TD
   - 護城河評估 Mermaid mindmap
   - 市場地位與競爭動態 Mermaid graph
   - 管理層執行力評分表格
## 4. 財務健康評估
   - 財務儀表板 Mermaid graph
   - 獲利能力趨勢表格（近3年）🟢🟡🔴
   - 資產負債表穩健度 Unicode 圖
   - 現金流生成 Mermaid graph LR
## 5. 成長性評估
   - 成長軌跡 Mermaid graph LR
   - 歷史成長率（3/5年 CAGR）表格
   - 未來成長驅動力 Mermaid graph TD
   - 市場份額趨勢 Unicode 圖
## 6. 估值合理性評估
   - 估值矩陣 Mermaid graph TD
   - 多重估值法比較表格（P/E/P/B/P/S/DCF）
   - 估值區間視覺化 Unicode 圖（低估/合理/高估）
   - 對標同業比較 Markdown 表格
## 7. 風險評估
   - 風險熱圖 Mermaid quadrantChart
   - 風險項目表格（高/中/低）🔴🟡🟢
   - 風險緩解措施
## 8. 催化劑與觸發因素
   - 催化劑時間軸 Mermaid gantt
   - 觸發因素 Mermaid graph TD
## 9. 投資建議
   - 最終評級 Mermaid graph + 框格
   - 評級 ★☆ 評星
   - 目標價區間（樂觀/基準/悲觀）Mermaid graph LR
   - 投資人適配度 Mermaid graph TD
   - 建議持倉時間與策略

> **免責聲明**：本報告為 AI 自動生成，僅供研究參考，不構成投資建議。
"""

# ── Economics Analysis ────────────────────────────────────────────────────────
PROMPT_ECONOMICS = """\
你是一位資深總體經濟分析師，請結合當前市場數據分析美國總體經濟環境。

═══════════════════════  嚴格要求  ═══════════════════════
1. 語言：全程使用**繁體中文**
2. 格式：完整 Markdown 格式
3. 數據引用：引用具體經濟指標數值與趨勢
4. 投資含義：分析對各資產類別與產業板塊的影響
5. ASCII 圖表：用於展示趨勢與周期位置
═══════════════════════════════════════════════════════════

━━ 市場參考數據（今日即時）━━
{financial_context}
━━━━━━━━━━━━━━━━━━━━━━━━

今日日期：{today}

請按以下架構輸出完整報告：

# 美國總體經濟分析報告
> **報告日期**：{today} ｜ **語言**：繁體中文 ｜ **分析標的**：{ticker}（市場代理）

## 目錄
## 1. 執行摘要（當前經濟環境快照表格 + 3大核心觀點）
## 2. 經濟周期定位（ASCII 經濟周期位置圖）
### 2.1 當前所處周期階段
### 2.2 領先/同步/落後指標綜合解讀
## 3. 核心經濟指標分析
### 3.1 GDP 成長與就業市場
### 3.2 通膨壓力（CPI/PCE/PPI 解讀）
### 3.3 聯準會政策立場（利率路徑展望）
### 3.4 消費者信心與支出
### 3.5 企業投資與庫存周期
## 4. 金融市場環境
### 4.1 股市估值水位（S&P 500 P/E 解讀）
### 4.2 債券市場（殖利率曲線形態分析）
### 4.3 美元指數與商品市場
### 4.4 信用利差與市場風險偏好
## 5. 風險因素分析（概率×影響 矩陣表格）
### 5.1 下行風險
### 5.2 上行催化劑
## 6. 產業板塊影響（表格：11大板塊 建議 + 理由）
## 7. 資產配置建議
### 7.1 股票/債券/現金/另類資產 建議比例
### 7.2 防禦型 vs 成長型 傾斜度
### 7.3 地理配置（美股 vs 國際）
## 8. 未來3-6個月展望與監控指標 checklist

> **免責聲明**：本報告為 AI 自動生成，僅供研究參考，不構成投資建議。
"""

# ── Portfolio Review ──────────────────────────────────────────────────────────
PROMPT_PORTFOLIO = """\
你是一位資深投資組合管理師，請以 **{ticker}** 作為核心持股，
結合當前市場環境，進行投資組合回顧與優化建議。

═══════════════════════  嚴格要求  ═══════════════════════
1. 語言：全程使用**繁體中文**
2. 格式：完整 Markdown 格式
3. ASCII 圖表：用於風險/報酬視覺化
4. 具體建議：給出可操作的倉位與再平衡建議
═══════════════════════════════════════════════════════════

━━ 標的數據（今日即時）━━
{financial_context}
━━━━━━━━━━━━━━━━━━━━━━━━

請按以下架構輸出完整報告：

# {ticker} 投資組合回顧報告
> **報告日期**：{today} ｜ **語言**：繁體中文 ｜ **數據來源**：Yahoo Finance

## 目錄
## 1. 執行摘要（持股表現速覽 + 核心建議 3點）
## 2. 標的表現評估
### 2.1 價格表現（與 SPY/QQQ 比較，ASCII 走勢圖）
### 2.2 風險指標（Beta/夏普比率/最大回撤估算）
### 2.3 基本面健康狀態評分
## 3. 投資論點驗證
### 3.1 原始買入論點回顧
### 3.2 當前論點是否仍成立（🟢 成立 / 🟡 部分成立 / 🔴 已失效）
### 3.3 主要變數變化分析
## 4. 倉位管理建議
### 4.1 建議倉位比例（保守/均衡/積極 投資人）
### 4.2 加碼/減碼觸發條件
### 4.3 止損/止盈設置建議
## 5. 再平衡建議
### 5.1 與同類股/ETF 替代方案比較表格
### 5.2 套利或對沖機會
## 6. 風險管理
### 6.1 集中度風險評估
### 6.2 尾部風險情境（黑天鵝影響評估）
## 7. 投資組合優化建議
### 7.1 相關性分析（{ticker} 與大盤及同業）
### 7.2 建議互補持股方向
## 8. 監控指標 checklist 與下次回顧觸發條件

> **免責聲明**：本報告為 AI 自動生成，僅供研究參考，不構成投資建議。
"""

# ── Sector Analysis ───────────────────────────────────────────────────────────
PROMPT_SECTOR = """\
你是一位美股板塊輪動策略師，請結合 **{ticker}** 代表的市場板塊，
分析當前 S&P 500 十一大板塊的輪動機會與配置建議。

═══════════════════════  嚴格要求  ═══════════════════════
1. 語言：全程使用**繁體中文**
2. 格式：完整 Markdown 格式
3. 板塊評分：所有 11 大板塊均需涵蓋
4. ASCII 圖表：用於板塊相對表現視覺化
5. 具體建議：給出超配/標配/低配的明確建議
═══════════════════════════════════════════════════════════

━━ 市場數據（今日即時）━━
{financial_context}
━━━━━━━━━━━━━━━━━━━━━━━━

請按以下架構輸出完整報告：

# 美股產業板塊分析報告
> **報告日期**：{today} ｜ **語言**：繁體中文 ｜ **參考標的**：{ticker}

## 目錄
## 1. 執行摘要（板塊輪動快照 + 3大核心觀點）
## 2. 當前市場環境（經濟周期定位 + 利率/通膨背景）
## 3. 十一大板塊綜合評分表
（表格：板塊 | 基本面 | 技術面 | 動能 | 估值 | 綜合評分 | 建議）
## 4. 重點板塊深度分析
### 4.1 超配板塊（Top 3）—— 各板塊詳細分析含 ASCII 條形圖
### 4.2 低配/避開板塊（Bottom 3）—— 各板塊風險分析
## 5. 板塊輪動訊號
### 5.1 資金流向分析
### 5.2 相對強度（RS）排名表
### 5.3 板塊輪動 ASCII 時鐘圖（4個象限）
## 6. 各板塊代表性 ETF 及個股推薦（表格）
## 7. 跨板塊風險因素
## 8. 配置建議
### 8.1 保守型投資組合板塊配比
### 8.2 積極型投資組合板塊配比
## 9. 未來1個月板塊輪動展望 + 監控指標 checklist

> **免責聲明**：本報告為 AI 自動生成，僅供研究參考，不構成投資建議。
"""

PROMPT_MAP = {
    "fundamental-analysis": PROMPT_FUNDAMENTAL,
    "technical-analysis":   PROMPT_TECHNICAL,
    "stock-eval":           PROMPT_STOCK_EVAL,
    "economics-analysis":   PROMPT_ECONOMICS,
    "portfolio-review":     PROMPT_PORTFOLIO,
    "sector-analysis":      PROMPT_SECTOR,
}


# ═════════════════════════════════════════════════════════════════════════════
# 4.  CLAUDE API
# ═════════════════════════════════════════════════════════════════════════════

def call_claude(ticker: str, context: str, analysis_type: str,
                model: str, max_tokens: int) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY environment variable is not set.")

    client   = anthropic.Anthropic(api_key=api_key)
    template = PROMPT_MAP[analysis_type]
    prompt   = template.format(
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

    text  = "\n\n".join(b.text for b in response.content if hasattr(b, "text"))
    usage = response.usage
    print(f"  ✅ response  in={usage.input_tokens}  out={usage.output_tokens}"
          f"  chars={len(text)}")
    return text


# ═════════════════════════════════════════════════════════════════════════════
# 5.  SAVE  (same-day deduplication)
# ═════════════════════════════════════════════════════════════════════════════

def save_report(ticker: str, content: str, output_dir: Path,
                analysis_type: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = ANALYSIS_TYPES[analysis_type]["filename_prefix"]
    label  = ANALYSIS_TYPES[analysis_type]["label"]
    base   = f"{prefix}_{TODAY}"

    # Same-day deduplication: base.md → base-2.md → base-3.md …
    path    = output_dir / f"{base}.md"
    counter = 2
    while path.exists():
        path    = output_dir / f"{base}-{counter}.md"
        counter += 1

    frontmatter = (
        "---\n"
        f'title: "{ticker} {label} {TODAY}"\n'
        f"date: {TODAY}\n"
        f"ticker: {ticker}\n"
        f"analysis_type: {analysis_type}\n"
        "language: zh-TW\n"
        "generated_by: Claude AI (scripts/generate_analysis.py)\n"
        "---\n\n"
    )
    path.write_text(frontmatter + content, encoding="utf-8")
    print(f"  ✅ saved → {path}")
    return path


# ═════════════════════════════════════════════════════════════════════════════
# 6.  CLI
# ═════════════════════════════════════════════════════════════════════════════

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
        help="Directory to save the report (default: claude_code/<ticker>/)",
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
    args          = parse_args()
    ticker        = args.ticker.upper()
    analysis_type = args.analysis_type
    output_dir    = args.output_dir or (Path("claude_code") / ticker.lower())

    label  = ANALYSIS_TYPES[analysis_type]["label"]
    banner = f"  {ticker}  |  {label}  |  model: {args.model}  |  out: {output_dir}"
    sep    = "=" * max(70, len(banner) + 4)
    print(f"\n{sep}\n{banner}\n{sep}\n")

    print("[1/3] Fetching financial data from Yahoo Finance …")
    data    = fetch_data(ticker)
    context = build_context(data, analysis_type)

    print("[2/3] Calling Claude API …")
    report  = call_claude(ticker, context, analysis_type, args.model, args.max_tokens)

    print("[3/3] Saving report …")
    save_report(ticker, report, output_dir, analysis_type)

    print(f"\n{sep}\n  Done!\n{sep}\n")


if __name__ == "__main__":
    main()
