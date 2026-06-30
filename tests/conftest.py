"""Shared pytest fixtures and path setup for the finance_data test suite.

The CLIs run with ``scripts/`` on ``sys.path`` (so ``import analysis`` works),
while the tests import the package as ``scripts.analysis.*``. We make both
resolvable here so the suite runs the same way whether or not the pytest
``pythonpath`` ini option is honoured (e.g. when invoked via a bare interpreter).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO_ROOT / "scripts"
for _p in (_REPO_ROOT, _SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


# ── Market-data fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def sample_hist() -> pd.DataFrame:
    """300 days of trending OHLCV data — enough to exercise every MA window
    (the longest is MA240), not just the short ones."""
    n = 300
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    prices = [100 + i + (i % 5 - 2) * 0.5 for i in range(n)]
    return pd.DataFrame(
        {
            "Open": [p + 0.2 for p in prices],
            "High": [p + 1 for p in prices],
            "Low": [p - 1 for p in prices],
            "Close": [p + 0.5 for p in prices],
            "Volume": [1_000_000 + i * 10_000 for i in range(n)],
        },
        index=dates,
    )


@pytest.fixture
def minimal_data(sample_hist) -> dict:
    """Minimal-but-valid ``data`` dict accepted by ``build_context`` for any type."""
    empty = pd.DataFrame()
    return {
        "ticker": "TEST",
        "price": 100.0,
        "price_now": 100.0,
        "price_52w_high": 110.0,
        "price_52w_low": 90.0,
        "price_series": {"2024-01": 100.5, "2024-02": 101.5, "2024-03": 102.5},
        "hist": sample_hist,
        "info": {"sector": "Technology", "marketCap": 1.2e12},
        "financials": {"totalRevenue": 1e9},
        "quote": {"regularMarketPrice": 100.0},
        "news": [{"title": "Test News", "summary": "Test Summary"}],
        "income": empty,
        "income_q": empty,
        "balance": empty,
        "balance_q": empty,
        "cashflow": empty,
        "cashflow_q": empty,
        "finviz": {},
        "finviz_text": "",
        "stockanalysis_text": "",
        "roic_text": "",
        "upgrades_text": "",
        "earnings_text": "",
        "insider_text": "",
        "major_holders_text": "",
        "institutional_text": "",
        "mutualfund_text": "",
    }
