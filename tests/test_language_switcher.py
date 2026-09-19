"""The language switcher is a Jinja override, so it gets rendered like one.

`docs/overrides/partials/alternate.html` is the only piece of the bilingual site
with no Python to unit-test, and it is the piece that decides where the 文A
button in the header sends the reader. It used to send anyone on a dated report
page back to the site root; these tests pin the rule that replaced that, so the
next edit to the partial can't quietly restore it.

Rendered against a stand-in for Material's page/config objects rather than a
real MkDocs build: the template only reads `page.url`, `page.is_index`,
`page.file.src_uri` and `config.extra.alternate`, and MkDocs' `url` filter is
just "resolve this site-root-relative path from the current page".
"""

import posixpath
from pathlib import Path
from types import SimpleNamespace

import pytest
from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader

pytestmark = pytest.mark.unit

PARTIALS = Path(__file__).resolve().parents[1] / "docs" / "overrides" / "partials"

ALTERNATE = [
    {"name": "English", "link": "/finance_data/", "lang": "en"},
    {"name": "繁體中文", "link": "/finance_data/zh/", "lang": "zh-TW"},
]


def _url_filter(path: str, page_url: str) -> str:
    """mkdocs.utils.normalize_url + get_relative_url, transcribed.

    Transcribed rather than imported because the suite runs without mkdocs
    installed — and because the trailing-slash rule is exactly what these tests
    are checking, so it has to be the real one.
    """
    path = path or "."
    other = page_url or "."
    if other != ".":
        head, tail = posixpath.split(other)
        other = head if "." in tail else other
    rel = posixpath.relpath(path, other)
    return rel + "/" if path.endswith("/") else rel


def _render(url: str, *, src_uri: str, is_index: bool) -> dict:
    """Render alternate.html for one page; return {lang: href}."""
    env = Environment(loader=ChoiceLoader([
        FileSystemLoader(str(PARTIALS.parent)),
        # The icon include is a theme asset, not part of what we're testing.
        DictLoader({".icons/material/translate.svg": "<svg/>"}),
    ]))
    env.filters["url"] = lambda path: _url_filter(path, url)
    page = SimpleNamespace(url=url, is_index=is_index,
                           file=SimpleNamespace(src_uri=src_uri))
    html = env.get_template("partials/alternate.html").render(
        page=page,
        config=SimpleNamespace(
            theme={"icon": {"alternate": "material/translate"}},
            extra={"alternate": ALTERNATE}),
        lang=SimpleNamespace(t=lambda key: key),
    )
    hrefs = dict(zip(
        [a["lang"] for a in ALTERNATE],
        [line.split('href="')[1].split('"')[0]
         for line in html.splitlines() if 'href="' in line]))
    return hrefs


def _targets(*args, **kw) -> "tuple[str, str]":
    """(english_href, chinese_href), each normalised to a site-root path."""
    h = _render(*args, **kw)
    return h["en"], h["zh-TW"]


# ── an index page maps to its own counterpart ────────────────────────────────

def test_ticker_index_maps_to_the_same_ticker():
    en, zh = _targets("reports/avav/", src_uri="reports/avav/index.md",
                      is_index=True)
    assert en == "./"                           # reports/avav/ → itself
    assert zh == "../../zh/reports/avav/"


def test_market_data_index_maps_to_the_same_ticker():
    _, zh = _targets("data/2330.tw/", src_uri="data/2330.tw/index.md",
                     is_index=True)
    assert zh == "../../zh/data/2330.tw/"


def test_a_zh_page_maps_back_to_its_english_twin():
    en, zh = _targets("zh/reports/avav/", src_uri="zh/reports/avav/index.md",
                      is_index=True)
    assert en == "../../../reports/avav/"
    assert zh == "./"


def test_a_non_index_page_listed_as_mirrored_keeps_its_own_url():
    en, zh = _targets("scripts/", src_uri="scripts.md", is_index=False)
    assert en == "./"
    assert zh == "../zh/scripts/"


# ── a leaf with no counterpart falls back to its parent, not the site root ───

def test_dated_report_falls_back_to_its_own_ticker_index():
    """The bug this file exists for: 文A from a report used to land on the ZH
    home page, four clicks from the ticker the reader was reading."""
    url = "reports/avav/fundamental_analysis_2026-09-18_gemini/"
    en, zh = _targets(
        url, src_uri="reports/avav/fundamental_analysis_2026-09-18_gemini.md",
        is_index=False)
    assert en == "../"                          # up to reports/avav/
    assert zh == "../../../zh/reports/avav/"
    assert not zh.endswith("/zh/"), "must not bounce to the ZH site root"


def test_dated_market_news_falls_back_to_its_own_ticker_feed():
    url = "market_news/nvda/market_news_2026-09-18_openai/"
    _, zh = _targets(url,
                     src_uri="market_news/nvda/market_news_2026-09-18_openai.md",
                     is_index=False)
    assert zh == "../../../zh/market_news/nvda/"


def test_a_top_level_page_with_no_parent_falls_back_to_the_site_root():
    en, zh = _targets("ARCHITECTURE/", src_uri="ARCHITECTURE.md",
                      is_index=False)
    assert en == ".."
    assert zh == "../zh/"


def test_the_site_root_maps_to_the_other_tree_root():
    en, zh = _targets("", src_uri="index.md", is_index=True)
    assert en == "."
    assert zh == "zh/"


def test_a_page_less_template_keeps_the_configured_links():
    """404.html renders with page=None. There is no counterpart to compute, and
    letting the url filter resolve "" against base_url emits "/finance_data/."."""
    env = Environment(loader=ChoiceLoader([
        FileSystemLoader(str(PARTIALS.parent)),
        DictLoader({".icons/material/translate.svg": "<svg/>"}),
    ]))
    env.filters["url"] = lambda path: path          # absolute links pass through
    html = env.get_template("partials/alternate.html").render(
        page=None,
        config=SimpleNamespace(
            theme={"icon": {"alternate": "material/translate"}},
            extra={"alternate": ALTERNATE}),
        lang=SimpleNamespace(t=lambda key: key),
    )
    hrefs = [l.split('href="')[1].split('"')[0]
             for l in html.splitlines() if 'href="' in l]
    assert hrefs == ["/finance_data/", "/finance_data/zh/"]
