"""Valuation assumptions and peer sets for the fundamental report's fact block.

Every number the model is handed as a "verified figure" is either reported data
or one of the named assumptions below; the fact block prints each assumption by
name so a reader can see which inputs are judgement rather than filings.
"""

# Cost-of-equity inputs (CAPM). The risk-free rate is fetched live (10-year
# Treasury, ^TNX); the equity risk premium is a fixed house assumption.
EQUITY_RISK_PREMIUM = 0.05
RISK_FREE_SYMBOL = "^TNX"

# Beta as CAPM receives it. A raw five-year beta is a noisy estimate that
# regresses toward 1, so it is Blume-adjusted (⅔ raw + ⅓) and then held inside
# a band. Read raw, 12 of the 30 company reports of 2026-11-14 discounted at
# 15% or more — NVDA at 16.26% on a beta of 2.25 — and 27 of 30 DCFs came out
# below the market price, by a median of 57%.
BETA_RAW_WEIGHT = 2 / 3
BETA_BOUNDS = (0.6, 2.0)
DEFAULT_BETA = 1.0          # used, and labelled as assumed, when Yahoo has none

# Pre-tax cost of debt when a company has debt but reports no interest expense
# (PLTR's leases): the risk-free rate plus this spread, labelled as assumed.
DEFAULT_CREDIT_SPREAD = 0.02

# A WACC outside this band is not believed: it is held at the nearer bound and
# the fact block prints both figures.
WACC_BOUNDS = (0.07, 0.14)

# ── FCFF DCF (the report's §8), computed in data/intrinsic_value.py ──────────
# House base case. Each is printed in the fact block next to the value it
# produced; the model explains and criticises them but does not change them.
FCFF_YEARS = 10                       # explicit forecast length
FCFF_TERMINAL_GROWTH = 0.03           # Gordon growth after the forecast
FCFF_GROWTH_BOUNDS = (0.0, 0.30)      # first-year revenue growth is TTM growth, held in here
FCFF_TERMINAL_CAPEX_TO_DA = 1.1       # capex fades to this multiple of D&A by the last year
# The operating margin fades from TTM to the median of this many fiscal years
# (TTM included), so a cycle peak or trough is not capitalised for ever. With
# fewer than MIN years of history, or a median that is not positive, TTM holds.
FCFF_MARGIN_YEARS = 5
FCFF_MARGIN_MIN_YEARS = 3
# Scenario shocks around the base case: (growth ×, margin ×, WACC +), probability.
FCFF_SCENARIOS = {
    "bear": ((0.5, 0.85, 0.01), 0.25),
    "base": ((1.0, 1.00, 0.00), 0.50),
    "bull": ((1.5, 1.10, -0.01), 0.25),
}

# ── §8.8 method weights ──────────────────────────────────────────────────────
# The model used to pick these per report: the DCF weight ran from 10% to 70%
# across the 30 company reports of 2026-11-14, and the weights decided the
# rating. They are fixed here by company type. A method with no value drops out
# and the rest are rescaled; analyst consensus never exceeds CONSENSUS_WEIGHT.
CONSENSUS_WEIGHT = 0.10
VALUATION_WEIGHTS = {
    # positive TTM operating income: cash flows and earnings both mean something
    "profitable": {"dcf": 0.40, "fwd_pe": 0.25, "ev_ebitda": 0.25},
    # earnings at a cycle peak or trough: forward P/E is left out
    "cyclical": {"dcf": 0.40, "ev_ebitda": 0.30, "ps": 0.20},
    # no operating profit: sales multiple first, forward earnings if positive
    "unprofitable": {"ps": 0.60, "fwd_pe": 0.30},
    # banks and lenders: deposits and loans are the business, not its financing
    "financial": {"fwd_pe": 0.50, "pb": 0.40},
}
# Report keys whose earnings follow a commodity cycle (memory and storage).
CYCLICAL = frozenset({"mu", "skhy", "sndk", "wdc"})
FINANCIAL_SECTORS = frozenset({"Financial Services"})
# A peer multiple outside these is a data artefact or a company with no
# earnings to speak of; it is left out of the median.
PEER_MULTIPLE_BOUNDS = {"forwardPE": (3.0, 60.0), "enterpriseToEbitda": (3.0, 40.0),
                        "priceToSalesTrailing12Months": (0.1, 30.0), "priceToBook": (0.2, 20.0)}
MIN_PEERS = 2

# Stage-1 QA flags a DCF value this far from the price (as a fraction of price),
# so a model that values a company at half its price is looked at, not published
# unremarked.
DCF_GAP_WARN = 0.50

# Used when the effective rate cannot be derived (pre-tax loss, missing tag) or
# falls outside a plausible band.
DEFAULT_TAX_RATE = 0.21
TAX_RATE_BOUNDS = (0.0, 0.35)

# Statements older than this (vs the price date) are stale: a TTM figure that
# skips the newest filed quarter is the error the store fix in
# fundamentals.fiscal_years() closed, so the fact block falls back to Yahoo's
# quarterly statements rather than quote a stale year.
MAX_STATEMENT_AGE_DAYS = 200

# Historical-multiple window for "current vs own history".
HISTORY_YEARS = 5

# Direct competitors whose multiples the report compares against (§7.1). Keys
# are report keys; tickers missing here get no peer table and the prompt tells
# the model to label any peer multiple it cites as an estimate.
PEERS = {
    "tsla": ["GM", "F", "RIVN"],
    "amd": ["NVDA", "INTC", "AVGO"],
    "nvda": ["AMD", "AVGO", "INTC"],
    "avgo": ["NVDA", "MRVL", "QCOM"],
    "intc": ["AMD", "NVDA", "QCOM"],
    "mrvl": ["AVGO", "NVDA", "AMD"],
    "mu": ["SKHY", "SNDK", "WDC"],
    "skhy": ["MU", "SNDK", "WDC"],
    "sndk": ["WDC", "MU", "SKHY"],
    "wdc": ["STX", "SNDK", "MU"],
    "tsm": ["INTC", "UMC", "GFS"],
    "2330.tw": ["UMC", "GFS", "INTC"],
    "goog": ["META", "MSFT", "AMZN"],
    "meta": ["GOOG", "SNAP", "PINS"],
    "msft": ["GOOG", "AMZN", "ORCL"],
    "amzn": ["MSFT", "GOOG", "WMT"],
    "orcl": ["MSFT", "SAP", "CRM"],
    "pltr": ["SNOW", "DDOG", "CRM"],
    "sofi": ["NU", "HOOD", "UPST"],
    "nu": ["SOFI", "MELI", "HOOD"],
    "grab": ["UBER", "SE", "DASH"],
    "nbis": ["CRWV", "ORCL", "MSFT"],
    "rklb": ["SPCX", "LUNR", "PL"],
    "spcx": ["RKLB", "ASTS", "IRDM"],
    "pl": ["SPIR", "BKSY", "RKLB"],
    "onds": ["AVAV", "KTOS", "RCAT"],
    "avav": ["KTOS", "ONDS", "LMT"],
    "ktos": ["AVAV", "LMT", "NOC"],
    "vst": ["CEG", "NRG", "TLN"],
    "uber": ["LYFT", "DASH", "GRAB"],
}

__all__ = [
    "EQUITY_RISK_PREMIUM", "RISK_FREE_SYMBOL", "DEFAULT_TAX_RATE", "TAX_RATE_BOUNDS",
    "MAX_STATEMENT_AGE_DAYS", "HISTORY_YEARS", "PEERS",
    "BETA_RAW_WEIGHT", "BETA_BOUNDS", "DEFAULT_BETA", "WACC_BOUNDS",
    "FCFF_YEARS", "FCFF_TERMINAL_GROWTH", "FCFF_GROWTH_BOUNDS",
    "FCFF_TERMINAL_CAPEX_TO_DA", "FCFF_MARGIN_YEARS", "FCFF_MARGIN_MIN_YEARS",
    "DEFAULT_CREDIT_SPREAD", "FCFF_SCENARIOS", "CONSENSUS_WEIGHT",
    "VALUATION_WEIGHTS", "CYCLICAL", "FINANCIAL_SECTORS", "PEER_MULTIPLE_BOUNDS",
    "MIN_PEERS", "DCF_GAP_WARN",
]
