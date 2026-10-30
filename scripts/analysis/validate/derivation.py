"""Re-check the worked equations a report prints as ``$$ … $$`` or ``$ … $`` math.

The model shows its work as chains like ``$a × w + $b × w = $x + $y = $S``,
and breaks them in the middle. RKLB 2026-10-28 §8.8 printed
``$28.825 + $16.250 + $3.520 + $5.200 + $5.108 = $59.323 ≈ $58.90`` (the terms
sum to $58.90) and ``\\frac{$58.90 − $58.60}{$58.90} = \\frac{+$0.72}{$58.90}``
(the difference is $0.30). Both ends of each chain were right; the middle was
invented. :func:`check` evaluates every link of every chain in Python and
reports the ones that do not hold. :func:`fix` repairs only the case above:
a single number in the middle of a chain whose two neighbours agree with each
other, so the correction is never a guess about which side is wrong.

Pure standard library: the stage-1 audit imports it.
"""

from __future__ import annotations

import ast
import operator
import re

# A link holds when the two sides agree within the rounding their printed
# figures allow (half a unit in each number's last place, propagated through
# the left side), plus this relative slack for rounded intermediates.
TOLERANCE_REL = 0.001

# Inline `$ … $` maths, told apart from prose prices ("$58.60 … $70"): no
# space inside either delimiter, no unescaped `$` or newline inside, at least
# one TeX command, and the closing `$` not followed by a digit. RKLB 2026-10-28
# writes its whole nine-step DCF derivation this way, as do 325 reports.
INLINE_MATH = (r"(?<![\\$])\$(?=[^\s$])(?P<inline>(?:\\.|[^$\\\n])*?\\[a-zA-Z](?:\\.|[^$\\\n])*?)"
               r"(?<=\S)\$(?![\d$])")
# Code, left alone: a fence (closed only by the same run), or a code span of
# any backtick-run length (CommonMark: "`` $$x$$ ``" is code too).
CODE = (r"(?P<code>(?m:^[ \t]*(?P<fence>`{3,}|~{3,})).*?(?m:^[ \t]*(?P=fence))"
        r"|(?<!`)(?P<tick>`+)(?!`)[^\n]*?(?<!`)(?P=tick)(?!`))")
# Code | `$$ … $$` | `$ … $`.
_MATH = re.compile(CODE + r"|\$\$(?P<display>.+?)\$\$|" + INLINE_MATH, re.S)
# Links compared for equality, and words that end a chain (an arrow or an
# inequality says "leads to", not "equals").
_LINK = re.compile(r"\\approx|≈|(?<![<>≤≥!\\])=")
_BREAK = re.compile(r"\\(?:implies|Rightarrow|rightarrow|longrightarrow|xrightarrow\{[^{}]*\}|to|"
                    r"le|ge|leq|geq|neq|sim|quad|qquad|text\{[^{}]*[，。；：,;:][^{}]*\})"
                    r"(?![a-zA-Z])|[→⇒≤≥<>≠]|\\\\")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
# Unit words glued to a figure. Mixed units in one chain are not compared.
# Only a `}` that closes `\text{` is consumed: "\mathbf{\$16.9M}" keeps its own.
_UNIT_WORD = r"(B|M|K|T|bn|億|兆|萬|x|倍)"
_UNIT = re.compile(r"(?<=\d)\s*(?:\\text\{\s*" + _UNIT_WORD + r"\s*\}|" + _UNIT_WORD + r"(?![A-Za-z]))")

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow,
        ast.USub: operator.neg, ast.UAdd: operator.pos}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("exponent")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("not arithmetic")


def _strip_wrappers(s: str) -> str:
    # \mathbf{x} → x, repeated for nesting; \text{label} → nothing.
    for _ in range(4):
        s = re.sub(r"\\(?:mathbf|boldsymbol|mathrm|bm|textbf|mathit)\{([^{}]*)\}", r"\1", s)
    return re.sub(r"\\text\{[^{}]*\}", " ", s)


def to_python(segment: str) -> "str | None":
    """``segment`` as a Python arithmetic expression, or None when it is not
    pure arithmetic (a label, a symbol, a unit we cannot normalise)."""
    s = _UNIT.sub("", segment)
    # "52\\text{週高點}": the figure is part of a label, not a quantity.
    if re.search(r"\d\s*\\text\{", s):
        return None
    # "\\text{EV} + …": a label not followed by a figure names a variable.
    if re.search(r"\\text\{[^{}]*\}(?!\s*(?:\\[,;! ]|\\quad)?\s*(?:\\\$|\$|NT|[-+−(]?\s*\d))", s):
        return None
    s = _strip_wrappers(s)
    s = s.replace("NT\\$", "").replace("NT$", "").replace("\\$", "").replace("$", "")
    s = re.sub(r"\\(?:left|right|,|;|!|\s)", " ", s)
    s = s.replace("\\times", "*").replace("\\cdot", "*").replace("×", "*")
    s = s.replace("\\div", "/").replace("÷", "/")
    s = s.replace("−", "-").replace("–", "-").replace("\\%", "%").replace("**", " ")
    s = re.sub(r"\^\{([^{}]*)\}", r"**(\1)", s)
    s = re.sub(r"\^(\d)", r"**\1", s)
    for _ in range(4):
        s = re.sub(r"\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}", r"((\1)/(\2))", s)
    s = s.replace("{", "(").replace("}", ")").replace("[", "(").replace("]", ")")
    s = _NUMBER.sub(lambda m: m.group(0).replace(",", ""), s)
    s = re.sub(r"(?<![\d.])(\d+(?:\.\d+)?)\s*%", r"(\1/100)", s)
    s = s.strip()
    if not re.search(r"\d", s) or not re.fullmatch(r"[\d\s.+\-*/()]+", s):
        return None
    return s


def evaluate(segment: str) -> "float | None":
    expr = to_python(segment)
    if expr is None:
        return None
    try:
        return _eval(ast.parse(expr, mode="eval"))
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError, TypeError, RecursionError):
        return None


def _rounding(segment: str) -> float:
    """How far ``segment``'s value can move when each printed number moves by
    half a unit in its last place."""
    base = evaluate(segment)
    if base is None:
        return 0.0
    total = 0.0
    for mt in _NUMBER.finditer(segment):
        digits = mt.group(0).replace(",", "")
        places = len(digits.partition(".")[2])
        bumped = f"{float(digits) + 0.5 * 10 ** -places:.{places + 1}f}"
        moved = evaluate(segment[:mt.start()] + bumped + segment[mt.end():])
        if moved is not None:
            total += abs(moved - base)
    return total


def agree(left: float, right: float, left_segment: str, right_segment: str) -> bool:
    slack = _rounding(left_segment) + _rounding(right_segment) + TOLERANCE_REL * abs(right) + 1e-9
    if abs(left - right) <= slack:
        return True
    # A deduction step printed as negative: "Capex = $1,228.2M × 12% = −$147.4M".
    if right < 0 < left and abs(left + right) <= slack and re.match(
            r"\s*(?:\\mathbf\{|\*\*)?\s*[-−]", right_segment):
        return True
    # A whole count floored from a ratio: "$1,500 ÷ $32.00 = 46 股". Only a
    # division on the left and a bare count on the right, or "$2.8 = $2" passes.
    nums = _NUMBER.findall(right_segment)
    return (len(nums) == 1 and "." not in nums[0] and not re.search(r"[%$]", right_segment)
            and bool(re.search(r"÷|\\div|\\frac|/", left_segment)) and 0 <= left - right < 1)


def _units(segment: str) -> "set[str]":
    return {a or b for a, b in _UNIT.findall(segment)}


def chains(span: str) -> "list[list[str]]":
    """The equality chains of one math span: its text split at each ``=`` /
    ``≈``, cut wherever an arrow, inequality or line break intervenes."""
    out = []
    for part in _BREAK.split(span):
        segments = _LINK.split(part)
        if len(segments) >= 2:
            out.append(segments)
    return out


def math_spans(text: str) -> "list[str]":
    """Every ``$$ … $$`` and inline ``$ … $`` span outside code."""
    return [body for _, body, _ in _spans(text)]


_OPERATOR_END = re.compile(r"(?:[+\-−×÷*/]|\\(?:div|times|cdot))\s*$")


def _spans(text: str) -> "list[tuple[re.Match, str, bool]]":
    """``(match, body, continued)`` for every math span. ``continued`` when
    the span picks up an expression begun before it on the same line, so its
    first figure is not the whole left side: QQQ 2026-10-21 wrote
    "$\\$0.535 \\div$ 平均計息負債 $\\$12.50 = 4.28\\%$", META 2026-10-15
    "$22.50 / $737.54 = \\mathbf{3.05\\%}$"."""
    out, prev_end, prev_body = [], None, ""
    for m in _MATH.finditer(text):
        if m.group("code"):
            prev_end = None
            continue
        body = m.group("display") if m.group("display") is not None else m.group("inline")
        before = text[text.rfind("\n", 0, m.start()) + 1:m.start()]
        same_line = prev_end is not None and "\n" not in text[prev_end:m.start()]
        continued = bool(_OPERATOR_END.search(before)) or (same_line and bool(_OPERATOR_END.search(prev_body)))
        out.append((m, body, continued))
        prev_end, prev_body = m.end(), body
    return out


def _bad_links(segments: "list[str]") -> "list[int]":
    """Indices ``i`` where ``segments[i] = segments[i+1]`` does not hold."""
    values = [evaluate(s) for s in segments]
    bad = []
    for i in range(len(segments) - 1):
        a, b = values[i], values[i + 1]
        if a is None or b is None or _units(segments[i]) != _units(segments[i + 1]):
            continue
        if not agree(a, b, segments[i], segments[i + 1]):
            bad.append(i)
    return bad


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", _strip_wrappers(s).replace("\\$", "$")).strip()


def check(text: str) -> "list[dict]":
    """Every link of every displayed chain that does not hold:
    ``{"left", "right", "computed", "stated"}``."""
    out = []
    for _, span, continued in _spans(text):
        for n, part in enumerate(_BREAK.split(span)):
            segments = _LINK.split(part)
            for i in _bad_links(segments):
                # A continued span's first figure is not the whole left side.
                if continued and n == 0 and i == 0:
                    continue
                out.append({"left": _clean(segments[i]), "right": _clean(segments[i + 1]),
                            "computed": evaluate(segments[i]), "stated": evaluate(segments[i + 1])})
    return out


def _format_like(original: str, value: float) -> str:
    places = len(original.partition(".")[2])
    body = f"{abs(value):,.{places}f}" if "," in original else f"{abs(value):.{places}f}"
    return body


def _repair(segments: "list[str]", continued: bool = False) -> "tuple[list[str], int]":
    """Fix each middle segment that disagrees with both neighbours while they
    agree with each other, by re-solving the one number it introduces. In a
    ``continued`` chain the first segment is not a whole left side, so it
    never serves as the reference."""
    fixed = 0
    segments = list(segments)
    for i in range(2 if continued else 1, len(segments) - 1):
        prev, mid, nxt = segments[i - 1], segments[i], segments[i + 1]
        a, m, b = evaluate(prev), evaluate(mid), evaluate(nxt)
        if a is None or m is None or b is None:
            continue
        if len({frozenset(_units(s)) for s in (prev, mid, nxt)}) != 1:
            continue
        if not agree(a, b, prev, nxt) or agree(a, m, prev, mid):
            continue
        # The number this step introduces: the one the previous step lacks.
        seen = {float(n.replace(",", "")) for n in _NUMBER.findall(prev)}
        new = [mt for mt in _NUMBER.finditer(mid) if float(mt.group(0).replace(",", "")) not in seen]
        if len(new) != 1:
            continue
        mt = new[0]
        f0 = evaluate(mid[:mt.start()] + "0" + mid[mt.end():])
        f1 = evaluate(mid[:mt.start()] + "1" + mid[mt.end():])
        if f0 is None or f1 is None or f1 == f0:
            continue
        x = (a - f0) / (f1 - f0)
        if x < 0:
            continue
        candidate = mid[:mt.start()] + _format_like(mt.group(0), x) + mid[mt.end():]
        value = evaluate(candidate)
        if value is None or not agree(a, value, prev, candidate):
            continue
        segments[i] = candidate
        fixed += 1
    return segments, fixed


def fix(text: str) -> "tuple[str, int]":
    """``text`` with every repairable chain repaired, and how many numbers
    were changed. Idempotent: a repaired chain holds."""
    total, out, last = 0, [], 0
    for m, span, continued in _spans(text):
        delim = "$$" if m.group("display") is not None else "$"
        pieces = _BREAK.split(span)
        seps = _BREAK.findall(span)
        rebuilt = []
        for n, part in enumerate(pieces):
            links = _LINK.findall(part)
            segments = _LINK.split(part)
            if len(segments) >= 3:
                segments, k = _repair(segments, continued and n == 0)
                total += k
            rebuilt.append(segments[0] + "".join(l + s for l, s in zip(links, segments[1:])))
        body = rebuilt[0] + "".join(s + p for s, p in zip(seps, rebuilt[1:]))
        out.append(text[last:m.start()] + delim + body + delim)
        last = m.end()
    out.append(text[last:])
    return "".join(out), total


__all__ = ["TOLERANCE_REL", "INLINE_MATH", "CODE", "check", "fix", "evaluate", "to_python", "chains", "math_spans", "agree"]
