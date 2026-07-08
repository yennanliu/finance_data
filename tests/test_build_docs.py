"""Unit tests for the deterministic helpers in build_docs.py.

The heavy build_* orchestrators read/write whole directory trees and run mmdc;
they're exercised by the CI build smoke. Here we pin the pure logic.
"""

from datetime import date
from pathlib import Path

import pytest

import build_docs as bd

pytestmark = pytest.mark.unit


# ── _file_date ───────────────────────────────────────────────────────────────

def test_file_date_parses_embedded_date():
    assert bd._file_date(Path("fundamental_analysis_2026-06-30_claude.md")) == date(2026, 6, 30)


def test_file_date_none_when_absent():
    assert bd._file_date(Path("index.md")) is None


def test_file_date_none_when_invalid():
    assert bd._file_date(Path("report_2026-13-40.md")) is None


# ── within_retention ─────────────────────────────────────────────────────────

def test_within_retention_recent(monkeypatch):
    monkeypatch.setattr(bd, "TODAY_DATE", date(2026, 6, 30))
    monkeypatch.setattr(bd, "RETENTION_DAYS", 120)
    assert bd.within_retention(Path("r_2026-06-01.md")) is True


def test_within_retention_old(monkeypatch):
    monkeypatch.setattr(bd, "TODAY_DATE", date(2026, 6, 30))
    monkeypatch.setattr(bd, "RETENTION_DAYS", 120)
    assert bd.within_retention(Path("r_2025-01-01.md")) is False


def test_within_retention_undated_always_published(monkeypatch):
    monkeypatch.setattr(bd, "RETENTION_DAYS", 120)
    assert bd.within_retention(Path("index.md")) is True


def test_within_retention_disabled(monkeypatch):
    monkeypatch.setattr(bd, "RETENTION_DAYS", 0)
    assert bd.within_retention(Path("r_2000-01-01.md")) is True


# ── prerender_mermaid ────────────────────────────────────────────────────────

CONTENT = "intro\n```mermaid\ngraph TD; A-->B\n```\noutro"


def test_prerender_noop_without_mmdc(monkeypatch):
    monkeypatch.setattr(bd, "_MMDC", None)
    assert bd.prerender_mermaid(CONTENT) == CONTENT


def test_prerender_replaces_with_svg(monkeypatch):
    monkeypatch.setattr(bd, "_MMDC", "mmdc")
    monkeypatch.setattr(bd, "_render_mermaid_block", lambda d: "<svg>OK</svg>")
    out = bd.prerender_mermaid(CONTENT)
    assert "mermaid-svg" in out
    assert "<svg>OK</svg>" in out
    assert "```mermaid" not in out


def test_prerender_keeps_block_on_failure(monkeypatch):
    monkeypatch.setattr(bd, "_MMDC", "mmdc")
    monkeypatch.setattr(bd, "_render_mermaid_block", lambda d: None)
    out = bd.prerender_mermaid(CONTENT)
    assert "```mermaid" in out  # fallback keeps original


# ── sanitize_mermaid ─────────────────────────────────────────────────────────

def test_sanitize_quotes_parens_in_node_label():
    out = bd.sanitize_mermaid("graph TD\n    A[ADX (14) = 26.95] --> B")
    assert 'A["ADX (14) = 26.95"]' in out


def test_sanitize_quotes_rectangle_ending_in_paren():
    # The `)]` at the end is a rectangle close, not a cylinder shape.
    out = bd.sanitize_mermaid("graph TD\n    C1[MA20: $383 (價格下方)]")
    assert 'C1["MA20: $383 (價格下方)"]' in out


def test_sanitize_leaves_already_quoted_labels():
    src = 'graph TD\n    A["已引號 (x)"] --> B'
    assert bd.sanitize_mermaid(src) == src


def test_sanitize_quotes_pipe_edge_label():
    out = bd.sanitize_mermaid("graph LR\n    A -->|漲 ($1) -> $2| B")
    assert '-->|"漲 ($1) -> $2"|' in out


def test_sanitize_fixes_subgraph_title_and_lone_comment():
    out = bd.sanitize_mermaid("graph TD\n    subgraph 悲觀 (跌破)\n    % note\n    end")
    assert 'subgraph "悲觀 (跌破)"' in out
    assert "\n    %% note" in out


def test_sanitize_normalizes_uppercase_keywords():
    out = bd.sanitize_mermaid("graph TD\n    SUBGRAPH X\n    A[x]\n    END")
    assert "subgraph X" in out and "SUBGRAPH" not in out
    assert out.rstrip().endswith("end")


def test_sanitize_wraps_bare_node_with_spaces():
    out = bd.sanitize_mermaid("graph TD\n    樂觀情境 --> 股價突破 $20")
    assert '["股價突破 $20"]' in out


def test_sanitize_noop_for_non_flowchart():
    src = "pie title Pie\n    \"A (x)\" : 50"
    assert bd.sanitize_mermaid(src) == src


def test_sanitize_blocks_only_touches_fences():
    content = "text (a)\n```mermaid\ngraph TD\n    A[x (1)]\n```\nmore (b)"
    out = bd.sanitize_mermaid_blocks(content)
    assert 'A["x (1)"]' in out
    assert out.startswith("text (a)\n")  # prose parens untouched
    assert out.endswith("\nmore (b)")


# ── misc helpers ─────────────────────────────────────────────────────────────

def test_t_translation_lookup():
    assert bd.t("en", "sector") == "Sector"
    assert bd.t("zh", "sector") == "產業"


@pytest.mark.parametrize("raw,expected", [
    ("Apple Inc.", "apple-inc"),
    ("AAPL", "aapl"),
    ("Hello World!!!", "hello-world"),
])
def test_slugify(raw, expected):
    assert bd.slugify(raw) == expected


def test_get_meta_unknown_ticker_defaults():
    meta = bd.get_meta("zzzz")
    assert meta["name"] == "ZZZZ"
    assert meta["sector"] == "Equity"
