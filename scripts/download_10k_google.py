#!/usr/bin/env python3
"""
Download 10-K financial data via yfinance, styled around Google Finance tickers.

Usage:
  python download_10k_google.py PLTR             # latest annual financials
  python download_10k_google.py PLTR 2024-12     # filter to fiscal year ending yyyy-mm
  python download_10k_google.py AAPL 2024-09 -e NASDAQ
"""

import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

import yfinance as yf
import pandas as pd


EXCHANGE_MAP = {
    "AAPL": "NASDAQ", "MSFT": "NASDAQ", "GOOGL": "NASDAQ", "GOOG": "NASDAQ",
    "AMZN": "NASDAQ", "META": "NASDAQ", "NVDA": "NASDAQ", "TSLA": "NASDAQ",
    "NFLX": "NASDAQ", "INTC": "NASDAQ", "AMD": "NASDAQ",  "CSCO": "NASDAQ",
    "PLTR": "NASDAQ", "SOFI": "NASDAQ", "COIN": "NASDAQ", "PYPL": "NASDAQ",
    "JPM":  "NYSE",   "V":    "NYSE",   "WMT":  "NYSE",   "DIS":  "NYSE",
    "BAC":  "NYSE",   "GS":   "NYSE",   "MS":   "NYSE",   "BA":   "NYSE",
    "TSM":  "NYSE",   "ORCL": "NYSE",   "IBM":  "NYSE",
}


def _fmt(value) -> str:
    """Format a numeric cell to a readable string (billions/millions)."""
    try:
        v = float(value)
        if abs(v) >= 1e9:
            return f"{v/1e9:,.2f}B"
        if abs(v) >= 1e6:
            return f"{v/1e6:,.1f}M"
        return f"{v:,.0f}"
    except (TypeError, ValueError):
        return str(value) if pd.notna(value) else "—"


def _df_to_md(df: pd.DataFrame, period: Optional[str]) -> list[str]:
    """Convert a financial DataFrame to a Markdown table, optionally filtered by period."""
    if df is None or df.empty:
        return ["_No data available._", ""]

    # Columns are datetime → format as YYYY-MM
    cols = df.columns.tolist()
    if period:
        target = period[:7]  # yyyy-mm
        cols = [c for c in cols if str(c)[:7] == target] or cols[:1]

    # Limit to most recent 4 periods if no filter
    if not period:
        cols = cols[:4]

    col_headers = [str(c)[:10] for c in cols]
    header = "| Metric | " + " | ".join(col_headers) + " |"
    sep    = "| --- | " + " | ".join(["---"] * len(col_headers)) + " |"
    rows   = [header, sep]

    for idx in df.index:
        vals = [_fmt(df.loc[idx, c]) for c in cols]
        rows.append(f"| {idx} | " + " | ".join(vals) + " |")

    return rows + [""]


class GoogleFinance10K:
    def __init__(self, ticker: str, exchange: Optional[str] = None):
        self.ticker = ticker.upper()
        self.exchange = (exchange or EXCHANGE_MAP.get(self.ticker, "NASDAQ")).upper()
        self.gf_url = f"https://www.google.com/finance/quote/{self.ticker}:{self.exchange}"
        self.stock = yf.Ticker(self.ticker)
        self.save_dir = Path(__file__).parent.parent / "10-k"
        self.save_dir.mkdir(exist_ok=True)

    def fetch_and_save(self, period: Optional[str] = None) -> Path:
        print(f"\nFetching 10-K data for {self.ticker}:{self.exchange}")
        print(f"  Google Finance: {self.gf_url}?tab=earnings")
        if period:
            print(f"  Period filter : {period}")

        info = self.stock.info or {}
        income  = self.stock.financials          # annual income statement
        balance = self.stock.balance_sheet       # annual balance sheet
        cashflow = self.stock.cashflow           # annual cash flow

        lines = self._build_report(period, info, income, balance, cashflow)

        period_str = period or datetime.today().strftime("%Y-%m")
        filename = f"{self.ticker}_{period_str}_10K_google.md"
        filepath = self.save_dir / filename
        filepath.write_text("\n".join(lines), encoding="utf-8")

        size_kb = filepath.stat().st_size / 1024
        print(f"✓ Saved: {filepath}  ({size_kb:.1f} KB)")
        return filepath

    def _build_report(
        self,
        period: Optional[str],
        info: dict,
        income: pd.DataFrame,
        balance: pd.DataFrame,
        cashflow: pd.DataFrame,
    ) -> list[str]:
        today = datetime.today().strftime("%Y-%m-%d")
        period_label = period or "Latest"

        lines = [
            f"# {self.ticker} Annual Report (10-K) — {period_label}",
            "",
            f"> Source: [Google Finance — {self.ticker}:{self.exchange}]({self.gf_url}?tab=earnings)  ",
            f"> Data via: yfinance  ",
            f"> Generated: {today}",
            "",
            "---",
            "",
        ]

        # Company overview
        want = [
            ("longName",            "Company"),
            ("sector",              "Sector"),
            ("industry",            "Industry"),
            ("country",             "Country"),
            ("fullTimeEmployees",   "Employees"),
            ("marketCap",           "Market Cap"),
            ("enterpriseValue",     "Enterprise Value"),
            ("trailingPE",          "P/E (TTM)"),
            ("forwardPE",           "P/E (Forward)"),
            ("priceToBook",         "Price/Book"),
            ("trailingEps",         "EPS (TTM)"),
            ("revenuePerShare",     "Revenue/Share"),
            ("returnOnEquity",      "ROE"),
            ("returnOnAssets",      "ROA"),
            ("debtToEquity",        "Debt/Equity"),
            ("currentRatio",        "Current Ratio"),
            ("totalRevenue",        "Total Revenue"),
            ("grossMargins",        "Gross Margin"),
            ("operatingMargins",    "Operating Margin"),
            ("profitMargins",       "Net Margin"),
        ]
        lines += ["## Company Overview", ""]
        for key, label in want:
            val = info.get(key)
            if val is not None:
                if isinstance(val, float) and abs(val) < 10:
                    formatted = f"{val:.2%}" if "Margin" in label or "ROE" in label or "ROA" in label else f"{val:.2f}"
                else:
                    formatted = _fmt(val)
                lines.append(f"- **{label}**: {formatted}")
        lines.append("")

        # Financial statements
        lines += ["## Income Statement (Annual)", ""]
        lines += _df_to_md(income, period)

        lines += ["## Balance Sheet (Annual)", ""]
        lines += _df_to_md(balance, period)

        lines += ["## Cash Flow Statement (Annual)", ""]
        lines += _df_to_md(cashflow, period)

        # Reference links
        lines += [
            "---",
            "## Reference Links",
            "",
            f"- [Google Finance — Earnings]({self.gf_url}?tab=earnings)",
            f"- [Google Finance — Financials]({self.gf_url}?tab=financials)",
            f"- [Google Finance — Balance Sheet]({self.gf_url}?tab=balance-sheet)",
            f"- [Google Finance — Cash Flow]({self.gf_url}?tab=cash-flow)",
            f"- [SEC EDGAR 10-K filings](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={self.ticker}&type=10-K)",
            "",
        ]
        return lines


def main():
    parser = argparse.ArgumentParser(
        description="Download 10-K financial data (Google Finance style)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python download_10k_google.py PLTR
  python download_10k_google.py AAPL 2024-09
  python download_10k_google.py TSM  2024-12 -e NYSE
        """,
    )
    parser.add_argument("ticker",           help="Stock ticker (e.g. PLTR, AAPL)")
    parser.add_argument("period", nargs="?", help="Report period yyyy-mm (default: latest)")
    parser.add_argument("-e", "--exchange",  help="Exchange override (default: auto-detect)")

    args = parser.parse_args()
    GoogleFinance10K(args.ticker, exchange=args.exchange).fetch_and_save(period=args.period)


if __name__ == "__main__":
    main()
