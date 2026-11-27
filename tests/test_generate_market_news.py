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


# ── _fetch_site ────────────────────────────────────────────────────────

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
    items = mn._fetch_site("Perplexity", "perplexity.ai", "TSLA", "Tesla, Inc.")
    assert [i["title"] for i in items] == [
        "Tesla Executive Says Launching Cybercabs In Dallas",
        "This Week in TSLA: Roadster Debut",
    ]
    assert all(i["publisher"] == "Perplexity" for i in items)


def test_fetch_perplexity_ticker_only_without_company(monkeypatch):
    monkeypatch.setattr(mn, "urlopen", lambda *a, **k: _FakeResp(PPLX_XML))
    assert [i["title"] for i in mn._fetch_site("Perplexity", "perplexity.ai", "TSLA")] == ["This Week in TSLA: Roadster Debut"]


def test_fetch_site_fails_soft(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("down")

    monkeypatch.setattr(mn, "urlopen", boom)
    assert mn._fetch_site("X", "x.com", "TSLA", "Tesla, Inc.") == []


X_XML = b"""<?xml version="1.0"?>
<rss><channel>
  <item><title>$TSLA - TESLA TO INVEST 3 BILLION EUROS IN GRUENHEIDE - X</title></item>
  <item><title>Tech stocks in pre-market: $DELL -7.7% $ARM -6.2% - X</title></item>
  <item><title>Tesla Robotaxi expands to Austin airport - X</title></item>
  <item><title>Hold TSLA, not ANT: a bare ticker is not a cashtag - X</title></item>
</channel></rss>"""


def test_fetch_site_reads_x_through_google_news(monkeypatch):
    urls = []

    def fake_urlopen(req, **k):
        urls.append(req.full_url)
        return _FakeResp(X_XML)

    monkeypatch.setattr(mn, "urlopen", fake_urlopen)
    items = mn._fetch_site("X", "x.com", "TSLA", "Tesla, Inc.", r"\$")
    assert urls == ["https://news.google.com/rss/search?q=TSLA+site:x.com+when:7d&hl=en-US&gl=US&ceid=US:en"]
    assert [i["title"] for i in items] == [
        "$TSLA - TESLA TO INVEST 3 BILLION EUROS IN GRUENHEIDE",
        "Tesla Robotaxi expands to Austin airport",
    ]
    assert all(i["publisher"] == "X" for i in items)


def test_x_needs_the_cashtag_when_the_company_name_is_absent(monkeypatch):
    monkeypatch.setattr(mn, "urlopen", lambda *a, **k: _FakeResp(X_XML))
    titles = [i["title"] for i in mn._fetch_site("X", "x.com", "TSLA", "", r"\$")]
    assert titles == ["$TSLA - TESLA TO INVEST 3 BILLION EUROS IN GRUENHEIDE"]


@pytest.mark.parametrize("site, prefix, xml, title", [
    ("x.com", r"\$", b"""<rss><channel>
  <item><title>2,500 ANT Believers Index blind boxes - X</title></item>
  <item><title>$ANT falls below IPO price - X</title></item>
</channel></rss>""", "$ANT falls below IPO price"),
    ("perplexity.ai", "", b"""<rss><channel>
  <item><title>Why ant colonies scale - Perplexity</title></item>
  <item><title>ANT closes below IPO price - Perplexity</title></item>
</channel></rss>""", "ANT closes below IPO price"),
])
def test_ticker_fallback_name_does_not_bypass_ticker_rules(monkeypatch, site, prefix, xml, title):
    """fetch_ticker_info() returns {"name": ticker} when Yahoo has no name (NBIS
    has no longName). That name must not re-admit bare or lowercase tickers."""
    monkeypatch.setattr(mn, "urlopen", lambda *a, **k: _FakeResp(xml))
    name = "X" if site == "x.com" else "Perplexity"
    assert [i["title"] for i in mn._fetch_site(name, site, "ANT", "ANT", prefix)] == [title]


def test_short_name_equal_to_ticker_still_matches(monkeypatch):
    """Only the fallback (name == ticker) is skipped. "Arm Holdings plc"
    shortens to "Arm", which is a real company name for ARM."""
    xml = b"""<rss><channel>
  <item><title>Arm announces new chips - X</title></item>
</channel></rss>"""
    monkeypatch.setattr(mn, "urlopen", lambda *a, **k: _FakeResp(xml))
    titles = [i["title"] for i in mn._fetch_site("X", "x.com", "ARM", "Arm Holdings plc", r"\$")]
    assert titles == ["Arm announces new chips"]


def test_prompt_tells_the_model_x_posts_are_not_news():
    prompt = mn.build_prompt("TSLA", {}, "")
    assert "「X」的條目是社群貼文" in prompt
    assert "必須在同一句註明「據 X 貼文」" in prompt


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

    def fake_site(name, site, ticker, company="", ticker_prefix=""):
        seen[name] = (site, company)
        if name != "Perplexity":
            return []
        return [
            {"title": "shared story", "providerPublishTime": 20},  # dup of the RSS item
            {"title": "Perplexity Exclusive", "providerPublishTime": 30},
        ]

    monkeypatch.setattr(mn, "_fetch_site", fake_site)
    out = mn.fetch_news("AAPL", "Apple Inc.")
    titles = [i["title"].lower() for i in out]
    assert seen == {"Perplexity": ("perplexity.ai", "Apple Inc."), "X": ("x.com", "Apple Inc.")}
    assert titles[0] == "perplexity exclusive"
    assert titles.count("shared story") == 1


def test_fetch_news_with_every_source_empty(monkeypatch):
    monkeypatch.setattr(mn, "yahoo_news", lambda t: [])
    monkeypatch.setattr(mn, "_fetch_rss", lambda *a, **k: [])
    monkeypatch.setattr(mn, "_fetch_site", lambda *a, **k: [])
    assert mn.fetch_news("AAPL") == []


@pytest.mark.parametrize("x_behaviour", ["down", "empty", "raises"])
def test_report_still_builds_without_x(monkeypatch, x_behaviour):
    """X unreachable, X with nothing on the stock, or a bug in the X fetcher:
    the other sources still reach the prompt and the report is not aborted."""
    real_urlopen = mn.urlopen

    def fake_urlopen(req, **k):
        if "site:x.com" in req.full_url:
            if x_behaviour == "down":
                raise TimeoutError("x.com unreachable")
            return _FakeResp(b'<?xml version="1.0"?><rss><channel></channel></rss>')
        return _FakeResp(RSS_XML)

    monkeypatch.setattr(mn, "yahoo_news", lambda t: [])
    monkeypatch.setattr(mn, "urlopen", fake_urlopen)
    if x_behaviour == "raises":
        real_site = mn._fetch_site
        def buggy(name, *a, **k):
            if name == "X":
                raise ValueError("unexpected")
            return real_site(name, *a, **k)
        monkeypatch.setattr(mn, "_fetch_site", buggy)

    items = mn.fetch_news("AAPL", "Apple Inc.")
    assert items and not any(i["publisher"] == "X" for i in items)
    block = mn.format_news_block(items)
    assert "無可用新聞" not in block
    assert "AAPL" in mn.build_prompt("AAPL", {"name": "Apple Inc."}, block)


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


def test_fetch_ticker_info_null_short_name_falls_back_to_ticker():
    # Yahoo can send an explicit null shortName with no longName; a None name
    # would reach _short_name() and abort the whole news fetch.
    obj = types.SimpleNamespace(info={"longName": None, "shortName": None})
    assert mn.fetch_ticker_info("ONDS", obj)["name"] == "ONDS"


def test_gemini_cap_covers_the_workflow_budget():
    """At 8000 the cap cut ~4% of reports off mid-line (thinking tokens share
    the budget), while the workflow asked for 20000. Keep them in step."""
    import re
    from pathlib import Path

    wf = (Path(__file__).resolve().parents[1] / ".github" / "workflows"
          / "daily_market_news.yml").read_text()
    workflow_budget = int(re.search(r'DEFAULT_MAX_TOKENS: "(\d+)"', wf).group(1))
    assert mn._GEMINI_MAX_TOKENS == workflow_budget == mn.DEFAULT_TOKENS == 20000


# ── select_news / price date / prompt rules (2026-11-27 QA findings) ─────────

from datetime import datetime as _dt, timezone as _tz

_NOW = _dt(2026, 11, 27, 12, tzinfo=_tz.utc)
_RECENT = int(_dt(2026, 11, 25, tzinfo=_tz.utc).timestamp())
_OLD = int(_dt(2017, 5, 9, tzinfo=_tz.utc).timestamp())


def _item(title, publisher="Google News", ts=_RECENT, summary=""):
    return {"title": title, "publisher": publisher, "providerPublishTime": ts,
            "summary": summary}


def test_select_news_drops_items_older_than_the_window_or_undated():
    items = [_item("AMD rallies"), _item("AMD in 2017", ts=_OLD), _item("AMD undated", ts=0)]
    assert [i["title"] for i in mn.select_news(items, "AMD", "Advanced Micro Devices, Inc.", _NOW)] \
        == ["AMD rallies"]


@pytest.mark.parametrize("title", [
    "Flytech Technology Co., Ltd. (6206.TW) Stock Price, News, Quote & History - Yahoo Finance",
    "Flytech Technology Co., Ltd. (6206.TW) Company Profile & Facts - Yahoo Finance",
    "Flytech Technology Co., Ltd. (6206.TW)",
    "Sandisk Corporation (SNDK) Stock Options Chain, Prices, Historical Calls & Puts",
    "META_TITLE_QUOTE - Yahoo Finance",
])
def test_select_news_drops_quote_and_profile_pages(title):
    assert mn.select_news([_item(title, publisher="Yahoo")], "6206.TW", "Flytech", _NOW) == []


def test_keyword_feed_items_must_name_the_company():
    items = [
        _item("Domino's Pizza: Consumer Weakness Is The Opportunity", "Seeking Alpha"),
        _item("盤中速報 - 南寶(4766)大漲7.1%", "Bing News"),
        _item("Nan Pao 2026-11-20 Earnings Call", "Google News"),
        _item("Resin maker beats", "Google News", summary="Nan Pao Resins reported…"),
    ]
    kept = mn.select_news(items, "4766.TW", "Nan Pao Resins Chemical Co., Ltd.", _NOW)
    assert [i["title"] for i in kept] == [i["title"] for i in items[1:]]


def test_a_tw_code_does_not_match_inside_a_longer_number():
    items = [_item("Index closes at 147661", "Google News")]
    assert mn.select_news(items, "4766.TW", "", _NOW) == []


def test_yahoo_search_items_are_not_held_to_the_name_rule():
    """Yahoo's search is per symbol; sector stories it returns stay."""
    items = [_item("Cerebras Expands AI Inference Reach", publisher="Zacks")]
    assert len(mn.select_news(items, "AMD", "Advanced Micro Devices, Inc.", _NOW)) == 1


def test_analyst_upside_is_computed_in_python():
    assert mn.analyst_upside({"current_price": 406.03, "target_mean": 662}) == "+63.0%"
    assert mn.analyst_upside({"current_price": "N/A", "target_mean": 662}) is None
    assert mn.analyst_upside({"current_price": 406.03}) is None


def test_prompt_says_the_market_was_closed_on_a_holiday(monkeypatch):
    class _D(mn.date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 26)
    monkeypatch.setattr(mn, "date", _D)
    prompt = mn.build_prompt("SOXX", {"name": "iShares", "current_price": 127.98,
                                      "price_date": "2026-11-25"}, "N")
    assert "127.98 USD（2026-11-25 收盤）" in prompt
    assert "2026-11-26 沒有已完成的交易日收盤" in prompt


def test_prompt_on_a_trading_day_has_no_closed_market_line(monkeypatch):
    class _D(mn.date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 25)
    monkeypatch.setattr(mn, "date", _D)
    prompt = mn.build_prompt("SOXX", {"current_price": 1, "price_date": "2026-11-25"}, "N")
    assert "沒有已完成的交易日收盤" not in prompt


def test_prompt_carries_the_profile_target_and_derivation_rules():
    prompt = mn.build_prompt("AMD", {"name": "AMD", "current_price": 406.03,
                                     "price_date": "2026-11-25", "target_mean": 662,
                                     "analyst_count": 40,
                                     "business_summary": "Advanced Micro Devices operates…"},
                             "N")
    assert "Advanced Micro Devices operates…" in prompt
    assert "+63.0%（程式計算）" in prompt
    assert "不得單憑它推論估值支撐" in prompt
    assert "不要自行計算百分比" in prompt
    assert "區分事實與推論" in prompt


def test_news_times_are_shown_in_the_exchange_zone():
    ts = int(_dt(2026, 11, 26, 1, tzinfo=_tz.utc).timestamp())  # 11-25 20:00 in New York
    block = mn.format_news_block([_item("S&P ends lower", ts=ts)], "America/New_York")
    assert "2026-11-25 20:00 EST" in block


def test_fetch_ticker_info_dates_the_price_from_the_quote():
    stamp = int(_dt(2026, 11, 25, 21, 0, tzinfo=_tz.utc).timestamp())  # 16:00 New York
    obj = types.SimpleNamespace(info={
        "longName": "iShares Semiconductor ETF", "regularMarketPrice": 127.98,
        "regularMarketTime": stamp, "exchangeTimezoneName": "America/New_York",
        "longBusinessSummary": "x" * 2000})
    info = mn.fetch_ticker_info("SOXX", obj)
    assert (info["current_price"], info["price_date"]) == (127.98, "2026-11-25")
    assert len(info["business_summary"]) == mn.BUSINESS_SUMMARY_CHARS


def test_report_front_matter_records_the_price_and_its_date(monkeypatch, tmp_path):
    monkeypatch.setattr(mn, "fetch_ticker_info", lambda t, obj=None: {
        "name": "Apple", "current_price": 200.5, "price_date": "2026-11-25"})
    monkeypatch.setattr(mn, "fetch_news", lambda t, company="": [])
    monkeypatch.setattr(mn, "call_openai", lambda p, m, t: "body")
    mn.generate_report("AAPL", "openai", "gpt-4o", 100, tmp_path)
    text = next(tmp_path.glob("*.md")).read_text(encoding="utf-8")
    assert "price: 200.5\nprice_date: 2026-11-25\n" in text


def test_generate_report_asks_yahoo_for_the_tw_symbol(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(mn, "fetch_ticker_info", lambda t, obj=None: seen.append(t) or {"name": t})
    monkeypatch.setattr(mn, "fetch_news", lambda t, company="": [])
    monkeypatch.setattr(mn, "call_openai", lambda p, m, t: "body")
    mn.generate_report("0050", "openai", "gpt-4o", 100, tmp_path)
    assert seen == ["0050.TW"]


def test_company_name_matches_case_sensitively():
    """grab's report filled up with "40-yard grab" and "money grab" posts."""
    items = [_item("Malcolm Simmons with a 40-yard grab!"),
             _item("Carpool Pilot Could Matter For Grab Stock")]
    kept = mn.select_news(items, "GRAB", "Grab Holdings Limited", _NOW)
    assert [i["title"] for i in kept] == ["Carpool Pilot Could Matter For Grab Stock"]


def test_mid_session_price_falls_back_to_the_last_close():
    import pandas as pd
    hist = pd.DataFrame({"Close": [91.0, 92.6]},
                        index=pd.DatetimeIndex(["2026-11-25", "2026-11-26"]))
    obj = types.SimpleNamespace(
        info={"longName": "Yuanta", "regularMarketPrice": 92.65,
              "regularMarketTime": int(_dt(2026, 11, 27, 2, 20, tzinfo=_tz.utc).timestamp()),
              "exchangeTimezoneName": "Asia/Taipei"},
        history=lambda period: hist)
    info = mn.fetch_ticker_info("0050.TW", obj)
    assert (info["current_price"], info["price_date"]) == (92.6, "2026-11-26")


def test_target_is_rounded_to_price_precision():
    prompt = mn.build_prompt("AMD", {"current_price": 406.03, "price_date": "2026-11-25",
                                     "target_mean": 649.8857}, "N")
    assert "649.89 USD" in prompt and "649.8857" not in prompt


def test_a_headline_ending_in_its_ticker_is_news():
    """Greptile on #118: the old rule dropped any title ending in "(TICKER)"."""
    items = [_item("AMD Announces Quarterly Results (AMD)", publisher="Yahoo"),
             _item("Advanced Micro Devices, Inc. (AMD)", publisher="Yahoo")]
    kept = mn.select_news(items, "AMD", "Advanced Micro Devices, Inc.", _NOW)
    assert [i["title"] for i in kept] == ["AMD Announces Quarterly Results (AMD)"]


def _quote(state, hour, minute):
    stamp = int(_dt(2026, 11, 27, hour, minute, tzinfo=_tz.utc).timestamp())
    return {"marketState": state, "regularMarketPrice": 130.0, "regularMarketTime": stamp,
            "exchangeTimezoneName": "America/New_York"}


def test_an_early_close_is_a_close():
    """The Friday after Thanksgiving closes at 13:00 New York (18:00 UTC)."""
    assert mn.session_close(_quote("POST", 18, 0)) == (130.0, "2026-11-27")


def test_a_trading_session_is_not_a_close():
    assert mn.session_close(_quote("REGULAR", 16, 0)) == (None, None)


def test_without_market_state_the_clock_rule_applies():
    q = _quote("", 16, 0)  # 11:00 New York
    assert mn.session_close(q) == (None, None)


def test_no_news_gets_the_short_prompt_and_the_system_messages_allow_it():
    prompt = mn.build_prompt("6206.TW", {"name": "Flytech", "business_summary": "POS maker"},
                             "（目前無可用新聞資料）", has_news=False)
    assert "300 字以內" in prompt and "POS maker" in prompt
    assert "400–600" not in prompt and "關鍵洞察" not in prompt
    for msg in (mn._OPENAI_SYSTEM_MESSAGE, mn._GEMINI_SYSTEM_MESSAGE):
        assert "沒有新聞時" in msg


def test_generate_report_uses_the_short_prompt_when_selection_leaves_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(mn, "fetch_ticker_info", lambda t, obj=None: {"name": "Flytech"})
    monkeypatch.setattr(mn, "fetch_news", lambda t, company="": [_item("old", ts=_OLD)])
    sent = {}
    monkeypatch.setattr(mn, "call_openai", lambda p, m, t: sent.setdefault("p", p) and "body")
    mn.generate_report("6206.TW", "openai", "gpt-4o", 100, tmp_path)
    assert "300 字以內" in sent["p"]
