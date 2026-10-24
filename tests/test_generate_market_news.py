"""Integration tests for the generate_market_news CLI entry script."""

import types

import pytest

import generate_market_news as mn

pytestmark = pytest.mark.integration


class _FakeResp:
    def __init__(self, data: bytes):
        self._d = data

    def read(self):
        return self._d

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


RSS_XML = b"""<?xml version="1.0"?>
<rss><channel>
  <item>
    <title>AAPL soars on earnings</title>
    <link>http://example.com/a</link>
    <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
    <description>&lt;p&gt;Great quarter&lt;/p&gt;</description>
  </item>
  <item>
    <title>AAPL launches product</title>
    <link>http://example.com/b</link>
    <pubDate>Tue, 02 Jan 2024 00:00:00 GMT</pubDate>
    <description>news body</description>
  </item>
</channel></rss>"""


# ── _fetch_rss ───────────────────────────────────────────────────────────────

def test_fetch_rss_parses_items(monkeypatch):
    monkeypatch.setattr(mn, "urlopen", lambda *a, **k: _FakeResp(RSS_XML))
    items = mn._fetch_rss("http://feed/{query}", "Test Feed", "AAPL", limit=5)
    assert len(items) == 2
    assert items[0]["title"] == "AAPL soars on earnings"
    assert items[0]["publisher"] == "Test Feed"
    assert items[0]["providerPublishTime"] > 0
    assert "<p>" not in items[0]["summary"]  # HTML stripped


def test_fetch_rss_handles_fetch_failure(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("down")

    monkeypatch.setattr(mn, "urlopen", boom)
    assert mn._fetch_rss("http://feed/{query}", "Test", "AAPL") == []


def test_fetch_rss_respects_limit(monkeypatch):
    monkeypatch.setattr(mn, "urlopen", lambda *a, **k: _FakeResp(RSS_XML))
    items = mn._fetch_rss("http://feed/{query}", "Test", "AAPL", limit=1)
    assert len(items) == 1


# ── _fetch_perplexity ────────────────────────────────────────────────────────

PPLX_XML = b"""<?xml version="1.0"?>
<rss><channel>
  <item><title>Tesla Executive Says Launching Cybercabs In Dallas - Perplexity</title></item>
  <item><title>This Week in TSLA: Roadster Debut - Perplexity</title></item>
  <item><title>Tesla, Inc. Stock Price: Quote, Forecast &amp; News (TSLA) - Perplexity</title></item>
  <item><title>Capcom Co., Ltd. Price: Quote, Forecast (9697.T) - Perplexity</title></item>
  <item><title>Morgan Stanley Raises Meta Price Target - Perplexity</title></item>
  <item><title>Perplexity - Perplexity</title></item>
  <item><title>Teslas tsla lowercase is not the ticker - Perplexity</title></item>
</channel></rss>"""


@pytest.mark.parametrize("name, short", [
    ("Tesla, Inc.", "Tesla"),
    ("NVIDIA Corporation", "NVIDIA"),
    ("Advanced Micro Devices, Inc.", "Advanced Micro Devices"),
    ("Smoore International Holdings Ltd", "Smoore International"),
    ("", ""),
])
def test_short_name_strips_corporate_suffixes(name, short):
    assert mn._short_name(name) == short


def test_fetch_perplexity_keeps_only_articles_about_the_company(monkeypatch):
    monkeypatch.setattr(mn, "urlopen", lambda *a, **k: _FakeResp(PPLX_XML))
    items = mn._fetch_perplexity("TSLA", "Tesla, Inc.")
    assert [i["title"] for i in items] == [
        "Tesla Executive Says Launching Cybercabs In Dallas",
        "This Week in TSLA: Roadster Debut",
    ]
    assert all(i["publisher"] == "Perplexity" for i in items)


def test_fetch_perplexity_ticker_only_without_company(monkeypatch):
    monkeypatch.setattr(mn, "urlopen", lambda *a, **k: _FakeResp(PPLX_XML))
    assert [i["title"] for i in mn._fetch_perplexity("TSLA")] == ["This Week in TSLA: Roadster Debut"]


def test_fetch_perplexity_fails_soft(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("down")

    monkeypatch.setattr(mn, "urlopen", boom)
    assert mn._fetch_perplexity("TSLA", "Tesla, Inc.") == []


# ── fetch_news (dedup + sort) ────────────────────────────────────────────────

def test_fetch_news_dedupes_and_sorts(monkeypatch):
    monkeypatch.setattr(mn, "yahoo_news", lambda t: [
        {"title": "Same Headline", "providerPublishTime": 100},
        {"title": "Older News", "providerPublishTime": 50},
    ])
    # RSS returns a duplicate (normalised) title plus a newer item
    monkeypatch.setattr(mn, "_fetch_rss", lambda url, name, ticker, limit=5: [
        {"title": "same headline!!", "providerPublishTime": 999},  # dup of "Same Headline"
        {"title": "Breaking Latest", "providerPublishTime": 500},
    ] if name == "Google News" else [])

    out = mn.fetch_news("AAPL")
    titles = [i["title"] for i in out]
    # duplicate collapsed (first occurrence kept), 3 unique remain
    assert titles.count("Same Headline") == 1
    assert "same headline!!" not in titles
    # sorted by providerPublishTime descending
    times = [i.get("providerPublishTime", 0) for i in out]
    assert times == sorted(times, reverse=True)


def test_fetch_news_merges_perplexity(monkeypatch):
    monkeypatch.setattr(mn, "yahoo_news", lambda t: [])
    monkeypatch.setattr(mn, "_fetch_rss", lambda *a, **k: [
        {"title": "Shared Story", "providerPublishTime": 10},
    ])
    seen = {}

    def fake_pplx(ticker, company=""):
        seen["company"] = company
        return [
            {"title": "shared story", "providerPublishTime": 20},  # dup of the RSS item
            {"title": "Perplexity Exclusive", "providerPublishTime": 30},
        ]

    monkeypatch.setattr(mn, "_fetch_perplexity", fake_pplx)
    out = mn.fetch_news("AAPL", "Apple Inc.")
    titles = [i["title"].lower() for i in out]
    assert seen["company"] == "Apple Inc."
    assert titles[0] == "perplexity exclusive"
    assert titles.count("shared story") == 1


def test_fetch_news_with_every_source_empty(monkeypatch):
    monkeypatch.setattr(mn, "yahoo_news", lambda t: [])
    monkeypatch.setattr(mn, "_fetch_rss", lambda *a, **k: [])
    monkeypatch.setattr(mn, "_fetch_perplexity", lambda *a, **k: [])
    assert mn.fetch_news("AAPL") == []


# ── format_news_block / build_prompt ─────────────────────────────────────────

def test_format_news_block_empty():
    assert "無可用新聞" in mn.format_news_block([])


def test_format_news_block_renders_items():
    block = mn.format_news_block([
        {"title": "Headline A", "publisher": "Reuters",
         "providerPublishTime": 1704067200, "link": "http://x", "summary": "sum"},
    ])
    assert "Headline A" in block
    assert "Reuters" in block
    assert "http://x" in block


def test_build_prompt_contains_ticker_and_sections():
    prompt = mn.build_prompt("AAPL", {"name": "Apple Inc", "sector": "Tech"}, "NEWSBLOCK")
    assert "AAPL" in prompt
    assert "Apple Inc" in prompt
    assert "NEWSBLOCK" in prompt
    assert "市場新聞分析報告" in prompt


# ── generate_report (provider dispatch + output) ─────────────────────────────

def test_generate_report_writes_file(monkeypatch, tmp_path):
    monkeypatch.setattr(mn.yf, "Ticker", lambda t: types.SimpleNamespace())
    monkeypatch.setattr(mn, "fetch_ticker_info", lambda t, obj=None: {"name": "Apple"})
    monkeypatch.setattr(mn, "fetch_news", lambda t, company="": [{"title": "x"}])
    called = {}

    def fake_openai(prompt, model, max_tokens):
        called["provider"] = "openai"
        return "report body"

    monkeypatch.setattr(mn, "call_openai", fake_openai)
    mn.generate_report("AAPL", "openai", "gpt-4o", 12000, tmp_path)

    files = list(tmp_path.glob("*.md"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert "type: market-news" in text
    assert "provider: openai" in text
    assert "report body" in text
    assert called["provider"] == "openai"
