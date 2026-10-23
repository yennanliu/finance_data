"""
Context builders for different analysis types.
"""

from __future__ import annotations

import textwrap

from ..config import TODAY
from ..utils.formatting import safe, pct, money, fmt_price, df_to_text
from ..data.technicals import price_ascii_chart, compute_technicals


def _ttm_sum(df, row: str):
    """Sum of the four newest quarterly values of ``row`` (yfinance frames are
    newest-first), or None unless all four are present."""
    try:
        if df is None or row not in df.index:
            return None
        vals = [float(v) for v in df.loc[row].iloc[:4]]
    except (TypeError, ValueError):
        return None
    if len(vals) < 4 or any(v != v for v in vals):  # NaN check
        return None
    return sum(vals)


def statement_ttm(data: dict) -> dict:
    """TTM operating margin and free cash flow from the quarterly statements.

    Yahoo's ``operatingMargins`` is the latest quarter only and its
    ``freeCashflow`` is its own "levered" figure, not operating cash flow less
    capex. Reports quoted both as TTM: TSLA's "TTM operating margin 1.4%" was
    Q2 alone (TTM 4.2%), and VST's "$37M FCF" was $2.25B as OCF − capex.
    """
    revenue = _ttm_sum(data.get("income_q"), "Total Revenue")
    op_income = _ttm_sum(data.get("income_q"), "Operating Income")
    ocf = _ttm_sum(data.get("cashflow_q"), "Operating Cash Flow")
    capex = _ttm_sum(data.get("cashflow_q"), "Capital Expenditure")  # negative
    fcf = ocf + capex if ocf is not None and capex is not None else None
    return {
        "revenue": revenue,
        "op_margin": op_income / revenue if op_income is not None and revenue else None,
        "ocf": ocf,
        "capex": -capex if capex is not None else None,
        "fcf": fcf,
    }


def currency_mismatch(info: dict) -> "tuple[str, str] | None":
    """(quote, statements) currencies when they differ, e.g. ('USD', 'TWD').

    An ADR such as TSM or SKHY is priced in USD but reports in TWD / KRW, and
    Yahoo's EV and price-to-sales ratios divide one by the other: TSM's report
    printed "FCF Yield 56.25%" and "EV/EBITDA 4.08x".
    """
    quote, fin = info.get("currency"), info.get("financialCurrency")
    if quote and fin and quote != fin:
        return quote, fin
    return None


def _market_overview(info: dict, data: dict) -> str:
    """Build market overview section.

    Every field names the period it covers: an unlabelled quarterly figure next
    to TTM statements gets read as TTM (see ``docs/FUNDAMENTAL_REPORT_REVIEW.md``
    §12).
    """
    ttm = statement_ttm(data)
    mkt = info.get('marketCap')
    mismatch = currency_mismatch(info)
    fin_ccy = info.get('financialCurrency') or info.get('currency') or "USD"
    fcf_yield = "N/A"
    if ttm["fcf"] is not None and mkt and not mismatch:
        fcf_yield = f"{ttm['fcf'] / float(mkt) * 100:.2f}%"

    def mixed(value):
        return "N/A (price and statements in different currencies)" if mismatch else value

    price_date = data.get('price_date') or "N/A"
    ccy_note = ""
    if mismatch:
        ccy_note = (f"\n⚠ Quoted in {mismatch[0]} but statements are in {mismatch[1]}: "
                    f"statement figures below are {mismatch[1]}; ratios that would mix the "
                    f"two currencies are withheld.")

    return f"""
━━ MARKET DATA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Last Close ({price_date}):  {fmt_price(data['price_now'])} {info.get('currency') or ''}{ccy_note}
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
P/S  Ratio (TTM):       {mixed(safe(info.get('priceToSalesTrailing12Months')))}
P/B  Ratio:             {safe(info.get('priceToBook'))}
EV / EBITDA (TTM):      {mixed(safe(info.get('enterpriseToEbitda')))}
EV / Revenue (TTM):     {mixed(safe(info.get('enterpriseToRevenue')))}
EPS (TTM):              ${safe(info.get('trailingEps'))}
EPS (Forward):          ${safe(info.get('forwardEps'))}
FCF Yield (TTM, OCF − capex): {fcf_yield}

━━ PROFITABILITY & GROWTH ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Revenue (TTM, {fin_ccy}):           {money(info.get('totalRevenue'))}
Revenue Growth (LATEST QUARTER vs same quarter last year, not TTM): {pct(info.get('revenueGrowth'))}
EPS Growth (LATEST QUARTER vs same quarter last year):              {pct(info.get('earningsGrowth'))}
Net Income Growth (LATEST QUARTER vs same quarter last year):       {pct(info.get('earningsQuarterlyGrowth'))}
Gross Margin (TTM):                 {pct(info.get('grossMargins'))}
Operating Margin (TTM, statements): {pct(ttm['op_margin'])}
Operating Margin (LATEST QUARTER):  {pct(info.get('operatingMargins'))}
EBITDA Margin (TTM):                {pct(info.get('ebitdaMargins'))}
Net Profit Margin (TTM):            {pct(info.get('profitMargins'))}
ROE (TTM):                          {pct(info.get('returnOnEquity'))}
ROA (TTM):                          {pct(info.get('returnOnAssets'))}

━━ BALANCE SHEET & CASH FLOW ({fin_ccy}) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Cash:             {money(info.get('totalCash'))}
Total Debt:             {money(info.get('totalDebt'))}
Net Cash / Debt:        {money((info.get('totalCash') or 0) - (info.get('totalDebt') or 0))}
Debt/Equity:            {safe(info.get('debtToEquity'))}
Current Ratio:          {safe(info.get('currentRatio'))}
Quick Ratio:            {safe(info.get('quickRatio'))}
Operating Cash Flow (TTM, statements): {money(ttm['ocf'])}
Capital Expenditure (TTM, statements): {money(ttm['capex'])}
Free Cash Flow (TTM) = OCF − capex:    {money(ttm['fcf'])}
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
        finviz_block = f"\n━━ FINVIZ SNAPSHOT (Cross-Reference) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('finviz_text', '  (no data)')}"
        stockanalysis_block = f"\n━━ STOCKANALYSIS.COM DATA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('stockanalysis_text', '  (no data)')}"
        roic_block = f"\n━━ ROIC.AI HISTORICAL DATA (10Y+) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('roic_text', '  (no data)')}"
        return "\n".join([
            company_hdr,
            f"\n━━ 24-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{chart}",
            _market_overview(info, data),
            technicals,
            f"\n━━ INCOME STATEMENT (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['income'], inc_rows)}",
            f"\n━━ INCOME STATEMENT (Quarterly) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['income_q'], inc_q_rows)}",
            f"\n━━ BALANCE SHEET (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['balance'], bs_rows)}",
            f"\n━━ CASH FLOW STATEMENT (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['cashflow'], cf_rows)}",
            finviz_block,
            stockanalysis_block,
            roic_block,
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
            _market_overview(info, data),
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
        finviz_block = f"\n━━ FINVIZ SNAPSHOT (Cross-Reference) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('finviz_text', '  (no data)')}"
        roic_block = f"\n━━ ROIC.AI HISTORICAL DATA (10Y+) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('roic_text', '  (no data)')}"
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
            finviz_block,
            roic_block,
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
        finviz_block = f"\n━━ FINVIZ SNAPSHOT (Cross-Reference) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('finviz_text', '  (no data)')}"
        roic_block = f"\n━━ ROIC.AI HISTORICAL DATA (10Y+) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('roic_text', '  (no data)')}"
        return "\n".join([
            company_hdr,
            f"\n━━ 24-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{chart}",
            _market_overview(info, data),
            analyst_block,
            f"\n━━ INCOME STATEMENT (Annual, last 4Y) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['income'], inc_rows)}",
            f"\n━━ INCOME STATEMENT (Quarterly, last 4Q) ━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['income_q'], inc_q_rows)}",
            f"\n━━ BALANCE SHEET (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['balance'], bs_rows)}",
            f"\n━━ CASH FLOW STATEMENT (Annual) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['cashflow'], cf_rows)}",
            finviz_block,
            roic_block,
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
        "Stock Based Compensation",
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
    fin_ccy = info.get("financialCurrency") or info.get("currency") or "USD"

    # Additional data sources
    finviz_block = f"\n━━ FINVIZ SNAPSHOT (Cross-Reference) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('finviz_text', '  (no data)')}"
    stockanalysis_block = f"\n━━ STOCKANALYSIS.COM DATA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('stockanalysis_text', '  (no data)')}"
    roic_block = f"\n━━ ROIC.AI HISTORICAL DATA (10Y+) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{data.get('roic_text', '  (no data)')}"

    cross_ref_note = """
━━ DATA SOURCE NOTE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The MARKET DATA / VALUATION / PROFITABILITY sections above are merged from
Yahoo Finance + Finviz (backfilled where Yahoo returned null). The sections
below (Finviz Snapshot, StockAnalysis, Roic.ai) provide additional detail
and historical data. Cross-reference ALL sources for your analysis — if one
source shows N/A, check the others for that metric.
"""

    return "\n".join([
        company_hdr,
        f"\n━━ 24-MONTH PRICE HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{chart}",
        _market_overview(info, data),
        analyst_block,
        f"\n━━ INCOME STATEMENT (Annual, last 4Y, {fin_ccy}) ━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['income'], inc_rows)}",
        f"\n━━ INCOME STATEMENT (Quarterly, last 4Q, {fin_ccy}) ━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['income_q'], inc_q_rows)}",
        f"\n━━ BALANCE SHEET (Annual, {fin_ccy}) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['balance'], bs_rows)}",
        f"\n━━ CASH FLOW STATEMENT (Annual, {fin_ccy}) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['cashflow'], cf_rows)}",
        f"\n━━ CASH FLOW STATEMENT (Quarterly, last 4Q, {fin_ccy}) ━━━━━━━━━━━━━━━━━━━\n{df_to_text(data['cashflow_q'], cf_rows)}",
        cross_ref_note,
        finviz_block,
        stockanalysis_block,
        roic_block,
        earnings_block,
        upgrades_block,
        news_block,
    ])


__all__ = ["build_context"]
