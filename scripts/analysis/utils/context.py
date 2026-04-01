"""
Context builders for different analysis types.
"""

from __future__ import annotations

import textwrap

from ..config import TODAY
from .formatting import safe, pct, money, fmt_price, df_to_text
from .data_fetch import price_ascii_chart, compute_technicals


def _market_overview(info: dict, data: dict) -> str:
    """Build market overview section."""
    fcf = info.get('freeCashflow')
    mkt = info.get('marketCap')
    try:
        fcf_yield = f"{float(fcf)/float(mkt)*100:.2f}%" if fcf and mkt else "N/A"
    except Exception:
        fcf_yield = "N/A"

    return f"""
━━ MARKET DATA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Current Price:          {fmt_price(data['price_now'])}
52W High:               {fmt_price(data['price_52w_high'])}
52W Low:                {fmt_price(data['price_52w_low'])}
Market Cap:             {money(info.get('marketCap'))}
Enterprise Value:       {money(info.get('enterpriseValue'))}
Beta:                   {safe(info.get('beta'))}
Short Ratio:            {safe(info.get('shortRatio'))}
Short % Float:          {pct(info.get('shortPercentOfFloat'))}
Shares Outstanding:     {money(info.get('sharesOutstanding'), prefix='')} shares
Float Shares:           {money(info.get('floatShares'), prefix='')} shares
Insider Own %:          {pct(info.get('heldPercentInsiders'))}
Institution Own %:      {pct(info.get('heldPercentInstitutions'))}

━━ VALUATION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
P/E  (Trailing):        {safe(info.get('trailingPE'))}
P/E  (Forward):         {safe(info.get('forwardPE'))}
PEG  Ratio:             {safe(info.get('pegRatio'))}
P/S  Ratio:             {safe(info.get('priceToSalesTrailing12Months'))}
P/B  Ratio:             {safe(info.get('priceToBook'))}
EV / EBITDA:            {safe(info.get('enterpriseToEbitda'))}
EV / Revenue:           {safe(info.get('enterpriseToRevenue'))}
EPS (TTM):              ${safe(info.get('trailingEps'))}
EPS (Forward):          ${safe(info.get('forwardEps'))}
FCF Yield:              {fcf_yield}

━━ PROFITABILITY & GROWTH ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Revenue (TTM):          {money(info.get('totalRevenue'))}
Revenue Growth (YoY):   {pct(info.get('revenueGrowth'))}
Earnings Growth (YoY):  {pct(info.get('earningsGrowth'))}
Earnings Growth (QoQ):  {pct(info.get('earningsQuarterlyGrowth'))}
Gross Margin:           {pct(info.get('grossMargins'))}
Operating Margin:       {pct(info.get('operatingMargins'))}
EBITDA Margin:          {pct(info.get('ebitdaMargins'))}
Net Profit Margin:      {pct(info.get('profitMargins'))}
ROE:                    {pct(info.get('returnOnEquity'))}
ROA:                    {pct(info.get('returnOnAssets'))}

━━ BALANCE SHEET SNAPSHOT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Cash:             {money(info.get('totalCash'))}
Total Debt:             {money(info.get('totalDebt'))}
Net Cash / Debt:        {money((info.get('totalCash') or 0) - (info.get('totalDebt') or 0))}
Debt/Equity:            {safe(info.get('debtToEquity'))}
Current Ratio:          {safe(info.get('currentRatio'))}
Quick Ratio:            {safe(info.get('quickRatio'))}
Operating Cash Flow:    {money(info.get('operatingCashflow'))}
Free Cash Flow:         {money(info.get('freeCashflow'))}
"""


def build_context(data: dict, analysis_type: str) -> str:
    """Assemble fetched data into context text appropriate for the analysis type."""
    info = data["info"]
    ticker = data["ticker"]

    company_hdr = f"""
╔══════════════════════════════════════════════════════════════════╗
║  FINANCIAL DATA PACKAGE  —  {ticker:<6}  —  {TODAY}
╚══════════════════════════════════════════════════════════════════╝

━━ COMPANY OVERVIEW ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ticker:    {ticker}
Name:      {safe(info.get('longName'))}
Sector:    {safe(info.get('sector'))}
Industry:  {safe(info.get('industry'))}
Country:   {safe(info.get('country'))}
Employees: {safe(info.get('fullTimeEmployees'))}
Summary:
{textwrap.fill(safe(info.get('longBusinessSummary', ''), ''), width=78, initial_indent='  ', subsequent_indent='  ')[:500]}
""".strip()

    news_lines = [
        f"  - {item['title']}"
        for item in data.get("news", [])
        if item.get("title")
    ]
    news_block = "\n━━ RECENT NEWS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n" + (
        "\n".join(news_lines) if news_lines else "  (no news)"
    )

    earnings_block = f"\n━━ EARNINGS HISTORY (EPS Beats/Misses) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('earnings_text', '  (no data)')}"
    upgrades_block = f"\n━━ ANALYST UPGRADES / DOWNGRADES (Recent) ━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('upgrades_text', '  (no data)')}"
    insider_block = f"\n━━ INSIDER TRANSACTIONS (Recent 20) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('insider_text', '  (no data)')}"
    major_holders_block = f"\n━━ MAJOR HOLDERS BREAKDOWN ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('major_holders_text', '  (no data)')}"
    institutional_block = f"\n━━ TOP INSTITUTIONAL HOLDERS (Top 20) ━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('institutional_text', '  (no data)')}"
    mutualfund_block = f"\n━━ TOP MUTUAL FUND HOLDERS (Top 10) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('mutualfund_text', '  (no data)')}"

    # insider-trading
    if analysis_type == "insider-trading":
        chart = price_ascii_chart(data["price_series"])
        return "\n".join([
            company_hdr,
            f"\n━━ 24-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{chart}",
            _market_overview(info, data),
            major_holders_block,
            insider_block,
            upgrades_block,
            news_block,
        ])

    # institutional-ownership
    if analysis_type == "institutional-ownership":
        chart = price_ascii_chart(data["price_series"])
        return "\n".join([
            company_hdr,
            f"\n━━ 24-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{chart}",
            _market_overview(info, data),
            major_holders_block,
            institutional_block,
            mutualfund_block,
            insider_block,
            upgrades_block,
            news_block,
        ])

    # earnings-call-analysis
    if analysis_type == "earnings-call-analysis":
        chart = price_ascii_chart(data["price_series"])
        inc_q_rows = ["Total Revenue", "Gross Profit", "Operating Income", "Net Income"]
        return "\n".join([
            company_hdr,
            f"\n━━ 24-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{chart}",
            _market_overview(info, data),
            f"\n━━ QUARTERLY INCOME (last 4Q) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['income_q'], inc_q_rows)}",
            earnings_block,
            upgrades_block,
            news_block,
        ])

    # report-generator: full context (all data)
    if analysis_type == "report-generator":
        chart = price_ascii_chart(data["price_series"])
        technicals = compute_technicals(data["hist"])
        inc_rows = [
            "Total Revenue", "Gross Profit", "Operating Income",
            "Net Income", "EBITDA", "Research And Development",
        ]
        inc_q_rows = ["Total Revenue", "Gross Profit", "Operating Income", "Net Income"]
        bs_rows = [
            "Total Assets", "Total Liabilities Net Minority Interest",
            "Stockholders Equity", "Cash And Cash Equivalents", "Total Debt",
            "Current Assets", "Current Liabilities",
        ]
        cf_rows = [
            "Operating Cash Flow", "Capital Expenditure", "Free Cash Flow",
            "Common Stock Repurchased", "Cash Dividends Paid",
        ]
        return "\n".join([
            company_hdr,
            f"\n━━ 24-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{chart}",
            _market_overview(info, data),
            technicals,
            f"\n━━ INCOME STATEMENT (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['income'], inc_rows)}",
            f"\n━━ INCOME STATEMENT (Quarterly) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['income_q'], inc_q_rows)}",
            f"\n━━ BALANCE SHEET (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['balance'], bs_rows)}",
            f"\n━━ CASH FLOW STATEMENT (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['cashflow'], cf_rows)}",
            major_holders_block,
            institutional_block,
            insider_block,
            earnings_block,
            upgrades_block,
            news_block,
        ])

    # technical-analysis: focus on price/indicator data
    if analysis_type == "technical-analysis":
        chart = price_ascii_chart(data["price_series"])
        technicals = compute_technicals(data["hist"])
        analyst = f"""
━━ ANALYST CONSENSUS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Recommendation:  {safe(info.get('recommendationKey'))}
# Analysts:      {safe(info.get('numberOfAnalystOpinions'))}
Target (Mean):   {fmt_price(info.get('targetMeanPrice'))}
Target (Low):    {fmt_price(info.get('targetLowPrice'))}
Target (High):   {fmt_price(info.get('targetHighPrice'))}
"""
        return "\n".join([
            company_hdr,
            f"\n━━ 24-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{chart}",
            technicals,
            analyst,
            upgrades_block,
            news_block,
        ])

    # economics-analysis: macro proxy via SPY / broad market
    if analysis_type == "economics-analysis":
        chart = price_ascii_chart(data["price_series"])
        return "\n".join([
            company_hdr,
            f"\n━━ 24-MONTH PRICE HISTORY ({ticker}) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{chart}",
            _market_overview(info, data),
            upgrades_block,
            news_block,
        ])

    # financial-report-analyst: comprehensive statements + insider
    if analysis_type == "financial-report-analyst":
        chart = price_ascii_chart(data["price_series"])
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
            f"\n━━ 24-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{chart}",
            _market_overview(info, data),
            f"\n━━ INCOME STATEMENT (Annual, last 4Y) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['income'], inc_rows)}",
            f"\n━━ INCOME STATEMENT (Quarterly, last 4Q) ━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['income_q'], inc_q_rows)}",
            f"\n━━ BALANCE SHEET (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['balance'], bs_rows)}",
            f"\n━━ BALANCE SHEET (Quarterly) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['balance_q'], bs_rows)}",
            f"\n━━ CASH FLOW STATEMENT (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['cashflow'], cf_rows)}",
            f"\n━━ CASH FLOW STATEMENT (Quarterly) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['cashflow_q'], cf_rows)}",
            insider_block,
            earnings_block,
            upgrades_block,
            news_block,
        ])

    # stock-valuation: full valuation + financials + analyst consensus
    if analysis_type == "stock-valuation":
        chart = price_ascii_chart(data["price_series"])
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
Recommendation:  {safe(info.get('recommendationKey'))}
# Analysts:      {safe(info.get('numberOfAnalystOpinions'))}
Target (Mean):   {fmt_price(info.get('targetMeanPrice'))}
Target (Low):    {fmt_price(info.get('targetLowPrice'))}
Target (High):   {fmt_price(info.get('targetHighPrice'))}
Dividend Yield:  {pct(info.get('dividendYield'))}
Payout Ratio:    {pct(info.get('payoutRatio'))}
"""
        return "\n".join([
            company_hdr,
            f"\n━━ 24-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{chart}",
            _market_overview(info, data),
            analyst_block,
            f"\n━━ INCOME STATEMENT (Annual, last 4Y) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['income'], inc_rows)}",
            f"\n━━ INCOME STATEMENT (Quarterly, last 4Q) ━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['income_q'], inc_q_rows)}",
            f"\n━━ BALANCE SHEET (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['balance'], bs_rows)}",
            f"\n━━ CASH FLOW STATEMENT (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['cashflow'], cf_rows)}",
            earnings_block,
            upgrades_block,
            insider_block,
            news_block,
        ])

    # all other types: full fundamental context
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
Recommendation:  {safe(info.get('recommendationKey'))}
# Analysts:      {safe(info.get('numberOfAnalystOpinions'))}
Target (Mean):   {fmt_price(info.get('targetMeanPrice'))}
Target (Low):    {fmt_price(info.get('targetLowPrice'))}
Target (High):   {fmt_price(info.get('targetHighPrice'))}
Dividend Yield:  {pct(info.get('dividendYield'))}
Payout Ratio:    {pct(info.get('payoutRatio'))}
5Y Avg Dividend: {pct(info.get('fiveYearAvgDividendYield'))}
"""
    chart = price_ascii_chart(data["price_series"])
    return "\n".join([
        company_hdr,
        f"\n━━ 24-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{chart}",
        _market_overview(info, data),
        analyst_block,
        f"\n━━ INCOME STATEMENT (Annual, last 4Y) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['income'], inc_rows)}",
        f"\n━━ INCOME STATEMENT (Quarterly, last 4Q) ━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['income_q'], inc_q_rows)}",
        f"\n━━ BALANCE SHEET (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['balance'], bs_rows)}",
        f"\n━━ CASH FLOW STATEMENT (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['cashflow'], cf_rows)}",
        earnings_block,
        upgrades_block,
        news_block,
    ])


__all__ = ["build_context"]
