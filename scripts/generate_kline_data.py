#!/usr/bin/env python3
"""
generate_kline_data.py — OHLCV data for the TradingView-style k-line charts
===========================================================================
Fetches daily OHLCV history from Yahoo Finance and writes one compact JSON
file per ticker to ``ai_gen_report/kline/<ticker>.json``. These files are the
data source for the interactive candlestick chart rendered at the top of every
per-ticker report page (see ``docs/javascripts/kline-chart.js`` and the chart
injection in ``scripts/build_docs.py``).

The JSON is intentionally tiny (short keys, rounded numbers, ~1 year of bars)
so the whole set stays a few hundred KB in git and loads instantly on the page.

Ticker universe (default): the union of
  • the tickers in ``scripts/.ticker_schedule.json`` (fundamental + technical), and
  • every ticker directory that already has a report under ai_gen_report/.
so a chart exists for exactly the pages the docs build renders.

Run locally:
    python scripts/generate_kline_data.py                 # all tickers
    python scripts/generate_kline_data.py TSLA 0050        # a subset
    python scripts/generate_kline_data.py --only-missing   # skip up-to-date files

Run in CI: see .github/workflows/update_kline_data.yml (daily, commits the JSON).

Fully offline-safe: importing this module does nothing; yfinance is imported
lazily inside fetch, so the test suite never touches the network.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
SCHEDULE_FILE = ROOT / "scripts" / ".ticker_schedule.json"
OUT_DIR = ROOT / "ai_gen_report" / "kline"
REPORT_ROOTS = [
    ROOT / "ai_gen_report" / "fundamental",
    ROOT / "ai_gen_report" / "technical",
    ROOT / "ai_gen_report" / "stock",
]

# How many daily bars to keep. 360-day window ≈ 248 trading days; 300 leaves
# comfortable headroom for holidays/gaps while keeping each file tiny.
KEEP_BARS = 300


# ── Ticker helpers ─────────────────────────────────────────────────────────────
def report_key(ticker: str) -> str:
    """The lowercased key used for the report directory and the JSON filename
    (matches how build_docs.py names per-ticker folders)."""
    return ticker.strip().lower()


def to_yf_symbol(ticker: str) -> str:
    """Map a ticker/report-key to the symbol Yahoo Finance expects.

    • ``2330.TW`` / ``2330.tw`` → ``2330.TW``   (already suffixed)
    • ``0050``                  → ``0050.TW``   (bare Taiwan listing)
    • ``brk.b``                 → ``BRK-B``     (US class shares use a dash)
    • ``tsla``                  → ``TSLA``
    """
    t = ticker.strip()
    low = t.lower()
    if low.endswith(".tw"):
        return t[:-3].upper() + ".TW"
    if t.replace(".", "").isdigit():
        return t.upper() + ".TW"
    return t.replace(".", "-").upper()


def currency_for(symbol: str) -> str:
    """Best-effort display currency inferred from the symbol suffix."""
    return "TWD" if symbol.upper().endswith(".TW") else "USD"


def discover_tickers() -> list[str]:
    """Union of scheduled tickers and tickers that already have report dirs."""
    keys: set[str] = set()

    if SCHEDULE_FILE.exists():
        try:
            sched = json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
            for group in sched.get("tickers", {}).values():
                for tk in group:
                    keys.add(report_key(tk))
        except Exception as e:  # pragma: no cover - defensive
            print(f"  ⚠ could not read {SCHEDULE_FILE.name}: {e}")

    for root in REPORT_ROOTS:
        if root.exists():
            for d in root.iterdir():
                if d.is_dir():
                    keys.add(report_key(d.name))

    return sorted(keys)


# ── Rounding ─────────────────────────────────────────────────────────────────
def _round_price(v: float) -> float:
    """2 decimals for normal prices; 4 for sub-$1 names so cents stay visible."""
    return round(v, 4 if abs(v) < 1 else 2)


# ── Fetch ────────────────────────────────────────────────────────────────────
def fetch_bars(symbol: str):
    """Return a list of {t,o,h,l,c,v} bars (oldest→newest) or None on failure."""
    import yfinance as yf  # lazy import keeps the module offline-safe

    tk = yf.Ticker(symbol)
    hist = tk.history(period="2y", interval="1d", auto_adjust=False)
    if hist is None or hist.empty:
        return None

    hist = hist.tail(KEEP_BARS)
    bars = []
    for ts, row in hist.iterrows():
        o, h, l, c = row.get("Open"), row.get("High"), row.get("Low"), row.get("Close")
        # Skip rows with missing OHLC (yfinance occasionally emits NaN rows).
        if any(x is None or x != x for x in (o, h, l, c)):  # x != x → NaN
            continue
        vol = row.get("Volume")
        try:
            vol = int(vol) if vol == vol else 0  # NaN → 0
        except Exception:
            vol = 0
        bars.append({
            "t": str(ts)[:10],
            "o": _round_price(float(o)),
            "h": _round_price(float(h)),
            "l": _round_price(float(l)),
            "c": _round_price(float(c)),
            "v": vol,
        })
    return bars or None


def build_payload(key: str, symbol: str, bars: list) -> dict:
    return {
        "ticker": key.upper(),
        "symbol": symbol,
        "currency": currency_for(symbol),
        "updated": date.today().isoformat(),
        "bars": bars,
    }


# ── Main ─────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("tickers", nargs="*",
                   help="Tickers to refresh (default: full discovered universe)")
    p.add_argument("--out", default=str(OUT_DIR),
                   help=f"Output directory (default: {OUT_DIR})")
    p.add_argument("--only-missing", action="store_true",
                   help="Skip tickers whose JSON already exists (any date)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    tickers = [report_key(t) for t in args.tickers] if args.tickers else discover_tickers()

    print(f"\n{'='*66}")
    print(f"  k-line data → {out_dir.relative_to(ROOT) if out_dir.is_relative_to(ROOT) else out_dir}")
    print(f"  {len(tickers)} tickers")
    print(f"{'='*66}\n")

    ok = fail = skip = 0
    for key in tickers:
        dst = out_dir / f"{key}.json"
        if args.only_missing and dst.exists():
            skip += 1
            continue

        symbol = to_yf_symbol(key)
        try:
            bars = fetch_bars(symbol)
        except Exception as e:
            print(f"  ✗ {key:<10} ({symbol})  fetch error: {e}")
            fail += 1
            continue

        if not bars:
            print(f"  ✗ {key:<10} ({symbol})  no data")
            fail += 1
            continue

        payload = build_payload(key, symbol, bars)
        dst.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        print(f"  ✓ {key:<10} ({symbol:<10}) {len(bars):>3} bars  →  {dst.name}")
        ok += 1

    print(f"\n{'='*66}")
    print(f"  done — {ok} written, {fail} failed, {skip} skipped")
    print(f"{'='*66}\n")

    # Non-zero exit only if literally nothing succeeded (lets CI catch a total
    # outage while tolerating a handful of individually-failing tickers).
    if ok == 0 and (fail or tickers):
        sys.exit(1)


if __name__ == "__main__":
    main()
