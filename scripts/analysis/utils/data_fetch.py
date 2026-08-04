"""Backward-compat shim.

The data-fetch code now lives in the layered ``analysis.data`` package:
  - analysis.data.sources     yfinance + Finviz/StockAnalysis/Roic scrapers
  - analysis.data.technicals  ASCII charts + technical indicators
  - analysis.data.prices      the committed OHLCV price store

Importing names from here keeps working for existing callers and tests.
"""

from ..data.sources import (  # noqa: F401
    fetch_data, fetch_finviz, fetch_stockanalysis, fetch_roic,
    _get_soup, _get_yf, _parse_finviz_number, _merge_finviz_into_info,
    _html_table_to_text, _format_finviz, _format_stockanalysis, _format_roic,
    _HEADERS,
)
from ..data.technicals import (  # noqa: F401
    price_ascii_chart, compute_moving_average_charts, compute_technicals,
    compute_levels,
)
