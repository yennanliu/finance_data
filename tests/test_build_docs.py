"""Unit tests for the deterministic helpers in build_docs.py.

The heavy build_* orchestrators read/write whole directory trees and run mmdc;
they're exercised by the CI build smoke. Here we pin the pure logic.
"""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

import build_docs as bd
from analysis.data import prices

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


# ── price-target scenario table ───────────────────────────────────────────────

# 10.2-style: emoji rows, target is the first $ value, explicit probability col.
_MD_EMOJI = """\
### 10.2 目標價與隱含報酬率

| 情境 | 權重機率 | 目標價 | 當前股價 | 隱含報酬率 |
|---|---|---|---|---|
| 🔴 **悲觀** | 15% | $180.00 | $202.81 | -11.2% |
| 🟡 **基準** | **60%** | **$300.00** | $202.81 | +49.1% |
| 🟢 **樂觀** | 25% | $500.00 | $202.81 | +146.5% |
| **加權目標價** | 100% | **$333.00** | $202.81 | +64.4% |
"""

# 7.3-style: target sits behind an EPS $ column, so "first $" would be wrong —
# the parser must pick the 隱含目標價 column by name.
_MD_TARGET_NOT_FIRST = """\
### 7.3 情境目標價推導

| 情境 | 12M 預估 EPS | 預期 P/E | 隱含目標價 | 相對現價漲跌幅 | 發生機率 |
|------|-------------|----------|------------|----------------|----------|
| 🔴 **悲觀** | $15.53 | 27.0x | **$420.00** | -19.5% | 20% |
| 🟡 **基準** | $16.94 | 36.5x | **$620.00** | +18.8% | 60% |
| 🟢 **樂觀** | $18.35 | 41.0x | **$750.00** | +43.7% | 20% |
"""

# text-labelled rows (no emoji), still carries a probability column.
_MD_TEXT_LABELS = """\
### 7.3 情境目標價

| 情境 | 目標價 (USD) | 隱含報酬率 | 機率權重 |
|------|-------------|------------|----------|
| 悲觀情境 | $90 | +20.9% | 20% |
| 基準情境 | $105 | +41.1% | 60% |
| 樂觀情境 | $120 | +61.2% | 20% |
"""

# scenario targets but no probability column → default weights applied.
_MD_NO_PROB = """\
### 7.3 情境目標價推導

| 情境 | 隱含目標價 | 相對現價漲跌幅 | 觸發條件 |
|------|------------|----------------|----------|
| 🔴 悲觀 | $420.00 | -19.5% | 需求急凍 |
| 🟡 基準 | $620.00 | +18.8% | 穩健增長 |
| 🟢 樂觀 | $750.00 | +43.7% | 超預期 |
"""

# a risk matrix reuses the emojis but in the 2nd cell and has no 目標價 column;
# an investment-thesis table has all-🟢 rows. Neither is a scenario table.
_MD_DECOYS = """\
### 9 風險矩陣

| # | 風險項目 | 發生機率 | 財務衝擊 | 風險評分 |
|---|----------|----------|----------|----------|
| 1 | 🔴 地緣政治風險 | 中 (45%) | 極高 (-25%) | 🔴 8.5/10 |

### 投資論點

| 評級 | 投資論點 | 說明 |
|------|----------|------|
| 🟢 論點① | 護城河 | 技術領先 |
| 🟢 論點② | 資本效率 | ROIC 高 |
"""


def _write_md(tmp_path, body):
    p = tmp_path / "fundamental_analysis_2026-07-18_gemini.md"
    p.write_text(body, encoding="utf-8")
    return p


def test_parse_scenario_emoji_table(tmp_path):
    s = bd.parse_scenario_targets(_write_md(tmp_path, _MD_EMOJI))
    assert [r["key"] for r in s] == ["bear", "base", "bull"]
    assert [r["target"] for r in s] == [180.0, 300.0, 500.0]
    assert [r["prob"] for r in s] == [0.15, 0.60, 0.25]
    assert not any(r.get("prob_default") for r in s)


def test_parse_scenario_target_column_not_first_dollar(tmp_path):
    # EPS $ column precedes the target — must not be mistaken for the target.
    s = bd.parse_scenario_targets(_write_md(tmp_path, _MD_TARGET_NOT_FIRST))
    assert [r["target"] for r in s] == [420.0, 620.0, 750.0]
    assert [r["prob"] for r in s] == [0.20, 0.60, 0.20]


def test_parse_scenario_text_labels(tmp_path):
    s = bd.parse_scenario_targets(_write_md(tmp_path, _MD_TEXT_LABELS))
    assert [r["key"] for r in s] == ["bear", "base", "bull"]
    assert [r["target"] for r in s] == [90.0, 105.0, 120.0]
    assert [r["prob"] for r in s] == [0.20, 0.60, 0.20]


def test_parse_scenario_defaults_probs_when_absent(tmp_path):
    s = bd.parse_scenario_targets(_write_md(tmp_path, _MD_NO_PROB))
    assert [r["target"] for r in s] == [420.0, 620.0, 750.0]
    assert [r["prob"] for r in s] == [0.20, 0.60, 0.20]
    assert all(r["prob_default"] for r in s)


def test_parse_scenario_ignores_decoy_tables(tmp_path):
    assert bd.parse_scenario_targets(_write_md(tmp_path, _MD_DECOYS)) == []


def test_parse_scenario_missing_file(tmp_path):
    assert bd.parse_scenario_targets(tmp_path / "nope.md") == []


def _patch_store(monkeypatch, tmp_path, ticker, close, dates=("2026-07-18",)):
    """Point build_docs at a temp price store holding one ticker."""
    monkeypatch.setattr(bd, "PRICES_DIR", tmp_path)
    bars = [{"date": d, "open": close - 1, "high": close + 1, "low": close - 2,
             "close": close, "volume": 1_000_000, "div": None, "split": None}
            for d in dates]
    prices.write_store(ticker, bars, tmp_path)


# Kept under the old name so the many existing call sites read unchanged.
_patch_kline = _patch_store


def test_current_price_reads_latest_close(monkeypatch, tmp_path):
    _patch_store(monkeypatch, tmp_path, "xyz", 202.81)
    assert bd._current_price("xyz") == (202.81, "2026-07-18")


def test_current_price_uses_the_newest_bar(monkeypatch, tmp_path):
    monkeypatch.setattr(bd, "PRICES_DIR", tmp_path)
    prices.write_store("xyz", [
        {"date": "2026-07-17", "open": 90, "high": 95, "low": 89, "close": 91,
         "volume": 1, "div": None, "split": None},
        {"date": "2026-07-18", "open": 91, "high": 99, "low": 90, "close": 98,
         "volume": 1, "div": None, "split": None},
    ], tmp_path)
    assert bd._current_price("xyz") == (98.0, "2026-07-18")


def test_current_price_missing_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(bd, "PRICES_DIR", tmp_path)
    assert bd._current_price("absent") is None


def test_target_price_block_renders_and_recomputes(monkeypatch, tmp_path):
    md = _write_md(tmp_path, _MD_EMOJI)
    _patch_kline(monkeypatch, tmp_path, "nvda", 200.0)
    out = bd.target_price_block("nvda", md, "zh")
    assert "目標價與隱含報酬率" in out
    # implied return recomputed against the live $200 price, not the report's.
    assert "-10.0%" in out          # 180/200 - 1
    assert "+150.0%" in out         # 500/200 - 1
    # weighted target = .15*180 + .60*300 + .25*500 = 332.0
    assert "$332.00" in out
    # weighted value column = probability × target (base = .60*300 = 180)
    assert "$180.00" in out


def test_target_price_block_english_headers(monkeypatch, tmp_path):
    md = _write_md(tmp_path, _MD_EMOJI)
    _patch_kline(monkeypatch, tmp_path, "nvda", 200.0)
    out = bd.target_price_block("nvda", md, "en")
    assert "Price Target & Implied Return" in out
    assert "| 🟡 Base |" in out


def test_target_price_block_default_prob_note(monkeypatch, tmp_path):
    md = _write_md(tmp_path, _MD_NO_PROB)
    _patch_kline(monkeypatch, tmp_path, "soxx", 500.0)
    out = bd.target_price_block("soxx", md, "zh")
    assert "預設" in out  # honest note about defaulted weights


def test_target_price_block_empty_without_kline(monkeypatch, tmp_path):
    md = _write_md(tmp_path, _MD_EMOJI)
    monkeypatch.setattr(bd, "PRICES_DIR", tmp_path)  # empty store
    assert bd.target_price_block("nvda", md, "zh") == ""


def test_target_price_block_empty_without_scenarios(monkeypatch, tmp_path):
    md = _write_md(tmp_path, _MD_DECOYS)
    _patch_kline(monkeypatch, tmp_path, "nvda", 200.0)
    assert bd.target_price_block("nvda", md, "zh") == ""


def test_target_price_block_none_path():
    assert bd.target_price_block("nvda", None, "zh") == ""


# ── derived chart payload ────────────────────────────────────────────────────
def _store_series(monkeypatch, tmp_path, ticker, n):
    """Write `n` consecutive daily bars for a ticker into a temp store."""
    monkeypatch.setattr(bd, "PRICES_DIR", tmp_path)
    start = date(2020, 1, 1)
    bars = [{"date": (start + timedelta(days=i)).isoformat(),
             "open": 100 + i, "high": 102 + i, "low": 98 + i, "close": 101 + i,
             "volume": 1_000_000 + i, "div": None, "split": None}
            for i in range(n)]
    prices.write_store(ticker, bars, tmp_path)
    return bars


def test_kline_payload_shape_matches_what_the_widget_consumes(monkeypatch, tmp_path):
    _store_series(monkeypatch, tmp_path, "amd", 5)
    data = json.loads(bd.kline_payload("amd"))
    assert data["ticker"] == "AMD"
    assert data["currency"] == "USD"
    # "updated" describes the data, not the build date, so a stale store reads
    # as stale rather than as fresh.
    assert data["updated"] == data["bars"][-1]["t"]
    assert set(data["bars"][0]) == {"t", "o", "h", "l", "c", "v"}


def test_kline_payload_caps_at_visible_plus_lookback(monkeypatch, tmp_path):
    _store_series(monkeypatch, tmp_path, "amd", 900)
    bars = json.loads(bd.kline_payload("amd"))["bars"]
    assert len(bars) == bd.KLINE_VISIBLE_BARS + bd.KLINE_LOOKBACK_BARS


def test_kline_payload_keeps_the_newest_bars(monkeypatch, tmp_path):
    written = _store_series(monkeypatch, tmp_path, "amd", 900)
    bars = json.loads(bd.kline_payload("amd"))["bars"]
    assert bars[-1]["t"] == written[-1]["date"]


def test_kline_payload_none_without_store(monkeypatch, tmp_path):
    monkeypatch.setattr(bd, "PRICES_DIR", tmp_path)
    assert bd.kline_payload("absent") is None


def test_kline_payload_maps_taiwan_currency(monkeypatch, tmp_path):
    _store_series(monkeypatch, tmp_path, "2330.tw", 3)
    assert json.loads(bd.kline_payload("2330.tw"))["currency"] == "TWD"


def test_write_kline_payload_writes_and_is_idempotent(monkeypatch, tmp_path):
    _store_series(monkeypatch, tmp_path, "amd", 5)
    dst = tmp_path / "out"
    assert bd.write_kline_payload("amd", dst) is True
    first = (dst / "kline.json").read_text(encoding="utf-8")
    assert bd.write_kline_payload("amd", dst) is True
    assert (dst / "kline.json").read_text(encoding="utf-8") == first


def test_write_kline_payload_skips_when_no_data(monkeypatch, tmp_path):
    monkeypatch.setattr(bd, "PRICES_DIR", tmp_path)
    dst = tmp_path / "out"
    assert bd.write_kline_payload("absent", dst) is False
    assert not (dst / "kline.json").exists()


# ── kline_block() attributes ─────────────────────────────────────────────────
def test_kline_block_defaults_to_a_page_relative_src(monkeypatch, tmp_path):
    _store_series(monkeypatch, tmp_path, "amd", 5)
    out = bd.kline_block("amd")
    assert 'class="kline-widget"' in out
    assert 'data-ticker="AMD"' in out
    assert 'data-src="kline.json"' in out
    # No as-of on the live index chart.
    assert "data-as-of" not in out


def test_kline_block_report_page_variant(monkeypatch, tmp_path):
    _store_series(monkeypatch, tmp_path, "amd", 5)
    out = bd.kline_block("amd", src="../kline.json",
                         as_of="2026-07-31", ma="30+,60+,200")
    # Report bodies are served one level deeper than the ticker index.
    assert 'data-src="../kline.json"' in out
    assert 'data-as-of="2026-07-31"' in out
    assert 'data-ma="30+,60+,200"' in out


def test_kline_block_empty_without_store(monkeypatch, tmp_path):
    monkeypatch.setattr(bd, "PRICES_DIR", tmp_path)
    assert bd.kline_block("absent") == ""


# ── front matter → header table ──────────────────────────────────────────────

_REPORT_FM = (
    '---\n'
    'title: "AMD 基本面深度分析 2026-07-28"\n'
    'date: 2026-07-28\n'
    'ticker: AMD\n'
    'generated_by: Google Gemini API (scripts/generate_analysis.py)\n'
    '---\n'
    '\n'
    '# AMD 基本面深度分析報告\n'
)


def test_split_frontmatter_separates_yaml_and_body():
    yaml_body, body = bd.split_frontmatter(_REPORT_FM)
    assert yaml_body.startswith('title: "AMD')
    assert body.lstrip("\n").startswith("# AMD")


def test_split_frontmatter_noop_without_block():
    assert bd.split_frontmatter("# Title\n") == ("", "# Title\n")


def test_frontmatter_table_renders_rows():
    table = bd.frontmatter_table(bd.split_frontmatter(_REPORT_FM)[0])
    assert table.startswith("| | |\n|---|---|\n")
    assert "| **title** | AMD 基本面深度分析 2026-07-28 |" in table  # quotes stripped
    assert "| **ticker** | AMD |" in table
    assert "| **generated_by** | Google Gemini API (scripts/generate_analysis.py) |" in table


def test_frontmatter_table_skips_nested_and_escapes_pipes():
    table = bd.frontmatter_table("search:\n  exclude: true\n# note\nlabel: a | b\n")
    assert "exclude" not in table  # nested key is not a scalar field
    assert "note" not in table
    assert r"| **label** | a \| b |" in table


def test_frontmatter_table_empty_without_fields():
    assert bd.frontmatter_table("search:\n  exclude: true\n") == ""


def test_copy_file_merges_meta_into_single_block(monkeypatch, tmp_path):
    monkeypatch.setattr(bd, "ROOT", tmp_path)  # copy_file logs paths relative to ROOT
    src = tmp_path / "r.md"
    src.write_text(_REPORT_FM, encoding="utf-8")
    dst = tmp_path / "out" / "r.md"
    bd.copy_file(src, dst, extra_meta=bd.SEARCH_EXCLUDE_META)
    out = dst.read_text(encoding="utf-8")
    # Exactly one front-matter block, so MkDocs strips it instead of rendering
    # the report's own block as body text.
    assert out.count("\n---\n") == 1
    assert out.startswith("---\nsearch:\n  exclude: true\ntitle: ")
    assert "| **ticker** | AMD |" in out


def test_copy_file_without_meta_leaves_frontmatter_alone(monkeypatch, tmp_path):
    monkeypatch.setattr(bd, "ROOT", tmp_path)
    src = tmp_path / "r.md"
    src.write_text(_REPORT_FM, encoding="utf-8")
    dst = tmp_path / "out" / "r.md"
    bd.copy_file(src, dst)
    assert dst.read_text(encoding="utf-8") == _REPORT_FM


# ── static chart embed ───────────────────────────────────────────────────────

_LEGACY_EMBED = (
    "<details>\n"
    "<summary>📊 靜態圖表 (點擊展開)</summary>\n"
    '<img src="technical_chart_2026-07-28.png" alt="Technical Chart" style="max-width:100%;">\n'
    "</details>\n"
)


def test_fix_static_chart_embed_converts_to_markdown_image():
    out = bd.fix_static_chart_embed(_LEGACY_EMBED)
    assert out == (
        '<details markdown="1">\n'
        "<summary>📊 靜態圖表 (點擊展開)</summary>\n"
        "\n"
        "![Technical Chart](technical_chart_2026-07-28.png)\n"
        "\n"
        "</details>\n"
    )


def test_fix_static_chart_embed_is_idempotent():
    once = bd.fix_static_chart_embed(_LEGACY_EMBED)
    assert bd.fix_static_chart_embed(once) == once


def test_fix_static_chart_embed_leaves_absolute_sources():
    html = '<img src="https://cdn.example.com/x.png" alt="Remote">'
    assert bd.fix_static_chart_embed(html) == html


def test_fix_static_chart_embed_noop_without_images():
    assert bd.fix_static_chart_embed("# Title\n") == "# Title\n"
