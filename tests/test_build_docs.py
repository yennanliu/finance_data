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


# ── sample-build mode ────────────────────────────────────────────────────────

def test_sanitize_wraps_bare_node_no_space_arrow():
    out = bd.sanitize_mermaid("graph TD\n    短期-->AI 技術需求")
    assert "短期 --> " in out and '["AI 技術需求"]' in out


def test_sanitize_collapses_id_bracket_after_pipe_and_amp():
    # `id [label]` gaps after a pipe edge-label or `&` join must close so the
    # label gets quoted; a `&` INSIDE a quoted label must be left untouched.
    out = bd.sanitize_mermaid(
        'graph TD\n    A -->|lbl| B [C (x)]\n    D & E [F (y)] --> G\n'
        '    X --> H["MACD & RSI"]')
    assert 'B["C (x)"]' in out
    assert 'E["F (y)"]' in out
    assert 'H["MACD & RSI"]' in out  # unchanged — no double-spacing


def test_sample_helpers_toggle(monkeypatch):
    monkeypatch.setattr(bd, "SAMPLE_BUILD", False)
    assert bd._sample([1, 2, 3, 4, 5]) == [1, 2, 3, 4, 5]
    monkeypatch.setattr(bd, "SAMPLE_BUILD", True)
    monkeypatch.setattr(bd, "SAMPLE_LIMIT", 2)
    monkeypatch.setattr(bd, "SAMPLE_TICKERS", [])
    assert bd._sample([1, 2, 3, 4, 5]) == [1, 2]


def test_sample_dirs_respects_allowlist(monkeypatch, tmp_path):
    dirs = [tmp_path / n for n in ("aaa", "bbb", "ccc")]
    monkeypatch.setattr(bd, "SAMPLE_BUILD", True)
    monkeypatch.setattr(bd, "SAMPLE_LIMIT", 3)
    monkeypatch.setattr(bd, "SAMPLE_TICKERS", ["ccc"])
    assert [d.name for d in bd._sample_dirs(dirs)] == ["ccc"]
    monkeypatch.setattr(bd, "SAMPLE_TICKERS", [])
    monkeypatch.setattr(bd, "SAMPLE_LIMIT", 2)
    assert [d.name for d in bd._sample_dirs(dirs)] == ["aaa", "bbb"]


def _mk_report(dirpath: Path, name: str, body: str):
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / name).write_text(body, encoding="utf-8")


def _patch_sample_env(monkeypatch, tmp_path, src_stock, *, limit, tickers):
    docs = tmp_path / "docs"
    for attr, val in [
        ("ROOT", tmp_path), ("SRC_STOCK", src_stock),
        ("SRC_FUNDAMENTAL", tmp_path / "ai_gen_report" / "fundamental"),
        ("SRC_TECHNICAL", tmp_path / "ai_gen_report" / "technical"),
        ("DOCS", docs), ("DOCS_ZH", docs / "zh"),
        ("_INCREMENTAL", False), ("_MMDC", None),
        ("SAMPLE_BUILD", True), ("SAMPLE_LIMIT", limit), ("SAMPLE_TICKERS", tickers),
    ]:
        monkeypatch.setattr(bd, attr, val)
    return docs


def test_sample_build_reports_caps_and_sanitizes(tmp_path, monkeypatch):
    # 3 tickers × 3 dated reports, each with a flowchart whose node label has
    # unquoted parens. Same date (today → within retention), distinct provider.
    src_stock = tmp_path / "ai_gen_report" / "stock"
    diagram = "```mermaid\ngraph TD\n    A[ADX (14) = 26.95] --> B\n```"
    for tk in ("aaa", "bbb", "ccc"):
        for provider in ("claude", "gemini", "openai"):
            _mk_report(src_stock / tk,
                       f"technical_analysis_{bd.TODAY}_{provider}.md",
                       f"# {tk} report\n\n{diagram}\n")
    docs = _patch_sample_env(monkeypatch, tmp_path, src_stock, limit=2, tickers=[])

    bd.build_reports(lang="en")

    report_dirs = sorted(p.name for p in (docs / "reports").iterdir() if p.is_dir())
    assert report_dirs == ["aaa", "bbb"]                 # capped to 2 tickers
    for tk in report_dirs:
        mds = list((docs / "reports" / tk).glob("technical_*.md"))
        assert len(mds) == 2                             # capped to 2 files/ticker
        for md in mds:
            assert 'A["ADX (14) = 26.95"]' in md.read_text(encoding="utf-8")
    assert (docs / "reports" / "index.md").exists()


def test_sample_build_reports_respects_sample_tickers(tmp_path, monkeypatch):
    src_stock = tmp_path / "ai_gen_report" / "stock"
    for tk in ("aaa", "bbb", "ccc"):
        _mk_report(src_stock / tk,
                   f"technical_analysis_{bd.TODAY}_openai.md", "# report\n")
    docs = _patch_sample_env(monkeypatch, tmp_path, src_stock, limit=3, tickers=["ccc"])

    bd.build_reports(lang="en")

    report_dirs = sorted(p.name for p in (docs / "reports").iterdir() if p.is_dir())
    assert report_dirs == ["ccc"]
