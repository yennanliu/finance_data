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
