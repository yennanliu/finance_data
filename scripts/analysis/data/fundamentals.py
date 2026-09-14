"""fundamentals.py — the committed quarterly fundamentals store
===============================================================
One CSV per ticker under ``data/fundamentals/<key>.csv`` holding up to ten years
of *reported* quarterly financial statements, sourced from SEC's XBRL
``companyfacts`` API. Sibling of :mod:`prices` and built to the same contract:
the docs build derives its chart payloads from here rather than each page
carrying its own copy. See ``docs/FUNDAMENTALS_STORE_EVAL.md``.

Update model — **fetch the full history, write incrementally**. A freshly
fetched period always wins over a stored one, so restatements and amendments
are a non-event: the restated figure simply overwrites what we had. Same rule,
and same reasoning, as the price store's treatment of splits.

The properties that make it work (each covered by ``tests/test_fundamentals.py``):

  I1 byte-stable  ``serialise(parse(text)) == text``.
  I2 idempotent   running the updater twice leaves the file untouched.
  I3 sorted       period ends strictly ascending, no duplicates.
  I4 capped       at most ``KEEP_YEARS`` back from the newest period.
  I5 atomic       temp file + ``os.replace``; never a half-written store.
  I6 gated        a fetch that fails :func:`gate` is never written.

Two things about XBRL that this module exists to absorb:

**``fy``/``fp`` label the filing, not the period.** A single 10-Q emits the
current quarter, the current year-to-date, *and* both prior-year comparatives —
all four carrying that filing's ``fy``/``fp``. Keying on them silently mixes
periods. Everything here keys on ``start``/``end`` instead and derives the
fiscal label from the annual period boundaries.

**Most statements are cumulative.** Cash-flow and many income items are reported
year-to-date (3/6/9/12-month spans from the fiscal year start), never as
discrete quarters. :func:`discrete_quarters` recovers the quarter by
differencing consecutive year-to-date facts, which also subsumes the "Q4 is
never tagged" problem — Q4 is just the last difference. Values reconstructed
this way are arithmetic on reported figures, not estimates, but they are not
themselves a tagged number; the ``form`` column records which filing the period
closed with.

The read path is pure standard library so ``build_docs.py`` stays offline and
dependency-light; the network lives in :func:`fetch_facts`.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

# ── Paths / constants ────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[3]
STORE_DIR = ROOT / "data" / "fundamentals"

# Ten years ≈ 40 quarters ≈ 10 KB of CSV per ticker. Matches the price store's
# depth so the two can be joined over their whole overlap.
KEEP_YEARS = 10

# Metric columns, in on-disk order. Adding one rewrites every row once — a
# deliberate, reviewable event. Do not reorder.
METRICS = (
    "revenue", "gross_profit", "operating_income", "net_income",
    "eps_basic", "eps_diluted", "shares_diluted",
    "rnd_expense", "sga_expense", "dep_amort",
    "ocf", "capex",
    "cash_and_equiv", "short_term_investments",
    "long_term_debt", "short_term_debt",
    "total_assets", "total_equity",
)

# Column order is part of the on-disk contract (I1). Do not reorder.
FIELDS = ("period_end", "fy", "fp", "form", "filed") + METRICS
HEADER = ",".join(FIELDS)


# ── Serialisation ────────────────────────────────────────────────────────────
# Deterministic and idempotent: formatting a value, parsing it back and
# formatting again must produce the same bytes. Fixed-point output (never
# `repr`) keeps scientific notation out of the CSV.
def fmt_value(v) -> str:
    """Canonical numeric text: integral values bare, otherwise up to 4 decimals.

    Statement figures are whole dollars (``96220000000``) while per-share ones
    are fractional (``2.46``); one formatter covers both without carrying a
    per-metric type table. Empty for a metric the filer does not tag — an
    absent figure must never serialise as ``0``.
    """
    if v is None:
        return ""
    s = f"{round(float(v), 4):.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def serialise(rows: list[dict]) -> str:
    """Render rows as the canonical CSV text (header + one line per period)."""
    out = [HEADER]
    for r in rows:
        out.append(",".join(
            [r["period_end"], str(r["fy"]), r["fp"], r["form"], r["filed"]]
            + [fmt_value(r.get(m)) for m in METRICS]
        ))
    return "\n".join(out) + "\n"


def parse(text: str) -> list[dict]:
    """Parse canonical CSV text into rows. Malformed lines are skipped.

    Hand-rolled rather than ``csv.reader`` for the same reason the price store
    is: no field can contain a comma or quote, and the docs build reads every
    store on every run.
    """
    rows: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("period_end,"):
            continue
        parts = line.split(",")
        if len(parts) < 5:
            continue
        try:
            row = {
                "period_end": parts[0],
                "fy": int(parts[1]),
                "fp": parts[2],
                "form": parts[3],
                "filed": parts[4],
            }
            for i, m in enumerate(METRICS, start=5):
                raw = parts[i] if i < len(parts) else ""
                row[m] = float(raw) if raw else None
        except ValueError:
            continue
        rows.append(row)
    return rows


# ── Store I/O ────────────────────────────────────────────────────────────────
def store_path(key: str, store_dir: Path | None = None) -> Path:
    """Path to a ticker's CSV. ``key`` is the lowercased report key."""
    return (store_dir or STORE_DIR) / f"{key.strip().lower()}.csv"


def load_store(key: str, store_dir: Path | None = None) -> list[dict]:
    """Rows for a ticker, oldest→newest. Empty list when the file is absent."""
    p = store_path(key, store_dir)
    if not p.exists():
        return []
    return parse(p.read_text(encoding="utf-8"))


def write_store(key: str, rows: list[dict], store_dir: Path | None = None) -> bool:
    """Write rows atomically (I5). Returns True only if the bytes changed (I2)."""
    p = store_path(key, store_dir)
    text = serialise(rows)
    if p.exists() and p.read_text(encoding="utf-8") == text:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".csv.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)  # atomic within the same directory
    return True


# ── Merge / trim ─────────────────────────────────────────────────────────────
def upsert(old: list[dict], new: list[dict]) -> list[dict]:
    """Merge fetched rows over stored ones, sorted and deduplicated (I3).

    A fetched period always wins — that single rule is the entire restatement
    story, exactly as it is for prices.
    """
    merged = {r["period_end"]: r for r in old}
    merged.update({r["period_end"]: r for r in new})
    return [merged[k] for k in sorted(merged)]


def trim(rows: list[dict], years: int = KEEP_YEARS) -> list[dict]:
    """Drop periods older than ``years`` before the *newest period* (I4).

    Measured from the newest row rather than today so the result depends only on
    the data — which is what makes I2 hold strictly.
    """
    if not rows:
        return rows
    newest = date.fromisoformat(rows[-1]["period_end"])
    try:
        cutoff = newest.replace(year=newest.year - years).isoformat()
    except ValueError:  # 29 Feb → 28 Feb
        cutoff = newest.replace(year=newest.year - years, day=28).isoformat()
    return [r for r in rows if r["period_end"] >= cutoff]


# ── Concept mapping ──────────────────────────────────────────────────────────
# Ordered candidates per metric; the first concept that carries a given period
# wins. Chains rather than single tags because concepts drift *within* a
# company: MSFT's revenue runs Revenues (2007-10) → SalesRevenueNet (2009-18) →
# RevenueFromContractWithCustomer… (2016-26), the ASC 606 changeover. A single
# tag gives MSFT 14 quarters; the chain gives the full run.
DURATION_CONCEPTS = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet",
    ),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "eps_basic": ("EarningsPerShareBasic", "EarningsPerShareBasicAndDiluted"),
    "eps_diluted": ("EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"),
    "shares_diluted": (
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasicAndDiluted",
    ),
    "rnd_expense": (
        "ResearchAndDevelopmentExpense",
        "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
    ),
    "sga_expense": (
        "SellingGeneralAndAdministrativeExpense",
        "GeneralAndAdministrativeExpense",
    ),
    "dep_amort": (
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAndAmortization",
    ),
    "ocf": (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    "capex": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ),
}

INSTANT_CONCEPTS = {
    "cash_and_equiv": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    "short_term_investments": (
        "ShortTermInvestments",
        "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
    ),
    "long_term_debt": ("LongTermDebtNoncurrent", "LongTermDebt"),
    "short_term_debt": ("LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings"),
    "total_assets": ("Assets",),
    "total_equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
}

# Units we read. Money is USD; per-share figures carry their own unit, and share
# counts are dimensionless.
_UNITS = ("USD", "USD/shares", "shares")

# Metrics that are *not* cumulative over the fiscal year and so must never be
# recovered by differencing. A diluted share count is a weighted average over
# its period: NVDA reports 24.61B / 24.57B / 24.54B / 24.51B year-to-date, and
# differencing those yields -0.03B — not a number, an artefact. Flows (revenue,
# income, cash) and per-share earnings do accumulate, so they difference
# correctly; a share count only ever comes from a directly reported period,
# falling back to the fiscal year's own weighted average for the final quarter.
NON_CUMULATIVE = ("shares_diluted",)

# Metrics that cannot legitimately be negative. Used to reject a *differenced*
# value — never a reported one, which is whatever the filer said it was.
#
# This catches the one way the year-to-date chain lies: a 10-K sometimes tags a
# concept more narrowly than the 10-Qs did, so the annual figure is smaller than
# the nine-month one it is supposedly the superset of. WDC FY2023 runs
# 3.74 → 6.84 → 9.65 → 6.26 on the same concept, and differencing the last step
# yields -3.39B of revenue. Refusing the value lets the next concept in the
# chain supply the period instead — which for KTOS FY2011 is exactly what
# SalesRevenueNet does, with a cleanly reported Q4 the first concept lacked.
NON_NEGATIVE = ("revenue", "shares_diluted", "rnd_expense", "sga_expense", "capex")

# Largest quarter-on-quarter change a share count can plausibly make. A money
# figure that is mis-scaled by a factor of 1000 trips the gate (gross profit
# would exceed revenue); a share count has no such relationship to check
# against, and it feeds market cap, so a scale error there puts a valuation
# three orders of magnitude out on the page.
#
# ONDS's FY2025 10-K tags diluted shares as 221,769 where the quarters run
# 105.0M / 150.7M / 259.9M — the filer dropped a factor of 1000 in the annual
# figure itself, so there is no correct alternative in the payload to prefer.
# Dropping the value leaves the market cap absent, which is honest; publishing
# it would not be. A genuine reverse split is the one legitimate way to trip
# this, and omitting a quarter is the better error.
MAX_SHARE_COUNT_STEP = 10.0


# ── XBRL extraction ──────────────────────────────────────────────────────────
def _days(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


# Periodic reports are the financial statements themselves; a proxy or
# registration statement merely repeats a figure out of one. Both carry the same
# number in practice, but preferring the filing that *is* the statement keeps the
# `form` column meaningful as provenance.
_PERIODIC_FORMS = ("10-K", "10-Q", "20-F", "40-F", "6-K", "8-K")


def _latest(points: list[dict]):
    """The authoritative point for one period.

    Measured on AMZN: up to four points per (concept, period), because every
    later filing repeats earlier periods as comparatives. The one to trust is
    the filing in which the period *is* the reporting period — the closest
    filing after the period end — not the most recent one to mention it.

    Later is not better. ONDS tags Q1 2025 diluted shares as 105,004,818 in the
    original 10-Q and as 105,005 in the comparative column of the next year's
    10-Q, having dropped a factor of 1000. Preferring the latest filing picks
    the broken figure and puts a market cap three orders of magnitude too small
    on the page; preferring the original picks the right one.

    The trade-off is that a genuine restatement in a later filing is not picked
    up while the original filing still covers the period — which is the "as
    first reported" convention, and the safer default when the alternative is
    trusting whichever transcription happened most recently.
    """
    def rank(p):
        form = p.get("form", "")
        periodic = any(form.startswith(f) for f in _PERIODIC_FORMS)
        filed, end = p.get("filed", ""), p.get("end", "")
        # Negative so that `max` prefers the smallest gap; a filing dated before
        # the period end (a forecast or an error) sorts worst.
        gap = -abs((date.fromisoformat(filed) - date.fromisoformat(end)).days) \
            if filed and end else -99999
        return (periodic, gap, p.get("accn", ""))

    return max(points, key=rank)


def _facts(node: dict, want_duration: bool) -> dict:
    """{(start, end): point} for one concept, deduped by filing date."""
    by_period: dict = {}
    for unit, points in (node.get("units") or {}).items():
        if unit not in _UNITS:
            continue
        for p in points:
            has_start = "start" in p
            if has_start != want_duration or "end" not in p or "val" not in p:
                continue
            key = (p.get("start", ""), p["end"])
            by_period.setdefault(key, []).append(p)
    return {k: _latest(v) for k, v in by_period.items()}


def fiscal_years(gaap: dict) -> list[tuple[str, str]]:
    """(start, end) of each fiscal year, newest last.

    Taken from whichever revenue concept carries ~annual spans. The fiscal
    calendar has to come from the data: AVGO's years end on dates like
    2026-11-01, so nothing about it can be assumed from the calendar.
    """
    years: dict[str, str] = {}
    for concept in DURATION_CONCEPTS["revenue"]:
        node = gaap.get(concept)
        if not node:
            continue
        for (start, end) in _facts(node, want_duration=True):
            if 350 < _days(start, end) < 380:
                years.setdefault(end, start)
    return [(years[e], e) for e in sorted(years)]


def discrete_quarters(facts: dict, fy_start: str, fy_end: str,
                      cumulative: bool = True, non_negative: bool = False) -> dict:
    """{period_end: value} for the four quarters of one fiscal year.

    Prefers a directly reported ~90-day fact. For cumulative metrics the rest is
    recovered by differencing consecutive year-to-date facts: cash-flow items
    are *only* ever reported that way (3/6/9/12-month spans from the fiscal year
    start), and income items stop tagging Q4 discretely because the 10-K reports
    the full year — one rule handles both.

    ``cumulative=False`` (see :data:`NON_CUMULATIVE`) takes reported quarters
    only, falling back to the fiscal year's own figure for the final quarter.
    """
    out: dict = {}

    # Directly reported quarters. Q1 comes through here too: its year-to-date
    # span *is* one quarter.
    for (start, end), p in facts.items():
        if fy_start <= start and end <= fy_end and 80 < _days(start, end) < 100:
            out[end] = p["val"]

    # Year-to-date chain: everything starting at the fiscal year start.
    ytd = {}
    limit = (date.fromisoformat(fy_start) + timedelta(days=5)).isoformat()
    for (start, end), p in facts.items():
        if fy_start <= start <= limit and end <= fy_end:
            ytd[end] = p["val"]

    if not cumulative:
        # A weighted average can't be differenced, so the closing quarter falls
        # back to the annual figure — the same measure over a longer window,
        # which for a share count sits within ~0.5% of the quarter's own.
        if ytd and fy_end not in out:
            out[fy_end] = ytd[fy_end] if fy_end in ytd else max(ytd.items())[1]
        return out

    prev_end, prev_val = None, 0.0
    for end in sorted(ytd):
        # The chain has to *start* at a quarter. MSFT's 2008 operating income
        # is tagged only as a 365-day fact; treating that lone point as a first
        # quarter would publish the whole year's profit as Q4.
        step = _days(prev_end, end) if prev_end else _days(fy_start, end)
        if end not in out and 80 < step < 100:
            value = round(ytd[end] - prev_val, 4)
            # A negative result here means the chain is inconsistent, not that
            # the quarter was negative. Leave the period unset so the next
            # concept in the chain can claim it.
            if not (non_negative and value < 0):
                out[end] = value
        prev_end, prev_val = end, ytd[end]

    return out


def _plausible_share_counts(counts: dict) -> dict:
    """Drop share counts that jump by more than :data:`MAX_SHARE_COUNT_STEP`.

    Anchored on the running median rather than the previous value, so one bad
    figure cannot drag the rest of the series out with it.
    """
    kept: dict = {}
    for end in sorted(counts):
        value = counts[end]
        if kept and value > 0:
            ordered = sorted(kept.values())
            median = ordered[len(ordered) // 2]
            ratio = value / median if median else 0
            if ratio > MAX_SHARE_COUNT_STEP or ratio < 1 / MAX_SHARE_COUNT_STEP:
                continue
        kept[end] = value
    return kept


def resolve(facts_json: dict) -> list[dict]:
    """Turn a companyfacts payload into store rows, oldest→newest."""
    gaap = (facts_json.get("facts") or {}).get("us-gaap") or {}
    if not gaap:
        return []

    years = fiscal_years(gaap)
    if not years:
        return []

    # Duration metrics: reconstruct discrete quarters per fiscal year, taking
    # the first concept in the chain that covers each period.
    values: dict = {m: {} for m in METRICS}
    for metric, concepts in DURATION_CONCEPTS.items():
        cumulative = metric not in NON_CUMULATIVE
        non_negative = metric in NON_NEGATIVE
        for concept in concepts:
            node = gaap.get(concept)
            if not node:
                continue
            facts = _facts(node, want_duration=True)
            for fy_start, fy_end in years:
                quarters = discrete_quarters(facts, fy_start, fy_end,
                                             cumulative, non_negative)
                for end, val in quarters.items():
                    values[metric].setdefault(end, val)

    values["shares_diluted"] = _plausible_share_counts(values["shares_diluted"])

    # Instant metrics: balance-sheet figures are as-of a date, no reconstruction.
    for metric, concepts in INSTANT_CONCEPTS.items():
        for concept in concepts:
            node = gaap.get(concept)
            if not node:
                continue
            for (_, end), p in _facts(node, want_duration=False).items():
                values[metric].setdefault(end, p["val"])

    # Provenance: which filing closed each period.
    provenance: dict = {}
    for concept in DURATION_CONCEPTS["revenue"]:
        node = gaap.get(concept)
        if not node:
            continue
        for (start, end), p in _facts(node, want_duration=True).items():
            provenance.setdefault(end, (p.get("form", ""), p.get("filed", "")))

    # One row per fiscal quarter, labelled from the fiscal-year boundaries
    # rather than from the unreliable fy/fp fields.
    rows: list[dict] = []
    for fy_start, fy_end in years:
        ends = sorted({e for e in values["revenue"] if fy_start < e <= fy_end})
        if not ends:
            continue
        for end in ends[-4:]:
            # Quarter index measured from the fiscal-year start, not from this
            # list's position. A year whose early quarters were never recovered
            # — the year-to-date chain often begins mid-year — would otherwise
            # relabel its survivors Q1 onward: ONDS's 2015-12-31 came out as Q2
            # of a December fiscal year, which is its fourth quarter.
            quarter = min(4, max(1, round(_days(fy_start, end) / 91.0)))
            form, filed = provenance.get(end, ("", ""))
            row = {
                "period_end": end,
                "fy": int(fy_end[:4]),
                "fp": f"Q{quarter}",
                "form": form,
                "filed": filed,
            }
            for m in METRICS:
                row[m] = values[m].get(end)
            rows.append(row)

    return sorted(rows, key=lambda r: r["period_end"])


# ── Fetch ────────────────────────────────────────────────────────────────────
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# SEC asks for a descriptive User-Agent and throttles anonymous traffic; this
# mirrors scripts/edgar_common.py so the two behave identically.
HEADERS = {"User-Agent": "finance-data-research contact@example.com"}


def _get_json(url: str, timeout: int = 60):
    import urllib.request
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        import json
        return json.loads(resp.read().decode("utf-8"))


def cik_map() -> dict:
    """{TICKER: zero-padded CIK} for every SEC registrant."""
    data = _get_json(TICKERS_URL)
    return {e["ticker"].upper(): str(e["cik_str"]).zfill(10)
            for e in data.values()}


class NoFacts(Exception):
    """The registrant exists but files no XBRL facts (an ETF or trust)."""


def fetch_facts(cik: str) -> dict | None:
    """Fetch one company's XBRL facts.

    Raises :class:`NoFacts` on a 404 — an ETF has a CIK and files with SEC, but
    has no financial statements to tag, so that is an expected outcome rather
    than an error. Returns None on any other failure.
    """
    import urllib.error
    try:
        return _get_json(COMPANYFACTS_URL.format(cik=str(cik).zfill(10)))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NoFacts(str(cik)) from exc
        print(f"  ⚠ companyfacts fetch failed: {exc}")
        return None
    except Exception as exc:  # network, malformed payload
        print(f"  ⚠ companyfacts fetch failed: {exc}")
        return None


# ── Sanity gate ──────────────────────────────────────────────────────────────
# A self-healing writer is also a self-destroying writer when upstream is wrong.
MIN_PERIOD_RATIO = 0.9
RECONCILE_TOLERANCE = 0.01  # 1%


def gate(new: list[dict], old: list[dict]) -> str | None:
    """Return a reason to reject ``new``, or None to accept it.

    Scoped to what actually goes wrong with XBRL: a mapping change that drops
    periods, a sign error, or an ordering violation that means the wrong
    concept got picked up.
    """
    if not new:
        return "empty result"

    overlapping = [r for r in old if r["period_end"] <= new[-1]["period_end"]]
    if len(new) < MIN_PERIOD_RATIO * len(overlapping):
        return (f"period count regression: {len(new)} < "
                f"{MIN_PERIOD_RATIO:.0%} of {len(overlapping)}")

    ends = [r["period_end"] for r in new]
    if ends != sorted(set(ends)):
        return "period ends not strictly ascending"

    # Only invariants that hold by *definition* belong here. Gross profit is
    # revenue less cost of revenue, so it cannot exceed revenue. Operating
    # income can and does exceed gross profit — AMD's 2009 Q4 booked the
    # GlobalFoundries settlement gain above the operating line — so comparing
    # those two would reject a decade of correct data over a real figure.
    for r in new:
        rev = r.get("revenue")
        if rev is not None and rev < 0:
            return f"negative revenue at {r['period_end']}"
        gp = r.get("gross_profit")
        if rev is not None and gp is not None and gp > rev * (1 + RECONCILE_TOLERANCE):
            return f"gross profit exceeds revenue at {r['period_end']}"

    return None


# ── Update ───────────────────────────────────────────────────────────────────
def update(key: str, cik: str, years: int = KEEP_YEARS,
           store_dir: Path | None = None,
           dry_run: bool = False) -> tuple[str, str]:
    """Refresh one ticker's store. Returns ``(status, detail)``.

    Status is one of created / appended / restated / unchanged / skipped /
    failed, matching :func:`prices.update` so the two CLIs read alike.
    """
    old = load_store(key, store_dir)
    try:
        facts = fetch_facts(cik)
    except NoFacts:
        return "skipped", "registrant files no XBRL facts (ETF or trust)"
    if facts is None:
        return "failed", "fetch failed"

    new = resolve(facts)
    if not new:
        return "skipped", "no us-gaap facts (ETF, or an IFRS filer)"

    reason = gate(new, old)
    if reason:
        return "skipped", reason

    merged = trim(upsert(old, new), years)
    if dry_run:
        changed = serialise(merged) != serialise(old)
        return ("appended" if changed else "unchanged",
                f"{len(merged)} periods [dry run]")
    if not write_store(key, merged, store_dir):
        return "unchanged", f"{len(merged)} periods"

    if not old:
        return "created", f"{len(merged)} periods"
    added = len(merged) - len(old)
    if added > 0:
        return "appended", f"+{added} period(s), {len(merged)} total"
    return "restated", f"{len(merged)} periods"
