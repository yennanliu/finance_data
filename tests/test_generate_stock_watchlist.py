"""Integration tests for the generate_stock_watchlist CLI entry script."""

import types
from datetime import datetime, timezone

import openai
import pytest

import generate_stock_watchlist as gsw

pytestmark = pytest.mark.integration


def _ns(**kw):
    return types.SimpleNamespace(**kw)


def _fake_response(text="WATCHLIST"):
    return _ns(
        choices=[_ns(message=_ns(content=text))],
        usage=_ns(prompt_tokens=10, completion_tokens=20),
    )


def _redirect_ws(monkeypatch, tmp_path):
    """Point the script's __file__ so ws/ resolves under tmp_path."""
    fake_script = tmp_path / "scripts" / "gen.py"
    fake_script.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(gsw, "__file__", str(fake_script))
    return tmp_path / "ws"


# ── _output_path sequencing ──────────────────────────────────────────────────

def test_output_path_sequence(monkeypatch, tmp_path):
    ws = _redirect_ws(monkeypatch, tmp_path)
    prefix = datetime.now(timezone.utc).strftime("%Y_%m")

    first = gsw._output_path()
    assert first == ws / f"{prefix}_001_open.txt"
    first.write_text("x")

    second = gsw._output_path()
    assert second == ws / f"{prefix}_002_open.txt"


# ── generate_watchlist ───────────────────────────────────────────────────────

def test_generate_watchlist_missing_key_exits(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        gsw.generate_watchlist()


def test_generate_watchlist_happy_path(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    create = lambda **kw: _fake_response("30 stocks here")
    monkeypatch.setattr(openai, "OpenAI",
                        lambda api_key=None: _ns(chat=_ns(completions=_ns(create=create))))
    out = gsw.generate_watchlist(model="gpt-4o", max_tokens=8000)
    assert out == "30 stocks here"


def test_generate_watchlist_retries_on_rate_limit(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    # The rate-limit sleep now happens inside the shared run_openai runner.
    from analysis.utils import llm as llm_mod
    monkeypatch.setattr(llm_mod.time, "sleep", lambda *_: None)

    class RL(Exception):
        pass

    monkeypatch.setattr(openai, "RateLimitError", RL)
    calls = {"n": 0}

    def create(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RL()
        return _fake_response("ok")

    monkeypatch.setattr(openai, "OpenAI",
                        lambda api_key=None: _ns(chat=_ns(completions=_ns(create=create))))
    out = gsw.generate_watchlist()
    assert out == "ok"
    assert calls["n"] == 2


# ── main ─────────────────────────────────────────────────────────────────────

def test_main_writes_watchlist_file(monkeypatch, tmp_path):
    ws = _redirect_ws(monkeypatch, tmp_path)
    monkeypatch.setattr(gsw, "generate_watchlist", lambda model, max_tokens: "BODY")
    monkeypatch.setattr("sys.argv", ["generate_stock_watchlist.py"])
    gsw.main()

    files = list(ws.glob("*_open.txt"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert "BODY" in text
    assert "Purpose:" in text  # header present
