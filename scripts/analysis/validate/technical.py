"""Deterministic checks for technical-analysis reports (QA stage 1).

Each check compares the report with something it cannot argue with: the
price and computed support/resistance levels the pipeline recorded in the
front matter, or the report's own entry/stop/target figures. Background:
``docs/TECHNICAL_REPORT_REVIEW.md`` — eight 2026-10-23 reports were written
on a ``$nan`` close and invented their levels, and TSM stated an R/R of
1 : 3.48 next to its own risk $11.5 / reward $51.97 (1 : 4.52). Pure stdlib.
"""

from __future__ import annotations

import re

from .market_data import quote_mismatch

LEVEL_TOLERANCE = 0.02    # dollars; levels are quoted to the cent
RR_TOLERANCE = 0.05       # relative, with an absolute floor of 0.06

NAN_RE = re.compile(r"\$\s*nan\b|\bnan\s*%|\bnan\s*\(當週\)", re.IGNORECASE)
HEADLINE_RE = re.compile(r"當前(?:基準)?價格\*\*[：:]\s*(?:NT)?\$?\s*([\d,]+(?:\.\d+)?)")
MONEY_RE = re.compile(r"\$\s*(-?\d[\d,]*(?:\.\d+)?)")
LABEL_RE = re.compile(r"\b([RS][123])\b")
RATIO_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[:：]\s*(\d+(?:\.\d+)?)")
RANGE_RE = re.compile(r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*(?:[–—~～-]|至)\s*\$?\s*(\d[\d,]*(?:\.\d+)?)")


def front_matter(text: str) -> dict:
    """Flat ``key: value`` pairs of a report's front matter (quotes stripped)."""
    m = re.match(r"^---\n(.+?)\n---\n", text, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


def parse_levels(summary: str) -> dict:
    """``"R1 562.23; S1 496.75"`` → ``{"R1": 562.23, "S1": 496.75}``."""
    return {k: float(v) for k, v in re.findall(r"([RS][123])\s+(-?\d+(?:\.\d+)?)", summary or "")}


def chapter(text: str, n: int) -> str:
    # Ends at the next numbered chapter, whichever it is: a report that skips
    # one must not have the following chapter's tables read as this one's.
    m = re.search(rf"^## {n}\..*?(?=^## \d+\.|^## 📋|\Z)", text, re.S | re.M)
    return m.group(0) if m else ""


def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _money(cell: str):
    m = MONEY_RE.search(cell)
    return float(m.group(1).replace(",", "")) if m else None


def _entry_prices(cell: str) -> list:
    """Entry prices a stated R/R may have been computed from: for a range
    ("$435–$440", "$718.35 至 $696.97") its midpoint — what prompt rule 17
    asks for — then either end, which reports written before that rule used
    (and usually said so); otherwise the cell's single price."""
    m = RANGE_RE.search(re.sub(r"\*|（[^）]*）|\([^)]*\)", "", cell))
    if m:
        lo, hi = (float(g.replace(",", "")) for g in m.groups())
        return [(lo + hi) / 2, lo, hi]
    single = _money(cell)
    return [single] if single is not None else []


def nan_values(text: str) -> list:
    """Every ``$nan`` / ``nan%`` the report printed."""
    return [m.group(0) for m in NAN_RE.finditer(text)]


def headline_price(text: str):
    m = HEADLINE_RE.search(text)
    return float(m.group(1).replace(",", "")) if m else None


def price_mismatch(text: str, price) -> "dict | None":
    """The headline 當前價格 against the close the context was given."""
    return quote_mismatch(headline_price(text), price)


def level_mismatches(text: str, levels: dict) -> list:
    """Ch.4 table rows labelled R1–R3 / S1–S3 whose value is not the computed
    level of the same label. Labels the pipeline did not compute are skipped."""
    out = []
    for line in chapter(text, 4).splitlines():
        if not line.startswith("|"):
            continue
        cells = _cells(line)
        m = LABEL_RE.search(cells[0]) if cells else None
        if not m or m.group(1) not in levels or len(cells) < 2:
            continue
        value = _money(cells[1])
        expected = levels[m.group(1)]
        if value is not None and abs(value - expected) > LEVEL_TOLERANCE:
            out.append({"label": m.group(1), "stated": value, "computed": expected})
    return out


_ROWS = {
    "entry": r"進場價",
    "t1": r"T1|第一目標|目標價\s*1",
    "t2": r"T2|第二目標|目標價\s*2",
    "stop": r"止損",
    "rr": r"風險報酬",
}


def _ratio(cell: str):
    m = RATIO_RE.search(cell.replace("$", ""))
    if not m:
        return None
    a, b = float(m.group(1)), float(m.group(2))
    if a == 1:
        return b
    if b == 1:
        return a
    return b / a if a else None


def rr_mismatches(text: str) -> list:
    """Ch.8 strategy columns whose stated R/R matches neither
    ``(T1 − entry) / (entry − stop)`` nor the same to T2 (sign-aware, so a
    short's target below entry and stop above it also come out positive)."""
    # Rows are read from the one table that holds the R/R row: the scenario
    # tables above it also have 止損 / 目標 rows, in other columns.
    rows = {}
    for table in re.findall(r"(?:^\|.*\n?)+", chapter(text, 8), re.M):
        found = {}
        for line in table.splitlines():
            cells = _cells(line)
            head = re.sub(r"[*\s]", "", cells[0]) if cells else ""
            for key, pat in _ROWS.items():
                if key not in found and re.search(pat, head):
                    found[key] = cells
                    break
        if all(k in found for k in ("entry", "stop", "rr")):
            rows = found
            break
    if not rows:
        return []
    out = []
    for col in range(1, len(rows["rr"])):
        try:
            entries, stop = _entry_prices(rows["entry"][col]), _money(rows["stop"][col])
            stated = _ratio(rows["rr"][col])
            targets = [_money(rows[k][col]) for k in ("t1", "t2") if k in rows]
        except IndexError:
            continue
        entries = [e for e in entries if e and e != stop]
        if not entries or not stop or not stated:
            continue

        def ratios(entry):
            calc = [round((t - entry) / (entry - stop), 2) for t in targets if t]
            return [c for c in calc if c > 0]

        if not any(abs(stated - c) <= max(0.06, RR_TOLERANCE * c)
                   for e in entries for c in ratios(e)) and ratios(entries[0]):
            out.append({"column": col, "stated": stated, "recomputed": ratios(entries[0])})
    return out


def check(text: str) -> "dict[str, list | dict]":
    """All technical checks; empty values mean the check passed or could not run."""
    fm = front_matter(text)
    try:
        price = float(fm["price"]) if fm.get("price") else None
    except ValueError:
        price = None
    return {
        "nan": nan_values(text),
        "price": price_mismatch(text, price),
        "levels": level_mismatches(text, parse_levels(fm.get("levels", ""))),
        "rr": rr_mismatches(text),
    }


__all__ = ["check", "nan_values", "price_mismatch", "level_mismatches",
           "rr_mismatches", "parse_levels", "front_matter", "headline_price"]
