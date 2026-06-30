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
    assert "Current Price:" in out


def test_missing_optional_text_blocks_are_resilient(minimal_data):
    # Drop all the optional ".get()"-accessed text blocks; should still build.
    for key in ["earnings_text", "upgrades_text", "insider_text",
                "major_holders_text", "institutional_text", "mutualfund_text",
                "finviz_text", "stockanalysis_text", "roic_text", "news"]:
        minimal_data.pop(key, None)
    out = build_context(minimal_data, "fundamental-analysis")
    assert "FINANCIAL DATA PACKAGE" in out
    assert "(no data)" in out  # default fallback used
