"""Tests for the shared Mermaid sanitizer (analysis.utils.mermaid).

Covers the exact node-label patterns that broke GitHub rendering on generated
technical-analysis reports: unquoted parentheses/colons in `[...]`, `{...}`,
`((...))` node shapes. The sanitizer must be deterministic and idempotent so it
can run both at report-generation time and again at docs-build time.
"""

from __future__ import annotations

from analysis.utils.mermaid import (
    mermaid_issue_locations,
    mermaid_syntax_issues,
    sanitize_mermaid,
    sanitize_mermaid_blocks,
)

# The four diagrams reported as "Parse error … got 'PS'" on GitHub, one per
# offending shape, plus the emoji/colon variants seen in real reports.
REPORTED = [
    ("A[ADX(14) = 17.44]", 'A["ADX(14) = 17.44"]'),
    ("H[RSI(14): 49.07 🟡]", 'H["RSI(14): 49.07 🟡"]'),
    ("B{ADX(14) < 25?}", 'B{"ADX(14) < 25?"}'),
    ("C[樂觀情境 (機率: 40%)]", 'C["樂觀情境 (機率: 40%)"]'),
    ("V((RSI(14) 中性))", 'V(("RSI(14) 中性"))'),
]


def test_quotes_every_reported_shape():
    for raw, expected in REPORTED:
        out = sanitize_mermaid(f"graph TD\n    {raw}")
        assert expected in out, f"{raw!r} -> {out!r}"


def test_already_quoted_labels_untouched():
    src = 'graph TD\n    A["ADX(14) = 17.44"] --> B{"MACD: -4.386"}'
    assert sanitize_mermaid(src) == src


def test_idempotent():
    src = "graph TD\n    A[ADX(14) = 17.44] --> B{未來 (估)}"
    once = sanitize_mermaid(src)
    assert sanitize_mermaid(once) == once


def test_blocks_only_touch_mermaid_fences():
    content = (
        "intro (with parens)\n"
        "```mermaid\n"
        "graph TD\n"
        "    A[ADX(14) = 17.44]\n"
        "```\n"
        "```python\n"
        "x = foo(1)  # not mermaid\n"
        "```\n"
    )
    out = sanitize_mermaid_blocks(content)
    assert 'A["ADX(14) = 17.44"]' in out
    assert "intro (with parens)" in out
    assert "x = foo(1)  # not mermaid" in out


def test_strips_stray_parenthetical_after_node_closer():
    # An editorial aside appended after the node's `]` makes Mermaid choke on
    # the stray `(` ('PS' token). It must be dropped, label kept intact.
    src = ('graph TD\n'
           '    E1 --> E2["下探 S3 $126.30 及 MA200 $157.33"] '
           '(此處 MA200 應該是 MA20 $125.24 或更低支撐)')
    out = sanitize_mermaid(src)
    assert out.rstrip().endswith('E2["下探 S3 $126.30 及 MA200 $157.33"]')
    assert "此處" not in out


def test_quoted_label_with_inner_parens_survives_trailing_strip():
    # The scenario diagram case: parens inside a quoted label must NOT be
    # mistaken for a stray trailing aside.
    src = 'graph TD\n    B --> C["樂觀情境 (機率: 40%)"]'
    assert sanitize_mermaid(src) == src


def test_non_flowchart_is_noop():
    src = "pie title Pets\n    \"Dogs\" : 386"
    assert sanitize_mermaid(src) == src


# ── mermaid_syntax_issues (the QA / CI detector) ─────────────────────────────

def test_detector_flags_unquoted_parens_in_node_label():
    content = "x\n```mermaid\ngraph TD\n    A[ADX(14) = 17.44] --> B{未來 (估)}\n```\n"
    issues = mermaid_syntax_issues(content)
    assert any("ADX(14)" in s for s in issues)
    assert any("未來 (估)" in s for s in issues)


def test_detector_flags_stray_trailing_parenthetical():
    content = ('```mermaid\ngraph TD\n'
               '    E1 --> E2["label"] (此處應為 MA20)\n```\n')
    assert mermaid_syntax_issues(content)


def test_detector_clean_after_sanitize():
    # The detector is the mirror of the sanitizer: whatever it reports, the
    # sanitizer repairs, so sanitized content must report nothing.
    broken = ("```mermaid\ngraph TD\n    A[ADX(14) = 17.44] --> B{ADX(14) < 25?}\n"
              '    B --> C[樂觀情境 (機率: 40%)] (aside)\n```\n')
    assert mermaid_syntax_issues(broken)
    assert mermaid_syntax_issues(sanitize_mermaid_blocks(broken)) == []


def test_detector_ignores_quoted_round_node_with_inner_parens():
    # `A("RSI(14): 49")` is valid — quotes protect the parens. The naive
    # first-`)` scan must not misread it as broken.
    content = '```mermaid\ngraph TD\n    A(("RSI(14): 49.07 中性"))\n```\n'
    assert mermaid_syntax_issues(content) == []


def test_detector_ignores_non_mermaid_and_non_flowchart():
    assert mermaid_syntax_issues("prose (with parens) only") == []
    assert mermaid_syntax_issues("```python\nx = foo(1)\n```") == []
    assert mermaid_syntax_issues("```mermaid\npie\n    \"A (x)\" : 5\n```") == []


def test_detector_reports_correct_line_numbers():
    content = (
        "line1\n"                       # 1
        "line2\n"                       # 2
        "```mermaid\n"                  # 3
        "graph TD\n"                    # 4  (block body starts here)
        "    A[ok] --> B[ADX(14)]\n"    # 5  <- offending
        "```\n"                         # 6
    )
    locs = mermaid_issue_locations(content)
    assert locs == [(5, "[ADX(14)]")]
