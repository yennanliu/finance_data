"""Benchmarks a ticker is measured against, all read from the price store.

Used by the technical report's relative-strength block and the ETF report's
performance table. Every benchmark is a report key that ``data/prices/`` holds,
so the comparison needs no network and can be tested offline. A ticker missing
from ``SECTOR_ETF`` simply gets no sector comparison.
"""

# Broad market, chosen by listing: Taiwan listings against 0050, the rest
# against VTI (US total market). A benchmark is never compared with itself.
MARKET_BENCHMARK_DEFAULT = "vti"
MARKET_BENCHMARK_BY_SUFFIX = {".tw": "0050"}
# 0050 is quoted in TWD; against a USD fund the difference would be mostly FX.
NO_MARKET_BENCHMARK = frozenset({"0050"})

SECTOR_ETF = {
    # semiconductors
    "nvda": "smh", "amd": "smh", "avgo": "smh", "intc": "smh", "mrvl": "smh",
    "mu": "smh", "sndk": "smh", "wdc": "smh", "skhy": "smh", "tsm": "smh",
    "soxx": "smh", "soxq": "smh",
    # large-cap technology
    "msft": "qqq", "goog": "qqq", "meta": "qqq", "amzn": "qqq", "orcl": "qqq",
    "pltr": "qqq", "tsla": "qqq", "nbis": "qqq", "uber": "qqq", "smh": "qqq",
}

BENCHMARK_NAMES = {"vti": "VTI（美國整體市場）", "0050": "0050（台灣 50）",
                   "smh": "SMH（半導體）", "qqq": "QQQ（Nasdaq-100）"}


def market_benchmark(key: str) -> "str | None":
    key = (key or "").lower()
    if key in NO_MARKET_BENCHMARK:
        return None
    for suffix, bench in MARKET_BENCHMARK_BY_SUFFIX.items():
        if key.endswith(suffix):
            return bench
    return None if key == MARKET_BENCHMARK_DEFAULT else MARKET_BENCHMARK_DEFAULT


def sector_benchmark(key: str) -> "str | None":
    return SECTOR_ETF.get((key or "").lower())


__all__ = ["market_benchmark", "sector_benchmark", "SECTOR_ETF", "BENCHMARK_NAMES"]
