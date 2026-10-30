"""Validation layer: post-hoc quality scanning of generated report files.

Two families of checks, both listed in :data:`ISSUE_TYPES`:

* **mechanical** — empty / refusal / too-short / cut-off / placeholder /
  HTML-leak / duplicate / unrenderable Mermaid, for any report;
* **structure and accuracy** (:func:`content_findings`) — a fundamental
  report's eleven chapters; then the report against its own
  figures (§8.8 sum, MOS, DCF premium, R/R, each step of a ``$$`` / ``$``
  equation chain), against the close and levels the
  pipeline recorded in its front matter, and that close against the committed
  price store (``market_data``). Background: ``docs/FUNDAMENTAL_REPORT_REVIEW.md``
  and ``docs/TECHNICAL_REPORT_REVIEW.md``.

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
from . import arithmetic, derivation, market_data, technical

# Every issue code the scan can emit, in the order the CLI documents them.
ISSUE_TYPES = {
    # mechanical — any report type
    "READ_ERROR": "the file could not be read",
    "DUPLICATE": "same ticker+type+date with a -2 / -3 suffix",
    "EMPTY": "the file is empty or whitespace only",
    "NO_FRONTMATTER": "no YAML front matter block",
    "REFUSAL": "the model refused instead of writing the report",
    "TOO_SHORT": "fewer content lines than a real report has",
    "PLACEHOLDER": "unfilled template placeholder ({ticker}, [INSERT …, $XXX)",
    "HTML_LEAK": "raw HTML / Plotly boilerplate instead of Markdown",
    "MERMAID": "a ```mermaid flowchart that will not render",
    "CUTOFF": "ends mid-sentence or mid-code-block (truncated)",
    # structure — fundamental
    "MISSING_SECTIONS": "fundamental report lacks one of chapters ## 1. … ## 11.",
    # accuracy — the report against its own figures
    "ARITHMETIC": "a derived valuation (§8.8 total, MOS, DCF premium) does not "
                  "recompute from the report's own figures",
    "DERIVATION": "a step of a $$ … $$ or $ … $ equation chain does not "
                  "recompute (a = b that is false)",
    "RR_MISMATCH": "a stated R/R matches neither target from its own entry/stop",
    "NAN_VALUE": "a $nan / nan% leaked from an empty data bar",
    # accuracy — the report against the market record
    "PRICE_MISMATCH": "the price the report quotes is not the close it was given",
    "LEVEL_MISMATCH": "a Ch.4 R1–S3 is not the computed level of the same label",
    "STORE_MISMATCH": "the close the report was given is not the committed "
                      "price store's close for that date",
    "STALE_PRICE": "a newer completed session existed before the report date",
}

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
    # The prompts' own example figures, copied verbatim: "$XXX", "$XX.XX",
    # "第 XX 百分位" (INTC and AVGO 2026-10-20/23, both OpenAI fallbacks).
    r"\$X{2,}",
    r"第\s?XX\s?百分位",
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
    # The duplicate suffix comes before the provider or after it
    # ("…_2026-10-23-2_gemini.md", "…_2026-10-23_gemini-2.md").
    r"^(?P<atype>[a-z_]+)_(?P<date>\d{4}-\d{2}-\d{2})(?P<dup>-\d+)?(?:_(?P<provider>[a-z]+))?(?P<dup_after>-\d+)?\.md$"
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
        is_dup = bool(m.group("dup") or m.group("dup_after"))
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

    # Accuracy: the report against the figures it was given and its own
    # arithmetic. A refusal has neither, so it is not checked.
    if "REFUSAL" not in issues:
        for code, note in content_findings(atype, text, content, ticker, date):
            if code not in issues:
                issues.append(code)
            notes.append(note)

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


def _fmt(d: dict, *keys: str) -> str:
    return " ".join(f"{k}={d[k]}" for k in keys)


def content_findings(atype: str, text: str, content: str, ticker: str,
                      date: str) -> "list[tuple[str, str]]":
    """``(issue code, note)`` pairs from the type-specific checks for one report:
    a fundamental report's chapters, then the accuracy checks.

    Each accuracy check compares the report with something it cannot argue with: its
    own figures, the close and levels the pipeline recorded in the front
    matter, or the committed price store. Checks that cannot run (no front
    matter price, no parseable table) stay silent.
    """
    fm = technical.front_matter(text)
    try:
        price = float(fm["price"]) if fm.get("price") else None
    except ValueError:
        price = None
    out: "list[tuple[str, str]]" = []

    if atype == "fundamental_analysis":
        missing = arithmetic.missing_chapters(content)
        if missing:
            out.append(("MISSING_SECTIONS", f"missing_chapters={missing}"))
        # §8.8 against the sum of its own terms (25 of 36 reports were off) …
        a = arithmetic.check(content, price)
        if a["status"] == "mismatch":
            out.append(("ARITHMETIC", f"8.8 stated={a['stated']} terms_sum={a['total']} "
                                      f"diff={a['diff_pct']}% weights={a['weights_pct']}%"))
        # … and the headline MOS / premium against the report's own inputs.
        for v in arithmetic.valuation_mismatches(content, a["price"], a["stated"]):
            out.append(("ARITHMETIC", f"{v['metric']} stated={v['stated']}% "
                                      f"expected={v['expected']}%"))
        quoted = market_data.quote_mismatch(arithmetic.report_price(content), price)
        if quoted:
            out.append(("PRICE_MISMATCH", "quoted " + _fmt(quoted, "stated", "price", "diff_pct")))

    if atype == "technical_analysis":
        tech = technical.check(text)
        if tech["nan"]:
            out.append(("NAN_VALUE", f"nan={len(tech['nan'])}× e.g. {tech['nan'][0]!r}"))
        if tech["price"]:
            out.append(("PRICE_MISMATCH", "headline " + _fmt(tech["price"], "stated", "price", "diff_pct")))
        if tech["levels"]:
            out.append(("LEVEL_MISMATCH", "levels=" + ", ".join(
                f"{l['label']} {l['stated']}≠{l['computed']}" for l in tech["levels"])))
        if tech["rr"]:
            out.append(("RR_MISMATCH", "rr=" + ", ".join(
                f"stated {r['stated']} vs {r['recomputed']}" for r in tech["rr"])))

    # Any report's worked equations: does each "=" in a $$ chain hold?
    steps = derivation.check(content)
    if steps:
        first = steps[0]
        out.append(("DERIVATION", f"steps={len(steps)}× e.g. {first['left'][:60]} = "
                                  f"{first['right'][:40]} (computes {first['computed']:.4g})"))

    # Any report that recorded its close: is that close the market's?
    record = market_data.check(fm, ticker, date)
    if record["store"]:
        out.append(("STORE_MISMATCH", "store " + _fmt(record["store"], "price", "store", "diff_pct")))
    if record["stale"]:
        out.append(("STALE_PRICE", f"price_date={fm.get('price_date')} "
                                   f"newer_sessions={record['stale']}"))
    return out


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
    "ISSUE_TYPES", "content_findings", "MIN_LINES", "REFUSAL_PATTERNS", "PLACEHOLDER_PATTERNS", "HTML_LEAK_PATTERNS",
    "CUTOFF_SIGNALS", "FRONTMATTER_RE", "DATE_RE", "FILENAME_RE",
    "ReportIssue", "parse_file", "collect_reports",
]
