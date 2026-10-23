"""Branch-coverage tests for analysis.utils.context.build_context.

Each analysis type assembles a different mix of sections; these tests assert the
distinguishing section markers per branch so a future refactor that drops or
mis-routes a section is caught.
"""

import pytest

from scripts.analysis.config import ANALYSIS_TYPES
from scripts.analysis.utils.context import build_context, _market_overview

pytestmark = pytest.mark.unit

COMMON_MARKERS = ["FINANCIAL DATA PACKAGE", "COMPANY OVERVIEW", "RECENT NEWS"]

# analysis_type -> (markers that must appear, markers that must NOT appear)
BRANCH_EXPECTATIONS = {
    "insider-trading": (
        ["MAJOR HOLDERS BREAKDOWN", "INSIDER TRANSACTIONS"],
        ["TOP INSTITUTIONAL HOLDERS", "INCOME STATEMENT"],
    ),
    "institutional-ownership": (
        ["TOP INSTITUTIONAL HOLDERS", "TOP MUTUAL FUND HOLDERS", "MAJOR HOLDERS BREAKDOWN"],
        ["INCOME STATEMENT"],
    ),
    "earnings-call-analysis": (
        ["QUARTERLY INCOME (last 4Q)", "EARNINGS HISTORY"],
        ["BALANCE SHEET (Annual)", "INCOME STATEMENT (Annual)"],
    ),
    "report-generator": (
        ["FINVIZ SNAPSHOT", "STOCKANALYSIS.COM DATA", "ROIC.AI HISTORICAL DATA",
         "INCOME STATEMENT (Annual)"],
        [],
    ),
    "technical-analysis": (
        ["ANALYST CONSENSUS"],
        ["INCOME STATEMENT"],
    ),
    "economics-analysis": (
        ["MARKET DATA"],
        ["INCOME STATEMENT", "ANALYST CONSENSUS"],
    ),
    "financial-report-analyst": (
        ["BALANCE SHEET (Quarterly)", "CASH FLOW STATEMENT (Quarterly)", "FINVIZ SNAPSHOT"],
        [],
    ),
    "stock-valuation": (
        ["ANALYST CONSENSUS", "Dividend Yield", "INCOME STATEMENT (Annual"],
        [],
    ),
    # default branch (full fundamental context)
    "fundamental-analysis": (
        ["DATA SOURCE NOTE", "STOCKANALYSIS.COM DATA", "5Y Avg Dividend"],
        [],
    ),
    "stock-eval": (["DATA SOURCE NOTE", "5Y Avg Dividend"], []),
    "sector-analysis": (["DATA SOURCE NOTE"], []),
    "portfolio-review": (["DATA SOURCE NOTE"], []),
}


@pytest.mark.parametrize("analysis_type", list(ANALYSIS_TYPES.keys()))
def test_all_types_return_nonempty_with_common_markers(minimal_data, analysis_type):
    out = build_context(minimal_data, analysis_type)
    assert isinstance(out, str) and out.strip()
    for marker in COMMON_MARKERS:
        assert marker in out, f"{analysis_type} missing common marker {marker!r}"
    # ticker always embedded
    assert "TEST" in out


@pytest.mark.parametrize("analysis_type,expect", BRANCH_EXPECTATIONS.items())
def test_branch_specific_sections(minimal_data, analysis_type, expect):
    present, absent = expect
    out = build_context(minimal_data, analysis_type)
    for marker in present:
        assert marker in out, f"{analysis_type}: expected section {marker!r} missing"
    for marker in absent:
        assert marker not in out, f"{analysis_type}: unexpected section {marker!r} present"


def test_market_overview_formats_known_fields(minimal_data):
    out = _market_overview(minimal_data["info"], minimal_data)
    assert "MARKET DATA" in out
    assert "VALUATION" in out
    assert "Last Close (" in out


def _quarters(**rows):
    """A yfinance-shaped quarterly frame: rows × newest-first quarter columns."""
    import pandas as pd
    cols = pd.to_datetime(["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30"])
    return pd.DataFrame({c: [v[i] for v in rows.values()] for i, c in enumerate(cols)},
                        index=list(rows))


def test_statement_ttm_is_ocf_minus_capex_over_four_quarters(minimal_data):
    """TSLA TTM to 2026-06: OCF $18.69B − capex $12.92B = $5.76B, not Yahoo's
    "levered" $4.84B that the report printed."""
    from scripts.analysis.context import statement_ttm
    minimal_data["income_q"] = _quarters(**{
        "Total Revenue": [28.236e9, 22.387e9, 24.901e9, 28.095e9, 22.496e9],
        "Operating Income": [0.398e9, 0.941e9, 1.409e9, 1.624e9, 0.923e9]})
    minimal_data["cashflow_q"] = _quarters(**{
        "Operating Cash Flow": [4.697e9, 3.937e9, 3.813e9, 6.238e9, 2.540e9],
        "Capital Expenditure": [-5.789e9, -2.493e9, -2.393e9, -2.248e9, -2.394e9]})
    t = statement_ttm(minimal_data)
    assert t["fcf"] == pytest.approx(5.761e9, rel=1e-3)
    assert t["capex"] == pytest.approx(12.923e9, rel=1e-3)
    assert t["op_margin"] == pytest.approx(4.372 / 103.619, rel=1e-3)   # 4.2%, not Q2's 1.4%


def test_statement_ttm_needs_four_quarters(minimal_data):
    from scripts.analysis.context import statement_ttm
    import pandas as pd
    minimal_data["cashflow_q"] = pd.DataFrame(
        {pd.Timestamp("2026-06-30"): [1.0, -0.5]},
        index=["Operating Cash Flow", "Capital Expenditure"])
    assert statement_ttm(minimal_data)["fcf"] is None


def test_overview_labels_every_quarterly_field_as_such(minimal_data):
    minimal_data["info"].update(revenueGrowth=0.255, operatingMargins=0.0141,
                                freeCashflow=4.84e9)
    out = _market_overview(minimal_data["info"], minimal_data)
    assert "Revenue Growth (LATEST QUARTER vs same quarter last year, not TTM): 25.5%" in out
    assert "Operating Margin (LATEST QUARTER):  1.4%" in out
    assert "(QoQ)" not in out          # earningsQuarterlyGrowth is YoY, never QoQ
    assert "$4.84B" not in out         # Yahoo's levered FCF is not passed on


def test_overview_withholds_ratios_that_mix_currencies(minimal_data):
    """TSM reports in TWD but trades in USD; Yahoo's EV/EBITDA mixes them."""
    minimal_data["info"].update(currency="USD", financialCurrency="TWD",
                                enterpriseToEbitda=4.08, priceToSalesTrailing12Months=1.2)
    out = _market_overview(minimal_data["info"], minimal_data)
    assert "4.08" not in out and "statements are in TWD" in out
    assert "EV / EBITDA (TTM):      N/A (price and statements in different currencies)" in out


def test_missing_optional_text_blocks_are_resilient(minimal_data):
    # Drop all the optional ".get()"-accessed text blocks; should still build.
    for key in ["earnings_text", "upgrades_text", "insider_text",
                "major_holders_text", "institutional_text", "mutualfund_text",
                "finviz_text", "stockanalysis_text", "roic_text", "news"]:
        minimal_data.pop(key, None)
    out = build_context(minimal_data, "fundamental-analysis")
    assert "FINANCIAL DATA PACKAGE" in out
    assert "(no data)" in out  # default fallback used
