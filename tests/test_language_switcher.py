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


# ── the selected language is marked as such ──────────────────────────────────

def _current(url: str, *, src_uri: str, is_index: bool) -> "list[str]":
    """hreflang of every switcher entry rendered with aria-current."""
    env = Environment(loader=ChoiceLoader([
        FileSystemLoader(str(PARTIALS.parent)),
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
    return [line.split('hreflang="')[1].split('"')[0]
            for line in html.splitlines() if "aria-current" in line]


def test_an_english_page_marks_english_as_selected():
    assert _current("reports/avav/", src_uri="reports/avav/index.md",
                    is_index=True) == ["en"]


def test_a_zh_page_marks_chinese_as_selected():
    assert _current("zh/reports/avav/", src_uri="zh/reports/avav/index.md",
                    is_index=True) == ["zh-TW"]


# ── the <head> copy of the targets, read after instant navigation ────────────
#
# Material's instant navigation never re-renders the header, so the switcher
# above only holds for the first page loaded; after an in-site click it still
# pointed at that page — usually home. main.html therefore publishes the same
# targets in <head> (which *is* synced) and lang-switch.js copies them onto the
# menu. These pin that the two copies come from one rule and cannot drift.

MAIN = PARTIALS.parent / "main.html"

PAGES = [
    ("", "index.md", True),
    ("zh/", "zh/index.md", True),
    ("reports/avav/", "reports/avav/index.md", True),
    ("zh/reports/avav/", "zh/reports/avav/index.md", True),
    ("data/2330.tw/", "data/2330.tw/index.md", True),
    ("scripts/", "scripts.md", False),
    ("ARCHITECTURE/", "ARCHITECTURE.md", False),
    ("reports/avav/fundamental_analysis_2026-09-18_gemini/",
     "reports/avav/fundamental_analysis_2026-09-18_gemini.md", False),
    ("market_news/nvda/market_news_2026-09-18_openai/",
     "market_news/nvda/market_news_2026-09-18_openai.md", False),
]


def _head_metas(url: str, *, src_uri: str, is_index: bool) -> dict:
    """Render main.html's alternate <meta> block; return {name/lang: content}."""
    src = MAIN.read_text(encoding="utf-8")
    start = src.index("{% if page %}\n    {% from \"partials/alternate-paths.html\"")
    block = src[start:src.index("{% endif %}", start) + len("{% endif %}")]
    env = Environment(loader=FileSystemLoader(str(PARTIALS.parent)))
    page = SimpleNamespace(url=url, is_index=is_index,
                           file=SimpleNamespace(src_uri=src_uri))
    html = env.from_string(block).render(page=page)
    out = {}
    for line in html.splitlines():
        if "<meta" not in line:
            continue
        content = line.split('content="')[1].split('"')[0]
        key = (line.split('data-lang="')[1].split('"')[0]
               if "data-lang" in line else line.split('name="')[1].split('"')[0])
        out[key] = content
    return out


@pytest.mark.parametrize("url,src_uri,is_index", PAGES)
def test_head_targets_match_the_rendered_switcher(url, src_uri, is_index):
    """Resolved from the site root, each <meta> path is where the server-side
    switcher sends the reader from that page."""
    metas = _head_metas(url, src_uri=src_uri, is_index=is_index)
    en, zh = _targets(url, src_uri=src_uri, is_index=is_index)
    here = posixpath.join("/site", url or ".")
    for rel, path in ((en, metas["en"]), (zh, metas["zh"])):
        assert (posixpath.normpath(posixpath.join(here, rel))
                == posixpath.normpath(posixpath.join("/site", path or ".")))


def test_head_targets_for_a_report_stay_on_its_ticker():
    metas = _head_metas(
        "reports/avav/fundamental_analysis_2026-09-18_gemini/",
        src_uri="reports/avav/fundamental_analysis_2026-09-18_gemini.md",
        is_index=False)
    assert metas == {"en": "reports/avav/", "zh": "zh/reports/avav/",
                     "fp:lang": "en"}


def test_head_targets_for_a_zh_page_name_its_tree():
    metas = _head_metas("zh/data/2330.tw/", src_uri="zh/data/2330.tw/index.md",
                        is_index=True)
    assert metas == {"en": "data/2330.tw/", "zh": "zh/data/2330.tw/",
                     "fp:lang": "zh"}


def test_lang_switch_script_is_loaded():
    """Without it the <head> targets are inert and the bug is back."""
    mkdocs = (PARTIALS.parents[2] / "mkdocs.yml").read_text(encoding="utf-8")
    assert "javascripts/lang-switch.js" in mkdocs
