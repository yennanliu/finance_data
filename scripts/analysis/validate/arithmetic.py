"""Re-check a fundamental report's §8.8 weighted fair value in Python.

25 of the 36 fundamental reports checked on 2026-10-22 printed a §8.8 weighted
fair value that differs by more than 0.5% from the sum of their own
``value × weight`` terms (``docs/FUNDAMENTAL_REPORT_REVIEW.md`` §12). Some
mis-add a subtotal; nine compute the right sum and then swap in a different
number with an invented reason ("精確微調", "區域匯率緩衝"). MOS and upside
inherit the wrong total.

:func:`check` recomputes the total from the terms the report itself printed.
It never second-guesses a term, only the addition, so a mismatch is always a
plain arithmetic error. Pure standard library: the stage-1 audit imports it.
"""

from __future__ import annotations

import re
from collections import Counter

# A mismatch above this is an error; below it, rounding.
TOLERANCE_PCT = 0.5

# Chapters every fundamental report must carry (prompts/fundamental.txt).
FUNDAMENTAL_CHAPTERS = tuple(range(1, 12))

_NUM = r"(\d[\d,]*(?:\.\d+)?)"
# "$583.87 × 35%", "NT$218.70 × 50%", "\$14.38 \times 40\%", "($181.75 × 0.40)"
_TERM = re.compile(
    r"\$\s?" + _NUM + r"\s*\)?\s*(?:×|\\times|\*)\s*\(?\s*(?:" + _NUM + r"\s*\\?%|(0?\.\d+))"
)
_STATED = re.compile(
    r"^\|\s*\**[★\s]*(?:綜合)?加權合理(?:價值|價格)[^|]*\|\s*\**\s*(?:NT)?\\?\$\s?" + _NUM, re.M
)
_RESULT = re.compile(r"=\s*\**\s*(?:\\mathbf\{)?(?:NT)?\\?\$\s?" + _NUM + r"\**\s*(?:（|\(|$|。|\s*≈)")
_PRICE = re.compile(
    r"(?:現價|當前股價|目前股價|目前市價|當前市價)\**\s*[:：]?\s*(?:為\s*)?\**\s*(?:NT)?\$\s?" + _NUM
)


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def section(text: str, number: str) -> str:
    """The body of ``### <number>`` up to the next ### / ## heading."""
    m = re.search(r"^###\s+" + re.escape(number) + r"\b.*?(?=^###?\s|\Z)", text, re.M | re.S)
    return m.group(0) if m else ""


def weighted_terms(s88: str) -> "list[tuple[float, float]]":
    """The ``(value, weight)`` pairs of the weighted-sum formula: the non-table
    line carrying the most terms (the last such line on a tie)."""
    best: "list[tuple[float, float]]" = []
    for line in s88.splitlines():
        if line.lstrip().startswith("|"):
            continue
        terms = []
        for value, pct, dec in _TERM.findall(line):
            weight = _num(pct) / 100 if pct else float(dec)
            terms.append((_num(value), weight))
        if len(terms) >= 2 and len(terms) >= len(best):
            best = terms
    return best


def report_price(text: str) -> "float | None":
    """The price the report used: its most frequent 現價 figure."""
    found = _PRICE.findall(text)
    return _num(Counter(found).most_common(1)[0][0]) if found else None


def check(text: str, price: "float | None" = None) -> dict:
    """Recompute §8.8. ``status`` is ``ok``, ``mismatch`` or ``unparsed``.

    ``price`` defaults to the report's own 現價; the pipeline passes the price
    it handed the model, so a misquoted price also shows up in MOS.
    """
    s88 = section(text, "8.8")
    terms = weighted_terms(s88)
    m = _STATED.search(s88)
    stated = _num(m.group(1)) if m else None
    if stated is None:
        # No table row (NBIS): the total is the last "= $X" of the derivation.
        ends = [x for line in s88.splitlines() if not line.lstrip().startswith("|")
                for x in _RESULT.findall(line)]
        stated = _num(ends[-1]) if ends else None
    out = {"status": "unparsed", "terms": terms, "stated": stated, "total": None,
           "weights_pct": None, "diff_pct": None, "price": price or report_price(text),
           "mos": None, "upside": None, "stated_mos": None, "stated_upside": None}
    if not terms or stated is None:
        return out

    total = round(sum(v * w for v, w in terms), 2)
    weights = round(sum(w for _, w in terms) * 100, 1)
    diff = round((stated / total - 1) * 100, 2) if total else None
    out.update(total=total, weights_pct=weights, diff_pct=diff)
    p = out["price"]
    if p and total:
        out["mos"] = round((total - p) / total * 100, 1)
        out["upside"] = round((total - p) / p * 100, 1)
        out["stated_mos"] = round((stated - p) / stated * 100, 1)
        out["stated_upside"] = round((stated - p) / p * 100, 1)
    bad = (diff is None or abs(diff) > TOLERANCE_PCT or abs(weights - 100) > 0.5)
    out["status"] = "mismatch" if bad else "ok"
    return out


def missing_chapters(text: str, chapters=FUNDAMENTAL_CHAPTERS) -> "list[int]":
    """Chapter numbers with no ``## N.`` heading."""
    present = {int(n) for n in re.findall(r"^##\s+(\d{1,2})\.", text, re.M)}
    return [n for n in chapters if n not in present]


def _money(v: float) -> str:
    return f"${v:,.2f}"


def annotate(text: str, result: dict) -> str:
    """Insert the recomputation into the report.

    Always appends a 「程式複算」 block to §8.8. On a mismatch it also puts a
    one-line notice under the title, because the wrong total is repeated in the
    executive summary a reader sees first. The model's own numbers are left as
    written: a visible correction beats a silent rewrite of a figure that
    appears in a dozen places.
    """
    if result["status"] == "unparsed":
        return text
    terms = " + ".join(f"{_money(v)} × {w * 100:g}%" for v, w in result["terms"])
    lines = [
        "",
        "> 🔎 **程式複算（Python，依本節各項自動重算）**",
        f"> 加權合理價值 = {terms} = **{_money(result['total'])}**（權重合計 {result['weights_pct']:g}%）",
    ]
    if result["mos"] is not None:
        lines.append(f"> 以價格 {_money(result['price'])} 計：MOS = **{result['mos']:+.1f}%**，"
                     f"上行空間 = **{result['upside']:+.1f}%**")
    if result["status"] == "mismatch":
        lines.append(f"> ⚠️ 本節寫的是 {_money(result['stated'])}，與各項加總相差 {result['diff_pct']:+.2f}%；"
                     f"以上方複算值為準。")
    else:
        lines.append("> ✅ 與本節所寫數值一致。")
    # Empty ">" lines keep each line its own paragraph inside the quote.
    block = lines[0] + "\n" + "\n>\n".join(lines[1:]) + "\n"

    s88 = section(text, "8.8")
    if s88:
        text = text.replace(s88, s88.rstrip("\n") + "\n" + block + "\n", 1)

    if result["status"] == "mismatch":
        notice = (f"\n> ⚠️ **程式複算更正**：8.8 節加權合理價值應為 **{_money(result['total'])}**"
                  f"（報告寫 {_money(result['stated'])}）")
        if result["mos"] is not None:
            notice += (f"；據此 MOS 為 **{result['mos']:+.1f}%**（報告寫 {result['stated_mos']:+.1f}%），"
                       f"上行空間 **{result['upside']:+.1f}%**")
        # Blank line after: the title is followed directly by the 報告日期 quote,
        # which would otherwise merge into this one.
        notice += "。報告其他段落引用的舊數值請以此為準。\n\n"
        text = re.sub(r"^(# [^\n]+\n)", lambda m: m.group(1) + notice, text, count=1, flags=re.M)
    return text


__all__ = ["TOLERANCE_PCT", "FUNDAMENTAL_CHAPTERS", "section", "weighted_terms",
           "report_price", "check", "missing_chapters", "annotate"]
