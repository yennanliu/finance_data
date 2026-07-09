"""Mermaid syntax repair for LLM-generated Markdown.

LLM-generated flowcharts routinely emit labels that Mermaid cannot parse
("Syntax error in text", ``got 'PS'``): unquoted parens/slashes/colons in node
& subgraph labels, lone ``%`` comments, trailing emoji after a node, spaces
between an id and its bracket, and bare node references with spaces. The most
common offender by far is an unquoted paren inside a node label, e.g.
``A[ADX(14) = 17.44]`` — Mermaid needs ``A["ADX(14) = 17.44"]``.

The repairs here are deterministic and idempotent (already-quoted labels are
left untouched), so they can run at report-generation time — keeping the source
``ai_gen_report/*.md`` that GitHub renders directly valid — and again at
docs-build time without conflict. Keeping the logic in one module means the
generator and the docs builder share exactly one implementation.
"""

from __future__ import annotations

import re

# Fence matcher shared by the generator (sanitize) and the docs builder
# (sanitize + optional SVG pre-render).
_MERMAID_FENCE_RE = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)

_MM_MULTI = ["((", "([", "[(", "[[", "{{"]
_MM_MULTI_CLOSE = {"((": "))", "([": "])", "[(": ")]", "[[": "]]", "{{": "}}"}
_MM_SINGLE_CLOSE = {"[": "]", "(": ")", "{": "}"}
_MM_KEYWORDS = ("subgraph", "end", "class", "classDef", "style", "click",
                "linkStyle", "direction", "graph", "flowchart")
_MM_BARE = re.compile(r"[^\w.\-]")
_MM_TRAILING_EMOJI = re.compile(
    r"([\]\)}])[ \t]+([\U0001F300-\U0001FAFF☀-➿️←-⇿]+)[ \t]*$", re.MULTILINE)
_MM_EDGE = re.compile(r"\s*(-->|---|-\.->|-\.-|===|==>|--[ox]|<-->)\s*")
# A parenthetical aside the model sometimes appends *after* a node's closing
# bracket, e.g. `E2["…$157.33"] (此處應為 MA20)`. Mermaid reads the stray `(`
# as an unexpected 'PS' token and the whole diagram fails to render. Nothing
# valid ever follows a node closer with a `(`, so dropping the aside is safe.
_MM_TRAILING_PAREN = re.compile(r"([\]\)}])\s*[（(][^）)]*[）)]\s*$", re.MULTILINE)


def _mm_is_id_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_" or ord(ch) > 0x2E7F  # incl. CJK


def _mm_quote(inner: str) -> str:
    s = inner.strip()
    if not s or '"' in inner:
        return inner
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return inner
    return f'"{inner}"'


def _mm_scan_quote(s: str) -> str:
    """Wrap every flowchart node label in quotes. The shape is decided at its
    opening delimiter, so a closer char inside a label (e.g. the `)` in
    `C1[MA20 (下方)]`) is never mistaken for the shape's real close."""
    out, i, n = [], 0, len(s)
    while i < n:
        op = close = None
        if i > 0 and _mm_is_id_char(s[i - 1]):
            if s[i:i + 2] in _MM_MULTI:
                op, close = s[i:i + 2], _MM_MULTI_CLOSE[s[i:i + 2]]
            elif s[i] in _MM_SINGLE_CLOSE:
                op, close = s[i], _MM_SINGLE_CLOSE[s[i]]
        if op:
            j = s.find(close, i + len(op))
            inner = s[i + len(op):j] if j != -1 else None
            if j != -1 and "\n" not in inner:
                out.append(op + _mm_quote(inner) + close)
                i = j + len(close)
                continue
        out.append(s[i])
        i += 1
    return "".join(out)


def _mm_fix_subgraph_title(m: "re.Match") -> str:
    indent, rest = m.group(1), m.group(2).rstrip()
    if not rest or rest.startswith('"'):
        return m.group(0)
    mb = re.match(r"(\S+)\s*\[(.+)\]$", rest)
    if mb:
        return f"{indent}subgraph {mb.group(1)} [{_mm_quote(mb.group(2))}]"
    if "[" in rest:
        return m.group(0)
    if ('"' not in rest) and re.search(r"[()]", rest):
        return f'{indent}subgraph "{rest}"'
    return m.group(0)


def _mm_collapse_id_bracket(diagram: str) -> str:
    out = []
    for line in diagram.split("\n"):
        if line.lstrip().split(" ", 1)[0] in _MM_KEYWORDS:
            out.append(line)
            continue
        line = re.sub(r"(?m)^(\s*)([\w.\-]+)[ \t]+([\[({])", r"\1\2\3", line)
        # Also collapse `id [label]` gaps right after an edge arrow, a pipe
        # edge-label close, or an `&` node-join (e.g. `A -->|x| B [y]`).
        line = re.sub(r"(-->|---|-\.->|==>|===|\||&)([ \t]*)([\w.\-]+)[ \t]+([\[({])",
                      r"\1 \3\4", line)
        out.append(line)
    return "\n".join(out)


def _mm_wrap_bare_nodes(diagram: str) -> str:
    """Wrap edge endpoints that are not valid node ids (e.g. `股價突破 $20`) as
    `nbN["…"]`, mapping identical text to one id so references stay connected."""
    ids: "dict[str, str]" = {}

    def node_id(text: str) -> str:
        text = text.strip()
        if text not in ids:
            ids[text] = f"nb{len(ids) + 1}"
        return ids[text]

    def fix_atom(atom: str) -> str:
        s = atom.strip()
        if not s or not _MM_BARE.search(s):
            return atom
        return f'{node_id(s)}["{s}"]'

    out = []
    for line in diagram.split("\n"):
        stripped = line.lstrip()
        if (not _MM_EDGE.search(line) or any(c in line for c in "[]{}()|")
                or stripped.split(" ", 1)[0] in _MM_KEYWORDS):
            out.append(line)
            continue
        indent = line[:len(line) - len(stripped)]
        tokens = _MM_EDGE.split(line)
        rebuilt = []
        for k, tok in enumerate(tokens):
            if k % 2 == 1:
                rebuilt.append(f" {tok} ")
            else:
                rebuilt.append(" & ".join(fix_atom(a) for a in tok.split("&")))
        out.append(indent + "".join(rebuilt).strip())
    return "\n".join(out)


def sanitize_mermaid(diagram: str) -> str:
    """Repair common mermaid syntax errors in a single diagram. No-op for
    non-flowchart types (pie/gantt/mindmap/quadrantChart)."""
    first = diagram.lstrip().split("\n", 1)[0].strip().lower()
    if not (first.startswith("graph") or first.startswith("flowchart")):
        return diagram
    diagram = re.sub(r"(?m)^(\s*)%(?!%)", r"\1%%", diagram)
    # Mermaid keywords are lowercase; the LLM sometimes emits SUBGRAPH / END.
    diagram = re.sub(r"(?mi)^(\s*)subgraph\b", r"\1subgraph", diagram)
    diagram = re.sub(r"(?mi)^(\s*)end(\s*)$", r"\1end\2", diagram)
    diagram = re.sub(r"(?m)^(\s*)subgraph\s+(.+)$", _mm_fix_subgraph_title, diagram)
    diagram = _MM_TRAILING_EMOJI.sub(r"\1", diagram)
    # Drop stray parenthetical asides appended after a node closer.
    diagram = _MM_TRAILING_PAREN.sub(r"\1", diagram)
    # Pipe edge labels `-->|text|` break on parens/`$`/`->`; quote their text.
    diagram = re.sub(r"\|([^|\n]+)\|",
                     lambda m: "|" + _mm_quote(m.group(1)) + "|", diagram)
    diagram = _mm_collapse_id_bracket(diagram)
    diagram = _mm_wrap_bare_nodes(diagram)
    diagram = _mm_scan_quote(diagram)
    return diagram


def sanitize_mermaid_blocks(content: str) -> str:
    """Apply sanitize_mermaid to every ```mermaid fence in a Markdown string.
    Runs on every build, independent of mmdc, so blocks are valid whether they
    are pre-rendered to SVG or rendered client-side."""
    def _repl(m: "re.Match") -> str:
        return "```mermaid\n" + sanitize_mermaid(m.group(1)) + "```"
    return _MERMAID_FENCE_RE.sub(_repl, content)


# Characters that make a flowchart node label unrenderable when left unquoted —
# Mermaid reads the paren as a shape token ('PS'/'PE') and the diagram fails.
_MM_RISK_CHARS = "()（）"


def _diagram_syntax_issues(diagram: str) -> "list[str]":
    """Return offending snippets in one flowchart diagram that Mermaid cannot
    parse: unquoted parens in a node label, or a stray parenthetical appended
    after a node closer. Empty for a clean (sanitized) diagram or a
    non-flowchart type. This is the detection mirror of :func:`sanitize_mermaid`
    — anything it reports, ``sanitize_mermaid`` repairs — so it doubles as a
    regression gate on generated reports."""
    first = diagram.lstrip().split("\n", 1)[0].strip().lower()
    if not (first.startswith("graph") or first.startswith("flowchart")):
        return []
    issues: "list[str]" = []
    for m in _MM_TRAILING_PAREN.finditer(diagram):
        issues.append(m.group(0).strip())
    s, i, n = diagram, 0, len(diagram)
    while i < n:
        op = close = None
        if i > 0 and _mm_is_id_char(s[i - 1]):
            if s[i:i + 2] in _MM_MULTI:
                op, close = s[i:i + 2], _MM_MULTI_CLOSE[s[i:i + 2]]
            elif s[i] in _MM_SINGLE_CLOSE:
                op, close = s[i], _MM_SINGLE_CLOSE[s[i]]
        if op:
            j = s.find(close, i + len(op))
            inner = s[i + len(op):j] if j != -1 else None
            if j != -1 and "\n" not in inner:
                # Mirror _mm_quote: any label already carrying a `"` is left to
                # the author (the quotes are assumed to protect its contents),
                # so the detector must not flag it either — otherwise a valid
                # quoted round node like `A("RSI(14): 49")` reads as broken.
                if '"' not in inner and any(c in inner for c in _MM_RISK_CHARS):
                    issues.append(op + inner + close)
                i = j + len(close)
                continue
        i += 1
    return issues


def mermaid_syntax_issues(content: str) -> "list[str]":
    """Return every unrenderable-Mermaid snippet across all ```mermaid fences in
    a Markdown string (empty if all blocks are valid). Used by the report
    quality checker to flag reports whose diagrams would fail on GitHub."""
    return [snip for _, snip in mermaid_issue_locations(content)]


def mermaid_issue_locations(content: str) -> "list[tuple[int, str]]":
    """Like :func:`mermaid_syntax_issues`, but each snippet is paired with its
    1-based line number in ``content`` — so a reporter can point at the exact
    line (e.g. a GitHub Actions ``file=…,line=…`` annotation)."""
    locs: "list[tuple[int, str]]" = []
    for m in _MERMAID_FENCE_RE.finditer(content):
        block = m.group(1)
        base_line = content.count("\n", 0, m.start(1)) + 1  # 1st line of block body
        for snip in _diagram_syntax_issues(block):
            idx = block.find(snip)
            line_in_block = block.count("\n", 0, idx) if idx != -1 else 0
            locs.append((base_line + line_in_block, snip))
    return locs


__all__ = [
    "sanitize_mermaid", "sanitize_mermaid_blocks",
    "mermaid_syntax_issues", "mermaid_issue_locations",
    "_MERMAID_FENCE_RE",
]
