"""Integration tests for the generate_stock_watchlist CLI entry script."""

import sys
import types
from datetime import datetime, timezone

import pytest

import generate_stock_watchlist as gsw

pytestmark = pytest.mark.integration


def _ns(**kw):
    return types.SimpleNamespace(**kw)


def _fake_response(text="WATCHLIST", finish_reason="STOP"):
    """A minimal Gemini-shaped response (text + finish_reason + usage_metadata)."""
    reason = type("Reason", (), {"name": finish_reason})()
    return _ns(
        text=text,
        candidates=[_ns(finish_reason=reason)],
        usage_metadata=_ns(prompt_token_count=10, candidates_token_count=20),
    )


def _install_gemini(monkeypatch, generate_content):
    """Install a fake ``google.genai`` SDK whose Client uses generate_content."""
    google_mod = types.ModuleType("google")
    genai_mod = types.ModuleType("google.genai")
    types_mod = types.ModuleType("google.genai.types")

    types_mod.GenerateContentConfig = lambda **kw: _ns(**kw)

    class Client:
        def __init__(self, api_key=None):
            self.models = _ns(generate_content=generate_content)

    genai_mod.Client = Client
    genai_mod.types = types_mod
    google_mod.genai = genai_mod
    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.genai", genai_mod)
    monkeypatch.setitem(sys.modules, "google.genai.types", types_mod)


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
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        gsw.generate_watchlist()


def test_generate_watchlist_happy_path(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    _install_gemini(monkeypatch, lambda **kw: _fake_response("30 stocks here"))
    out = gsw.generate_watchlist(model="gemini-2.5-flash", max_tokens=8000)
    assert out == "30 stocks here"


def test_generate_watchlist_retries_on_rate_limit(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    # The rate-limit sleep now happens inside the shared run_gemini runner.
    from analysis.utils import llm as llm_mod
    monkeypatch.setattr(llm_mod.time, "sleep", lambda *_: None)

    calls = {"n": 0}

    def generate_content(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise Exception("RESOURCE_EXHAUSTED: quota exceeded")
        return _fake_response("ok")

    _install_gemini(monkeypatch, generate_content)
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
