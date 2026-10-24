# Site Build

How `scripts/build_docs.py` turns `ai_gen_report/` and `data/` into the MkDocs
site, and the conventions its pages follow. `docs/` is mostly generated (see
`.gitignore`). Edit the sources in `ai_gen_report/`, `data/` and `scripts/`, not
the generated output.

```bash
uv pip install "mkdocs-material==9.5.*" mkdocs-awesome-pages-plugin minify-html
uv run python scripts/build_docs.py && uv run mkdocs serve
```

CI builds with `mkdocs build --strict` through the `build-site` composite action
(`.github/actions/build-site/`). `deploy.yml` publishes once a night at 04:00
UTC, after the generation window.

---

## What gets published

| Source | Published at | Notes |
|--------|--------------|-------|
| `ai_gen_report/{fundamental,technical,stock}/<ticker>/` | `docs/reports/<ticker>/` | The three trees are merged per ticker |
| `ai_gen_report/market_news/<ticker>/` | `docs/market_news/<ticker>/` | |
| `data/prices/` + `data/fundamentals/` | `docs/data/` (**Market Data**) | One tabbed page per ticker |
| `notebook_llm/`, `10-k/`, `10-q/`, `13-f/` | `docs/notebooks/`, `docs/sec/` | Index pages only; PDFs link to GitHub raw |

Every index page is also written under `docs/zh/`. Dated report and news pages
are English-tree only (see [Bilingual site](#bilingual-site)).

**Retention.** Only reports from the last `REPORT_RETENTION_DAYS` days (default
120) are published. Separately, `prune_old_reports.yml` deletes files older than
90 days from `ai_gen_report/` on the 1st of each month, using
`scripts/maintain_ai_gen_report.py prune --before YYYY-MM-DD`. The same script's
`reorg` command re-splits reports into the three trees.

---

## Market Data (`docs/data/`)

An overview table plus one tabbed page per ticker. Python computes every series
(`data/price_analytics.py`, `data/fundamental_analytics.py`,
`data/intrinsic_value.py`). `docs/javascripts/price-charts.js` only draws them,
which keeps the site's numbers testable in pytest. See
[`PRICE_STORE_DESIGN.md`](PRICE_STORE_DESIGN.md) §12–§13.

| Tab | Contents |
|-----|----------|
| Overview | Candles, returns, TTM figures |
| Price | Drawdown, rolling volatility, return distribution, monthly heatmap |
| Financials | **Annual overview** (GuruFocus-style grouped bars incl. ROIC vs. WACC), statements, margins, returns on capital, **Financial strength** scorecard |
| Valuation | Each multiple's **range vs. its own history**, then P/E, P/S, P/B, EV multiples, P/E bands |
| Intrinsic value | DCF, reverse DCF, sensitivity grid, per-share growth table, WACC build-up |
| Data & glossary | Both CSVs, JSON payloads, term definitions |

- **Intrinsic value.** Every assumption is a named constant in
  `intrinsic_value.py` and is printed on the page. The views are static HTML/SVG
  from `build_docs.py` §6c with no `data-src`, so `price-charts.js` skips them.
- **Split adjustment.** Per-share figures are split-adjusted on read
  (`fundamental_analytics.split_adjust`).
- **Chart cards** each carry a one-line explainer and captioned x/y axes. The
  valuation multiples and rolling volatility also draw a dashed line at the
  series' own historical average (`price_analytics.series_average`, computed in
  Python).
- **Downloads.** The two CSV links carry an explicit `download` attribute. A
  browser renders `.json` in place, but it navigates away from `text/csv` and
  saves it silently, which looks like a dead link. The JSON payloads stay plain
  links so they still open in place.
- **Legacy URLs.** `docs/prices/<ticker>/` and `docs/fundamentals/<ticker>/` are
  redirect stubs (`build_legacy_redirects()`), hidden from the nav with `.pages`
  `hide: true`.

---

## Page anatomy

- **Section indexes** (`docs/reports/`, `docs/market_news/`): a stats strip
  (`hub_stats_block`), a one-line disclaimer, a filter box and a **card grid**
  (`hub_card`), all static HTML. `docs/javascripts/hub.js` only toggles `hidden`
  on cards. Each card's badge opens the newest report of that type.
- **Ticker index** (`docs/reports/<ticker>/`) opens with a **hero**
  (`ticker_hero_block()`) before the candlestick chart:
  - identity chips: ticker, sector, report count per type
  - KPI tiles read from `price_analytics.summary()`
  - a 52-week rail with the last close marked on it

  The bear/base/bull spread under **Price Target** is drawn the same way
  (`scenario_rail()`). Both are static HTML with every position computed in
  Python as a percentage, so they render with JS off and always agree with the
  Market Data page. The company flag sits in the hero, not the h1: the h1's
  clipped gradient paints twemoji black on the dark scheme.
- **Dated report and news pages** open with a meta bar (`report_meta_block`)
  instead of the raw front-matter table. It has a ticker back-link, an
  older/newer stepper *within the same report type*, and type / date / model /
  language chips. It is raw HTML, so hrefs are written against the page's
  directory URL (`../`, `../<stem>/`); MkDocs rewrites Markdown links, never raw
  ones. `copy_file(..., meta_block=...)` swaps it in. Without a meta block the
  table is still emitted, and tests pin both.
- **Inner pages** get a linked breadcrumb trail from `overrides/main.html`
  (`.crumbs`; Material's own `navigation.path` is Insiders-only) and a
  reading-progress bar from `hub.js`.

---

## Landing page

The landing page is data-driven. `write_hub_payload()` derives `docs/hub.json`
(gitignored) from the price store and the published report set.
`overrides/home.html` hydrates its slots from that file, and `home_zh.html`
inherits the script. Slots that carry figures stay `hidden` until the payload
arrives, so a failed fetch shows nothing rather than stale numbers.

| Section | Driven by |
|---------|-----------|
| **Terminal hero** — a macOS Terminal window running the real CLI (`python scripts/generate_analysis.py <TICKER> --analysis-type …`) | Re-runs for the featured report and prints its model, date, figures and link. Without data the static session stays |
| **Market pulse** — a beeswarm of every priced ticker on a diverging return axis, with 1D / 1M / YTD / 1Y tabs | Tape entries carry `chg`, `chg_1m`, `ytd`, `chg_1y`. `hub_payload()["breadth"]` (`_breadth()`) supplies up/down/flat counts, best/worst, the axis half-width `span`, and `scale` |
| **Analysis wheel** — the pipeline's twelve types | `hub_payload()["types"]` (`_type_counts()`), from `ANALYSIS_TYPES`, counting `.md` and `.html` reports in the retention window |
| Headline counts, hero card, six newest reports | `hub_payload()` |

- The pulse switches `scale` to `symlog` when the largest move exceeds 3× the
  80th-percentile move. Otherwise one +400% YTD would pin every other bubble to
  the midline. JS only maps values to pixels and dodges overlaps.
- In the wheel, types with reports are drawn solid with their counts; the rest
  are outlines marked "in pipeline". Names, families and descriptions live in the
  `lenses` / `fams` COPY entries in `home.html`. Add one there when a type is
  added to `ANALYSIS_TYPES`.
- Landing-page styles and script live inside `home.html` itself.
- `home.html` is one template for both languages. `home_zh.html` only overrides
  `{% block home_lang %}`, and the strings live in its `COPY` table.

---

## Styling

- **Visual language** follows finlab.finance/en/blog, an editorial "research
  magazine" look:
  - light paper scheme by default (`mkdocs.yml` palette order, no `media:` keys)
  - ink `#111827` on `#fbfcfe`
  - light Space Grotesk headings over a DM Sans body (Google Fonts, loaded in
    `overrides/main.html`)
  - hairline borders, 1rem cards, pill controls with an ink-filled active state
- **Colour tokens.** All colours are `--fp-*` tokens defined per scheme at the
  top of `docs/stylesheets/extra.css`. Add a token there rather than hardcoding a
  hex in a component.
- **Stylesheets:**

  | File | Covers |
  |------|--------|
  | `extra.css` | Tokens and theme-wide rules |
  | `kline.css`, `prices.css` | Candlestick widget, Market Data pages |
  | `ticker.css` | Ticker hero, KPI tiles, scenario rail |
  | `hub.css` | Section index cards and stats, meta bar, breadcrumbs, reading-progress bar |
  | `report.css` | Report pages: headings, body, lists, quotes, code, admonitions, tables. Loaded last in `extra_css` |

  Don't reintroduce article typography into `extra.css`. The old scattered rules,
  including a mobile block that set body text to `1rem` (20px), made reports read
  oversized.
- **Font size.** Material's root font-size is 20px, so size in rem accordingly.
- **Tables.** `responsive-tables.js` tags figure columns `.is-num` (≥60% of a
  column's cells read as numbers, so they are right-aligned) and sign-led cells
  `.is-pos` / `.is-neg`, by **text inspection only**. It never computes a value.
  Material left-aligns cells via `[dir=ltr] … td:not([align])`, hence the
  `!important` on `.is-num`.

---

## Release, icons and meta

- **Version** is `[project].version` in `pyproject.toml`. Cut a release with the
  manual **Release** workflow:

  ```bash
  gh workflow run release.yml -f bump=patch       # or minor | major | current
  gh workflow run release.yml -f version=X.Y.Z
  gh workflow run release.yml -f bump=patch -f dry_run=true   # preview
  ```

  It runs the tests, bumps `pyproject.toml` and `uv.lock` via
  `scripts/release_version.py`, commits to main, creates GitHub Release `vX.Y.Z`
  with generated notes and dispatches `deploy.yml`.
- `scripts/mkdocs_release_hook.py` publishes the version with the commit SHA as
  `config.extra.release`, shown as a header pill and in the footer. Never
  hardcode a version in a template.
- The favicon (SVG + PNG fallbacks), apple-touch-icon and `og:image` share card
  live in `docs/assets/`. Open Graph, Twitter and theme-color meta are emitted in
  `overrides/main.html` `extrahead`, using each page's `description` front
  matter.

---

## Bilingual site

The site is **one** MkDocs build. `docs/` is English and `docs/zh/` is
Traditional Chinese, so `theme.language` is `en` everywhere and nothing about the
ZH tree is automatic. It needs no separate deploy: `build_docs.py` writes both
trees and `mkdocs build --strict` ships them together.

- **UI copy** lives in `LANG_TEXT` in `build_docs.py` (`t(lang, key)`), and both
  halves must carry every key. Chart labels drawn by JS are localised separately
  in `docs/javascripts/price-charts.js` and `kline-chart.js`, which detect `/zh/`
  from the URL.
- **Nav.** `build_nav_pages()` lists `- zh` on the **EN** root `.pages`. Without
  it awesome-pages drops `docs/zh/` from the nav entirely (a `nav:` with no `...`
  is exhaustive), and every ZH page renders the *English* tab row, linking back
  into the English tree.
- **Theme overrides.** Three partials in `docs/overrides/partials/` make
  navigation language-aware. They are written against the
  `mkdocs-material==9.5.*` pin in `.github/actions/build-site/action.yml`.
  - `tabs.html` / `nav.html`: on a ZH page, render the `zh` subtree as the tab
    row and sidebar, so both trees render identically. The subtree is found by
    URL prefix, not by title, so renaming it in `LANG_TEXT` cannot break the
    lookup.
  - `alternate.html`: points the language switcher at *the same page* in the
    other tree. The ZH tree mirrors **index pages only**, so a dated leaf with no
    twin falls back **one directory up**, to its ticker or section index, which
    always has one. It used to fall back to the site root, which made 文A on
    `/reports/avav/<report>/` look like it jumped to the home page. A wrong guess
    here 404s. Two tests hold this:
    - `test_every_unmirrored_page_has_a_mirrored_parent` (`test_build_docs.py`)
      pins that every twin-less page sits directly inside a mirrored directory
    - `tests/test_language_switcher.py` renders the partial against MkDocs' own
      `url` filter

    The path rule itself lives in `alternate-paths.html` (macros). `main.html`
    uses it too, to publish each page's targets in `<head>` as
    `<meta name="fp:alternate">`. That second copy exists because
    `navigation.instant` syncs `<head>` on every in-site click but **never
    re-renders the header**, so the menu kept the first-loaded page's links and
    sent the reader to the other tree's home page.
    `docs/javascripts/lang-switch.js` copies the metas onto the menu after each
    navigation (pinned by `tests/test_lang_switch_js.py`), and the reader's
    current language is marked `aria-current`.
- **`docs/includes/`** is listed in `exclude_docs` in `mkdocs.yml`. It is a
  `pymdownx.snippets` source auto-appended to every page, not a page. When MkDocs
  published it anyway, it was the one directory on the site with no index for the
  switcher to fall back to.
