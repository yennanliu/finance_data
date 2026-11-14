"""The report's one scorecard: read its sub-scores, compute the composite.

The 2026-11-14 review (``docs/REPORT_REVIEW.md`` F9, F10, T8) found three
scorecards in a fundamental report with different scores for similar items
and no formula for the total, and no score, rating or signal in either
report's front matter. Each report now has one scorecard table. The model
gives the sub-scores, which are its judgement; the composite is their
arithmetic mean, which is arithmetic, so it is computed here, written back
over whatever the model printed, and recorded in the front matter.

Pure stdlib: ``pipeline.py`` calls it after generation and stage-1 QA reads
the same parsers.
"""

from __future__ import annotations

import re

# Sub-score labels in table order, and the decimals of the composite.
FUNDAMENTAL = {"labels": ("成長性", "獲利能力", "財務健康", "估值", "護城河", "管理層與資本配置"),
               "scale": 10, "digits": 1, "chapter": 1}
TECHNICAL = {"labels": ("趨勢強度", "動能指標", "支撐穩定度", "成交量配合", "形態完整度", "均線排列"),
             "scale": 100, "digits": 0, "chapter": 1}
TOTAL_RE = re.compile(r"綜合評分|綜合總分")
# A line elsewhere in the report that restates the composite.
MENTION_RE = re.compile(r"綜合評分|綜合總分|投資評分|依評分|總分")

# Technical signal thresholds: the prompt's strategy routing.
BULLISH_AT, BEARISH_AT = 60, 40

# Rule 20's ratings, worst to best.
RATING_ORDER = ("賣出", "減碼", "持有", "買入", "強烈買入")
_RATING_WORD = re.compile("|".join(sorted(RATING_ORDER, key=len, reverse=True)))

_NUM = r"(\d{1,3}(?:\.\d+)?)"


def chapter(text: str, n: int) -> str:
    m = re.search(rf"^## {n}\..*?(?=^## \d+\.|\Z)", text, re.S | re.M)
    return m.group(0) if m else ""


def _score_in(line: str, label: str, scale: int) -> "float | None":
    """The score a line gives for ``label``: the first table cell after the
    label that is a bare number (optionally ``/scale``), or, outside a table,
    the first ``N/scale``."""
    rest = line.split(label, 1)[1]
    if "|" in rest:
        for cell in rest.split("|")[1:]:
            m = re.fullmatch(rf"\**\s*{_NUM}\s*(?:/\s*{scale})?\s*\**", cell.strip())
            if m:
                return float(m.group(1))
        return None
    m = re.search(rf"{_NUM}\s*/\s*{scale}\b", rest)
    return float(m.group(1)) if m else None


def _round_half_up(value: float, digits: int) -> "float | int":
    """Half rounds up (42.5 → 43), as a reader with a calculator expects;
    ``round()`` would give 42. Sub-scores are small decimals, so the 1e-9
    absorbs binary noise without moving a real half."""
    scaled = int(value * 10 ** digits + 0.5 + 1e-9)
    return scaled / 10 ** digits if digits else scaled


def _card(text: str, spec: dict) -> str:
    """The scorecard itself: the table in the spec's chapter that names the
    most sub-scores (at least half), so a score quoted in another table of the
    chapter is not read as a sub-score. Without such a table (an older report
    drew the card as an ASCII box) the whole chapter is searched."""
    body = chapter(text, spec["chapter"])
    best, hits = body, 0
    for table in re.findall(r"(?:^\|.*\n?)+", body, re.M):
        n = sum(1 for label in spec["labels"] if label in table)
        if n > hits:
            best, hits = table, n
    return best if hits * 2 >= len(spec["labels"]) else body


def read(text: str, spec: dict) -> dict:
    """``{"scores": {label: score}, "stated": composite or None, "total": mean
    or None}`` from the report's scorecard.

    ``total`` is None unless every sub-score was found and is within the scale:
    a mean of five of six would be a different quantity from the one defined.
    """
    scores, stated = {}, None
    for line in _card(text, spec).splitlines():
        if stated is None and TOTAL_RE.search(line):
            stated = _score_in(line, TOTAL_RE.search(line).group(0), spec["scale"])
            continue
        for label in spec["labels"]:
            if label not in scores and label in line:
                value = _score_in(line, label, spec["scale"])
                if value is not None and 0 <= value <= spec["scale"]:
                    scores[label] = value
                break
    total = None
    if len(scores) == len(spec["labels"]):
        total = _round_half_up(sum(scores.values()) / len(scores), spec["digits"])
    return {"scores": scores, "stated": stated, "total": total}


def _fmt(value: float, digits: int) -> str:
    return f"{value:.{digits}f}"


def fix(text: str, spec: dict) -> "tuple[str, dict]":
    """Write the computed composite over the stated one: on the scorecard's
    total row, and wherever else a line restates it as ``N/scale`` or ``N 分``.
    Returns the report and the :func:`read` result with ``"corrected": bool``.

    Only a number in one of those forms is touched, so another figure on the
    same line that happens to equal the old composite is left alone.
    """
    result = read(text, spec)
    result["corrected"] = False
    total, stated = result["total"], result["stated"]
    if total is None or stated is None or abs(total - stated) < 10 ** -spec["digits"] / 2:
        return text, result
    new = _fmt(total, spec["digits"])
    digits = _fmt(stated, spec["digits"]).split(".")
    # The stated figure as the model may have printed it: "7", "7.0", "7.20".
    old = re.escape(digits[0]) + (rf"(?:\.{digits[1]}0*)" + ("?" if set(digits[1]) == {"0"} else "")
                                  if len(digits) > 1 else r"(?:\.0+)?")
    bare = re.compile(rf"(?<![\d.]){old}(?![\d.])")
    scaled = re.compile(rf"(?<![\d.]){old}(?=\s*(?:/\s*{spec['scale']}\b|分))")
    out, total_row_done = [], False
    for line in text.splitlines(keepends=True):
        if not total_row_done and TOTAL_RE.search(line) and _score_in(
                line, TOTAL_RE.search(line).group(0), spec["scale"]) == stated:
            head, tail = line.split(TOTAL_RE.search(line).group(0), 1)
            line = head + TOTAL_RE.search(line).group(0) + bare.sub(new, tail, count=1)
            total_row_done = True
        elif MENTION_RE.search(line):
            line = scaled.sub(new, line)
        out.append(line)
    fixed = "".join(out)
    result["corrected"] = fixed != text
    return fixed, result


def signal(score: "float | None") -> "str | None":
    """``bullish`` / ``neutral`` / ``bearish`` from a technical composite, by
    the thresholds the prompt routes its main strategy on."""
    if score is None:
        return None
    return "bullish" if score >= BULLISH_AT else "bearish" if score <= BEARISH_AT else "neutral"


def stated_rating(text: str) -> "str | None":
    """The rating the executive summary gives: the rating word on the first
    chapter-1 line that says 評級. On a line that adjusts it ("依 MOS 應為 X，
    調整為 Y") the adjusted one is taken."""
    for line in chapter(text, 1).splitlines():
        if "評級" not in line or "評級門檻" in line:
            continue
        adjusted = re.search(r"調整為\s*\**\s*(" + _RATING_WORD.pattern + ")", line)
        if adjusted:
            return adjusted.group(1)
        words = _RATING_WORD.findall(line)
        # "強烈買入/買入/持有/減碼/賣出" is the template's own list, not a rating.
        if words and len(set(words)) == 1:
            return words[0]
    return None


def rating_gap(stated: "str | None", computed: "str | None") -> "int | None":
    """How many notches the report's rating is from the computed one (positive
    = more bullish), or None when either is not one of rule 20's five."""
    if stated not in RATING_ORDER or computed not in RATING_ORDER:
        return None
    return RATING_ORDER.index(stated) - RATING_ORDER.index(computed)


__all__ = ["FUNDAMENTAL", "TECHNICAL", "read", "fix", "signal", "stated_rating",
           "rating_gap", "RATING_ORDER", "BULLISH_AT", "BEARISH_AT"]
