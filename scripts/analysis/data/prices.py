"""prices.py — the committed OHLCV price store
==============================================
One CSV per ticker under ``data/prices/<key>.csv`` holding up to ten years of
daily bars. This is the single source of truth for every chart on the site: the
docs build derives its chart payloads from here rather than each page carrying
its own copy of the data. See ``docs/PRICE_STORE_DESIGN.md`` for the full
rationale.

Update model — **fetch the full history nightly, write incrementally**. Yahoo
restates historical prices on a split, so a freshly-fetched bar always wins over
a stored one. That makes splits, dividend re-adjustments and upstream
corrections a non-event: the restated history simply overwrites what we had and
that night's diff is large instead of one line. There is no split detection and
no adjustment bookkeeping anywhere in this module.

The properties that make it work (each covered by ``tests/test_prices.py``):

  I1 byte-stable  ``serialise(parse(text)) == text`` — unchanged bars must
                  serialise to identical bytes or every night rewrites every
                  line and the whole design quietly collapses.
  I2 idempotent   running the updater twice leaves the file untouched.
  I3 sorted       dates strictly ascending, no duplicates.
  I4 capped       at most ``KEEP_YEARS`` back from the newest bar.
  I5 atomic       temp file + ``os.replace``; never a half-written store.
  I6 gated        a fetch that fails :func:`gate` is never written.

The read path is pure standard library so ``build_docs.py`` stays offline and
dependency-light; ``yfinance`` is imported lazily inside :func:`fetch_history`.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

# ── Paths / constants ────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[3]
STORE_DIR = ROOT / "data" / "prices"

# Depth of history kept per ticker. Ten years ≈ 2,520 bars ≈ 121 KB of CSV,
# which covers every window the site could plausibly serve while keeping the
# whole store around 5 MB. Raise this and re-run --backfill to go deeper.
KEEP_YEARS = 10

# Column order is part of the on-disk contract (I1). Do not reorder.
FIELDS = ("date", "open", "high", "low", "close", "volume", "div", "split")
HEADER = ",".join(FIELDS)

PRICE_FIELDS = ("open", "high", "low", "close")
EVENT_FIELDS = ("div", "split")


# ── Serialisation ────────────────────────────────────────────────────────────
# Everything here must be *deterministic and idempotent*: formatting a value,
# parsing it back and formatting again has to produce the same bytes. Fixed-point
# output (never `repr`) also keeps scientific notation — `1e-05` — out of the CSV.
def fmt_price(v: float) -> str:
    """Canonical price text: 2 decimals normally, 4 for sub-$1 names.

    The 4-vs-2 decision is made on the 4dp-rounded value, not the raw input, so
    a price like 0.99999 formats to "1.00" and *stays* "1.00" when re-read —
    deciding on the raw value would flip-flop across the $1 boundary and break I1.
    """
    r = round(float(v), 4)
    return f"{r:.4f}" if abs(r) < 1 else f"{r:.2f}"


def fmt_event(v) -> str:
    """Canonical dividend / split text; empty when there is no event.

    Trailing zeros are stripped to a canonical form (4.0 → "4", 0.250 → "0.25"),
    which survives a parse/format round trip unchanged.
    """
    if v is None:
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ""
    if f != f or f == 0:  # NaN or no event
        return ""
    s = f"{round(f, 6):.6f}".rstrip("0").rstrip(".")
    return s or ""


def fmt_volume(v) -> str:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return "0"
    return str(n)


def serialise(bars: list[dict]) -> str:
    """Render bars as the canonical CSV text (header + one line per bar)."""
    out = [HEADER]
    for b in bars:
        out.append(",".join((
            b["date"],
            fmt_price(b["open"]),
            fmt_price(b["high"]),
            fmt_price(b["low"]),
            fmt_price(b["close"]),
            fmt_volume(b["volume"]),
            fmt_event(b.get("div")),
            fmt_event(b.get("split")),
        )))
    return "\n".join(out) + "\n"


def parse(text: str) -> list[dict]:
    """Parse canonical CSV text into bars. Malformed lines are skipped.

    Deliberately hand-rolled rather than ``csv.reader``: no field can contain a
    comma or quote, and this keeps the read path allocation-light for the ~2,500
    lines × 38 tickers the docs build reads on every run.
    """
    bars: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("date,"):
            continue
        parts = line.split(",")
        if len(parts) < 6:
            continue
        try:
            bar = {
                "date": parts[0],
                "open": float(parts[1]),
                "high": float(parts[2]),
                "low": float(parts[3]),
                "close": float(parts[4]),
                "volume": int(parts[5] or 0),
                "div": float(parts[6]) if len(parts) > 6 and parts[6] else None,
                "split": float(parts[7]) if len(parts) > 7 and parts[7] else None,
            }
        except ValueError:
            continue
        bars.append(bar)
    return bars


# ── Store I/O ────────────────────────────────────────────────────────────────
def store_path(key: str, store_dir: Path | None = None) -> Path:
    """Path to a ticker's CSV. ``key`` is the lowercased report key."""
    return (store_dir or STORE_DIR) / f"{key.strip().lower()}.csv"


def load_store(key: str, store_dir: Path | None = None) -> list[dict]:
    """Bars for a ticker, oldest→newest. Empty list when the file is absent."""
    p = store_path(key, store_dir)
    if not p.exists():
        return []
    return parse(p.read_text(encoding="utf-8"))


def write_store(key: str, bars: list[dict], store_dir: Path | None = None) -> bool:
    """Write bars atomically (I5). Returns True only if the bytes changed (I2).

    The no-change early return is what keeps the nightly commit to a single
    appended line — and what makes an I1 regression visible as an unexpectedly
    dirty working tree rather than as silent churn.
    """
    p = store_path(key, store_dir)
    text = serialise(bars)
    if p.exists() and p.read_text(encoding="utf-8") == text:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".csv.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)  # atomic within the same directory
    return True


# ── Merge / trim / window ────────────────────────────────────────────────────
def upsert(old: list[dict], new: list[dict]) -> list[dict]:
    """Merge fetched bars over stored ones, sorted and deduplicated (I3).

    A fetched bar always wins on a date collision — that single rule is the
    entire split / re-adjustment / correction story.
    """
    merged = {b["date"]: b for b in old}
    merged.update({b["date"]: b for b in new})
    return [merged[d] for d in sorted(merged)]


def _years_before(iso: str, years: int) -> str:
    """ISO date ``years`` calendar years before ``iso`` (Feb-29 safe)."""
    y, m, d = (int(x) for x in iso.split("-"))
    try:
        return date(y - years, m, d).isoformat()
    except ValueError:  # 29 Feb → 28 Feb
        return date(y - years, m, d - 1).isoformat()


def trim(bars: list[dict], years: int = KEEP_YEARS) -> list[dict]:
    """Drop bars older than ``years`` before the *newest bar* (I4).

    Measured from the newest bar rather than today's date so the result depends
    only on the data — running the same input twice on different days yields
    identical bytes, which is what makes I2 hold strictly.
    """
    if not bars:
        return bars
    cutoff = _years_before(bars[-1]["date"], years)
    return [b for b in bars if b["date"] >= cutoff]


def window(bars: list[dict], *, days: int | None = None,
           as_of: str | None = None, lookback: int = 0) -> list[dict]:
    """Slice bars for a chart payload.

    ``as_of``   — drop bars after this ISO date (a report dated D must show the
                  chart as it stood on D, not today's prices).
    ``days``    — keep the newest ``days`` *bars* (trading days, not calendar).
    ``lookback``— additionally keep this many bars before the window so a
                  client-side MA200 is fully defined at the left edge.
    """
    out = bars
    if as_of:
        out = [b for b in out if b["date"] <= as_of]
    if days is not None:
        out = out[-(days + max(lookback, 0)):] if days > 0 else []
    return out


# ── Fetch ────────────────────────────────────────────────────────────────────
def fetch_history(symbol: str, years: int = KEEP_YEARS) -> list[dict] | None:
    """Fetch ``years`` of daily bars from Yahoo. Returns None on no data.

    ``auto_adjust=False`` keeps the as-reported (split-adjusted, not
    dividend-adjusted) OHLC, with dividends and splits carried as their own
    columns instead of folded into an ``adj_close`` — an ``adj_close`` would be
    retroactively restated by *every* dividend, rewriting a payer's whole file
    each quarter.
    """
    import yfinance as yf  # lazy import keeps this module offline-safe

    hist = yf.Ticker(symbol).history(
        period=f"{years}y", interval="1d", auto_adjust=False, actions=True,
    )
    if hist is None or hist.empty:
        return None

    bars = []
    for ts, row in hist.iterrows():
        o, h, l, c = (row.get(k) for k in ("Open", "High", "Low", "Close"))
        if any(x is None or x != x for x in (o, h, l, c)):  # x != x → NaN
            continue
        bars.append({
            "date": str(ts)[:10],
            "open": float(o), "high": float(h), "low": float(l), "close": float(c),
            "volume": _as_int(row.get("Volume")),
            "div": _as_float(row.get("Dividends")),
            "split": _as_float(row.get("Stock Splits")),
        })
    return bars or None


def _as_int(v) -> int:
    try:
        return int(v) if v == v else 0  # NaN → 0
    except (TypeError, ValueError):
        return 0


def _as_float(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if (f != f or f == 0) else f


# ── Sanity gate ──────────────────────────────────────────────────────────────
# A writer that heals itself from upstream is also one that destroys itself when
# upstream is wrong. Nothing gets written unless it clears these checks; a
# rejected ticker keeps whatever it already had on disk.
MIN_OVERLAP_RATIO = 0.9

# Tolerance for the open/close-within-high-low check. Yahoo occasionally emits a
# close a hair outside the day's range through its own adjustment rounding, and a
# hard comparison would block that ticker's updates forever over a fraction of a
# cent. Wide enough to absorb rounding, far too tight to admit a real bad bar.
OHLC_TOLERANCE = 0.005  # 0.5%


def gate(new: list[dict] | None, old: list[dict]) -> str | None:
    """Return None when ``new`` is safe to write, else a human-readable reason.

    A *large* diff is deliberately not a failure — that is the legitimate
    signature of a split, and callers log it instead.
    """
    if not new:
        return "empty fetch"

    seen = set()
    prev = ""
    for b in new:
        d = b["date"]
        if d in seen:
            return f"duplicate date {d}"
        if d <= prev:
            return f"dates not ascending at {d}"
        seen.add(d)
        prev = d

        o, h, l, c = (b[k] for k in PRICE_FIELDS)
        if any(x != x for x in (o, h, l, c)):
            return f"NaN price on {d}"
        if any(x <= 0 for x in (o, h, l, c)):
            return f"non-positive price on {d}"
        if h < l:
            return f"high < low on {d}"
        slack = h * OHLC_TOLERANCE
        if not (l - slack <= c <= h + slack) or not (l - slack <= o <= h + slack):
            return f"open/close outside high-low range on {d}"

    # Compare like with like: only stored bars inside the fetched date range can
    # be expected to reappear in the fetch.
    first = new[0]["date"]
    overlap = [b for b in old if b["date"] >= first]
    if overlap and len(new) < MIN_OVERLAP_RATIO * len(overlap):
        return f"bar count regression ({len(new)} fetched vs {len(overlap)} stored)"

    return None


# ── Update one ticker ────────────────────────────────────────────────────────
def update(key: str, symbol: str | None = None, years: int = KEEP_YEARS,
           store_dir: Path | None = None) -> tuple[str, str]:
    """Refresh one ticker's store. Returns ``(status, detail)``.

    status is one of ``appended`` (or ``created``), ``restated``, ``unchanged``,
    ``skipped`` (gate rejected), ``failed`` (fetch error / no data).
    """
    if symbol is None:
        symbol = to_yf_symbol(key)

    old = load_store(key, store_dir)
    try:
        new = fetch_history(symbol, years)
    except Exception as e:  # network / parsing / upstream schema surprises
        return "failed", f"fetch error: {e}"
    if not new:
        return "failed", "no data"

    reason = gate(new, old)
    if reason:
        return "skipped", reason

    merged = trim(upsert(old, new), years)
    if not write_store(key, merged, store_dir):
        return "unchanged", f"{len(merged)} bars"

    if not old:
        return "created", f"{len(merged)} bars"
    # Any stored bar whose values were replaced means upstream restated history
    # (a split, a dividend re-adjustment, a correction) — worth calling out,
    # because it is also the one case where the commit diff is huge.
    changed = _restated_count(old, new)
    if changed:
        return "restated", f"{changed} existing bars rewritten, {len(merged)} total"
    return "appended", f"{len(merged)} bars"


def _restated_count(old: list[dict], new: list[dict]) -> int:
    """How many *settled* stored bars the fetch reports differently.

    The newest stored bar is excluded: when a run lands during a live session
    (03:30 UTC is mid-session in Taipei) that bar is provisional and legitimately
    changes on the next run. Counting it would report "restated" nightly and
    drain the signal of its meaning — a restatement should mean upstream rewrote
    *settled history*, which is the one case whose commit diff is enormous.
    """
    if not old:
        return 0
    newest_settled = old[-1]["date"]
    by_date = {b["date"]: b for b in new}
    n = 0
    for b in old:
        if b["date"] >= newest_settled:
            continue
        cur = by_date.get(b["date"])
        if cur is None:
            continue
        if any(fmt_price(cur[f]) != fmt_price(b[f]) for f in PRICE_FIELDS):
            n += 1
    return n


# ── Ticker helpers ───────────────────────────────────────────────────────────
def report_key(ticker: str) -> str:
    """The lowercased key used for report directories and store filenames."""
    return ticker.strip().lower()


def to_yf_symbol(ticker: str) -> str:
    """Map a ticker/report-key to the symbol Yahoo Finance expects.

    ``2330.tw`` → ``2330.TW``, ``0050`` → ``0050.TW`` (bare Taiwan listing),
    ``brk.b`` → ``BRK-B`` (US class shares use a dash), ``tsla`` → ``TSLA``.
    """
    t = ticker.strip()
    if t.lower().endswith(".tw"):
        return t[:-3].upper() + ".TW"
    if t.replace(".", "").isdigit():
        return t.upper() + ".TW"
    return t.replace(".", "-").upper()


def currency_for(symbol: str) -> str:
    """Best-effort display currency inferred from the symbol suffix."""
    return "TWD" if symbol.upper().endswith(".TW") else "USD"


__all__ = [
    "KEEP_YEARS", "STORE_DIR", "FIELDS",
    "fmt_price", "fmt_event", "fmt_volume", "serialise", "parse",
    "store_path", "load_store", "write_store",
    "upsert", "trim", "window",
    "fetch_history", "gate", "update",
    "report_key", "to_yf_symbol", "currency_for",
]
