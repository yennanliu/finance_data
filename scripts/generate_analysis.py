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
import os
import sys
import textwrap
import time
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
DEFAULT_TOKENS = 20000  # Increased to allow more comprehensive analysis (OpenAI gpt-4o max: 20000)

ANALYSIS_TYPES = {
    "fundamental-analysis": {
        "filename_prefix": "fundamental_analysis",
        "label":           "基本面深度分析",
        "ext":             ".md",
    },
    "technical-analysis": {
        "filename_prefix": "technical_analysis",
        "label":           "技術分析",
        "ext":             ".md",
    },
    "stock-eval": {
        "filename_prefix": "stock_eval",
        "label":           "綜合股票評估",
        "ext":             ".md",
    },
    "economics-analysis": {
        "filename_prefix": "economics_analysis",
        "label":           "總體經濟分析",
        "ext":             ".md",
    },
    "portfolio-review": {
        "filename_prefix": "portfolio_review",
        "label":           "投資組合回顧",
        "ext":             ".md",
    },
    "sector-analysis": {
        "filename_prefix": "sector_analysis",
        "label":           "產業板塊分析",
        "ext":             ".md",
    },
    "earnings-call-analysis": {
        "filename_prefix": "earnings_call_analysis",
        "label":           "財報電話會議分析",
        "ext":             ".md",
    },
    "insider-trading": {
        "filename_prefix": "insider_trading",
        "label":           "內部人交易分析",
        "ext":             ".md",
    },
    "institutional-ownership": {
        "filename_prefix": "institutional_ownership",
        "label":           "機構持股分析",
        "ext":             ".md",
    },
    "report-generator": {
        "filename_prefix": "report",
        "label":           "綜合HTML投資報告",
        "ext":             ".html",
    },
    "financial-report-analyst": {
        "filename_prefix": "financial_report_analyst",
        "label":           "財報深度解析",
        "ext":             ".md",
    },
    "stock-valuation": {
        "filename_prefix": "stock_valuation",
        "label":           "多方法估值分析",
        "ext":             ".md",
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

    # price history (2Y for richer technical context) ─────────────────────────
    try:
        hist           = t.history(period="2y")
        price_now      = float(hist["Close"].iloc[-1]) if not hist.empty else None
        price_52w      = hist.tail(252)
        price_52w_high = float(price_52w["High"].max()) if not hist.empty else None
        price_52w_low  = float(price_52w["Low"].min())  if not hist.empty else None
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

    # analyst upgrades/downgrades (last 10 actions) ───────────────────────────
    upgrades_text = "  (no data)"
    try:
        upg = t.upgrades_downgrades
        if upg is not None and not upg.empty:
            upg = upg.sort_index(ascending=False).head(10)
            lines = []
            for dt, row in upg.iterrows():
                date_str = str(dt)[:10]
                firm     = str(row.get("Firm", ""))[:20]
                action   = str(row.get("Action", ""))
                to_grade = str(row.get("ToGrade", ""))
                lines.append(f"  {date_str}  {firm:<20}  {action:<12}  → {to_grade}")
            upgrades_text = "\n".join(lines)
    except Exception:
        pass

    # insider transactions ────────────────────────────────────────────────────
    insider_text = "  (no data)"
    try:
        ins = t.insider_transactions
        if ins is not None and not ins.empty:
            ins = ins.sort_index(ascending=False).head(20)
            lines = ["  日期          姓名/職稱                  交易類型      股數         價值"]
            for dt, row in ins.iterrows():
                date_str  = str(dt)[:10]
                name      = str(row.get("Insider", row.get("Name", "")))[:24]
                tx_type   = str(row.get("Transaction", ""))[:16]
                shares    = row.get("Shares", 0)
                value     = row.get("Value", 0)
                try:
                    flag = "🟢" if "Purchase" in tx_type or "Buy" in tx_type else "🔴" if "Sale" in tx_type or "Sell" in tx_type else "⬜"
                except Exception:
                    flag = "⬜"
                lines.append(
                    f"  {date_str}  {name:<24}  {tx_type:<16}  {shares:>10,.0f}  {_money(value)}  {flag}"
                )
            insider_text = "\n".join(lines)
    except Exception:
        pass

    # major holders / institutional holders ───────────────────────────────────
    major_holders_text = "  (no data)"
    try:
        mh = t.major_holders
        if mh is not None and not mh.empty:
            lines = []
            for _, row in mh.iterrows():
                val = row.iloc[0] if len(row) > 0 else ""
                lbl = row.iloc[1] if len(row) > 1 else ""
                lines.append(f"  {str(val):<12}  {str(lbl)}")
            major_holders_text = "\n".join(lines)
    except Exception:
        pass

    institutional_text = "  (no data)"
    try:
        ih = t.institutional_holders
        if ih is not None and not ih.empty:
            ih = ih.head(20)
            lines = ["  持股機構                          股數            持股%        價值          變化%"]
            for _, row in ih.iterrows():
                holder  = str(row.get("Holder", ""))[:32]
                shares  = row.get("Shares", 0)
                pct_out = row.get("% Out",  float("nan"))
                value   = row.get("Value",  0)
                chg     = row.get("% Change", float("nan"))
                try:
                    chg_str = f"{float(chg):+.2f}%"
                    arrow   = "🟢" if float(chg) > 0 else "🔴" if float(chg) < 0 else "⬜"
                except Exception:
                    chg_str, arrow = "N/A", "⬜"
                lines.append(
                    f"  {holder:<32}  {shares:>14,.0f}  {pct_out:.2%}  {_money(value)}  {chg_str} {arrow}"
                )
            institutional_text = "\n".join(lines)
    except Exception:
        pass

    mutualfund_text = "  (no data)"
    try:
        mf = t.mutualfund_holders
        if mf is not None and not mf.empty:
            mf = mf.head(10)
            lines = ["  基金名稱                              股數            持股%        價值"]
            for _, row in mf.iterrows():
                holder = str(row.get("Holder", ""))[:36]
                shares = row.get("Shares", 0)
                pct    = row.get("% Out",  float("nan"))
                value  = row.get("Value",  0)
                lines.append(f"  {holder:<36}  {shares:>14,.0f}  {pct:.2%}  {_money(value)}")
            mutualfund_text = "\n".join(lines)
    except Exception:
        pass

    # earnings history (beats/misses) ─────────────────────────────────────────
    earnings_text = "  (no data)"
    try:
        eh = t.earnings_history
        if eh is not None and not eh.empty:
            eh = eh.sort_index(ascending=False).head(8)
            lines = ["  Quarter      EPS Est  EPS Act  Surprise%"]
            for dt, row in eh.iterrows():
                q     = str(dt)[:10]
                est   = row.get("epsestimate", float("nan"))
                act   = row.get("epsactual",   float("nan"))
                surp  = row.get("epsdifference", float("nan"))
                surp_pct = row.get("surprisepercent", float("nan"))
                try:
                    flag = "✅" if float(surp) >= 0 else "❌"
                except Exception:
                    flag = "  "
                lines.append(
                    f"  {q}  {est:>8.2f}  {act:>8.2f}  "
                    f"{surp_pct:>+7.1f}%  {flag}"
                )
            earnings_text = "\n".join(lines)
    except Exception:
        pass

    return {
        "ticker":               ticker,
        "info":                 info,
        "hist":                 hist,
        "income":               _safe_df(lambda: t.financials),
        "income_q":             _safe_df(lambda: t.quarterly_financials),
        "balance":              _safe_df(lambda: t.balance_sheet),
        "balance_q":            _safe_df(lambda: t.quarterly_balance_sheet),
        "cashflow":             _safe_df(lambda: t.cashflow),
        "cashflow_q":           _safe_df(lambda: t.quarterly_cashflow),
        "news":                 (t.news or [])[:10],
        "price_now":            price_now,
        "price_52w_high":       price_52w_high,
        "price_52w_low":        price_52w_low,
        "price_series":         price_series,
        "upgrades_text":        upgrades_text,
        "earnings_text":        earnings_text,
        "insider_text":         insider_text,
        "major_holders_text":   major_holders_text,
        "institutional_text":   institutional_text,
        "mutualfund_text":      mutualfund_text,
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
    """Compute technical indicators from OHLCV history DataFrame."""
    if hist is None or hist.empty:
        return "  (no OHLC data)"
    try:
        import pandas as pd
        import numpy as np

        close  = hist["Close"]
        high   = hist["High"]
        low    = hist["Low"]
        volume = hist["Volume"]

        # ── Moving averages ───────────────────────────────────────────────────
        ma20  = close.rolling(20).mean()
        ma50  = close.rolling(50).mean()
        ma200 = close.rolling(200).mean()

        # ── RSI-14 ────────────────────────────────────────────────────────────
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss.replace(0, float("nan"))
        rsi   = 100 - (100 / (1 + rs))

        # ── MACD (12/26/9) ────────────────────────────────────────────────────
        ema12  = close.ewm(span=12, adjust=False).mean()
        ema26  = close.ewm(span=26, adjust=False).mean()
        macd   = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        hist_m = macd - signal

        # ── Bollinger Bands (20, 2σ) ──────────────────────────────────────────
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_up  = bb_mid + 2 * bb_std
        bb_lo  = bb_mid - 2 * bb_std
        bb_pct = (close - bb_lo) / (bb_up - bb_lo).replace(0, float("nan"))

        # ── ATR-14 ────────────────────────────────────────────────────────────
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low  - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean()

        # ── Stochastic %K/%D (14,3,3) ─────────────────────────────────────────
        low14  = low.rolling(14).min()
        high14 = high.rolling(14).max()
        stoch_k = 100 * (close - low14) / (high14 - low14).replace(0, float("nan"))
        stoch_d = stoch_k.rolling(3).mean()

        # ── ADX-14 (trend strength) ───────────────────────────────────────────
        up_move   = high.diff()
        down_move = -low.diff()
        plus_dm   = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
        minus_dm  = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
        atr14_adx = tr.ewm(alpha=1/14, adjust=False).mean()
        plus_di   = 100 * plus_dm.ewm(alpha=1/14, adjust=False).mean() / atr14_adx.replace(0, float("nan"))
        minus_di  = 100 * minus_dm.ewm(alpha=1/14, adjust=False).mean() / atr14_adx.replace(0, float("nan"))
        dx        = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float("nan"))
        adx       = dx.ewm(alpha=1/14, adjust=False).mean()

        # ── OBV (On-Balance Volume) ───────────────────────────────────────────
        obv_direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
        obv = (volume * obv_direction).cumsum()
        obv_ma20 = obv.rolling(20).mean()

        # ── Volume ────────────────────────────────────────────────────────────
        avg_vol_20 = volume.rolling(20).mean()
        avg_vol_50 = volume.rolling(50).mean()

        # ── Last values ───────────────────────────────────────────────────────
        last         = close.iloc[-1]
        last_ma20    = ma20.iloc[-1]
        last_ma50    = ma50.iloc[-1]
        last_ma200   = ma200.iloc[-1] if len(close) >= 200 else float("nan")
        last_rsi     = rsi.iloc[-1]
        last_macd    = macd.iloc[-1]
        last_signal  = signal.iloc[-1]
        last_hist_m  = hist_m.iloc[-1]
        last_bb_up   = bb_up.iloc[-1]
        last_bb_lo   = bb_lo.iloc[-1]
        last_bb_pct  = bb_pct.iloc[-1]
        last_atr     = atr14.iloc[-1]
        last_stoch_k = stoch_k.iloc[-1]
        last_stoch_d = stoch_d.iloc[-1]
        last_adx     = adx.iloc[-1]
        last_plus_di = plus_di.iloc[-1]
        last_minus_di= minus_di.iloc[-1]
        last_obv     = obv.iloc[-1]
        last_obv_ma  = obv_ma20.iloc[-1]
        last_vol     = volume.iloc[-1]
        last_avg_vol = avg_vol_20.iloc[-1]
        last_avg_vol50 = avg_vol_50.iloc[-1]

        # ── 52-week position ──────────────────────────────────────────────────
        w52_high = float(high.tail(252).max())
        w52_low  = float(low.tail(252).min())
        w52_pct  = (last - w52_low) / (w52_high - w52_low) * 100 if w52_high != w52_low else 50

        # ── RSI divergence hint (last 20 bars) ────────────────────────────────
        price_20  = close.tail(20)
        rsi_20    = rsi.tail(20)
        price_dir = "⬆" if price_20.iloc[-1] > price_20.iloc[0] else "⬇"
        rsi_dir   = "⬆" if rsi_20.iloc[-1]   > rsi_20.iloc[0]   else "⬇"
        divergence = ""
        if price_dir == "⬆" and rsi_dir == "⬇":
            divergence = "⚠️ 頂背離 (Bearish Divergence)"
        elif price_dir == "⬇" and rsi_dir == "⬆":
            divergence = "⚠️ 底背離 (Bullish Divergence)"
        else:
            divergence = "無明顯背離"

        # ── Weekly OHLCV table (last 20 weeks) ───────────────────────────────
        weekly_close  = close.resample("W").last().dropna().tail(20)
        weekly_volume = volume.resample("W").sum().dropna().tail(20)
        ohlcv_lines   = ["  日期          收盤      RSI     MACD柱    週成交量"]
        for wdt in weekly_close.index:
            wdt_str = wdt.strftime("%Y-%m-%d")
            wc  = weekly_close.get(wdt, float("nan"))
            # nearest rsi/macd for this week
            try:
                idx_slice = rsi[rsi.index <= wdt]
                wr = float(idx_slice.iloc[-1]) if not idx_slice.empty else float("nan")
            except Exception:
                wr = float("nan")
            try:
                idx_slice = hist_m[hist_m.index <= wdt]
                wm = float(idx_slice.iloc[-1]) if not idx_slice.empty else float("nan")
            except Exception:
                wm = float("nan")
            wv = weekly_volume.get(wdt, float("nan"))
            try:
                ohlcv_lines.append(
                    f"  {wdt_str}  {wc:>8.2f}  {wr:>6.1f}  {wm:>+8.3f}  {wv:>12,.0f}"
                )
            except Exception:
                pass

        na = lambda v: f"{v:.2f}" if v == v else "N/A"
        na3 = lambda v: f"{v:.3f}" if v == v else "N/A"

        vol_ratio = last_vol / last_avg_vol if last_avg_vol > 0 else float("nan")
        obv_trend = "OBV > MA → 量能支撐上漲" if last_obv > last_obv_ma else "OBV < MA → 量能疲弱"

        atr_pct = last_atr / last * 100 if last > 0 else float("nan")

        return f"""
  ── 當前技術指標快照 ──
  收盤價:       ${last:.2f}
  52W 高/低:    ${w52_high:.2f} / ${w52_low:.2f}  (目前位於52W區間 {w52_pct:.1f}%)
  ATR(14):      ${na(last_atr)}  ({na(atr_pct)}% of price) — 每日波動參考

  ── 均線系統 ──
  MA20:         ${na(last_ma20)}   {'▲ 上方' if last > last_ma20 else '▼ 下方'}
  MA50:         ${na(last_ma50)}   {'▲ 上方' if last > last_ma50 else '▼ 下方'}
  MA200:        ${na(last_ma200)}  {'▲ 上方' if last_ma200 == last_ma200 and last > last_ma200 else '▼ 下方' if last_ma200 == last_ma200 else 'N/A'}
  均線排列:     {'多頭排列 MA20>MA50>MA200' if last_ma20 == last_ma20 and last_ma50 == last_ma50 and last_ma200 == last_ma200 and last_ma20 > last_ma50 > last_ma200 else '空頭排列 MA20<MA50<MA200' if last_ma20 == last_ma20 and last_ma50 == last_ma50 and last_ma200 == last_ma200 and last_ma20 < last_ma50 < last_ma200 else '混合排列'}

  ── 動能指標 ──
  RSI(14):      {na(last_rsi)}    {'🔴 超買 >70' if last_rsi > 70 else '🟢 超賣 <30' if last_rsi < 30 else '🟡 中性 30-70'}
  RSI 背離:     {divergence}
  MACD:         {na3(last_macd)}
  MACD Signal:  {na3(last_signal)}
  MACD Hist:    {last_hist_m:+.3f}  {'🟢 看多' if last_hist_m > 0 else '🔴 看空'}
  Stoch %K:     {na(last_stoch_k)}  Stoch %D: {na(last_stoch_d)}  {'超買' if last_stoch_k > 80 else '超賣' if last_stoch_k < 20 else '中性'}

  ── 趨勢強度 (ADX) ──
  ADX(14):      {na(last_adx)}  {'強趨勢 >25' if last_adx > 25 else '弱趨勢/盤整 <25'}
  +DI:          {na(last_plus_di)}  -DI: {na(last_minus_di)}  {'多頭主導' if last_plus_di > last_minus_di else '空頭主導'}

  ── 布林通道 ──
  BB上軌:       ${na(last_bb_up)}
  BB中軌(MA20): ${na(last_ma20)}
  BB下軌:       ${na(last_bb_lo)}
  BB %B:        {na(last_bb_pct)}  (0=下軌, 0.5=中軌, 1=上軌)

  ── 成交量 ──
  最新成交量:   {last_vol:,.0f}
  20日均量:     {last_avg_vol:,.0f}  (量比: {na(vol_ratio)}x)
  50日均量:     {last_avg_vol50:,.0f}
  OBV趨勢:      {obv_trend}

  ── 近20週收盤走勢 ──
{chr(10).join(ohlcv_lines)}
"""
    except Exception as exc:
        return f"  (technical indicator error: {exc})"


# ═════════════════════════════════════════════════════════════════════════════
# 2.  CONTEXT BUILDERS  (one per analysis type)
# ═════════════════════════════════════════════════════════════════════════════

def _market_overview(info: dict, data: dict) -> str:
    # FCF yield
    fcf = info.get('freeCashflow')
    mkt = info.get('marketCap')
    try:
        fcf_yield = f"{float(fcf)/float(mkt)*100:.2f}%" if fcf and mkt else "N/A"
    except Exception:
        fcf_yield = "N/A"

    return f"""
━━ MARKET DATA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Current Price:          {_fmt_price(data['price_now'])}
52W High:               {_fmt_price(data['price_52w_high'])}
52W Low:                {_fmt_price(data['price_52w_low'])}
Market Cap:             {_money(info.get('marketCap'))}
Enterprise Value:       {_money(info.get('enterpriseValue'))}
Beta:                   {_safe(info.get('beta'))}
Short Ratio:            {_safe(info.get('shortRatio'))}
Short % Float:          {_pct(info.get('shortPercentOfFloat'))}
Shares Outstanding:     {_money(info.get('sharesOutstanding'), prefix='')} shares
Float Shares:           {_money(info.get('floatShares'), prefix='')} shares
Insider Own %:          {_pct(info.get('heldPercentInsiders'))}
Institution Own %:      {_pct(info.get('heldPercentInstitutions'))}

━━ VALUATION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
P/E  (Trailing):        {_safe(info.get('trailingPE'))}
P/E  (Forward):         {_safe(info.get('forwardPE'))}
PEG  Ratio:             {_safe(info.get('pegRatio'))}
P/S  Ratio:             {_safe(info.get('priceToSalesTrailing12Months'))}
P/B  Ratio:             {_safe(info.get('priceToBook'))}
EV / EBITDA:            {_safe(info.get('enterpriseToEbitda'))}
EV / Revenue:           {_safe(info.get('enterpriseToRevenue'))}
EPS (TTM):              ${_safe(info.get('trailingEps'))}
EPS (Forward):          ${_safe(info.get('forwardEps'))}
FCF Yield:              {fcf_yield}

━━ PROFITABILITY & GROWTH ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Revenue (TTM):          {_money(info.get('totalRevenue'))}
Revenue Growth (YoY):   {_pct(info.get('revenueGrowth'))}
Earnings Growth (YoY):  {_pct(info.get('earningsGrowth'))}
Earnings Growth (QoQ):  {_pct(info.get('earningsQuarterlyGrowth'))}
Gross Margin:           {_pct(info.get('grossMargins'))}
Operating Margin:       {_pct(info.get('operatingMargins'))}
EBITDA Margin:          {_pct(info.get('ebitdaMargins'))}
Net Profit Margin:      {_pct(info.get('profitMargins'))}
ROE:                    {_pct(info.get('returnOnEquity'))}
ROA:                    {_pct(info.get('returnOnAssets'))}

━━ BALANCE SHEET SNAPSHOT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Cash:             {_money(info.get('totalCash'))}
Total Debt:             {_money(info.get('totalDebt'))}
Net Cash / Debt:        {_money((info.get('totalCash') or 0) - (info.get('totalDebt') or 0))}
Debt/Equity:            {_safe(info.get('debtToEquity'))}
Current Ratio:          {_safe(info.get('currentRatio'))}
Quick Ratio:            {_safe(info.get('quickRatio'))}
Operating Cash Flow:    {_money(info.get('operatingCashflow'))}
Free Cash Flow:         {_money(info.get('freeCashflow'))}
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

    earnings_block       = f"\n━━ EARNINGS HISTORY (EPS Beats/Misses) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('earnings_text', '  (no data)')}"
    upgrades_block       = f"\n━━ ANALYST UPGRADES / DOWNGRADES (Recent) ━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('upgrades_text', '  (no data)')}"
    insider_block        = f"\n━━ INSIDER TRANSACTIONS (Recent 20) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('insider_text', '  (no data)')}"
    major_holders_block  = f"\n━━ MAJOR HOLDERS BREAKDOWN ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('major_holders_text', '  (no data)')}"
    institutional_block  = f"\n━━ TOP INSTITUTIONAL HOLDERS (Top 20) ━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('institutional_text', '  (no data)')}"
    mutualfund_block     = f"\n━━ TOP MUTUAL FUND HOLDERS (Top 10) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('mutualfund_text', '  (no data)')}"

    # ── insider-trading ───────────────────────────────────────────────────────
    if analysis_type == "insider-trading":
        price_chart = _price_ascii_chart(data["price_series"])
        return "\n".join([
            company_hdr,
            f"\n━━ 24-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{price_chart}",
            _market_overview(info, data),
            major_holders_block,
            insider_block,
            upgrades_block,
            news_block,
        ])

    # ── institutional-ownership ────────────────────────────────────────────────
    if analysis_type == "institutional-ownership":
        price_chart = _price_ascii_chart(data["price_series"])
        return "\n".join([
            company_hdr,
            f"\n━━ 24-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{price_chart}",
            _market_overview(info, data),
            major_holders_block,
            institutional_block,
            mutualfund_block,
            insider_block,
            upgrades_block,
            news_block,
        ])

    # ── earnings-call-analysis ────────────────────────────────────────────────
    if analysis_type == "earnings-call-analysis":
        price_chart = _price_ascii_chart(data["price_series"])
        inc_q_rows  = ["Total Revenue", "Gross Profit", "Operating Income", "Net Income"]
        return "\n".join([
            company_hdr,
            f"\n━━ 24-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{price_chart}",
            _market_overview(info, data),
            f"\n━━ QUARTERLY INCOME (last 4Q) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['income_q'], inc_q_rows)}",
            earnings_block,
            upgrades_block,
            news_block,
        ])

    # ── report-generator: full context (all data) ─────────────────────────────
    if analysis_type == "report-generator":
        price_chart = _price_ascii_chart(data["price_series"])
        technicals  = _compute_technicals(data["hist"])
        inc_rows = [
            "Total Revenue", "Gross Profit", "Operating Income",
            "Net Income", "EBITDA", "Research And Development",
        ]
        inc_q_rows = ["Total Revenue", "Gross Profit", "Operating Income", "Net Income"]
        bs_rows    = [
            "Total Assets", "Total Liabilities Net Minority Interest",
            "Stockholders Equity", "Cash And Cash Equivalents", "Total Debt",
            "Current Assets", "Current Liabilities",
        ]
        cf_rows    = [
            "Operating Cash Flow", "Capital Expenditure", "Free Cash Flow",
            "Common Stock Repurchased", "Cash Dividends Paid",
        ]
        return "\n".join([
            company_hdr,
            f"\n━━ 24-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{price_chart}",
            _market_overview(info, data),
            technicals,
            f"\n━━ INCOME STATEMENT (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['income'], inc_rows)}",
            f"\n━━ INCOME STATEMENT (Quarterly) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['income_q'], inc_q_rows)}",
            f"\n━━ BALANCE SHEET (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['balance'], bs_rows)}",
            f"\n━━ CASH FLOW STATEMENT (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['cashflow'], cf_rows)}",
            major_holders_block,
            institutional_block,
            insider_block,
            earnings_block,
            upgrades_block,
            news_block,
        ])

    # ── technical-analysis: focus on price/indicator data ─────────────────────
    if analysis_type == "technical-analysis":
        price_chart = _price_ascii_chart(data["price_series"])
        technicals  = _compute_technicals(data["hist"])
        analyst = f"""
━━ ANALYST CONSENSUS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Recommendation:  {_safe(info.get('recommendationKey'))}
# Analysts:      {_safe(info.get('numberOfAnalystOpinions'))}
Target (Mean):   {_fmt_price(info.get('targetMeanPrice'))}
Target (Low):    {_fmt_price(info.get('targetLowPrice'))}
Target (High):   {_fmt_price(info.get('targetHighPrice'))}
"""
        return "\n".join([
            company_hdr,
            f"\n━━ 24-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{price_chart}",
            technicals,
            analyst,
            upgrades_block,
            news_block,
        ])

    # ── economics-analysis: macro proxy via SPY / broad market ────────────────
    if analysis_type == "economics-analysis":
        price_chart = _price_ascii_chart(data["price_series"])
        return "\n".join([
            company_hdr,
            f"\n━━ 24-MONTH PRICE HISTORY ({ticker}) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{price_chart}",
            _market_overview(info, data),
            upgrades_block,
            news_block,
        ])

    # ── financial-report-analyst: comprehensive statements + insider ──────────
    if analysis_type == "financial-report-analyst":
        price_chart = _price_ascii_chart(data["price_series"])
        inc_rows = [
            "Total Revenue", "Gross Profit", "Operating Income",
            "Net Income", "EBITDA", "Research And Development",
            "Selling General Administrative",
        ]
        inc_q_rows = ["Total Revenue", "Gross Profit", "Operating Income", "Net Income"]
        bs_rows = [
            "Total Assets", "Total Liabilities Net Minority Interest",
            "Stockholders Equity", "Cash And Cash Equivalents", "Total Debt",
            "Current Assets", "Current Liabilities",
            "Accounts Receivable", "Inventory", "Accounts Payable",
        ]
        cf_rows = [
            "Operating Cash Flow", "Capital Expenditure", "Free Cash Flow",
            "Common Stock Repurchased", "Cash Dividends Paid",
            "Stock Based Compensation",
        ]
        return "\n".join([
            company_hdr,
            f"\n━━ 24-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{price_chart}",
            _market_overview(info, data),
            f"\n━━ INCOME STATEMENT (Annual, last 4Y) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['income'], inc_rows)}",
            f"\n━━ INCOME STATEMENT (Quarterly, last 4Q) ━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['income_q'], inc_q_rows)}",
            f"\n━━ BALANCE SHEET (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['balance'], bs_rows)}",
            f"\n━━ BALANCE SHEET (Quarterly) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['balance_q'], bs_rows)}",
            f"\n━━ CASH FLOW STATEMENT (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['cashflow'], cf_rows)}",
            f"\n━━ CASH FLOW STATEMENT (Quarterly) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['cashflow_q'], cf_rows)}",
            insider_block,
            earnings_block,
            upgrades_block,
            news_block,
        ])

    # ── stock-valuation: full valuation + financials + analyst consensus ───────
    if analysis_type == "stock-valuation":
        price_chart = _price_ascii_chart(data["price_series"])
        inc_rows = [
            "Total Revenue", "Gross Profit", "Operating Income",
            "Net Income", "EBITDA", "Research And Development",
        ]
        inc_q_rows = ["Total Revenue", "Gross Profit", "Operating Income", "Net Income"]
        bs_rows = [
            "Total Assets", "Total Liabilities Net Minority Interest",
            "Stockholders Equity", "Total Debt", "Cash And Cash Equivalents",
        ]
        cf_rows = [
            "Operating Cash Flow", "Capital Expenditure", "Free Cash Flow",
            "Common Stock Repurchased",
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
        return "\n".join([
            company_hdr,
            f"\n━━ 24-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{price_chart}",
            _market_overview(info, data),
            analyst_block,
            f"\n━━ INCOME STATEMENT (Annual, last 4Y) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['income'], inc_rows)}",
            f"\n━━ INCOME STATEMENT (Quarterly, last 4Q) ━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['income_q'], inc_q_rows)}",
            f"\n━━ BALANCE SHEET (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['balance'], bs_rows)}",
            f"\n━━ CASH FLOW STATEMENT (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['cashflow'], cf_rows)}",
            earnings_block,
            upgrades_block,
            insider_block,
            news_block,
        ])

    # ── all other types: full fundamental context ──────────────────────────────
    inc_rows = [
        "Total Revenue", "Gross Profit", "Operating Income",
        "Net Income", "EBITDA", "Research And Development",
        "Selling General Administrative",
    ]
    inc_q_rows = [
        "Total Revenue", "Gross Profit", "Operating Income", "Net Income",
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
5Y Avg Dividend: {_pct(info.get('fiveYearAvgDividendYield'))}
"""
    price_chart = _price_ascii_chart(data["price_series"])
    return "\n".join([
        company_hdr,
        f"\n━━ 24-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{price_chart}",
        _market_overview(info, data),
        analyst_block,
        f"\n━━ INCOME STATEMENT (Annual, last 4Y) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['income'], inc_rows)}",
        f"\n━━ INCOME STATEMENT (Quarterly, last 4Q) ━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['income_q'], inc_q_rows)}",
        f"\n━━ BALANCE SHEET (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['balance'], bs_rows)}",
        f"\n━━ CASH FLOW STATEMENT (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{_df_to_text(data['cashflow'], cf_rows)}",
        earnings_block,
        upgrades_block,
        news_block,
    ])


# ═════════════════════════════════════════════════════════════════════════════
# 3.  PROMPT TEMPLATES
# ═════════════════════════════════════════════════════════════════════════════

# ── Fundamental Analysis ──────────────────────────────────────────────────────
PROMPT_FUNDAMENTAL = """\
你是一位頂級美股投資研究分析師，擁有 CFA 資格，深度精通基本面分析、估值建模與產業研究。
請根據下方提供的即時財務數據，為 **{ticker}** 撰寫一份機構級基本面深度分析報告。

═══════════════════════  嚴格要求  ═══════════════════════
1. 語言：全程使用**繁體中文**（Traditional Chinese）
2. 格式：完整 **Markdown** 格式（# ## ### 層級標題）
3. 視覺化圖表（必須大量使用）：
   - **Mermaid 圖表**：流程/關係/趨勢（graph, pie, mindmap, gantt）
   - **ASCII 方框圖表**：使用 ╔═╗╚═╝║ 字符創建專業方框
   - **Unicode 進度條**：使用 ▓░█ 等字符創建視覺化進度條
4. 深度要求：
   - 每個章節必須引用具體財務數字，不得只講概念
   - 季度對季度（QoQ）與年度對年度（YoY）成長率必須計算並標註
   - 利潤率趨勢必須分析，解釋改善或惡化的原因
   - 同業比較：必須點名 2-3 家直接競爭對手的估值倍數進行對比
   - ROIC vs WACC：必須分析公司是否在創造還是摧毀股東價值
5. 表格：重要比較數據一律用 Markdown 表格呈現，加入視覺指標 🟢🟡🔴
6. 評分：各維度給出 1-10 分並附理由
7. EPS 趨勢：分析過去 4 季盈餘表現（超預期/不及預期）及原因
8. **報告長度**：必須達到 15000-20000 字，充分展開每個章節的分析
═══════════════════════════════════════════════════════════

━━ 財務數據（今日即時）━━
{financial_context}
━━━━━━━━━━━━━━━━━━━━━━━━

請按以下架構輸出完整報告。每個章節都必須包含豐富的視覺化圖表與具體數字分析：

---

# {ticker} 基本面深度分析報告
> **報告日期**：{today} ｜ **語言**：繁體中文 ｜ **數據來源**：Yahoo Finance ｜ **分析師**：CFA 級機構研究

---

## 目錄

必須使用表格格式呈現目錄，包含章節編號、章節名稱、核心結論：

| # | 章節 | 核心結論 |
|---|------|----------|
| 1 | 執行摘要 | 評級 + 目標價區間 |
| 2 | 公司概覽與商業模式 | 護城河評估 |
| ... | ... | ... |

---

## 1. 執行摘要

### 1.1 核心評分儀表板

使用 Mermaid graph 呈現五大維度評分（基本面/成長/獲利/財務健康/估值），格式範例：

```mermaid
graph TD
    TICKER["🎯 TICKER 綜合評分<br/>總分：X.X/10"]

    F["📊 基本面<br/>X/10<br/>核心原因"]
    G["🚀 成長性<br/>X/10<br/>核心原因"]
    P["💰 獲利能力<br/>X/10<br/>核心原因"]
    B["🏦 財務健康<br/>X/10<br/>核心原因"]
    V["📈 估值<br/>X/10<br/>核心原因"]

    TICKER --> F
    TICKER --> G
    TICKER --> P
    TICKER --> B
    TICKER --> V

    F --> F1["✅ 具體數據點1<br/>✅ 具體數據點2"]
    ...
```

### 1.2 評分進度條視覺化

使用 ASCII 方框圖呈現各維度評分，格式範例：

```
╔══════════════════════════════════════════════════════════════╗
║              TICKER 多維度評分儀表板 (1-10分)                ║
╠══════════════════════════════════════════════════════════════╣
║ 基本面強度  X.X ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░  ★★★★★           ║
║ 成長動能    X.X ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░  ★★★★★           ║
║ 獲利品質    X.X ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░  ★★★★★           ║
║ 財務健康    X.X ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░  ★★★★★           ║
║ 估值合理性  X.X ▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░  ★★★★☆           ║
║ 護城河深度  X.X ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░  ★★★★★           ║
║ 管理層執行  X.X ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░  ★★★★★           ║
║ 技術創新力  X.X ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░  ★★★★★           ║
╠══════════════════════════════════════════════════════════════╣
║ 綜合總分    X.X ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░  🏆 評語              ║
╚══════════════════════════════════════════════════════════════╝
```

### 1.3 五大投資論點 + 三大核心風險

使用詳細表格呈現，格式：

| 類型 | 項目 | 具體依據 | 信心度 |
|------|------|----------|--------|
| 🟢 **投資論點①** | **論點標題** | 具體數據支撐（引用財務數字） | 🟢 極高/高 |
| 🟢 **投資論點②** | **論點標題** | 具體數據支撐 | 🟢 極高/高 |
| ... | ... | ... | ... |
| 🟡 **風險①** | **風險標題** | 具體描述與潛在影響 | 🟡 中度 |
| 🔴 **風險②** | **風險標題** | 具體描述與潛在影響 | 🔴 高衝擊 |

### 1.4 快速統計卡片

| 指標 | 公司實際值 | 行業均值 | S&P 500 均值 | 狀態 |
|------|-------------|----------|--------------|------|
| 收入 YoY 成長 | **XX%** | ~X% | ~X% | 🟢/🟡/🔴 |
| 毛利率 | **XX%** | ~X% | ~X% | 🟢/🟡/🔴 |
| 淨利率 | **XX%** | ~X% | ~X% | 🟢/🟡/🔴 |
| ROE | **XX%** | ~X% | ~X% | 🟢/🟡/🔴 |
| Forward P/E | **XXx** | ~Xx | ~Xx | 🟢/🟡/🔴 |
| ... | ... | ... | ... | ... |

### 1.5 投資結論

使用 ASCII 方框呈現，格式：

```
╔══════════════════════════════════════════════════════════════════╗
║                    📊 投資結論摘要                               ║
╠══════════════════════════════════════════════════════════════════╣
║  評級：🟢 強烈買入/買入/持有/觀望/賣出                          ║
║  當前股價：$XXX.XX                                               ║
║  目標價區間：                                                    ║
║    悲觀情境：$XXX（+X%）                                         ║
║    基準情境：$XXX（+X%）  ← 12個月主要目標                      ║
║    樂觀情境：$XXX（+X%）                                         ║
║  投資評分：X.X/10                                                ║
║  適合投資人：成長型、長線持有者等                                ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## 2. 公司概覽與商業模式

### 2.1 業務結構與收入來源

使用 Mermaid graph TD 呈現業務結構，必須包含：
- 公司總覽節點（市值、年營收）
- 主要業務板塊（佔比百分比、金額）
- 子業務細分
- 軟體/服務收入（如適用）

### 2.2 市場份額

使用 Mermaid pie chart 呈現市場份額，格式：

```mermaid
pie title 市場份額估算（年份）
    "公司名稱（GPU）" : XX
    "競爭對手1" : XX
    "競爭對手2" : XX
    ...
```

### 2.3 競爭護城河分析

使用 Mermaid mindmap 呈現護城河，必須包含 6 大類別：
- 技術領先
- 軟體生態系統
- 網路效應
- 客戶鎖定
- 規模效應
- 生態夥伴

### 2.4 護城河強度評分

使用 ASCII 方框圖呈現，格式：

```
╔══════════════════════════════════════════════════════════════╗
║                  公司名稱 護城河強度評分                      ║
╠══════════════════════════════════════════════════════════════╣
║ 護城河項目1    XX/10  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  🏆 評語        ║
║ 護城河項目2    X/10   ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░  🟢 評語        ║
...
╠══════════════════════════════════════════════════════════════╣
║ 綜合護城河     X.X    ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░  🏆 總結評語     ║
╚══════════════════════════════════════════════════════════════╝
```

---

## 3. 損益表深度分析

### 3.1 年度收入成長趨勢（近4年）

使用 ASCII 方框圖呈現收入趨勢，格式：

```
╔══════════════════════════════════════════════════════════════════╗
║              公司名稱 年度收入趨勢（FY20XX-FY20XX）              ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  FY20XX  $XX.XXB  ██████░░░░░░░░░░░░░░░░░░░  YoY: +X.X%  🟢    ║
║  FY20XX  $XX.XXB  ██████████████░░░░░░░░░░░  YoY:+XXX.X% 🟢    ║
...
║                   |      |      |      |      |                  ║
║                   0     XXB   XXB   XXB   XXB                    ║
║                                                                  ║
║  📊 X年累計 CAGR：+XX.X%                                        ║
╚══════════════════════════════════════════════════════════════════╝
```

### 3.2 季度收入趨勢分析

使用詳細表格呈現最近 4 季的 QoQ 和 YoY 成長率，必須包含備註說明。

### 3.3 利潤率演變分析

表格格式：

| 利潤率指標 | FY20XX | FY20XX | FY20XX | FY20XX | 趨勢 | 評估 |
|------------|--------|--------|--------|--------|------|------|
| **毛利率** | XX% | XX% | XX% | XX% | ↗️/↘️ 趨勢說明 | 🟢/🟡/🔴 |
| **營業利益率** | XX% | XX% | XX% | XX% | ↗️/↘️ 趨勢說明 | 🟢/🟡/🔴 |
...

**利潤率演變深度解析**：必須解釋變化原因（產品組合、定價能力、成本控制等）

### 3.4 費用結構分析

使用 Mermaid pie chart + ASCII 方框圖展示費用結構

### 3.5 季度 EPS 趨勢與盈餘品質

表格 + 盈餘品質評估說明

---

## 4. 資產負債表分析

### 4.1 資產結構分解

使用 Mermaid graph TD 展示資產結構（總資產→流動/非流動→細項）

### 4.2 流動性指標分析

表格包含歷史趨勢比較 + 行業均值 + 評估

### 4.3 債務結構分析

使用 ASCII 方框圖呈現債務健康診斷，格式：

```
╔══════════════════════════════════════════════════════════════════╗
║                   公司名稱 債務健康診斷                          ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  總債務：        $XX.XXB  ██░░░░░░░░░░░░░░░░░░░  評語            ║
║  總現金+投資：   $XXX.XB  ████████████████████░  評語            ║
║  淨現金（正）：  $XXX.XB  ████████████████░░░░░  🟢 強勁        ║
║                                                                  ║
║  Debt/EBITDA：   X.XXx  🟢 極低                                 ║
║  Interest Coverage: XXXx+  🟢 無風險                             ║
...
╚══════════════════════════════════════════════════════════════════╝
```

### 4.4 股東權益趨勢

ASCII 方框圖展示歷年股東權益變化

---

## 5. 現金流量深度分析

### 5.1 現金流量瀑布圖

使用 Mermaid graph LR 展示：淨利 → 營業現金流 → 資本支出 → FCF → 股息/回購 → 淨現金變化

### 5.2 FCF 轉換率趨勢

表格展示歷年 FCF/Net Income 比率及趨勢

### 5.3 自由現金流趨勢

ASCII 方框圖展示歷年 FCF 及 FCF Yield

### 5.4 資本配置評估

使用 Mermaid pie chart + 表格展示資本配置（回購/投資/Capex/股息/留存）

---

## 6. 獲利能力與資本效率

### 6.1 ROE / ROA / ROIC 趨勢

表格包含歷年數據 + 行業均值對比 + 評估

### 6.2 ROIC vs WACC 分析（核心價值創造判斷）

**必須**使用 ASCII 方框圖呈現完整的 ROIC vs WACC 分析，格式：

```
╔══════════════════════════════════════════════════════════════════╗
║                ROIC vs WACC 深度分析                            ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  WACC 估算：                                                     ║
║  ├── 無風險利率（10Y美債）：  X.X%                               ║
║  ├── 市場風險溢酬 (ERP)：     X.X%                              ║
║  ├── Beta：                   X.XX                               ║
║  ├── 股權成本 = X.X%+X.XX×X.X% = XX.X%                         ║
║  ├── 債務成本（稅後）：       ~X.X%                             ║
║  ├── 資本結構：股權 ~XX%，債務 ~XX%                             ║
║  └── ✅ WACC ≈ XX.X%                                            ║
║                                                                  ║
║  ROIC 估算（FY20XX）：                                           ║
║  ├── NOPAT = $XXX.XB × (1-XX%) ≈ $XXX.XB                       ║
║  ├── 投入資本 = 股東權益 + 債務 - 現金 ≈ $XXXB                  ║
║  └── ✅ ROIC ≈ XX.X%                                            ║
║                                                                  ║
║  ★ 經濟價值增加（EVA）= ROIC - WACC = +XX.Xpp                   ║
║                                                                  ║
║  ROIC  XX.X%  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░  🟢              ║
║  WACC  XX.X%  ▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░  ──              ║
║  EVA   +XXpp  ████████████████████████░░░░░░░░  🏆 強力創造    ║
║                                                                  ║
║  📊 結論：ROIC 為 WACC 的 X.X 倍，強力創造股東價值              ║
╚══════════════════════════════════════════════════════════════════╝
```

### 6.3 杜邦三因素分解

使用 Mermaid graph LR 展示：ROE = 淨利率 × 資產週轉率 × 財務槓桿

### 6.4 獲利能力儀表板

使用 Mermaid graph TD 展示各利潤率及其驅動因素

---

## 7. 估值深度分析

### 7.1 同業估值比較表格

必須點名 2-3 家競爭對手，完整比較表格格式：

| 估值指標 | **本公司** | **競爭對手1** | **競爭對手2** | **競爭對手3** | 本公司評估 |
|----------|----------|---------|---------|---------|-----------|
| **Trailing P/E** | XXx | XXx | XXx | XXx | 🟢/🟡/🔴 評語 |
| **Forward P/E** | **XXx** | XXx | XXx | XXx | 🟢/🟡/🔴 評語 |
| **P/S Ratio** | XXx | XXx | XXx | XXx | 🟢/🟡/🔴 評語 |
...

### 7.2 歷史估值區間分析

ASCII 方框圖展示歷史 P/E 區間及當前位置

### 7.3 DCF 敏感性分析（6格目標價矩陣）

**假設條件**說明 + 6格矩陣表格：

| 情境 | **WACC = X%** | **WACC = X%（基準）** | **WACC = X%** |
|------|--------------|----------------------|--------------|
| 🟢 **樂觀** | **$XXX** (+X%) | **$XXX** (+X%) | **$XXX** (+X%) |
| 🟡 **基準** | **$XXX** (+X%) | **$XXX** (+X%) | **$XXX** (+X%) |
| 🔴 **悲觀** | **$XXX** (+X%) | **$XXX** (+X%) | **$XXX** (+X%) |

### 7.4 估值綜合區間

ASCII 方框圖展示估值區間及當前股價位置

---

## 8. 成長催化劑

### 8.1 催化劑時間軸

使用 Mermaid gantt 展示短期/中期/長期催化劑

### 8.2 TAM 市場規模分析

ASCII 方框圖展示各市場 TAM、滲透率、貢獻收入

### 8.3 成長驅動力結構圖

使用 Mermaid graph TD 展示短期/中期/長期成長驅動力

---

## 9. 風險矩陣

### 9.1 風險評分矩陣

使用 Mermaid quadrantChart 或表格呈現風險機率 vs 衝擊

### 9.2 風險清單詳細分析

詳細表格格式：

| # | 風險項目 | 發生機率 | 財務衝擊 | 風險評分 | 緩解措施 |
|---|----------|----------|----------|----------|----------|
| 1 | 🔴 **風險名稱** | 高 (XX%) | 高 (-X%收入) | 🔴 X.X/10 | 緩解措施描述 |
...

---

## 10. 投資建議

### 10.1 最終綜合評級雷達圖

ASCII 方框圖展示所有維度評分

### 10.2 目標價與隱含報酬率

表格展示各情境目標價、隱含報酬率、機率權重

### 10.3 買入時機與觸發因素

ASCII 方框圖 checklist 格式：

```
╔══════════════════════════════════════════════════════════════════╗
║                  ✅ 買入觸發因素 Checklist                      ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  立即買入觸發條件（多數符合）：                                  ║
║  ✅ 條件1描述                                                    ║
║  ✅ 條件2描述                                                    ║
...
║  加碼觸發條件（出現以下任一）：                                  ║
║  ☐ 條件描述                                                     ║
...
║  減碼/停損觸發條件（出現以下任一）：                             ║
║  ☐ 條件描述                                                     ║
...
╚══════════════════════════════════════════════════════════════════╝
```

### 10.4 投資人適配度分析

使用 Mermaid graph TD 展示各類投資人適配度（成長型/價值型/股息型/短期交易）及原因

### 10.5 關鍵監控指標

表格展示監控類型、指標、關注點、頻率

---

> **免責聲明**：本報告為 AI 自動生成，僅供研究參考，不構成投資建議。投資有風險，入市需謹慎。
"""

# ── Technical Analysis ────────────────────────────────────────────────────────
PROMPT_TECHNICAL = """\
你是一位資深技術分析師，擁有超過15年經驗，精通多時框架分析、圖表形態識別與量化技術指標解讀。
請根據下方提供的 {ticker} 技術數據，撰寫一份完整的技術分析報告。

═══════════════════════  嚴格要求  ═══════════════════════
1. 語言：全程使用**繁體中文**
2. 格式：完整 Markdown 格式
3. 視覺化圖表（必須大量使用）：
   - **Mermaid 圖表**：指標關係、趨勢判斷（graph）
   - **ASCII 圖表**：繪製支撐阻力位示意圖、走勢形態
   - **Unicode 進度條**：顯示各指標強度（▓░█）
4. 具體數字：所有支撐/阻力位、目標價、止損點必須給出精確數值（不得只說「附近」）
5. 交易建議：每個策略必須包含 進場點 / 止損點 / 目標價1 / 目標價2 / 風險報酬比
6. 指標整合：不得孤立分析指標，必須說明多個指標是否互相確認或矛盾
7. 背離分析：明確判斷 RSI / MACD 是否存在頂背離或底背離，給出結論
8. ADX 解讀：說明趨勢強度，判斷是趨勢行情還是盤整行情
9. OBV 分析：說明量能是否確認價格走勢
10. 視覺指標：使用 🟢🟡🔴 表示多空訊號強度
═══════════════════════════════════════════════════════════

━━ 技術數據（今日即時，含2年歷史）━━
{financial_context}
━━━━━━━━━━━━━━━━━━━━━━━━

請按以下架構輸出完整報告，每個章節都要包含豐富的視覺化圖表與精確數值：

# {ticker} 技術分析報告
> **報告日期**：{today} ｜ **語言**：繁體中文 ｜ **數據來源**：Yahoo Finance

## 目錄
## 1. 技術面概覽
   - 技術訊號儀表板 Mermaid graph（所有指標：買入/中性/賣出 計分）
   - 核心指標速覽表（含 MA/RSI/MACD/Stoch/ADX/ATR/OBV）🟢🟡🔴
   - 技術綜合評分（1-10分）Unicode 進度條
   - 52週價格位置分析（目前在哪個區間）
## 2. 趨勢分析（多時框架）
   - 多時框趨勢判斷 Mermaid graph TD（月線→週線→日線→短期）
   - ADX 趨勢強度解讀：是趨勢行情 or 盤整行情？
   - 均線排列（MA20/MA50/MA200）: 多頭/空頭/混合 判斷
   - 長/中/短期趨勢 Unicode 走勢圖
## 3. 圖表形態分析
   - 形態識別 Mermaid graph LR（頭肩頂/底、雙頂/底、三角形、旗形等）
   - ASCII 走勢示意圖（標注支撐、阻力、形態關鍵點位）
   - 形態目標價計算（含量測方法說明）
   - 近期重要 K 線組合分析（日線/週線）
## 4. 支撐與阻力（精確數值）
   - 支撐阻力位 ASCII 視覺化圖（標注全部關鍵價位）
   - 阻力位表格（近端/中端/強阻力，各含具體價格與依據）
   - 支撐位表格（近端/中端/強支撐，各含具體價格與依據）
   - 斐波那契回調位計算表格（38.2% / 50% / 61.8%）
   - 布林通道上下軌作為動態支撐阻力分析
## 5. 技術指標深度解讀
   - 指標訊號彙整 Mermaid graph TD
   - RSI(14) 分析：數值/超買超賣/背離判斷（頂背離/底背離）Unicode 進度條
   - MACD(12/26/9) 分析：交叉/零軸/柱狀圖趨勢 Mermaid graph
   - Stochastic(14,3,3) 分析：%K/%D 交叉/超買超賣
   - 布林通道(20,2σ) 分析：%B 位置/收縮擴張 ASCII 圖
   - ATR(14) 分析：波動率水準、止損距離建議
## 6. 量價分析
   - OBV 趨勢分析：是否確認價格走勢（量能背離？）
   - 成交量與價格配合度分析（放量突破 / 縮量回調）
   - 量能評分 Unicode 進度條 ▓░
   - 量能異常信號識別
## 7. 多時框架訊號總結
   - 時框架評分表格（月線/週線/日線：趨勢/動能/成交量/綜合）🟢🟡🔴
   - 訊號一致性：多指標是否互相確認（或矛盾之處）
## 8. 交易策略建議（精確數值）
   - 策略選擇流程圖 Mermaid graph TD（趨勢行情 vs 盤整行情）
   - **多頭策略**（進場點/止損/目標1/目標2/風險報酬比）表格
   - **空頭策略**（進場點/止損/目標1/目標2/風險報酬比）表格
   - **盤整策略**（高賣低買區間）
   - 倉位管理建議（% of portfolio）
   - 整體技術訊號強度 ★☆ 評星
## 9. 風險提示與監控
   - 關鍵失效條件（什麼價位/信號代表判斷錯誤）checklist
   - 近期催化劑事件（財報/Fed/產業數據）對技術形態的影響
   - 風險場景 Mermaid graph（突破 vs 跌破情境）

> **免責聲明**：本報告為 AI 自動生成，僅供研究參考，不構成投資建議。
"""

# ── Stock Evaluation ──────────────────────────────────────────────────────────
PROMPT_STOCK_EVAL = """\
你是一位頂級美股投資評估師，擁有基金管理與企業估值經驗，請對 **{ticker}** 進行全方位綜合評估。

═══════════════════════  嚴格要求  ═══════════════════════
1. 語言：全程使用**繁體中文**
2. 格式：完整 Markdown 格式
3. 視覺化圖表（必須大量使用）：
   - **Mermaid 圖表**：雷達圖概念（graph）、決策樹（graph TD）
   - **ASCII 雷達圖**：多維度評分視覺化（必須包含）
   - **Unicode 評分條**：各項指標強度（▓░█）
4. 綜合評分：8個維度，各給出 1-10 分並附具體理由
5. ROIC vs WACC：必須估算，判斷是否創造股東價值
6. 同業比較：點名 2-3 家直接競爭對手，進行全面對比
7. 資本配置：評估管理層資本分配效率（buyback/股息/投資/M&A）
8. 視覺指標：使用 🟢🟡🔴 + ★☆ 評星
═══════════════════════════════════════════════════════════

━━ 財務數據（今日即時）━━
{financial_context}
━━━━━━━━━━━━━━━━━━━━━━━━

請按以下架構輸出完整報告：

# {ticker} 綜合股票評估報告
> **報告日期**：{today} ｜ **語言**：繁體中文 ｜ **數據來源**：Yahoo Finance

## 目錄
## 1. 評估總覽
   - ASCII 雷達圖（8個維度評分視覺化，必須繪製）
   - 八維度評分：成長性/獲利能力/財務健康/估值/競爭優勢/管理品質/動能/風險（各1-10分）
   - Unicode 評分條視覺化 ▓░
   - 投資結論：明確給出 強力買入/買入/持有/觀望/賣出 + 目標價 + 預期報酬率
## 2. 八維度評分矩陣
   - Markdown 表格（各維度 評分/依據/趨勢/🟢🟡🔴）
   - 風險/報酬定位使用 Markdown 表格呈現（高風險高報酬/低風險低報酬等象限）
   - 與同業整體比較 Mermaid graph
## 3. 業務品質與護城河
   - 商業模式可持續性評估 Mermaid graph TD
   - 護城河評估 Mermaid mindmap（6種護城河類型各評分）
   - 護城河強度 Unicode 條形圖 ▓░
   - 市場地位：TAM / 市場份額 / 行業地位
## 4. 財務健康全面評估
   - 財務儀表板 Mermaid graph（獲利/流動/槓桿/效率）
   - 獲利能力趨勢表格（近4年：毛利率/營業利益率/淨利率/FCF Margin）🟢🟡🔴
   - 資產負債表穩健度 Unicode 圖（流動比/速動比/淨負債/D/E）
   - 現金流質量分析（FCF 轉換率/FCF yield）
## 5. 成長性評估
   - 歷史 CAGR 表格（1/3/5年：收入/EPS/FCF）
   - 未來成長催化劑 Mermaid graph TD
   - 市場份額趨勢分析
   - 成長軌跡 Unicode 長條圖
## 6. 估值合理性 & 同業比較
   - **同業比較表格**（點名 2-3 家競爭對手：P/E/P/S/EV/EBITDA/P/B/FCF Yield）🟢🟡🔴
   - 歷史估值區間（P/E 5年高/中/低，目前所處位置）
   - 多重估值法彙整（DDM/DCF/相對估值）→ 目標價區間
   - 估值區間視覺化 Unicode 圖（低估/合理/高估標示）
## 7. 資本配置與管理層評估
   - **ROIC vs WACC**：估算數值，判斷 EVA 正負，說明是否創造股東價值
   - 資本配置歷史（buyback / 股息 / CAPEX / M&A 比例）Mermaid pie chart
   - 管理層執行力評分表格（承諾達成率/資本紀律/戰略清晰度）
   - 股東友善度評分 Unicode 條形圖
## 8. 風險評估
   - 風險熱圖 Mermaid quadrantChart（機率 × 衝擊）
   - 風險清單表格（高/中/低，含緩解措施）🔴🟡🟢
   - 最大下行情境分析（bear case 目標價）
## 9. 催化劑與觸發因素
   - 催化劑時間軸 Mermaid gantt（近期/中期/長期）
   - 正面觸發因素 Mermaid graph TD
## 10. 投資建議
   - 最終評級 ★☆ 評星 + 結論框格
   - 目標價區間（樂觀/基準/悲觀）及隱含報酬率表格
   - 投資人適配度（成長/價值/股息/短線）Mermaid graph TD
   - 建議持倉時間、加碼觸發條件、止損觸發條件
   - 關鍵監控指標 checklist

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

# ── Earnings Call Analysis ────────────────────────────────────────────────────
PROMPT_EARNINGS_CALL = """\
你是一位專業的財報電話會議（Earnings Call）分析師，擅長解讀管理層語氣、識別關鍵信號與市場影響。
請根據下方提供的 **{ticker}** 財務數據與近期新聞，進行財報電話會議深度分析。

═══════════════════════  嚴格要求  ═══════════════════════
1. 語言：全程使用**繁體中文**
2. 格式：完整 Markdown 格式
3. 視覺化：使用 Mermaid graph、表格、Unicode 進度條 ▓░█
4. 情緒分析：量化評分管理層語氣（樂觀/中性/謹慎/悲觀）
5. 具體數字：所有 guidance、業績數字必須引用
6. 信號識別：區分「管理層刻意強調」vs「輕描淡寫」的項目
7. 市場影響：分析財報後的預期股價反應與催化劑
8. 視覺指標：使用 🟢🟡🔴 + ★☆ 評星
═══════════════════════════════════════════════════════════

━━ 財務數據與背景資訊（今日即時）━━
{financial_context}
━━━━━━━━━━━━━━━━━━━━━━━━

今日日期：{today}

請按以下架構輸出完整報告：

# {ticker} 財報電話會議分析報告
> **報告日期**：{today} ｜ **語言**：繁體中文 ｜ **數據來源**：Yahoo Finance + 公開資訊

## 目錄
## 1. 財報摘要儀表板
   - 核心財務數據 vs 市場預期對比表格（Revenue/EPS/Margin 🟢🟡🔴）
   - 最近4季 EPS 超預期/不及預期紀錄 Unicode 進度條
   - 財報反應評分（1-10分）
## 2. 業績表現深度解讀
   - 收入成長分析（季度 QoQ + YoY，趨勢 ASCII 圖）
   - 利潤率變動分析（毛利率/營業利益率/淨利率）🟢🟡🔴
   - 各業務板塊表現（若有）Mermaid pie chart
   - EPS 質量分析（one-time items / recurring earnings）
## 3. 管理層語氣與情緒分析
   - 整體語氣評分 Mermaid graph（樂觀↔悲觀量表）
   - 管理層常用措辭分析表格（正面/中性/負面關鍵詞）
   - 與上季財報語氣對比 🟢🟡🔴
   - 管理層公信力歷史評估（過往 guidance 達成率）
## 4. 關鍵主題與信號識別
   - 強調項目（管理層重複提及）Mermaid mindmap
   - 刻意迴避/輕描淡寫的風險項目 🔴
   - 新增/消失的關鍵詞（與上季比較）
   - 隱藏信號解讀表格
## 5. Forward Guidance 分析
   - 下季/全年 Guidance 表格（Revenue/EPS/Margin 指引）
   - Guidance vs 市場共識對比 🟢🟡🔴
   - Guidance 保守度評估（歷史達成率）
   - 上調/下調趨勢 ASCII 圖
## 6. 分析師 Q&A 重點
   - 熱點問題分類 Mermaid graph TD
   - 管理層回答品質評分（直接/迴避）表格
   - 分析師關注焦點轉移分析
## 7. 競爭環境與行業洞察
   - 管理層提及的競爭動態
   - 行業趨勢信號（需求/定價/庫存）
   - 宏觀環境影響評估
## 8. 財報後市場影響預測
   - 短期股價反應預測（1週）🟢🟡🔴
   - 估值重定價可能性分析
   - 催化劑與風險事件時間軸 Mermaid gantt
   - 分析師預測修正方向
## 9. 投資行動建議
   - 財報品質綜合評分 ★☆
   - 買入/持有/觀望/賣出 結論
   - 關鍵監控指標 checklist（下季重點關注）

> **免責聲明**：本報告為 AI 自動生成，僅供研究參考，不構成投資建議。
"""

# ── Insider Trading Analysis ──────────────────────────────────────────────────
PROMPT_INSIDER_TRADING = """\
你是一位專精美國 SEC 監管與內部人交易的投資研究分析師。
請根據下方提供的 **{ticker}** 內部人交易數據，進行深度內部人交易分析報告。

═══════════════════════  嚴格要求  ═══════════════════════
1. 語言：全程使用**繁體中文**
2. 格式：完整 Markdown 格式
3. 視覺化：Mermaid graph、表格、Unicode 進度條 ▓░█
4. 信號解讀：區分「例行性賣出」（期權履約）vs「有意義的買賣」
5. 聰明錢判斷：識別哪些內部人的交易最具參考價值
6. 時機分析：交易時點與股價走勢的關係
7. 視覺指標：🟢（買入）🔴（賣出）🟡（中性）
═══════════════════════════════════════════════════════════

━━ 內部人交易數據（今日即時）━━
{financial_context}
━━━━━━━━━━━━━━━━━━━━━━━━

今日日期：{today}

請按以下架構輸出完整報告：

# {ticker} 內部人交易深度分析報告
> **報告日期**：{today} ｜ **語言**：繁體中文 ｜ **數據來源**：Yahoo Finance (SEC Form 4)

## 目錄
## 1. 內部人交易概覽儀表板
   - 買賣比率 Mermaid pie chart（近6個月買入 vs 賣出）
   - 淨買入/賣出金額 Unicode 進度條（正=淨買入 🟢，負=淨賣出 🔴）
   - 交易活躍度評分（1-10分）
   - 整體信號：看多/中性/看空 🟢🟡🔴
## 2. 詳細交易記錄分析
   - 全部交易記錄表格（日期/姓名/職位/交易類型/股數/價值 🟢🔴）
   - 最大單筆交易分析（買入前5名 + 賣出前5名）
   - 交易價格 vs 當時股價對比（內部人買/賣點位 ASCII 圖）
## 3. 關鍵內部人識別
   - 最具參考價值的內部人排名表格（CEO/CFO/董事 加權）
   - 「聰明錢」標記：過往交易與股價的相關性
   - 內部人職位分布 Mermaid pie chart
## 4. 買入信號分析
   - 有意義的買入交易（過濾期權履約，聚焦公開市場買入）🟢
   - 集群買入識別（多位內部人同期買入）
   - 買入規模 vs 薪酬對比（高信心指標）
   - 歷史買入準確率分析
## 5. 賣出信號分析
   - 例行性賣出識別（期權履約/稅務規劃）⬜
   - 異常賣出預警（大額、集中、多人同時）🔴
   - 賣出與業績公告時間關係分析
## 6. 持股結構分析
   - 主要持股者分布（內部人 vs 機構 vs 散戶）Mermaid pie chart
   - 內部人整體持股比例趨勢（增加/減少）
   - 機構持股前20名表格（含持股變化 🟢🔴）
## 7. 時機與價格分析
   - 內部人交易時機 vs 股價走勢 ASCII 圖（標注買賣點）
   - 交易後1/3/6個月股價表現統計
   - 交易集中在哪個股價區間（成本基礎分析）
## 8. 綜合信號解讀與投資建議
   - 內部人交易信號強度評分 ★☆
   - 買入/持有/觀望 建議（基於內部人行為）
   - 關鍵監控觸發點 checklist（什麼樣的交易出現應特別注意）

> **免責聲明**：本報告為 AI 自動生成，僅供研究參考，不構成投資建議。
"""

# ── Institutional Ownership Analysis ─────────────────────────────────────────
PROMPT_INSTITUTIONAL = """\
你是一位專精機構投資者行為分析的研究分析師，擅長解讀 13F 持股變化與聰明錢動向。
請根據下方提供的 **{ticker}** 機構持股數據，進行深度機構持股分析報告。

═══════════════════════  嚴格要求  ═══════════════════════
1. 語言：全程使用**繁體中文**
2. 格式：完整 Markdown 格式
3. 視覺化：Mermaid graph、表格、Unicode 進度條 ▓░█
4. 聰明錢識別：區分不同類型機構（對沖基金/共同基金/養老金/ETF）的意義
5. 持股變化解讀：大幅加倉/減倉的含義分析
6. 籌碼集中度：分析股權集中度對股價的影響
7. 視覺指標：🟢（加倉）🔴（減倉）🟡（持平）
═══════════════════════════════════════════════════════════

━━ 機構持股數據（今日即時）━━
{financial_context}
━━━━━━━━━━━━━━━━━━━━━━━━

今日日期：{today}

請按以下架構輸出完整報告：

# {ticker} 機構持股深度分析報告
> **報告日期**：{today} ｜ **語言**：繁體中文 ｜ **數據來源**：Yahoo Finance (13F)

## 目錄
## 1. 持股結構總覽儀表板
   - 股權結構分布 Mermaid pie chart（機構/散戶/內部人/ETF）
   - 機構持股比例 Unicode 進度條
   - 整體機構信心評分（1-10分）🟢🟡🔴
   - 聰明錢趨勢：淨增持/淨減持 信號
## 2. 主要機構持股明細
   - 前20大機構持股表格（機構名稱/股數/持股%/市值/變化% 🟢🔴）
   - 加倉最多 Top 5 🟢
   - 減倉最多 Top 5 🔴
   - 新進機構（首次建倉）✨
   - 清倉機構（完全出清）⚠️
## 3. 機構類型分析
   - 機構類型分布 Mermaid pie chart（對沖基金/共同基金/養老金/ETF/保險）
   - 各類型機構持股變化趨勢表格
   - 主動管理 vs 被動指數基金比例
## 4. 聰明錢識別與分析
   - 頂級對沖基金持倉（Bridgewater / Blackrock / Vanguard 等代表性機構）
   - 聰明錢一致性：多家頂尖機構同向操作？
   - 知名基金經理持倉記錄（若有）
   - 聰明錢信號強度 ★☆ 評星
## 5. 共同基金持股分析
   - 前10大共同基金持股表格
   - 基金類型（成長/價值/平衡）偏好分析
   - 基金持股比例佔基金 AUM 分析（高持倉=高信心）
## 6. 籌碼集中度分析
   - 前10大機構集中度（佔流通股%）Unicode 進度條
   - 籌碼集中度歷史趨勢（集中增加/分散）
   - 集中度對股價波動的影響評估
   - 大股東鎖定效應分析
## 7. 持股變化趨勢解讀
   - 機構持股整體趨勢（增持/減持/持平）ASCII 走勢圖
   - 近期最顯著持股變化事件分析
   - 持股變化與股價的歷史相關性
## 8. 空頭數據分析
   - 放空比率（Short Float %）
   - Short Ratio（空頭回補天數）
   - 空頭倉位變化趨勢
   - 軋空潛力評估 🟢🔴
## 9. 綜合機構行為信號與投資建議
   - 機構持股信號強度評分 ★☆
   - 機構動向支持的投資方向（買入/持有/觀望）
   - 關鍵監控指標 checklist（下季 13F 重點關注對象）

> **免責聲明**：本報告為 AI 自動生成，僅供研究參考，不構成投資建議。
"""

# ── Report Generator (HTML) ───────────────────────────────────────────────────
PROMPT_REPORT_GENERATOR = """\
你是一位頂級金融報告設計師兼分析師，擅長用 HTML + Chart.js 生成互動式專業投資報告。
請根據下方提供的 **{ticker}** 完整財務數據，生成一份美觀的 HTML 投資報告。

═══════════════════════  嚴格要求  ═══════════════════════
1. 語言：全程使用**繁體中文**
2. 輸出格式：**純 HTML 文件**（完整可獨立運行，含 CSS 與 Chart.js CDN）
3. 設計風格：
   - 深色主題（dark theme）：背景 #0d1117，文字 #e6edf3
   - 強調色：#58a6ff（藍）、#3fb950（綠）、#f85149（紅）、#d29922（黃）
   - 卡片式佈局（card layout）
   - 響應式設計（RWD）
4. 圖表（必須包含，使用 Chart.js 4.x CDN）：
   - 股價走勢折線圖（近24個月月收盤）
   - 收入/利潤趨勢長條圖（近4年）
   - 技術指標儀表板（RSI/MACD 數值卡片）
   - 估值倍數雷達圖（P/E / P/B / P/S / EV/EBITDA）
   - 機構持股結構圓餅圖
5. 數據表格：使用 HTML table，含 hover 效果與顏色編碼
6. 評分系統：每個維度用 CSS progress bar 顯示（0-100%）
7. 報告結構完整，等同於機構研究報告品質
═══════════════════════════════════════════════════════════

━━ 完整財務數據（今日即時）━━
{financial_context}
━━━━━━━━━━━━━━━━━━━━━━━━

今日日期：{today}

請輸出完整的 HTML 文件（從 <!DOCTYPE html> 開始到 </html> 結束），包含以下章節：

1. **Header**：公司名稱、Ticker、報告日期、整體評級徽章
2. **Executive Summary**：關鍵指標卡片（股價/市值/P/E/ROE/FCF）+ 投資結論
3. **Price Chart**：Chart.js 折線圖（24個月月收盤價）
4. **Financial Performance**：Chart.js 長條圖（收入/毛利/淨利趨勢，近4年）
5. **Valuation Dashboard**：估值倍數卡片 + Chart.js 雷達圖（同業比較）
6. **Technical Indicators**：RSI/MACD/MA 數值卡片 + 信號燈（🟢🔴）
7. **Fundamentals Table**：完整財務數據 HTML 表格（含顏色編碼）
8. **Institutional Ownership**：Chart.js 圓餅圖 + 前10大機構表格
9. **Risk & Scoring**：多維度評分 CSS progress bar（成長/獲利/估值/技術/機構信心）
10. **Investment Thesis**：投資論點 + 目標價 + 監控指標 checklist
11. **Footer**：免責聲明

確保：
- 所有 Chart.js 使用 CDN：https://cdn.jsdelivr.net/npm/chart.js@4
- CSS 完全內嵌（無外部 CSS 依賴）
- 數據直接硬編碼到 JavaScript（從上方財務數據提取）
- 文件可直接在瀏覽器開啟，無需伺服器

> **免責聲明**：本報告為 AI 自動生成，僅供研究參考，不構成投資建議。
"""

# ── Financial Report Analyst ──────────────────────────────────────────────────
PROMPT_FINANCIAL_REPORT_ANALYST = """\
你是一位精通 SEC 監管文件解讀的頂級財報分析師，擁有 CPA 與 CFA 雙重資格，擅長從財務報表、\
MD&A 與附注中發掘機構研究員容易忽略的深層信息。
請根據下方 **{ticker}** 的即時財務數據，進行八階段財報深度解析。

═══════════════════════  嚴格要求  ═══════════════════════
1. 語言：全程使用**繁體中文**
2. 格式：完整 Markdown 格式（# ## ### 層級標題）
3. 視覺化圖表（必須大量使用）：
   - **Mermaid 圖表**：財務結構、風險矩陣（graph, quadrantChart）
   - **ASCII 圖表**：DSO/DIO/FCF 趨勢折線圖
   - **Unicode 評分條**：各維度強度 ▓░█
4. 會計品質評分（0–21分）：依七大標準評分，附詳細拆解表格
5. 紅旗偵測：識別風險因素變化、附注異常、分部報告調整
6. 管理層語氣量化評分（1–5分），追蹤 Guidance 達成率
7. 營運資本分析：計算 DSO / DIO / AP Days，判斷趨勢 🟢🟡🔴
8. FCF 轉換率（FCF / Net Income）：目標 >80%；SBC 佔收入比 >5% 須預警 🔴
9. 視覺指標：使用 🟢🟡🔴 + HIGH/MED/LOW 紅旗等級
10. 最終輸出標準化訊號塊（BULLISH / NEUTRAL / BEARISH）
═══════════════════════════════════════════════════════════

━━ 財務數據（今日即時）━━
{financial_context}
━━━━━━━━━━━━━━━━━━━━━━━━

今日日期：{today}

請按八階段架構輸出完整報告：

# {ticker} 財報深度解析報告
> **報告日期**：{today} ｜ **語言**：繁體中文 ｜ **框架**：8-Phase Financial Report Analysis

## 目錄
## 階段 1：文件定向（Document Orientation）
   - 財報類型識別（10-K / 10-Q / 8-K / 財報新聞稿）+ 涵蓋期間
   - 審計師意見類型（無保留/保留/否定/無法表示）及審計師是否變更 🔴
   - 申報日期適時性評估（是否延遲申報）
   - 前期財務重述記錄

## 階段 2：MD&A 深度解讀
   - **收入分析**：分部/產品收入拆解、有機 vs 無機成長、積壓訂單趨勢、管理層 Guidance 具體性
   - **利潤率分析**：Non-GAAP vs GAAP 差異表格（Non-GAAP 排除項成長速度 > GAAP 費用 → 警訊 🔴）
   - **流動性與資本資源**：現金部位、循環信用額度、12個月/3年債務到期時間表、OCF/FCF
   - **Forward Guidance**：具體數字 vs 方向性語言趨勢分析（語氣降格 → 信心減弱信號）

## 階段 3：財務報表深度解讀
   - **損益表**：收入認列政策變動、應收帳款成長 vs 收入成長對比（塞貨信號 🔴）、遞延收入趨勢
   - **資產負債表**：商譽/無形資產佔總資產比、DSO/DIO 趨勢表格、利息保障倍數、淨負債/EBITDA
   - **現金流量表**（最難操縱）：
     - GAAP 淨利 → 營業現金流調節分析
     - FCF 轉換率趨勢表格（目標 >80%）🟢🟡🔴
     - SBC 佔收入比例評估（>5% → 稀釋預警 🔴）
     - 資本支出 vs 折舊（維護性 vs 成長性 CAPEX 判斷）

## 階段 4：風險因素分析
   - 新增風險因素表格（法規/法律/客戶集中/網路安全/持續經營）🔴
   - 消失或縮減的風險因素（是否刻意淡化？）🟡
   - 風險描述語言強化分析（擴展描述 → 升級警示）
   - 競爭風險語言 vs 上期對比

## 階段 5：會計附注深度解析
   - 關鍵會計估計審查（收入認列/商譽減損/SBC 估值）
   - 關聯方交易識別 + 金額揭露 🔴
   - 分部報告變更分析（隱藏績效欠佳部門？）
   - 或有負債 + 法律訴訟重大性評估

## 階段 6：管理層語氣分析
   - 整體語氣評分表格（各財報段落 1–5 分）Mermaid graph
   - 對沖語言清單：「we cannot assure」/「significant uncertainty」/被動語態 負面項目 🔴
   - 正面強調 vs 刻意迴避項目對比表格
   - **Guidance 準確度計分卡**：近4季 預測 vs 實際（命中率 / 平均誤差）

## 階段 7：季度環比比較（適用 10-Q）
   - QoQ 趨勢表格（本季 vs 上季 vs 去年同期）
   - 加速 / 穩定 / 減速 / 惡化 趨勢判斷 🟢🟡🔴
   - 季節性調整後核心趨勢解讀

## 階段 8：內部人活動交叉驗證
   - 近期 CEO/CFO 公開市場買入（強烈看多信號）🟢
   - 低價大量賣出（負面信號）🔴
   - 新設 10b5-1 計畫（中性參考）
   - 高管離職（尤其 CFO 離職 → 重大紅旗）🔴

## 綜合評估輸出

### 財務健康儀表板
| 指標 | 數值 | 評分 | 趨勢 |
|------|------|------|------|
| 收入成長 | | /10 | 🟢🟡🔴 |
| FCF 轉換率 | | /10 | |
| 毛利率 | | /10 | |
| 淨負債/EBITDA | | /10 | |
| DSO 趨勢 | | /10 | |
| 管理層語氣 | | /5 | |
| 會計品質評分 | | /21 | |

### 會計品質評分（0–21）
| 標準 | 滿分 | 得分 | 評估說明 |
|------|------|------|---------|
| 收入認列清晰度 | 3 | | |
| Non-GAAP 調節合理性 | 3 | | |
| FCF 轉換率 | 3 | | |
| 營運資本健康度 | 3 | | |
| 附注透明度 | 3 | | |
| 審計師意見 | 3 | | |
| 關聯方交易 | 3 | | |
| **合計** | **21** | | |

### 紅旗彙整表格
| 嚴重度 | 紅旗項目 | 位置/段落 | 投資含義 |
|--------|---------|---------|---------|
| HIGH 🔴 | | | |
| MED 🟡 | | | |
| LOW ⬜ | | | |

### 投資訊號
```
Signal:     BULLISH / NEUTRAL / BEARISH
Confidence: HIGH / MEDIUM / LOW
Horizon:    SHORT / MEDIUM / LONG-TERM
Score:      X.X / 10
Action:     BUY / HOLD / SELL
```
**評分指引**：8.0–10.0 強烈看多 ｜ 6.0–7.9 溫和看多 ｜ 4.0–5.9 中性 ｜ 2.0–3.9 溫和看空 ｜ 0.0–1.9 強烈看空

> **免責聲明**：本報告為 AI 自動生成，僅供研究參考，不構成投資建議。
"""

# ── Stock Valuation ───────────────────────────────────────────────────────────
PROMPT_STOCK_VALUATION = """\
你是一位頂級股票估值專家，擁有投資銀行與私募股權估值經驗，精通 DCF、可比公司分析、\
EV/EBITDA 倍數法、P/E 估值與剩餘收益模型。
請根據下方 **{ticker}** 的即時財務數據，運用五種方法進行多方法估值分析，\
最終彙整橄欖球場圖（Football Field Chart）與機率加權內在價值。

═══════════════════════  嚴格要求  ═══════════════════════
1. 語言：全程使用**繁體中文**
2. 格式：完整 Markdown 格式（# ## ### 層級標題）
3. 視覺化圖表（必須大量使用）：
   - **ASCII 橄欖球場圖**：彙整5種方法的熊/基準/牛市價值區間（必須繪製）
   - **Mermaid 圖表**：DCF 情境樹、估值比較（graph, quadrantChart）
   - **Unicode 評分條**：安全邊際視覺化 ▓░█
4. 五種方法均需完整計算，並列出所有假設條件
5. DCF：三情境（樂觀20%/基準60%/悲觀20%），10年投影，6格敏感性矩陣（WACC × 終端成長率）
6. CCA：點名5–8家同業，比較 EV/Revenue / EV/EBITDA / P/E / EV/FCF
7. 機率加權綜合估值：整合全部方法並附權重說明
8. 風險調整報酬：計算各情境隱含報酬率，目標風險報酬比 ≥ 3:1
9. 分析師共識比較：與市場目標價對比
10. 安全邊際評估：>30% 折價=吸引力高 🟢 ｜ 0–10%=合理定價 🟡 ｜ >50% 溢價=昂貴 🔴
═══════════════════════════════════════════════════════════

━━ 財務數據（今日即時）━━
{financial_context}
━━━━━━━━━━━━━━━━━━━━━━━━

今日日期：{today}

請按以下架構輸出完整報告：

# {ticker} 多方法估值分析報告
> **報告日期**：{today} ｜ **語言**：繁體中文 ｜ **框架**：5-Method Football Field Valuation

## 目錄
## 1. 估值摘要儀表板
   - **ASCII 橄欖球場圖**（必須繪製）：
     ```
     方法                熊市    基準    牛市
     ─────────────────────────────────────────────────────
     DCF                 $XX     $XX     $XX   |---[=====]-----|
     可比公司 CCA        $XX     $XX     $XX   |--[====]-------|
     EV/EBITDA 倍數      $XX     $XX     $XX   |----[====]-----|
     P/E 倍數            $XX     $XX     $XX   |---[=====]-----|
     剩餘收益            $XX     $XX     $XX   |----[====]-----|
     ─────────────────────────────────────────────────────
     機率加權綜合        $XX     $XX     $XX   ★
     目前股價            $XX                   ↑
     ```
   - 綜合估值結論表格（當前股價 vs 各方法目標價 vs 安全邊際）🟢🟡🔴
   - 投資訊號：明確給出 強力買入/買入/持有/觀望/賣出 + 隱含報酬率

## 2. 方法一：DCF 貼現現金流分析
   - **WACC 計算**：Ke（CAPM）/ Kd / 資本結構詳細計算表格
   - **三情境假設表格**：
     | 假設 | 樂觀（20%） | 基準（60%） | 悲觀（20%） |
     |------|----------|----------|----------|
     | 前5年收入CAGR | | | |
     | 後5年收入CAGR | | | |
     | 目標EBITDA Margin | | | |
     | 終端成長率 | | | |
     | WACC | | | |
     | 目標價 | | | |
   - **10年自由現金流投影表格**（含終端價值計算與佔比）
   - **敏感性分析矩陣**（6格：WACC × 終端成長率）：
     ```
              終端成長率
     WACC    1.0%    2.0%    3.0%
     8%      $XX     $XX     $XX
     9%      $XX     $XX     $XX
     10%     $XX     $XX     $XX
     ```
   - DCF 機率加權目標價：**$XX**

## 3. 方法二：可比公司分析（CCA）
   - **同業比較表格**（5–8家同業，必須點名公司）：
     | 公司 | EV/Revenue | EV/EBITDA | P/E | EV/FCF | 綜合評分 |
     |------|-----------|----------|-----|--------|---------|
     | 同業1 | | | | | |
     | 同業2 | | | | | |
     | 中位數 | | | | | |
     | **{ticker}** | | | | | 🟢🟡🔴 |
   - 各倍數法目標價計算表格（中位數倍數 × {ticker} 財務指標）
   - CCA 目標價區間：**$XX – $XX**

## 4. 方法三：EV/EBITDA 倍數估值
   - 歷史 EV/EBITDA 區間分析（5年：高/均值/低）
   - **三層估值表格**：
     | 情境 | EV/EBITDA倍數 | 依據 | 目標價 |
     |------|-------------|-----|------|
     | 保守 | | | $XX |
     | 基準 | | | $XX |
     | 優質溢價 | | | $XX |
   - EV/EBITDA 目標價：**$XX**

## 5. 方法四：P/E 倍數估值（含 PEG）
   - 歷史 P/E 區間（5年：高/均值/低）
   - **P/E 估值表格**（Forward P/E × EPS 估計）：
     | 情境 | P/E倍數 | Forward EPS | 目標價 |
     |------|--------|------------|------|
     | 保守 | | | $XX |
     | 基準 | | | $XX |
     | 成長溢價 | | | $XX |
   - **PEG 比率分析**：PEG = P/E ÷ EPS成長率，合理 PEG 區間評估
   - P/E 目標價：**$XX**

## 6. 方法五：剩餘收益 / 經濟附加值（EVA）
   （適用金融股、資產密集型或 FCF 為負的成長公司）
   - **EVA 計算**：NOPAT - (WACC × 投入資本)，判斷是否創造股東價值
   - **剩餘收益投影**（10年），含終端殘差值
   - 內在價值 = 帳面價值 + 未來剩餘收益現值
   - 剩餘收益目標價：**$XX**

## 7. 機率加權綜合內在價值
   - **綜合估值表格**（各方法權重 + 加權貢獻）：
     | 方法 | 基準目標價 | 權重 | 加權貢獻 |
     |------|---------|------|--------|
     | DCF | $XX | 35% | $XX |
     | CCA | $XX | 25% | $XX |
     | EV/EBITDA | $XX | 20% | $XX |
     | P/E | $XX | 15% | $XX |
     | 剩餘收益 | $XX | 5% | $XX |
     | **機率加權綜合** | | **100%** | **$XX** |
   - 安全邊際 Unicode 進度條 ▓░
   - 安全邊際評估：>30% 折價=吸引力高 🟢 ｜ 0–10%=合理定價 🟡 ｜ >50% 溢價=昂貴 🔴

## 8. 風險調整報酬分析
   - **三情境期望報酬表格**：
     | 情境 | 機率 | 目標價 | 隱含報酬率 | 機率加權報酬 |
     |------|------|------|---------|-----------|
     | 牛市 | 20% | $XX | +XX% | +XX% |
     | 基準 | 60% | $XX | +XX% | +XX% |
     | 熊市 | 20% | $XX | -XX% | -XX% |
     | **期望報酬** | | | | **+XX%** |
   - 風險報酬比：X:1（目標 ≥ 3:1）
   - 下行保護評估（熊市情境最大虧損幅度）

## 9. 分析師共識比較
   - 分析師目標價統計（Mean / Low / High / 本報告目標）對比表格 🟢🟡🔴
   - 本報告 vs 共識的主要差異分析（更樂觀/悲觀的核心假設差異）
   - 近期評級調整趨勢

## 10. 估值結論與投資建議
   - 最終估值區間摘要（熊/基準/牛市目標價）
   - 安全邊際視覺化 Unicode ▓░ 進度條
   - **投資訊號**：
     ```
     Signal:      BULLISH / NEUTRAL / BEARISH
     Confidence:  HIGH / MEDIUM / LOW
     Horizon:     SHORT / MEDIUM / LONG-TERM
     Score:       X.X / 10
     Action:      BUY / HOLD / SELL
     Target:      $XX（基準） | $XX（牛市） | $XX（熊市）
     Risk/Reward: X:1
     ```
   - 關鍵估值假設監控 checklist（什麼數據變化需重新估值）
   - 觸發重新評估的指標

> **免責聲明**：本報告為 AI 自動生成，僅供研究參考，不構成投資建議。
"""

PROMPT_MAP = {
    "fundamental-analysis":   PROMPT_FUNDAMENTAL,
    "technical-analysis":     PROMPT_TECHNICAL,
    "stock-eval":             PROMPT_STOCK_EVAL,
    "economics-analysis":     PROMPT_ECONOMICS,
    "portfolio-review":       PROMPT_PORTFOLIO,
    "sector-analysis":        PROMPT_SECTOR,
    "earnings-call-analysis": PROMPT_EARNINGS_CALL,
    "insider-trading":        PROMPT_INSIDER_TRADING,
    "institutional-ownership":    PROMPT_INSTITUTIONAL,
    "report-generator":           PROMPT_REPORT_GENERATOR,
    "financial-report-analyst":   PROMPT_FINANCIAL_REPORT_ANALYST,
    "stock-valuation":            PROMPT_STOCK_VALUATION,
}


# ═════════════════════════════════════════════════════════════════════════════
# 4.  LLM API (Claude / OpenAI)
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

    max_retries = 5
    base_delay  = 30  # seconds
    for attempt in range(1, max_retries + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            break
        except anthropic.RateLimitError as e:
            if attempt == max_retries:
                raise
            delay = base_delay * (2 ** (attempt - 1))  # 30 60 120 240 …
            print(f"  ⚠️  Rate limit hit (attempt {attempt}/{max_retries})."
                  f" Retrying in {delay}s …")
            time.sleep(delay)

    text  = "\n\n".join(b.text for b in response.content if hasattr(b, "text"))
    usage = response.usage
    print(f"  ✅ response  in={usage.input_tokens}  out={usage.output_tokens}"
          f"  chars={len(text)}")
    return text


def call_openai(ticker: str, context: str, analysis_type: str,
                model: str, max_tokens: int) -> str:
    """Call OpenAI API and return the response text."""
    try:
        import openai
    except ImportError:
        sys.exit("ERROR: 'openai' not installed.  Run: pip install openai")

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        sys.exit("ERROR: OPENAI_API_KEY environment variable is not set.")

    # OpenAI models have different max token limits - use optimized values for detailed analysis
    # gpt-4o & gpt-4o-mini: 128k context window, can support higher output limits
    # gpt-4-turbo: older model with lower limits
    openai_max_tokens = {
        "gpt-4o": 20000,         # Generous limit for comprehensive stock analysis reports
        "gpt-4o-mini": 12000,    # Good limit for detailed analysis
        "gpt-4-turbo": 4096,     # Hard limit for this older model
        "gpt-4": 8192,           # Standard limit for older model
    }
    model_max = openai_max_tokens.get(model, 20000)
    effective_max_tokens = min(max_tokens, model_max)
    if effective_max_tokens != max_tokens:
        print(f"  [INFO] Capping max_tokens from {max_tokens} to {effective_max_tokens} for {model}")

    # System message to improve output quality (matching Claude's detailed style)
    system_message = """你是一位頂級美股投資研究分析師，擁有 CFA 資格與 15 年以上投資研究經驗，專精基本面分析、估值建模、技術分析與產業研究。

你必須嚴格遵循以下原則產出機構級專業報告：

## 核心要求（必須100%遵守）
1. **完整性**：必須按照 prompt 中要求的所有章節完整輸出，不得省略任何章節或使用「略」「以下省略」等簡化語
2. **深度分析**：每個章節必須提供詳盡、專業的分析內容，每個子章節至少 500-1000 字
3. **具體數據**：每個論點必須引用具體的財務數據、比率、估值倍數等數字支撐
4. **專業格式**：使用完整的 Markdown 格式，包含層級標題（### ####）、表格、條列
5. **視覺指標**：大量使用 🟢🟡🔴 標記評估結果、★☆ 評星

## 視覺化要求（極其重要）
你必須在報告中大量使用以下視覺化元素：

### ASCII 方框圖（必須使用）
使用 ╔═╗╚═╝║ 字符創建專業方框，例如：
```
╔══════════════════════════════════════════════════════════════╗
║              標題                                            ║
╠══════════════════════════════════════════════════════════════╣
║  內容行1                                                     ║
║  內容行2                                                     ║
╚══════════════════════════════════════════════════════════════╝
```

### Unicode 進度條（必須使用）
使用 ▓░█ 創建進度條，例如：
- 評分 9.5: ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░
- 評分 7.0: ▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░

### Mermaid 圖表（必須使用）
- graph TD: 業務結構、資產結構、成長驅動力
- graph LR: 現金流瀑布、杜邦分解
- pie: 市場份額、費用結構、資本配置
- mindmap: 競爭護城河
- gantt: 催化劑時間軸

## 輸出標準
- **報告長度**：完整報告必須達到 15000-20000 字（充分利用提供的 token 額度）
- **表格使用**：所有關鍵數據比較必須使用 Markdown 表格呈現
- **評分系統**：各維度評分（1-10分）必須附上具體理由和數據支撐
- **Mermaid 語法**：確保所有 Mermaid 圖表語法正確，使用 quadrantChart 或表格呈現風險矩陣

## 分析深度
- 計算並標註 YoY / QoQ 成長率（必須有具體百分比）
- **ROIC vs WACC 分析**：必須估算 WACC（包含 Beta、無風險利率、ERP），計算 ROIC，判斷 EVA
- **杜邦分解**：必須將 ROE 分解為淨利率 × 資產週轉率 × 財務槓桿
- 同業比較：必須點名 2-3 家直接競爭對手，完整比較 P/E、P/S、EV/EBITDA、P/B、FCF Yield
- DCF 敏感性分析：必須提供 3×2 共 6 格的目標價矩陣
- 風險評估：列出至少 8-10 項風險因素，包含機率、衝擊、緩解措施
- 投資建議：明確給出買入/持有/賣出建議、目標價區間、觸發條件 checklist

## 對不完整數據的處理
- 如果部分財務數據缺失，基於公司背景、產業知識、市場環境進行專業推演
- 對缺失數據明確說明推演依據，但分析內容必須高質量
- 不要出現「N/A」「無可用數據」等佔位符，改為基於相關信息的分析推導
- 即使數據不完整，也必須維持報告的完整性和專業水準

## 特別注意
- 不要在任何地方使用「以下省略」「其餘類推」等簡化語
- 每個章節都必須完整展開，提供有實質價值的分析
- 報告結尾必須有完整的投資建議章節，包含目標價、觸發條件、投資人適配度"""

    client   = openai.OpenAI(api_key=api_key)
    template = PROMPT_MAP[analysis_type]
    prompt   = template.format(
        ticker=ticker,
        financial_context=context,
        today=TODAY,
    )

    print(f"  → OpenAI API  model={model}  max_tokens={effective_max_tokens}")

    max_retries = 5
    base_delay  = 30  # seconds
    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=effective_max_tokens,
                temperature=0.7,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt},
                ],
            )
            break
        except openai.RateLimitError as e:
            if attempt == max_retries:
                raise
            delay = base_delay * (2 ** (attempt - 1))  # 30 60 120 240 …
            print(f"  ⚠️  Rate limit hit (attempt {attempt}/{max_retries})."
                  f" Retrying in {delay}s …")
            time.sleep(delay)

    text = response.choices[0].message.content
    usage = response.usage
    total_tokens = usage.prompt_tokens + usage.completion_tokens
    print(f"  ✅ response  in={usage.prompt_tokens}  out={usage.completion_tokens}  total={total_tokens}"
          f"  chars={len(text)}")

    # Log if we're under-utilizing available tokens
    if usage.completion_tokens < effective_max_tokens * 0.7:
        print(f"  ℹ️  Token usage is {usage.completion_tokens}/{effective_max_tokens} ({100*usage.completion_tokens//effective_max_tokens}%) - report could be more detailed")
    return text


def call_llm(ticker: str, context: str, analysis_type: str,
             provider: str, model: str, max_tokens: int) -> str:
    """Dispatch to the appropriate LLM provider."""
    if provider == "openai":
        return call_openai(ticker, context, analysis_type, model, max_tokens)
    else:
        return call_claude(ticker, context, analysis_type, model, max_tokens)


# ═════════════════════════════════════════════════════════════════════════════
# 5.  SAVE  (same-day deduplication)
# ═════════════════════════════════════════════════════════════════════════════

def save_report(ticker: str, content: str, output_dir: Path,
                analysis_type: str, provider: str = "claude") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    meta    = ANALYSIS_TYPES[analysis_type]
    prefix  = meta["filename_prefix"]
    label   = meta["label"]
    ext     = meta.get("ext", ".md")

    # Map provider to simple suffix
    model_suffix = "openai" if provider == "openai" else "claude"
    base    = f"{prefix}_{TODAY}_{model_suffix}"

    # Same-day deduplication: base.ext → base-2.ext → base-3.ext …
    path    = output_dir / f"{base}{ext}"
    counter = 2
    while path.exists():
        path    = output_dir / f"{base}-{counter}{ext}"
        counter += 1

    if ext == ".html":
        # HTML output: write as-is (Claude generates complete HTML)
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


# ═════════════════════════════════════════════════════════════════════════════
# 6.  CLI
# ═════════════════════════════════════════════════════════════════════════════

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
        help="Directory to save the report (default: claude_code/<ticker>/)",
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
    args          = parse_args()
    ticker        = args.ticker.upper()
    analysis_type = args.analysis_type
    provider      = args.provider
    output_dir    = args.output_dir or (Path("claude_code") / ticker.lower())

    label  = ANALYSIS_TYPES[analysis_type]["label"]
    banner = f"  {ticker}  |  {label}  |  provider: {provider}  |  model: {args.model}  |  out: {output_dir}"
    sep    = "=" * max(70, len(banner) + 4)
    print(f"\n{sep}\n{banner}\n{sep}\n")

    print("[1/3] Fetching financial data from Yahoo Finance …")
    data    = fetch_data(ticker)
    context = build_context(data, analysis_type)

    print(f"[2/3] Calling {provider.upper()} API …")
    report  = call_llm(ticker, context, analysis_type, provider, args.model, args.max_tokens)

    print("[3/3] Saving report …")
    save_report(ticker, report, output_dir, analysis_type, provider=provider)

    print(f"\n{sep}\n  Done!\n{sep}\n")


if __name__ == "__main__":
    main()
