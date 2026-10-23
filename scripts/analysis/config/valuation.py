"""Valuation assumptions and peer sets for the fundamental report's fact block.

Every number the model is handed as a "verified figure" is either reported data
or one of the named assumptions below; the fact block prints each assumption by
name so a reader can see which inputs are judgement rather than filings.
"""

# Cost-of-equity inputs (CAPM). The risk-free rate is fetched live (10-year
# Treasury, ^TNX); the equity risk premium is a fixed house assumption.
EQUITY_RISK_PREMIUM = 0.05
RISK_FREE_SYMBOL = "^TNX"

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
}

__all__ = [
    "EQUITY_RISK_PREMIUM", "RISK_FREE_SYMBOL", "DEFAULT_TAX_RATE", "TAX_RATE_BOUNDS",
    "MAX_STATEMENT_AGE_DAYS", "HISTORY_YEARS", "PEERS",
]
