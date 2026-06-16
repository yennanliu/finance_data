"""Tests for the RAG eval toolkit (no API calls)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from eval import judges as J
from eval import retrieval as R
from eval.context_store import (
    context_sidecar_path,
    read_context_sidecar,
    write_context_sidecar,
)


# ── context_store ────────────────────────────────────────────────────────────

def test_sidecar_path():
    assert context_sidecar_path("a/b/report_2026-06-16_gemini.md").name == \
        "report_2026-06-16_gemini.context.json"
    # dedup-suffixed filenames keep the trailing suffix swap
    assert context_sidecar_path("x/foo-2.md").name == "foo-2.context.json"


def test_sidecar_roundtrip(tmp_path):
    report = tmp_path / "market_news_2026-06-16_gemini.md"
    report.write_text("# report", encoding="utf-8")
    path = write_context_sidecar(
        report, ticker="AAPL", analysis_type="market-news",
        provider="gemini", model="gemini-3.5-flash", date="2026-06-16",
        context_text="P/E is 28.1", retrieved_docs=[{"id": "n1", "title": "x"}],
    )
    assert path is not None and path.exists()
    data = read_context_sidecar(report)
    assert data["ticker"] == "AAPL"
    assert data["context_text"] == "P/E is 28.1"
    assert data["retrieved_docs"][0]["id"] == "n1"
    assert data["context_sha256"]  # hashed


def test_sidecar_never_raises():
    # writing to an impossible path returns None instead of raising
    assert write_context_sidecar(
        "/nonexistent_dir_xyz/r.md", ticker="A", analysis_type="t",
        provider="p", model="m", date="d", context_text="c") is None
    assert read_context_sidecar("/nope/missing.md") is None


# ── judges.extract_json ──────────────────────────────────────────────────────

def test_extract_json_plain():
    assert J.extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    assert J.extract_json('```json\n{"answer_relevance": 4}\n```')["answer_relevance"] == 4


def test_extract_json_with_prose():
    txt = 'Sure! Here is the result:\n{"claims": [{"supported": true}]}\nDone.'
    assert J.extract_json(txt)["claims"][0]["supported"] is True


def test_extract_json_array():
    assert J.extract_json("noise [1, 2, 3] tail") == [1, 2, 3]


# ── retrieval metrics ────────────────────────────────────────────────────────

def test_precision():
    sample = {
        "retrieved_docs": [{"id": "n1"}, {"id": "n2"}, {"id": "n3"}],
        "relevance_labels": {"n1": 1, "n2": 0, "n3": 1},
    }
    assert R.precision(sample) == 2 / 3


def test_precision_none_without_labels():
    assert R.precision({"retrieved_docs": [{"id": "n1"}]}) is None


def test_recall_event_coverage():
    sample = {
        "gold_events": ["Q3 earnings beat", "iPhone launch"],
        "retrieved_docs": [{"title": "Apple Q3 earnings beat estimates", "summary": ""}],
    }
    # one of two gold events covered by the retrieved title
    assert R.recall(sample, report_md="") == 0.5


def test_f1():
    assert R.f1(0.5, 0.5) == 0.5
    assert R.f1(None, 0.5) is None


def test_evaluate_sample():
    sample = {
        "ticker": "AAPL", "date": "2026-06-16",
        "retrieved_docs": [{"id": "n1", "title": "Apple earnings beat"}],
        "relevance_labels": {"n1": 1},
        "gold_events": ["earnings beat"],
    }
    out = R.evaluate_sample(sample)
    assert out["precision"] == 1.0
    assert out["recall"] == 1.0
    assert out["f1"] == 1.0
