"""Data sources layer: Yahoo Finance (yfinance) + web scrapers
(Finviz, StockAnalysis.com, Roic.ai). This is the network-touching layer;
pure formatters for the scraped payloads live alongside their fetchers.
"""

from __future__ import annotations

import re
import time

from ..exceptions import DataFetchError
from ..utils.formatting import money
from .prices import to_yf_symbol


# ── HTTP helpers ─────────────────────────────────────────────────────

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def _num(value, default: float = 0.0) -> float:
    """Coerce a possibly None/NaN/str value to float; return ``default`` on failure.

    Holder/insider rows from yfinance routinely carry missing values; formatting
    those with ``:,.0f`` / ``:.2%`` would raise and (under the broad try/except
    around each section) silently discard the *entire* section. This keeps a bad
    cell from sinking the rest.
    """
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return default if f != f else f  # NaN → default


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
            # Other non-200s (e.g. transient 5xx) → raise so the retry path
            # applies its backoff instead of immediately re-requesting.
            resp.raise_for_status()
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
    except ImportError as exc:
        # Raise (don't sys.exit) so callers / test runners can handle it.
        raise DataFetchError("'yfinance' not installed. Run: uv sync") from exc


def yahoo_news(symbol: str, count: int = 10) -> list[dict]:
    """Yahoo Finance headlines for *symbol*, newest first ([] on any failure).

    ``Ticker.news`` reads Yahoo's ``/xhr/ncp`` endpoint, which now 404s, and
    yfinance (still in 1.7.0) swallows that into ``[]`` -- every news block was
    silently empty. The search endpoint behind ``yf.Search`` still serves news,
    in the flat ``title`` / ``publisher`` / ``link`` / ``providerPublishTime``
    shape the callers read.
    """
    try:
        return _get_yf().Search(symbol, max_results=0, news_count=count,
                                enable_fuzzy_query=False).news or []
    except Exception:
        return []


# Local close of each exchange we cover; a bar dated today before this time is a
# session still in progress, not a close.
_SESSION_CLOSE = {"Asia/Taipei": (13, 30)}
_DEFAULT_SESSION_CLOSE = (16, 0)  # New York


def last_completed_close(hist, now=None):
    """``(close, 'YYYY-MM-DD')`` of the last *finished* session in ``hist``.

    yfinance's daily history includes today's bar while the market is open, so
    ``Close.iloc[-1]`` mid-session is an intraday tick. Reports cite the price
    as a close, so a bar dated today before the exchange's close is skipped.
    A tz-naive index carries no session information and is taken as-is.
    """
    from datetime import datetime

    if hist is None or hist.empty:
        return None, None
    closes = hist["Close"].dropna()
    if closes.empty:
        return None, None
    tz = getattr(closes.index, "tz", None)
    if tz is not None:
        now = now or datetime.now(tz)
        close_h, close_m = _SESSION_CLOSE.get(str(tz), _DEFAULT_SESSION_CLOSE)
        last = closes.index[-1]
        open_session = (last.date() == now.date()
                        and (now.hour, now.minute) < (close_h, close_m))
        if open_session and len(closes) > 1:
            closes = closes.iloc[:-1]
    return float(closes.iloc[-1]), str(closes.index[-1])[:10]


def quote_close(info: dict):
    """``(price, 'YYYY-MM-DD')`` from Yahoo's regular-market quote, if it is a close.

    Yahoo's daily history sometimes leaves the latest session's bar empty (all
    NaN) or omits it, while the quote still carries the official close: on
    2026-10-23 the SKHY report was given the 10-21 close ($143.25) although the
    10-22 close ($131.69) was in ``regularMarketPrice``. A quote stamped before
    the exchange's close is an intraday tick and is ignored.
    """
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    price, stamp = info.get("regularMarketPrice"), info.get("regularMarketTime")
    tzname = info.get("exchangeTimezoneName")
    try:
        price = float(price)
        tz = ZoneInfo(tzname) if tzname else timezone.utc
        when = datetime.fromtimestamp(int(stamp), tz)
    except (TypeError, ValueError, KeyError, OSError):
        return None, None
    if price != price or price <= 0:
        return None, None
    close_h, close_m = _SESSION_CLOSE.get(tzname or "", _DEFAULT_SESSION_CLOSE)
    if (when.hour, when.minute) < (close_h, close_m):
        return None, None
    return price, when.date().isoformat()


def complete_bars(hist, info: dict, now=None):
    """``(hist, close_source)``: daily bars every indicator can be computed from.

    After the US close Yahoo often publishes the new session's bar with volume
    but NaN open/high/low/close. ``compute_technicals`` read that bar as the
    latest, so on 2026-10-23 eight technical reports were given ``$nan`` for the
    price, no MA/RSI/ATR/Bollinger values and no support/resistance levels, and
    were written anyway. Bars without a close are dropped, as is a bar for a
    session still in progress; if the quote carries a newer official close
    (:func:`quote_close`), it is appended as that session's bar. ``close_source``
    is ``"daily_bar"``, ``"quote"`` or ``None`` when no bar is left.
    """
    from datetime import datetime

    import pandas as pd

    info = info or {}
    if hist is None or hist.empty:
        return hist, None
    dropped = hist[hist["Close"].isna()]
    hist = hist[hist["Close"].notna()]
    if hist.empty:
        return hist, None
    tz = getattr(hist.index, "tz", None)
    if tz is not None:
        local = (now or datetime.now(tz)).astimezone(tz)
        close_h, close_m = _SESSION_CLOSE.get(str(tz), _DEFAULT_SESSION_CLOSE)
        if (hist.index[-1].date() == local.date()
                and (local.hour, local.minute) < (close_h, close_m)
                and len(hist) > 1):
            hist = hist.iloc[:-1]

    q_price, q_date = quote_close(info)
    if not q_date or q_date <= str(hist.index[-1])[:10]:
        return hist, "daily_bar"
    stamp = pd.Timestamp(q_date)
    stamp = stamp.tz_localize(tz) if tz is not None else stamp
    # The empty bar Yahoo published for this session still carries its volume.
    same_day = dropped[[str(i)[:10] == q_date for i in dropped.index]]
    volume = info.get("regularMarketVolume")
    if volume is None and not same_day.empty:
        volume = same_day["Volume"].iloc[-1]

    def _num(key):
        v = info.get(key)
        return float(v) if isinstance(v, (int, float)) and v == v and v > 0 else q_price

    bar = pd.DataFrame({
        "Open": [_num("regularMarketOpen")],
        "High": [max(_num("regularMarketDayHigh"), q_price)],
        "Low": [min(_num("regularMarketDayLow"), q_price)],
        "Close": [q_price],
        "Volume": [float(volume) if volume is not None and volume == volume else 0.0],
    }, index=pd.DatetimeIndex([stamp], name=hist.index.name))
    for col in hist.columns.difference(bar.columns):
        bar[col] = 0.0
    return pd.concat([hist, bar[hist.columns]]), "quote"


def fetch_data(ticker: str) -> dict:
    """Download fundamentals, price history, and news from Yahoo Finance."""
    yf = _get_yf()
    # Yahoo needs the exchange suffix: a bare "0050" is a 404, which left the
    # 0050 report with no price or statements at all, written from memory.
    symbol = to_yf_symbol(ticker)
    print(f"  → yfinance: {symbol}")
    t = yf.Ticker(symbol)
    # .info is network-dependent and frequently raises (rate limits, bad
    # tickers, API drift); degrade to an empty dict rather than crash the run.
    try:
        info = t.info or {}
    except Exception as e:
        print(f"  ⚠ Failed to fetch ticker info: {e}")
        info = {}

    # price history (2Y for richer technical context)
    try:
        hist, close_source = complete_bars(t.history(period="2y"), info)
        price_now, price_date = last_completed_close(hist)
        price_52w = hist.tail(252)
        price_52w_high = float(price_52w["High"].max()) if not hist.empty else None
        price_52w_low = float(price_52w["Low"].min()) if not hist.empty else None
        monthly = hist["Close"].resample("ME").last().dropna()
        price_series = {str(k)[:7]: round(float(v), 2) for k, v in monthly.items()}
    except Exception:
        hist = close_source = None
        price_now = price_52w_high = price_52w_low = price_date = None
        price_series = {}

    # A newer close in the quote than in the daily bars: the bar was empty.
    q_price, q_date = quote_close(info)
    if q_date and (price_date is None or q_date > price_date):
        price_now, price_date = q_price, q_date

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
                shares = _num(row.get("Shares"))
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
                shares = _num(row.get("Shares"))
                pct_out = _num(row.get("% Out"), float("nan"))
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
                shares = _num(row.get("Shares"))
                pct = _num(row.get("% Out"), float("nan"))
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

    # Which sources actually returned data: recorded in the report's front
    # matter, so a header claiming Finviz/Roic.ai can be checked against it.
    income = _safe_df(lambda: t.financials)
    income_q = _safe_df(lambda: t.quarterly_financials)
    cashflow_q = _safe_df(lambda: t.quarterly_cashflow)
    source_status = {
        "yfinance_info": bool(info),
        "yfinance_prices": price_now is not None,
        "yfinance_statements": income is not None or income_q is not None,
        "finviz": bool(finviz_data),
        "stockanalysis": any(stockanalysis_data.values()) if stockanalysis_data else False,
        "roic": bool(roic_data),
    }

    # ── Merge: backfill missing Yahoo info from Finviz ──
    info = _merge_finviz_into_info(info, finviz_data)

    return {
        "ticker": ticker,
        "symbol": symbol,
        "info": info,
        "hist": hist,
        "income": income,
        "income_q": income_q,
        "balance": _safe_df(lambda: t.balance_sheet),
        "balance_q": _safe_df(lambda: t.quarterly_balance_sheet),
        "cashflow": _safe_df(lambda: t.cashflow),
        "cashflow_q": cashflow_q,
        "news": yahoo_news(symbol),
        "price_now": price_now,
        "price_date": price_date,
        "close_source": close_source,
        "source_status": source_status,
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
