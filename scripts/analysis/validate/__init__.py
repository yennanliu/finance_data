"""Validation layer: post-hoc quality scanning of generated report files.

Detects empty/refusal/too-short/cut-off/placeholder/HTML-leak/duplicate reports.
This is distinct from the *generation-time* refusal detection in
:mod:`analysis.llm` — that decides whether to retry a live call; this inspects
already-written report files. The ``check_report_quality.py`` CLI builds its
console/CSV output on top of ``parse_file`` and ``collect_reports``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..utils.mermaid import mermaid_syntax_issues

# ── tuneable thresholds / patterns ───────────────────────────────────────────
MIN_LINES = 80          # below this (after frontmatter) → TOO_SHORT
REFUSAL_PATTERNS = [
    r"抱歉[，,]?\s*(我無法|我不能|無法完成|無法為|我沒有辦法)",
    r"I('m| am) sorry",
    r"I cannot (assist|complete|fulfill|help)",
    r"I can't (assist|complete|fulfill|help)",
    r"無法完成(這個|該|此)請求",
    r"無法(為您|協助您?)完成",
    r"由於.*缺乏.*具體.*資訊.*無法",
]
PLACEHOLDER_PATTERNS = [
    r"\{ticker\}",
    r"\{financial_context\}",
    r"\{today\}",
    r"\[INSERT",
    r"<YOUR_",
]
HTML_LEAK_PATTERNS = [
    r"window\.PlotlyConfig",
    r"<script[\s>]",
    r"<!DOCTYPE html",
    r"<html[\s>]",
]
CUTOFF_SIGNALS = [
    r"```\s*$",          # unclosed code block at end
    r"[，,、]\s*$",       # ends with a comma / enumeration separator
    r"\.\.\.\s*$",       # literal ellipsis at end
    r"[^\.\?！。）\)」』…]\s*$",  # ends without sentence-ending punctuation (broad)
]

FRONTMATTER_RE = re.compile(r"^---\n(.+?)\n---\n", re.DOTALL)
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
FILENAME_RE = re.compile(
    r"^(?P<atype>[a-z_]+)_(?P<date>\d{4}-\d{2}-\d{2})(?:-\d+)?(?:_(?P<provider>[a-z]+))?\.md$"
)


# ── data model ────────────────────────────────────────────────────────────────
@dataclass
class ReportIssue:
    path: str
    ticker: str
    analysis_type: str
    date: str
    provider: str
    issues: List[str] = field(default_factory=list)
    line_count: int = 0
    content_lines: int = 0
    note: str = ""

    def is_bad(self) -> bool:
        return len(self.issues) > 0


def parse_file(path: Path, min_lines: int = MIN_LINES) -> ReportIssue:
    """Scan a single report file and return a populated ``ReportIssue``."""
    rel = str(path)
    # derive ticker from parent dir name
    ticker = path.parent.name

    m = FILENAME_RE.match(path.name)
    if m:
        atype = m.group("atype")
        date = m.group("date")
        provider = m.group("provider") or "claude"
        is_dup = bool(re.search(r"-\d+\.md$", path.name))
    else:
        atype, date, provider, is_dup = "unknown", "", "unknown", False

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return ReportIssue(rel, ticker, atype, date, provider,
                           issues=["READ_ERROR"], note=str(e))

    total_lines = text.count("\n")
    # strip frontmatter for content analysis
    fm_match = FRONTMATTER_RE.match(text)
    content = text[fm_match.end():] if fm_match else text
    content_lines = content.count("\n")

    issues: List[str] = []
    notes: List[str] = []

    # DUPLICATE
    if is_dup:
        issues.append("DUPLICATE")

    # EMPTY
    if not content.strip():
        issues.append("EMPTY")
        return ReportIssue(rel, ticker, atype, date, provider, issues,
                           total_lines, content_lines)

    # NO_FRONTMATTER
    if not fm_match:
        issues.append("NO_FRONTMATTER")

    # REFUSAL
    for pat in REFUSAL_PATTERNS:
        if re.search(pat, text):
            issues.append("REFUSAL")
            break

    # TOO_SHORT  (only if not already a refusal, which is short by definition)
    if "REFUSAL" not in issues and content_lines < min_lines:
        issues.append("TOO_SHORT")
        notes.append(f"content_lines={content_lines}")

    # PLACEHOLDER
    for pat in PLACEHOLDER_PATTERNS:
        if re.search(pat, text):
            issues.append("PLACEHOLDER")
            break

    # HTML_LEAK — only flag when the file IS mostly raw HTML (not intentional embedded charts).
    # Technical analysis files legitimately embed Plotly HTML; flag only when:
    #   - file contains HTML boilerplate AND has very few Markdown headings (< 2)
    html_boilerplate = any(re.search(p, text) for p in HTML_LEAK_PATTERNS)
    if html_boilerplate:
        md_headings = len(re.findall(r"^#{1,3} ", text, re.MULTILINE))
        if md_headings < 2:
            issues.append("HTML_LEAK")

    # MERMAID — flowchart blocks with unrenderable syntax (unquoted parens in a
    # node label, stray parenthetical after a closer). Reports are sanitized at
    # generation time, so any hit here is a regression worth surfacing.
    mermaid_bad = mermaid_syntax_issues(text)
    if mermaid_bad:
        issues.append("MERMAID")
        notes.append(f"mermaid={len(mermaid_bad)}× e.g. {mermaid_bad[0][:60]!r}")

    # CUTOFF — check last non-empty line
    lines = [l for l in text.splitlines() if l.strip()]
    if lines:
        last = lines[-1].rstrip()
        # skip lines that are obviously table rows or code fences
        if not re.match(r"^(\||-{3,}|={3,}|```)", last):
            # check for cutoff signals
            for pat in CUTOFF_SIGNALS[:-1]:   # explicit patterns
                if re.search(pat, last):
                    issues.append("CUTOFF")
                    notes.append(f"last_line={last[:80]!r}")
                    break
            # broad "no sentence ending" check — only for short files
            if "CUTOFF" not in issues and content_lines < min_lines:
                if re.search(CUTOFF_SIGNALS[-1], last):
                    # avoid flagging lines ending with CJK closing punctuation
                    if not re.search(r"[。！？…」』）\)]$", last):
                        issues.append("CUTOFF")
                        notes.append(f"last_line={last[:80]!r}")

    return ReportIssue(
        path=rel,
        ticker=ticker,
        analysis_type=atype,
        date=date,
        provider=provider,
        issues=issues,
        line_count=total_lines,
        content_lines=content_lines,
        note="; ".join(notes),
    )


def collect_reports(root: Path, since: Optional[str], until: Optional[str],
                    ticker_filter: Optional[str]) -> List[Path]:
    """Gather ``*.md`` report paths under ``root`` filtered by month/ticker."""
    paths = []
    for p in root.rglob("*.md"):
        if ticker_filter and p.parent.name.lower() != ticker_filter.lower():
            continue
        m = DATE_RE.search(p.name)
        if m:
            d = m.group(1)[:7]  # YYYY-MM
            if since and d < since:
                continue
            if until and d > until:
                continue
        paths.append(p)
    return sorted(paths)


__all__ = [
    "MIN_LINES", "REFUSAL_PATTERNS", "PLACEHOLDER_PATTERNS", "HTML_LEAK_PATTERNS",
    "CUTOFF_SIGNALS", "FRONTMATTER_RE", "DATE_RE", "FILENAME_RE",
    "ReportIssue", "parse_file", "collect_reports",
]
