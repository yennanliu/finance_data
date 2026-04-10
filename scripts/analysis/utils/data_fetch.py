"""
Data fetching utilities for financial data from multiple sources.
Sources: Yahoo Finance, Finviz, StockAnalysis, Macrotrends
"""

from __future__ import annotations

import re
import sys
import time

from .formatting import money


# ── HTTP helpers ─────────────────────────────────────────────────────

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def _get_soup(url: str, retries: int = 2):
    """Fetch a URL and return a BeautifulSoup object."""
    import requests
    from bs4 import BeautifulSoup

    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=15)
            if resp.status_code == 200:
                return BeautifulSoup(resp.text, "html.parser")
            if resp.status_code == 403:
                return None  # blocked, skip
        except Exception:
            if attempt < retries:
                time.sleep(1)
    return None


# ── Finviz ───────────────────────────────────────────────────────────

def fetch_finviz(ticker: str) -> dict:
    """Scrape Finviz snapshot table for valuation & key ratios."""
    print(f"  → finviz: {ticker}")
    url = f"https://finviz.com/quote.ashx?t={ticker}&ty=c&p=d&b=1"
    soup = _get_soup(url)
    if soup is None:
        return {}

    data = {}
    try:
        table = soup.find("table", class_="snapshot-table2")
        if not table:
            return {}
        tds = table.find_all("td")
        # pairs of (label, value) in sequential tds
        for i in range(0, len(tds) - 1, 2):
            label = tds[i].get_text(strip=True)
            value = tds[i + 1].get_text(strip=True)
            data[label] = value
    except Exception:
        pass
    return data


def _format_finviz(data: dict) -> str:
    """Format Finviz data into readable text block."""
    if not data:
        return "  (no Finviz data available)"

    # Key metrics to display, grouped
    groups = {
        "Valuation": [
            "P/E", "Forward P/E", "PEG", "P/S", "P/B", "P/C", "P/FCF",
            "EPS (ttm)", "EPS next Y", "EPS next 5Y", "EPS past 5Y",
        ],
        "Performance": [
            "Perf Week", "Perf Month", "Perf Quarter", "Perf Half Y",
            "Perf Year", "Perf YTD",
        ],
        "Profitability": [
            "ROA", "ROE", "ROI", "Gross Margin", "Oper. Margin",
            "Profit Margin",
        ],
        "Financial Health": [
            "Current Ratio", "Quick Ratio", "Debt/Eq", "LT Debt/Eq",
        ],
        "Analyst & Ownership": [
            "Target Price", "Recom", "Short Float", "Short Ratio",
            "Insider Own", "Insider Trans", "Inst Own", "Inst Trans",
        ],
        "Technicals": [
            "SMA20", "SMA50", "SMA200", "RSI (14)", "Volatility",
            "Avg Volume", "Rel Volume", "Beta",
        ],
    }

    lines = []
    for group_name, keys in groups.items():
        items = [(k, data[k]) for k in keys if k in data and data[k] != "-"]
        if items:
            lines.append(f"  [{group_name}]")
            for k, v in items:
                lines.append(f"    {k:<18} {v}")
    return "\n".join(lines) if lines else "  (no Finviz data available)"


# ── StockAnalysis ────────────────────────────────────────────────────

def fetch_stockanalysis(ticker: str) -> dict:
    """Scrape StockAnalysis.com for financial ratios and key stats."""
    print(f"  → stockanalysis: {ticker}")
    result = {"ratios": "", "growth": ""}

    # Financial ratios page
    url = f"https://stockanalysis.com/stocks/{ticker.lower()}/financials/?p=annual"
    soup = _get_soup(url)
    if soup:
        try:
            tables = soup.find_all("table")
            if tables:
                result["financials_annual"] = _html_table_to_text(tables[0], max_rows=25)
        except Exception:
            pass

    time.sleep(0.5)

    # Quarterly financials
    url_q = f"https://stockanalysis.com/stocks/{ticker.lower()}/financials/?p=quarterly"
    soup_q = _get_soup(url_q)
    if soup_q:
        try:
            tables = soup_q.find_all("table")
            if tables:
                result["financials_quarterly"] = _html_table_to_text(tables[0], max_rows=15)
        except Exception:
            pass

    time.sleep(0.5)

    # Balance sheet
    url_bs = f"https://stockanalysis.com/stocks/{ticker.lower()}/financials/balance-sheet/"
    soup_bs = _get_soup(url_bs)
    if soup_bs:
        try:
            tables = soup_bs.find_all("table")
            if tables:
                result["balance_sheet"] = _html_table_to_text(tables[0], max_rows=20)
        except Exception:
            pass

    return result


def _html_table_to_text(table, max_rows: int = 20) -> str:
    """Convert an HTML table element to formatted text."""
    rows = table.find_all("tr")
    if not rows:
        return ""
    lines = []
    for row in rows[:max_rows + 1]:
        cells = row.find_all(["th", "td"])
        vals = [c.get_text(strip=True) for c in cells]
        if vals:
            lines.append("  " + "  |  ".join(f"{v:<14}" for v in vals[:8]))
    return "\n".join(lines)


def _format_stockanalysis(data: dict) -> str:
    """Format StockAnalysis data into readable text blocks."""
    sections = []
    if data.get("financials_annual"):
        sections.append(f"  [Annual Income Statement]\n{data['financials_annual']}")
    if data.get("financials_quarterly"):
        sections.append(f"  [Quarterly Income Statement]\n{data['financials_quarterly']}")
    if data.get("balance_sheet"):
        sections.append(f"  [Balance Sheet]\n{data['balance_sheet']}")
    return "\n\n".join(sections) if sections else "  (no StockAnalysis data available)"


# ── Roic.ai ──────────────────────────────────────────────────────────

def fetch_roic(ticker: str) -> dict:
    """Scrape Roic.ai for historical value investing metrics (10Y+)."""
    print(f"  → roic.ai: {ticker}")
    url = f"https://roic.ai/company/{ticker.upper()}"
    soup = _get_soup(url)
    if soup is None:
        return {}

    result = {}
    try:
        tables = soup.find_all("table")
        for i, table in enumerate(tables[:7]):
            rows = table.find_all("tr")
            if not rows:
                continue
            # Use first row as header to identify the table
            header_cells = rows[0].find_all(["th", "td"])
            headers = [c.get_text(strip=True) for c in header_cells]

            data_rows = []
            for row in rows[1:]:
                cells = row.find_all(["th", "td"])
                vals = [c.get_text(strip=True) for c in cells]
                if vals and any(v for v in vals):
                    data_rows.append(vals)

            if data_rows:
                result[f"table_{i}"] = {"headers": headers, "rows": data_rows}
    except Exception:
        pass
    return result


def _format_roic(data: dict) -> str:
    """Format Roic.ai data into readable text."""
    if not data:
        return "  (no Roic.ai data available)"

    lines = []
    for key, table_data in data.items():
        headers = table_data.get("headers", [])
        rows = table_data.get("rows", [])
        if not rows:
            continue

        # Determine column widths (cap at 14 chars, show up to 8 cols)
        cols = min(len(headers), 8) if headers else min(len(rows[0]), 8)
        if headers:
            lines.append("  " + "  |  ".join(f"{h[:14]:<14}" for h in headers[:cols]))
            lines.append("  " + "-" * (cols * 18))
        for row in rows:
            lines.append("  " + "  |  ".join(f"{v[:14]:<14}" for v in row[:cols]))
        lines.append("")
    return "\n".join(lines) if lines else "  (no Roic.ai data available)"


def _parse_finviz_number(val: str):
    """Parse Finviz string value into a float. Returns None on failure."""
    if not val or val == "-":
        return None
    val = val.strip()
    try:
        # Handle percentages: "12.34%" → 0.1234
        if val.endswith("%"):
            return float(val[:-1]) / 100
        # Handle magnitudes: "1.23B", "456.7M", "12.3K"
        multipliers = {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3}
        if val[-1] in multipliers:
            return float(val[:-1]) * multipliers[val[-1]]
        return float(val.replace(",", ""))
    except (ValueError, IndexError):
        return None


def _merge_finviz_into_info(info: dict, finviz: dict) -> dict:
    """Backfill missing Yahoo Finance info fields using Finviz data."""
    if not finviz:
        return info

    # Mapping: Finviz label → (Yahoo info key, is_percentage)
    # is_percentage=True means Finviz shows "12.3%" and Yahoo expects 0.123
    mapping = {
        "P/E": ("trailingPE", False),
        "Forward P/E": ("forwardPE", False),
        "PEG": ("pegRatio", False),
        "P/S": ("priceToSalesTrailing12Months", False),
        "P/B": ("priceToBook", False),
        "EPS (ttm)": ("trailingEps", False),
        "EPS next Y": ("forwardEps", False),
        "ROA": ("returnOnAssets", True),
        "ROE": ("returnOnEquity", True),
        "Gross Margin": ("grossMargins", True),
        "Oper. Margin": ("operatingMargins", True),
        "Profit Margin": ("profitMargins", True),
        "Current Ratio": ("currentRatio", False),
        "Quick Ratio": ("quickRatio", False),
        "Debt/Eq": ("debtToEquity", False),
        "Beta": ("beta", False),
        "Short Ratio": ("shortRatio", False),
        "Short Float": ("shortPercentOfFloat", True),
        "Target Price": ("targetMeanPrice", False),
        "Recom": ("recommendationMean", False),
        "Insider Own": ("heldPercentInsiders", True),
        "Inst Own": ("heldPercentInstitutions", True),
        "Market Cap": ("marketCap", False),
        "Avg Volume": ("averageVolume", False),
        "Volatility": None,  # skip, format differs
        "Dividend %": ("dividendYield", True),
        "Payout": ("payoutRatio", True),
    }

    filled = []
    for fv_key, spec in mapping.items():
        if spec is None:
            continue
        yf_key, is_pct = spec
        # Only backfill if Yahoo value is missing
        if info.get(yf_key) is not None:
            continue
        fv_val = finviz.get(fv_key)
        if not fv_val or fv_val == "-":
            continue
        parsed = _parse_finviz_number(fv_val)
        if parsed is not None:
            # Finviz percentages are already parsed as decimals by _parse_finviz_number
            info[yf_key] = parsed
            filled.append(yf_key)

    if filled:
        print(f"  ✓ Backfilled from Finviz: {', '.join(filled)}")

    return info


def _get_yf():
    """Lazy import of yfinance."""
    try:
        import yfinance as yf
        return yf
    except ImportError:
        sys.exit("ERROR: 'yfinance' not installed.  Run: pip install yfinance")


def fetch_data(ticker: str) -> dict:
    """Download fundamentals, price history, and news from Yahoo Finance."""
    yf = _get_yf()
    print(f"  → yfinance: {ticker}")
    t = yf.Ticker(ticker)
    info = t.info or {}

    # price history (2Y for richer technical context)
    try:
        hist = t.history(period="2y")
        price_now = float(hist["Close"].iloc[-1]) if not hist.empty else None
        price_52w = hist.tail(252)
        price_52w_high = float(price_52w["High"].max()) if not hist.empty else None
        price_52w_low = float(price_52w["Low"].min()) if not hist.empty else None
        monthly = hist["Close"].resample("ME").last().dropna()
        price_series = {str(k)[:7]: round(float(v), 2) for k, v in monthly.items()}
    except Exception:
        hist = None
        price_now = price_52w_high = price_52w_low = None
        price_series = {}

    # financial statements
    def _safe_df(fn):
        try:
            df = fn()
            return df if df is not None and not df.empty else None
        except Exception:
            return None

    # analyst upgrades/downgrades (last 10 actions)
    upgrades_text = "  (no data)"
    try:
        upg = t.upgrades_downgrades
        if upg is not None and not upg.empty:
            upg = upg.sort_index(ascending=False).head(10)
            lines = []
            for dt, row in upg.iterrows():
                date_str = str(dt)[:10]
                firm = str(row.get("Firm", ""))[:20]
                action = str(row.get("Action", ""))
                to_grade = str(row.get("ToGrade", ""))
                lines.append(f"  {date_str}  {firm:<20}  {action:<12}  → {to_grade}")
            upgrades_text = "\n".join(lines)
    except Exception:
        pass

    # insider transactions
    insider_text = "  (no data)"
    try:
        ins = t.insider_transactions
        if ins is not None and not ins.empty:
            ins = ins.sort_index(ascending=False).head(20)
            lines = ["  日期          姓名/職稱                  交易類型      股數         價值"]
            for dt, row in ins.iterrows():
                date_str = str(dt)[:10]
                name = str(row.get("Insider", row.get("Name", "")))[:24]
                tx_type = str(row.get("Transaction", ""))[:16]
                shares = row.get("Shares", 0)
                value = row.get("Value", 0)
                try:
                    flag = "🟢" if "Purchase" in tx_type or "Buy" in tx_type else "🔴" if "Sale" in tx_type or "Sell" in tx_type else "⬜"
                except Exception:
                    flag = "⬜"
                lines.append(
                    f"  {date_str}  {name:<24}  {tx_type:<16}  {shares:>10,.0f}  {money(value)}  {flag}"
                )
            insider_text = "\n".join(lines)
    except Exception:
        pass

    # major holders / institutional holders
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
                holder = str(row.get("Holder", ""))[:32]
                shares = row.get("Shares", 0)
                pct_out = row.get("% Out", float("nan"))
                value = row.get("Value", 0)
                chg = row.get("% Change", float("nan"))
                try:
                    chg_str = f"{float(chg):+.2f}%"
                    arrow = "🟢" if float(chg) > 0 else "🔴" if float(chg) < 0 else "⬜"
                except Exception:
                    chg_str, arrow = "N/A", "⬜"
                lines.append(
                    f"  {holder:<32}  {shares:>14,.0f}  {pct_out:.2%}  {money(value)}  {chg_str} {arrow}"
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
                pct = row.get("% Out", float("nan"))
                value = row.get("Value", 0)
                lines.append(f"  {holder:<36}  {shares:>14,.0f}  {pct:.2%}  {money(value)}")
            mutualfund_text = "\n".join(lines)
    except Exception:
        pass

    # earnings history (beats/misses)
    earnings_text = "  (no data)"
    try:
        eh = t.earnings_history
        if eh is not None and not eh.empty:
            eh = eh.sort_index(ascending=False).head(8)
            lines = ["  Quarter      EPS Est  EPS Act  Surprise%"]
            for dt, row in eh.iterrows():
                q = str(dt)[:10]
                est = row.get("epsestimate", float("nan"))
                act = row.get("epsactual", float("nan"))
                surp = row.get("epsdifference", float("nan"))
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

    # ── Additional sources (best-effort, non-blocking) ──
    finviz_data = {}
    stockanalysis_data = {}
    roic_data = {}

    try:
        finviz_data = fetch_finviz(ticker)
    except Exception as e:
        print(f"  ⚠ Finviz fetch failed: {e}")

    try:
        stockanalysis_data = fetch_stockanalysis(ticker)
    except Exception as e:
        print(f"  ⚠ StockAnalysis fetch failed: {e}")

    try:
        roic_data = fetch_roic(ticker)
    except Exception as e:
        print(f"  ⚠ Roic.ai fetch failed: {e}")

    # ── Merge: backfill missing Yahoo info from Finviz ──
    info = _merge_finviz_into_info(info, finviz_data)

    return {
        "ticker": ticker,
        "info": info,
        "hist": hist,
        "income": _safe_df(lambda: t.financials),
        "income_q": _safe_df(lambda: t.quarterly_financials),
        "balance": _safe_df(lambda: t.balance_sheet),
        "balance_q": _safe_df(lambda: t.quarterly_balance_sheet),
        "cashflow": _safe_df(lambda: t.cashflow),
        "cashflow_q": _safe_df(lambda: t.quarterly_cashflow),
        "news": (t.news or [])[:10],
        "price_now": price_now,
        "price_52w_high": price_52w_high,
        "price_52w_low": price_52w_low,
        "price_series": price_series,
        "upgrades_text": upgrades_text,
        "earnings_text": earnings_text,
        "insider_text": insider_text,
        "major_holders_text": major_holders_text,
        "institutional_text": institutional_text,
        "mutualfund_text": mutualfund_text,
        # Additional sources
        "finviz_data": finviz_data,
        "finviz_text": _format_finviz(finviz_data),
        "stockanalysis_data": stockanalysis_data,
        "stockanalysis_text": _format_stockanalysis(stockanalysis_data),
        "roic_data": roic_data,
        "roic_text": _format_roic(roic_data),
    }


def price_ascii_chart(price_series: dict) -> str:
    """Generate ASCII chart from price series."""
    if not price_series:
        return "  (no price history)"
    lines = [f"  {'月份':>7}  {'收盤價':>8}  走勢"]
    min_p = min(price_series.values())
    max_p = max(price_series.values())
    rng = max_p - min_p or 1
    for month, price in price_series.items():
        bars = int((price - min_p) / rng * 30)
        lines.append(f"  {month}  {price:>8.2f}  {'█' * bars}")
    return "\n".join(lines)


def compute_moving_average_charts(hist) -> str:
    """Generate ASCII charts for moving averages (5, 10, 20, 60, 120, 240 days)."""
    if hist is None or hist.empty:
        return ""

    try:
        import pandas as pd

        close = hist["Close"]
        ma_periods = [5, 10, 20, 60, 120, 240]

        ma_lines = ["  ── 移動平均線 (MA) 走勢 ──"]

        for period in ma_periods:
            if len(close) < period:
                ma_lines.append(f"  MA{period:3d}: (資料不足，需要{period}筆數據)")
                continue

            ma = close.rolling(period).mean()
            last_ma = ma.iloc[-1]

            # Get last 30 values for sparkline
            ma_tail = ma.tail(30)
            if ma_tail.isna().all():
                ma_lines.append(f"  MA{period:3d}: N/A")
                continue

            # Create sparkline
            ma_valid = ma_tail.dropna()
            if len(ma_valid) > 0:
                min_val = ma_valid.min()
                max_val = ma_valid.max()
                rng = max_val - min_val if max_val != min_val else 1

                sparkline = ""
                chars = "▁▂▃▄▅▆▇█"
                for val in ma_valid:
                    pos = int((val - min_val) / rng * 8)
                    pos = max(0, min(pos, len(chars) - 1))  # Clamp to valid range
                    sparkline += chars[pos]

                # Current price vs MA
                current = close.iloc[-1]
                diff = current - last_ma
                pct_diff = (diff / last_ma * 100) if last_ma != 0 else 0
                arrow = "▲" if diff > 0 else "▼" if diff < 0 else "="

                ma_lines.append(
                    f"  MA{period:3d}: ${last_ma:8.2f}  {arrow} {diff:+7.2f} ({pct_diff:+6.2f}%)  {sparkline}"
                )
            else:
                ma_lines.append(f"  MA{period:3d}: N/A")

        return "\n".join(ma_lines)
    except Exception as e:
        return f"  (MA chart error: {e})"


def generate_plotly_candlestick_chart(hist, ticker: str) -> str:
    """Generate an interactive candlestick chart with MA(30,60,200) overlays using Plotly.

    Args:
        hist: OHLCV DataFrame from yfinance (must have OHLCV columns)
        ticker: Stock ticker symbol

    Returns:
        HTML embed code with <div> and <script>, or empty string on failure
    """
    if hist is None or hist.empty or len(hist) < 60:
        return ""

    try:
        import plotly.graph_objects as go
        import pandas as pd

        # Use last 200 trading days for good chart visibility
        df = hist[["Open", "High", "Low", "Close", "Volume"]].tail(200).copy()

        # Calculate MAs
        df["MA30"] = df["Close"].rolling(window=30).mean()
        df["MA60"] = df["Close"].rolling(window=60).mean()
        df["MA200"] = df["Close"].rolling(window=200).mean()

        # Create candlestick figure
        fig = go.Figure()

        # Add candlestick chart
        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df["Open"],
                high=df["High"],
                low=df["Low"],
                close=df["Close"],
                name="價格",
                hovertemplate=(
                    "<b>%{x|%Y-%m-%d}</b><br>"
                    "開: $%{open:.2f}<br>"
                    "高: $%{high:.2f}<br>"
                    "低: $%{low:.2f}<br>"
                    "收: $%{close:.2f}<extra></extra>"
                ),
            )
        )

        # Add MA lines with custom colors
        ma_config = [
            ("MA30", "#2196F3", "點線"),
            ("MA60", "#9C27B0", "虛線"),
            ("MA200", "#FF6F00", "實線"),
        ]

        for ma_col, color, dash in ma_config:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df[ma_col],
                    mode="lines",
                    name=ma_col,
                    line=dict(color=color, width=2, dash="dash" if dash == "虛線" else "solid"),
                    hovertemplate=f"{ma_col}: $%{{y:.2f}}<extra></extra>",
                )
            )

        # Update layout
        fig.update_layout(
            title=f"{ticker}  |  MA(30/60/200)  |  最近200交易日",
            yaxis_title="股價 (USD)",
            xaxis_title="日期",
            hovermode="x unified",
            template="plotly_dark",
            height=500,
            xaxis_rangeslider_visible=False,
            font=dict(size=11),
        )

        # Convert to HTML embed
        html_embed = fig.to_html(include_plotlyjs="cdn", div_id="candlestick-chart")
        return html_embed

    except ImportError:
        print(f"  ⚠ plotly not installed, skipping interactive chart generation")
        return ""
    except Exception as e:
        print(f"  ⚠ Interactive chart generation failed: {e}")
        return ""


def generate_candlestick_chart(hist, ticker: str, output_path: str) -> str:
    """Generate a candlestick chart with MA(30,60,200) overlays and save as PNG.

    Args:
        hist: OHLCV DataFrame from yfinance (must have OHLCV columns)
        ticker: Stock ticker symbol
        output_path: File path where PNG will be saved

    Returns:
        output_path if successful, empty string on failure
    """
    if hist is None or hist.empty or len(hist) < 60:
        return ""

    try:
        import mplfinance as mpf
        import matplotlib
        import matplotlib.patches as mpatches
        matplotlib.use("Agg")  # headless backend, no display

        # Use last 200 trading days for good chart visibility
        df = hist[["Open", "High", "Low", "Close", "Volume"]].tail(200).copy()

        # Define MA periods and colors
        ma_config = [(30, "#2196F3"), (60, "#9C27B0"), (200, "#212121")]

        # Build MA list based on available data
        mavs = []
        ma_colors = []
        legend_labels = []
        for period, color in ma_config:
            if len(df) >= period:
                mavs.append(period)
                ma_colors.append(color)
                legend_labels.append(f"MA{period}")

        if not mavs:
            return ""

        # Create custom style
        style = mpf.make_mpf_style(
            base_mpf_style="charles",
            rc={
                "axes.labelsize": 9,
                "xtick.labelsize": 8,
                "ytick.labelsize": 8,
                "legend.fontsize": 10,
            },
        )

        # Generate the chart with returnfig to add custom legend
        fig, axes = mpf.plot(
            df,
            type="candle",
            mav=tuple(mavs),
            volume=True,
            style=style,
            mavcolors=ma_colors,
            title=f"{ticker}  |  MA{mavs}  |  最近200交易日",
            figsize=(12, 7),
            returnfig=True,
        )

        # Add custom legend with MA labels
        legend_patches = [
            mpatches.Patch(facecolor=color, label=label)
            for label, color in zip(legend_labels, ma_colors)
        ]
        axes[0].legend(
            handles=legend_patches,
            loc="upper left",
            frameon=True,
            fancybox=True,
            shadow=True,
            fontsize=10,
        )

        # Save the figure
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        import matplotlib.pyplot as plt
        plt.close(fig)

        return output_path
    except ImportError:
        print(f"  ⚠ mplfinance not installed, skipping chart generation")
        return ""
    except Exception as e:
        print(f"  ⚠ Chart generation failed: {e}")
        return ""


def compute_technicals(hist) -> str:
    """Compute technical indicators from OHLCV history DataFrame."""
    if hist is None or hist.empty:
        return "  (no OHLC data)"
    try:
        import pandas as pd
        import numpy as np

        close = hist["Close"]
        high = hist["High"]
        low = hist["Low"]
        volume = hist["Volume"]

        # Moving averages
        ma5 = close.rolling(5).mean()
        ma10 = close.rolling(10).mean()
        ma20 = close.rolling(20).mean()
        ma50 = close.rolling(50).mean()
        ma200 = close.rolling(200).mean()

        # RSI-14
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, float("nan"))
        rsi = 100 - (100 / (1 + rs))

        # MACD (12/26/9)
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        hist_m = macd - signal

        # Bollinger Bands (20, 2σ)
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_up = bb_mid + 2 * bb_std
        bb_lo = bb_mid - 2 * bb_std
        bb_pct = (close - bb_lo) / (bb_up - bb_lo).replace(0, float("nan"))

        # ATR-14
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean()

        # Stochastic %K/%D (14,3,3)
        low14 = low.rolling(14).min()
        high14 = high.rolling(14).max()
        stoch_k = 100 * (close - low14) / (high14 - low14).replace(0, float("nan"))
        stoch_d = stoch_k.rolling(3).mean()

        # ADX-14 (trend strength)
        up_move = high.diff()
        down_move = -low.diff()
        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
        atr14_adx = tr.ewm(alpha=1/14, adjust=False).mean()
        plus_di = 100 * plus_dm.ewm(alpha=1/14, adjust=False).mean() / atr14_adx.replace(0, float("nan"))
        minus_di = 100 * minus_dm.ewm(alpha=1/14, adjust=False).mean() / atr14_adx.replace(0, float("nan"))
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float("nan"))
        adx = dx.ewm(alpha=1/14, adjust=False).mean()

        # OBV (On-Balance Volume)
        obv_direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
        obv = (volume * obv_direction).cumsum()
        obv_ma20 = obv.rolling(20).mean()

        # Volume
        avg_vol_20 = volume.rolling(20).mean()
        avg_vol_50 = volume.rolling(50).mean()

        # Last values
        last = close.iloc[-1]
        last_ma20 = ma20.iloc[-1]
        last_ma50 = ma50.iloc[-1]
        last_ma200 = ma200.iloc[-1] if len(close) >= 200 else float("nan")
        last_rsi = rsi.iloc[-1]
        last_macd = macd.iloc[-1]
        last_signal = signal.iloc[-1]
        last_hist_m = hist_m.iloc[-1]
        last_bb_up = bb_up.iloc[-1]
        last_bb_lo = bb_lo.iloc[-1]
        last_bb_pct = bb_pct.iloc[-1]
        last_atr = atr14.iloc[-1]
        last_stoch_k = stoch_k.iloc[-1]
        last_stoch_d = stoch_d.iloc[-1]
        last_adx = adx.iloc[-1]
        last_plus_di = plus_di.iloc[-1]
        last_minus_di = minus_di.iloc[-1]
        last_obv = obv.iloc[-1]
        last_obv_ma = obv_ma20.iloc[-1]
        last_vol = volume.iloc[-1]
        last_avg_vol = avg_vol_20.iloc[-1]
        last_avg_vol50 = avg_vol_50.iloc[-1]

        # 52-week position
        w52_high = float(high.tail(252).max())
        w52_low = float(low.tail(252).min())
        w52_pct = (last - w52_low) / (w52_high - w52_low) * 100 if w52_high != w52_low else 50

        # RSI divergence hint (last 20 bars)
        price_20 = close.tail(20)
        rsi_20 = rsi.tail(20)
        price_dir = "⬆" if price_20.iloc[-1] > price_20.iloc[0] else "⬇"
        rsi_dir = "⬆" if rsi_20.iloc[-1] > rsi_20.iloc[0] else "⬇"
        divergence = ""
        if price_dir == "⬆" and rsi_dir == "⬇":
            divergence = "⚠️ 頂背離 (Bearish Divergence)"
        elif price_dir == "⬇" and rsi_dir == "⬆":
            divergence = "⚠️ 底背離 (Bullish Divergence)"
        else:
            divergence = "無明顯背離"

        # Weekly OHLCV table (last 20 weeks)
        weekly_close = close.resample("W").last().dropna().tail(20)
        weekly_volume = volume.resample("W").sum().dropna().tail(20)
        ohlcv_lines = ["  日期          收盤      RSI     MACD柱    週成交量"]
        for wdt in weekly_close.index:
            wdt_str = wdt.strftime("%Y-%m-%d")
            wc = weekly_close.get(wdt, float("nan"))
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

        # Get MA charts
        ma_charts = compute_moving_average_charts(hist)

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

{ma_charts}

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


__all__ = [
    "fetch_data", "price_ascii_chart", "compute_technicals", "generate_candlestick_chart",
    "fetch_finviz", "fetch_stockanalysis", "fetch_roic",
]
