"""Re-check a fundamental report's valuation arithmetic in Python: the §8.8
weighted fair value, and the headline MOS / DCF premium derived from it.

25 of the 36 fundamental reports checked on 2026-10-22 printed a §8.8 weighted
fair value that differs by more than 0.5% from the sum of their own
``value × weight`` terms (``docs/FUNDAMENTAL_REPORT_REVIEW.md`` §12). Some
mis-add a subtotal; nine compute the right sum and then swap in a different
number with an invented reason ("精確微調", "區域匯率緩衝"). MOS and upside
inherit the wrong total.

:func:`check` recomputes the total from the terms the report itself printed.
It never second-guesses a term, only the addition, so a mismatch is always a
plain arithmetic error. :func:`correct` then writes the recomputed total, MOS
and upside back into the report: the notice-only approach left 22 of 35
fundamental reports on 2026-10-23 opening with a banner saying their headline
fair value was wrong. Pure standard library: the stage-1 audit imports it.
"""

from __future__ import annotations

import re
from collections import Counter

# A mismatch above this is an error; below it, rounding.
TOLERANCE_PCT = 0.5
# MOS and the DCF premium are percentages, often printed to the whole point.
TOLERANCE_PP = 1.0

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
_PCT = r"([+\-−]?\d+(?:\.\d+)?)\s*%"
# §1.0 dashboard: "| **安全邊際（MOS）** | **-7.7%** ＝ ..."
_MOS = re.compile(r"安全邊際[^|\n]{0,12}\|\s*\**\s*" + _PCT)
# "DCF 內在價值（基準）** | **$403.07** ｜ 當前價格溢價 **+28.2%**"
_PREMIUM = re.compile(r"DCF 內在價值[^\n]*?\$\s?" + _NUM
                      + r"[^\n]*?(折溢價|溢價|折價)[^\d+\-−\n]{0,8}" + _PCT)
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


def _signed(s: str) -> float:
    return float(s.replace("−", "-"))


def valuation_mismatches(text: str, price, fair_value) -> "list[dict]":
    """The headline MOS and DCF premium against the report's own figures.

    Prompt rule 16 fixes both: MOS = (§8.8 fair value − price) / fair value,
    premium = price / DCF value − 1 (positive = price above value). AVGO
    2026-10-23 printed a premium of +16% on a DCF of $368.55 at $321.68
    (−12.7%); NVDA printed MOS +25% that its own figures make +35.9%. An
    unsigned "折溢價 16%" says nothing about direction and is skipped.
    """
    out = []
    if not price:
        return out
    m = _MOS.search(text)
    if m and fair_value:
        stated, expected = _signed(m.group(1)), (fair_value - price) / fair_value * 100
        if abs(stated - expected) > TOLERANCE_PP:
            out.append({"metric": "MOS", "stated": stated, "expected": round(expected, 1)})
    m = _PREMIUM.search(text)
    if m:
        dcf, word, raw = _num(m.group(1)), m.group(2), m.group(3)
        if raw[0] in "+-−":
            stated = _signed(raw)
        elif word != "折溢價":
            stated = float(raw) if word == "溢價" else -float(raw)
        else:
            stated = None
        expected = (price / dcf - 1) * 100 if dcf else None
        if stated is not None and expected is not None and abs(stated - expected) > TOLERANCE_PP:
            out.append({"metric": "premium", "stated": stated, "expected": round(expected, 1)})
    return out


# Prompt rule 20: the rating is set by which of these MOS bands it falls in.
RATING_BANDS = ((-25, "賣出"), (-10, "減碼"), (10, "持有"), (25, "買入"))
_TOP_BAND = "強烈買入／買入（視 ROIC 與 WACC）"


def rating_band(mos: float) -> str:
    for upper, label in RATING_BANDS:
        if mos < upper:
            return label
    return _TOP_BAND


def _money_re(v: float) -> "re.Pattern":
    """``$479.69`` / ``NT$1,068.84`` / ``\\$1,745`` as the report may have
    printed ``v``, never the prefix of a longer number."""
    forms = {f"{v:,.2f}", f"{v:.2f}"}
    if v == int(v):
        forms |= {f"{int(v):,}", str(int(v))}
    alts = "|".join(re.escape(f) for f in sorted(forms, key=len, reverse=True))
    return re.compile(r"(\\?\$\s?)(?:" + alts + r")(?!\d|[.,]\d)")


_MONEY_TOKEN = re.compile(r"(\\?\$\s?)" + _NUM + r"(?![\d.,]\d)")
_PCT_TOKEN = re.compile(r"([+\-−]?)(\d+(?:\.\d+)?)\s*(\\?%)")   # "\%" in LaTeX
_MOS_LINE = re.compile(r"安全邊際|MOS")
_UPSIDE_LINE = re.compile(r"上行空間|上漲空間")


def correct(text: str, result: dict) -> str:
    """Write the recomputed §8.8 total, MOS and upside back into the report.

    Only for a ``mismatch`` whose weights sum to 100%, and whose stated total
    is not itself one of the terms (see below): then the terms are a
    complete weighted average and their sum is the fair value by definition.
    The stated total is replaced wherever it is printed (it is repeated in the
    TOC, §1.0 and the ASCII boxes). MOS and upside are replaced only near a
    label naming them (or, for upside, beside the fair value), and only where
    the figure is within one unit in its last printed place of the old value
    (a whole percent must round to it),
    so an unrelated percentage on the same line survives. On those lines the
    "fair value − price" difference a derivation prints ("−$70.00 ÷ $233.78")
    is replaced too, unless the correction flips its sign.
    """
    if (result["status"] != "mismatch" or abs(result["weights_pct"] - 100) > 0.5
            or result["mos"] is None):
        return text
    stated, total, price = result["stated"], result["total"], result["price"]
    # Often the "total" is one of the terms carried down (TSLA, INTC and NVDA
    # 2026-10-23 each printed a method's own value as the weighted one).
    # Replacing it everywhere would rewrite that method's value too, so such
    # a report keeps its figures and gets the notice instead.
    if any(abs(v - stated) < 0.005 for v, _ in result["terms"]):
        return text
    text = _money_re(stated).sub(lambda m: m.group(1) + f"{total:,.2f}", text)

    old = {"mos": (stated - price) / stated * 100, "upside": (stated - price) / price * 100}
    new = {"mos": (total - price) / total * 100, "upside": (total - price) / price * 100}

    def swap(line: str, keys: list, loose: bool) -> str:
        def one(m):
            sign, digits = m.group(1), m.group(2)
            value = -float(digits) if sign in ("-", "−") else float(digits)
            places = len(digits.partition(".")[2])
            for k in keys:
                # One unit in the last place: MRVL 2026-10-27 printed upside
                # −30.0% for its −29.94%, and the exact match left it behind.
                # Only on a line that itself names the figure or shows the
                # fair value: under a table header, a method's own upside near
                # the old total (AVAV's DCF row, +18.6%) is not the total's.
                # A whole percent stays exact, or every "25%" weight near a
                # 24.6% MOS would be rewritten.
                slack = 10 ** -places + 1e-9 if places and loose else 0.5 * 10 ** -places + 1e-9
                if abs(old[k] - value) <= slack:
                    v = new[k]
                    prefix = ("−" if sign == "−" else "-") if v < 0 else ("+" if sign else "")
                    return f"{prefix}{abs(v):.{places}f}{m.group(3)}"
            return m.group(0)
        line = _PCT_TOKEN.sub(one, line)
        return _MONEY_TOKEN.sub(gap, line) if loose else line

    # The difference a derivation prints on the way ("= −$70.00 ÷ $233.78").
    gap_old, gap_new = stated - price, total - price

    def gap(m):
        places = len(m.group(2).partition(".")[2])
        if (gap_old * gap_new <= 0 or places == 0
                or abs(_num(m.group(2)) - abs(gap_old)) > 10 ** -places + 1e-9):
            return m.group(0)
        body = f"{abs(gap_new):,.{places}f}" if "," in m.group(2) else f"{abs(gap_new):.{places}f}"
        return m.group(1) + body

    # A figure's label can sit up to two lines above it (a derivation's
    # "= ... = −9.7%" line), and an upside column beside the fair value
    # ("| $471.23 | −8.8% |") carries no label at all.
    fair_value = _money_re(total)
    lines = text.split("\n")
    for i, line in enumerate(lines):
        context = "\n".join(lines[max(0, i - 2):i + 1])
        keys = (["mos"] if _MOS_LINE.search(context) else []) + \
               (["upside"] if _UPSIDE_LINE.search(context) or fair_value.search(line) else [])
        if keys:
            loose = bool(_MOS_LINE.search(line) or _UPSIDE_LINE.search(line) or fair_value.search(line))
            lines[i] = swap(line, keys, loose)
    return "\n".join(lines)


_AMOUNT = r"(?:NT)?(?:\\?\$\s?)?" + _NUM
_RUN_TOTAL = re.compile(r"[`*\s]*=\s*[`*\s]*(?:\\mathbf\{)?\s*(?:NT)?\\?\$?\s?" + _NUM)


def _half_ulp(digits: str) -> float:
    return 0.5 * 10 ** -len(digits.partition(".")[2])


def fix_products(text: str, result: dict) -> str:
    """Rewrite §8.8's product line (``= $a + $b + … = $S``) so each product is
    its term's ``value × weight``.

    After :func:`correct` rewrites the total, a product the model got wrong is
    left adding up to the old total: RKLB 2026-10-11 printed
    ``30.44 + 12.50 + 11.78 + 26.64 = $78.08`` (the products sum to $81.36).
    Only when the printed total already equals the sum of the terms (``ok``,
    or after :func:`correct`), so the rewritten products add up to it; and
    only a run of exactly ``len(terms)`` amounts joined by ``+``, each within
    25% of its own product, followed by its own ``= $S`` that the rewritten
    products, as printed, add up to. Each product keeps its printed precision.
    """
    terms, n = result["terms"], len(result["terms"])
    s88 = section(text, "8.8")
    if result["status"] not in ("ok", "corrected") or n < 2 or not s88:
        return text
    run = re.compile(r"(?<![\d.×*])" + r"\s*\+\s*".join([_AMOUNT] * n) + r"(?![\d.]|\s*(?:×|\\times|\*))")

    def one(m: "re.Match") -> str:
        # The same run in the same order: every amount near its own product.
        if any(abs(_num(m.group(i + 1)) - v * w) > 0.25 * abs(v * w)
               for i, (v, w) in enumerate(terms)):
            return m.group(0)
        # The line's own "= $S" must follow, and the rewritten products, as
        # printed, must add up to it; otherwise the line is left as written.
        after = _RUN_TOTAL.match(m.string, m.end())
        if not after:
            return m.group(0)
        out, last, printed, slack = [], m.start(), 0.0, _half_ulp(after.group(1))
        for i, (value, weight) in enumerate(terms):
            start, end = m.span(i + 1)
            digits = m.group(i + 1)
            places = len(digits.partition(".")[2])
            new = f"{value * weight:,.{places}f}" if "," in digits else f"{value * weight:.{places}f}"
            if abs(_num(digits) - value * weight) <= 0.5 * 10 ** -places + 1e-6:
                new = digits   # right to the precision printed
            printed += _num(new)
            slack += _half_ulp(digits)
            out.append(m.string[last:start] + new)
            last = end
        if abs(printed - _num(after.group(1))) > slack + 1e-6:
            return m.group(0)
        out.append(m.string[last:m.end()])
        return "".join(out)

    fixed = run.sub(one, s88)
    return text.replace(s88, fixed, 1) if fixed != s88 else text


def missing_chapters(text: str, chapters=FUNDAMENTAL_CHAPTERS) -> "list[int]":
    """Chapter numbers with no ``## N.`` heading."""
    present = {int(n) for n in re.findall(r"^##\s+(\d{1,2})\.", text, re.M)}
    return [n for n in chapters if n not in present]


def _money(v: float) -> str:
    return f"${v:,.2f}"


def annotate(text: str, result: dict) -> str:
    """Insert the recomputation into the report.

    Always appends a 「程式複算」 block to §8.8. On a ``corrected`` report (see
    :func:`correct`) it adds a one-line notice under the title saying what was
    changed, and warns when the change moves MOS into another rule-20 rating
    band. On a ``mismatch`` it could not correct (weights not 100%) it leaves
    the figures alone and the notice gives the recomputed value instead.
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
    if result["status"] == "corrected":
        lines.append(f"> ✏️ 模型原寫 {_money(result['stated'])}（與各項加總相差 {result['diff_pct']:+.2f}%），"
                     f"本報告的合計、MOS 與上行空間已改為上方複算值。")
    elif result["status"] == "mismatch":
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
        # A paragraph, not a quote: Python-Markdown merges two adjacent quotes
        # even across a blank line, and the title is followed by the 報告日期 one.
        notice = (f"\n**⚠️ 程式複算更正**：8.8 節加權合理價值應為 **{_money(result['total'])}**"
                  f"（報告寫 {_money(result['stated'])}）")
        if result["mos"] is not None:
            notice += (f"；以價格 {_money(result['price'])} 計，MOS 為 **{result['mos']:+.1f}%**、"
                       f"上行空間 **{result['upside']:+.1f}%**（若用報告所寫的 "
                       f"{_money(result['stated'])} 則 MOS 為 {result['stated_mos']:+.1f}%）")
        notice += "。報告其他段落引用的舊數值請以此為準。\n\n"
    elif result["status"] == "corrected":
        notice = (f"\n**✏️ 程式複算更正**：8.8 節加權合理價值由模型原寫的 {_money(result['stated'])} "
                  f"更正為 **{_money(result['total'])}**（各項加總），MOS "
                  f"{result['stated_mos']:+.1f}% → **{result['mos']:+.1f}%**，全文已同步。")
        before, after = rating_band(result["stated_mos"]), rating_band(result["mos"])
        if before != after:
            notice += (f" ⚠️ 更正後 MOS 落在規則 20 的「{after}」區間（原為「{before}」），"
                       f"本報告的評級是依原數值給出的。")
        notice += "\n\n"
    else:
        return text
    return re.sub(r"^(# [^\n]+\n)", lambda m: m.group(1) + notice, text, count=1, flags=re.M)


__all__ = ["TOLERANCE_PCT", "TOLERANCE_PP", "FUNDAMENTAL_CHAPTERS", "section",
           "weighted_terms", "report_price", "check", "valuation_mismatches",
           "missing_chapters", "annotate", "correct", "fix_products", "rating_band", "RATING_BANDS"]
