"""Integration tests for the LLM provider functions with all SDKs mocked.

No real network/API calls: fake `anthropic` / `openai` / `google.genai` modules
are injected into ``sys.modules`` and ``time.sleep`` is neutralised so retry
paths run instantly.
"""

import sys
import types

import pytest

from scripts.analysis.utils import llm
from scripts.analysis.utils.llm import (
    call_claude, call_openai, call_gemini,
    _is_refusal, _refusal_override_prefix, _repeated_heading, _gemini_finish_reason,
    OPENAI_MAX_TOKENS,
)
from scripts.analysis.exceptions import LLMError

pytestmark = pytest.mark.integration


# ── fake SDK response objects (match the shapes llm.py reads) ────────────────

class _Usage:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeAnthropicResponse:
    def __init__(self, text, input_tokens=10, output_tokens=999):
        self.content = [type("Block", (), {"text": text})()]
        self.usage = _Usage(input_tokens=input_tokens, output_tokens=output_tokens)


class FakeOpenAIResponse:
    def __init__(self, text, prompt_tokens=10, completion_tokens=999):
        msg = type("Msg", (), {"content": text})()
        self.choices = [type("Choice", (), {"message": msg})()]
        self.usage = _Usage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)


class FakeGeminiResponse:
    def __init__(self, text, finish_reason="STOP", prompt_tokens=10, output_tokens=999):
        self.text = text
        reason = type("Reason", (), {"name": finish_reason})()
        self.candidates = [type("Candidate", (), {"finish_reason": reason})()]
        self.usage_metadata = _Usage(
            prompt_token_count=prompt_tokens, candidates_token_count=output_tokens
        )

LONG_OK = "# AAPL 分析報告\n" + ("這是一段完整的投資分析內容。" * 60)  # > 500 chars, no refusal
REFUSAL = "抱歉，我無法協助完成這個請求。"


class _RateLimit(Exception):
    """Stand-in for anthropic/openai RateLimitError (matched by the fake module)."""


class Scripted:
    """Callable returning/raising scripted items; records call kwargs."""

    def __init__(self, *items):
        self.items = list(items)
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append(kwargs)
        item = self.items.pop(0) if len(self.items) > 1 else self.items[0]
        if isinstance(item, BaseException):
            raise item
        return item


# ── fake SDK installers ──────────────────────────────────────────────────────

def install_anthropic(monkeypatch, create):
    mod = types.ModuleType("anthropic")

    class Anthropic:
        def __init__(self, api_key=None):
            self.messages = types.SimpleNamespace(create=create)

    mod.RateLimitError = _RateLimit
    mod.Anthropic = Anthropic
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    return mod


def install_openai(monkeypatch, create):
    mod = types.ModuleType("openai")

    class OpenAI:
        def __init__(self, api_key=None):
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=create)
            )

    mod.RateLimitError = _RateLimit
    mod.OpenAI = OpenAI
    monkeypatch.setitem(sys.modules, "openai", mod)
    return mod


def install_gemini(monkeypatch, generate_content):
    google_mod = types.ModuleType("google")
    genai_mod = types.ModuleType("google.genai")
    types_mod = types.ModuleType("google.genai.types")

    def GenerateContentConfig(**kw):
        return types.SimpleNamespace(**kw)

    types_mod.GenerateContentConfig = GenerateContentConfig

    class Client:
        def __init__(self, api_key=None):
            self.models = types.SimpleNamespace(generate_content=generate_content)

    genai_mod.Client = Client
    genai_mod.types = types_mod
    google_mod.genai = genai_mod
    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.genai", genai_mod)
    monkeypatch.setitem(sys.modules, "google.genai.types", types_mod)
    return genai_mod


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda *_: None)


# ── pure refusal/heading helpers ─────────────────────────────────────────────

def test_is_refusal_true_for_short_refusal():
    assert _is_refusal("抱歉，我無法協助") is True


def test_is_refusal_false_for_long_text():
    assert _is_refusal(REFUSAL + "x" * 600) is False  # too long to be a refusal


def test_is_refusal_false_without_pattern():
    assert _is_refusal("short normal answer") is False


def test_refusal_override_escalates():
    first = _refusal_override_prefix("AAPL", 1)
    third = _refusal_override_prefix("AAPL", 3)
    assert "AAPL" in first
    assert "最高優先指令" in third  # stronger wording kicks in at attempt >= 3


def test_repeated_heading_detects_duplicate():
    text = "# Title\n## 1.1 Section\nbody\n## 1.1 Section\nmore"
    assert _repeated_heading(text) == "## 1.1 Section"


def test_repeated_heading_none_when_unique():
    assert _repeated_heading("# A\n## B\n## C") == ""


def test_gemini_finish_reason_extracts_name():
    resp = FakeGeminiResponse("x", finish_reason="MAX_TOKENS")
    assert _gemini_finish_reason(resp) == "MAX_TOKENS"


def test_openai_max_tokens_table():
    assert OPENAI_MAX_TOKENS["gpt-4"] == 8192
    assert OPENAI_MAX_TOKENS["gpt-4o"] == 16384


# ── Claude ───────────────────────────────────────────────────────────────────

def test_claude_missing_key_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    install_anthropic(monkeypatch, Scripted(FakeAnthropicResponse(LONG_OK)))
    with pytest.raises(LLMError):
        call_claude("AAPL", "ctx", "fundamental-analysis", "claude-x", 8000)


def test_claude_happy_path(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    create = Scripted(FakeAnthropicResponse(LONG_OK))
    install_anthropic(monkeypatch, create)
    out = call_claude("AAPL", "ctx", "fundamental-analysis", "claude-x", 8000)
    assert out == LONG_OK
    assert len(create.calls) == 1


def test_claude_retries_on_rate_limit(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    create = Scripted(_RateLimit(), FakeAnthropicResponse(LONG_OK))
    install_anthropic(monkeypatch, create)
    out = call_claude("AAPL", "ctx", "fundamental-analysis", "claude-x", 8000)
    assert out == LONG_OK
    assert len(create.calls) == 2


def test_claude_retries_on_refusal_then_succeeds(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    create = Scripted(FakeAnthropicResponse(REFUSAL), FakeAnthropicResponse(LONG_OK))
    install_anthropic(monkeypatch, create)
    out = call_claude("AAPL", "ctx", "fundamental-analysis", "claude-x", 8000)
    assert out == LONG_OK
    assert len(create.calls) == 2
    # the retry call carries a temperature + an override-prefixed prompt
    assert "temperature" in create.calls[1]
    assert "覆寫" in create.calls[1]["messages"][0]["content"]


# ── OpenAI ───────────────────────────────────────────────────────────────────

def test_openai_missing_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    install_openai(monkeypatch, Scripted(FakeOpenAIResponse(LONG_OK)))
    with pytest.raises(LLMError):
        call_openai("AAPL", "ctx", "fundamental-analysis", "gpt-4o", 16000)


def test_openai_happy_path(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    create = Scripted(FakeOpenAIResponse(LONG_OK))
    install_openai(monkeypatch, create)
    out = call_openai("AAPL", "ctx", "fundamental-analysis", "gpt-4o", 16000)
    assert out == LONG_OK


def test_openai_caps_max_tokens_for_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    create = Scripted(FakeOpenAIResponse(LONG_OK))
    install_openai(monkeypatch, create)
    call_openai("AAPL", "ctx", "fundamental-analysis", "gpt-4", 100000)
    assert create.calls[0]["max_tokens"] == 8192  # capped from 100000


def test_openai_retries_on_refusal(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    create = Scripted(FakeOpenAIResponse(REFUSAL), FakeOpenAIResponse(LONG_OK))
    install_openai(monkeypatch, create)
    out = call_openai("AAPL", "ctx", "fundamental-analysis", "gpt-4o", 16000)
    assert out == LONG_OK
    assert len(create.calls) == 2


# ── Gemini ───────────────────────────────────────────────────────────────────

def test_gemini_missing_key_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    install_gemini(monkeypatch, Scripted(FakeGeminiResponse(LONG_OK)))
    with pytest.raises(LLMError):
        call_gemini("AAPL", "ctx", "fundamental-analysis", "gemini-2.5-flash", 8000)


def test_gemini_happy_path(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    gen = Scripted(FakeGeminiResponse(LONG_OK))
    install_gemini(monkeypatch, gen)
    out = call_gemini("AAPL", "ctx", "fundamental-analysis", "gemini-2.5-flash", 8000)
    assert out == LONG_OK
    assert len(gen.calls) == 1


def test_gemini_retries_on_truncation_at_full_budget(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    gen = Scripted(
        FakeGeminiResponse(LONG_OK, finish_reason="MAX_TOKENS"),
        FakeGeminiResponse(LONG_OK, finish_reason="STOP"),
    )
    install_gemini(monkeypatch, gen)
    out = call_gemini("AAPL", "ctx", "fundamental-analysis", "gemini-2.5-flash", 1000)
    assert out == LONG_OK
    assert len(gen.calls) == 2
    # the retry bumps the budget to the model ceiling
    assert gen.calls[1]["config"].max_output_tokens == 65536


def test_gemini_retries_on_repeated_heading(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    degenerate = "# T\n## 1.1\n" + ("body " * 80) + "\n## 1.1\nloop"
    gen = Scripted(
        FakeGeminiResponse(degenerate, finish_reason="STOP"),
        FakeGeminiResponse(LONG_OK, finish_reason="STOP"),
    )
    install_gemini(monkeypatch, gen)
    out = call_gemini("AAPL", "ctx", "fundamental-analysis", "gemini-2.5-flash", 1000)
    assert out == LONG_OK
    assert len(gen.calls) == 2
