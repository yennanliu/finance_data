# Stock Summary Page — design & implementation plan

> Status: **proposal only** — nothing implemented. Survey + plan for adding a
> GuruFocus-style *Summary* page alongside the existing per-ticker report page
> (`https://yennj12.js.org/finance_data/reports/amzn/`).
>
> Companion to `docs/PRICE_STORE_DESIGN.md`, whose store→derive→render pattern
> this proposal deliberately copies.

---

## 1. What we have today

The AMZN page is produced by `build_reports()` (`scripts/build_docs.py:1215`).
Its whole content is:

| Block | Source |
|---|---|
| `# 🛒 Amazon.com Inc. (AMZN)` + sector line | `COMPANY_META` / `get_meta()` (`build_docs.py:577`) |
| Candlestick hero chart (30D/180D/360D) | `kline.json`, derived at build time from `data/prices/amzn.csv` (`kline_payload()`, `build_docs.py:666`) |
| Price-target & implied-return table | **Parsed out of the latest fundamental report's markdown** — `parse_scenario_targets()` (`build_docs.py:852`) hunts for a pipe table with a target column |
| "Latest Reports" cards | Newest `.md` per report type |
| "Available Reports" archive | Every dated report inside the 120-day retention window |

So the page is a **report directory listing with a chart on top**. There is no
valuation, no financial statement, no profitability, no ownership — the only
"fundamental" number on it (the price target) is scraped back out of LLM prose.

What the repo *does* already have that is reusable:

- **A committed data store pattern that works.** `data/prices/<key>.csv`, 38
  tickers, ten years of daily bars, refreshed by
  `.github/workflows/update_kline_data.yml` → `scripts/update_prices.py`, read
  at build time by a pure-stdlib module (`analysis/data/prices.py`), with
  derived statistics in a second pure-stdlib module
  (`analysis/data/price_analytics.py`) and a published section
  (`docs/prices/`) that has an index table, per-ticker pages, CSV/JSON/ZIP
  downloads and a machine-readable `index.json` manifest.
- **A chart widget contract.** `docs/javascripts/price-charts.js` renders any
  `<div class="pchart" data-src data-series data-kind data-title data-color
  data-unit>`; `kind` is currently `area | line | histogram`. All maths is done
  in Python at build time — the JS only draws (`PRICE_STORE_DESIGN.md` §12).
- **Fundamental fetchers, already written, currently thrown away.**
  `analysis/data/sources.py` has `fetch_data()` (yfinance `info`, statements,
  upgrades/downgrades, insider transactions, major/institutional holders),
  `fetch_finviz()` (the whole snapshot table: P/E, PEG, P/B, P/FCF, ROA/ROE/ROI,
  margins, Debt/Eq, current & quick ratio, short float, insider/institutional
  ownership, beta), `fetch_stockanalysis()` and `fetch_roic()` (10y+ history).
  Every one of these results is formatted into a text blob, handed to an LLM as
  context, and **discarded**. Nothing is persisted.
- Bilingual rendering (`t(lang, key)` with EN/ZH `STRINGS`), awesome-pages nav
  generation, incremental writes, and a sample-build mode for smoke tests.

**The gap is data persistence, not data access.** We already fetch most of what
a summary page needs; we throw it away after each LLM call.

---

## 2. What a GuruFocus summary page is made of

Modules on `gurufocus.com/stock/NVDA/summary`, scored for feasibility here:

| # | GF module | Fields | Feasible? |
|---|---|---|---|
| 1 | Quote header | price, change, market cap, enterprise value, volume, avg volume, 52w range, beta | ✅ have (prices store + yfinance/Finviz) |
| 2 | **GF Score** + 5 ranks (Financial Strength, Profitability, Growth, GF Value, Momentum) | 0–100 composite | ⚠️ proprietary — build our **own** scored the same shape, never call it GF Score |
| 3 | **GF Value** line + valuation verdict | intrinsic value line on the price chart | ⚠️ proprietary formula — substitute a transparent *historical-multiple fair-value band* |
| 4 | Warning / good signs | rule-fired flags | ✅ fully replicable — every GF sign is a rule over statements |
| 5 | Financial Strength | cash-to-debt, equity-to-asset, debt-to-equity, debt-to-EBITDA, interest coverage, Piotroski F, Altman Z, Beneish M, WACC vs ROIC | ✅ computable from statements |
| 6 | Profitability & Growth | gross/operating/net/FCF margin, ROE, ROA, ROIC, ROC (Greenblatt), 3y & 5y revenue/EBITDA/EPS/FCF growth | ✅ |
| 7 | Valuation ratios | PE, forward PE, PEG, PS, PB, P/FCF, EV/EBIT, EV/EBITDA, EV/Revenue, price-to-tangible-book, earnings yield (Greenblatt), FCF yield, Shiller PE | ✅ except Shiller PE (needs 10y inflation-adjusted EPS — defer) |
| 8 | Dividend & buyback | yield, forward yield, payout ratio, 3y dividend growth, buyback ratio, shareholder yield | ✅ |
| 9 | Historical financials charts | revenue / net income / FCF / EPS bars, annual + quarterly | ✅ (needs a new chart `kind`) |
| 10 | Industry percentile ranks ("higher than 87% of 1,003 companies in Semiconductors") | per-metric percentile | ⚠️ we cover 38 tickers, not an industry — either label it honestly ("vs. 38 covered tickers") or drop |
| 11 | Insider trades | Form 4 rows | ✅ yfinance `insider_transactions` (already fetched) |
| 12 | Guru trades / 13F | famous-investor positions | ❌ skip — `13-f/` holds only an `index.txt` today |
| 13 | Institutional ownership | % held, top holders | ✅ already fetched |
| 14 | Analyst estimates & targets | mean/high/low target, recommendation, EPS estimates | ✅ yfinance + Finviz — **plus** we already have LLM scenario targets, which GF does not |
| 15 | Peer comparison | side-by-side ratios | ✅ within our own universe (needs a peer map) |
| 16 | Business description | segments, employees | ✅ `longBusinessSummary` |
| 17 | News | headlines | ✅ already have `docs/market_news/` |
| 18 | Filings | 10-K/10-Q links | ✅ already have `docs/sec/` |

**Do not scrape GuruFocus.** Their ToS forbids it and their scores are
proprietary. Everything above is reachable from yfinance, Finviz (already
scraped), StockAnalysis/Roic (already scraped) and SEC.

---

## 3. The data layer — a second committed store

### 3.1 Why a store, not a build-time fetch

`build_docs.py` states its own constraint at the top (`build_docs.py:38`): it
imports only pure-stdlib modules so **the docs build stays offline and
dependency-light**. It runs on every deploy, in CI, twice (EN + ZH). Fetching
yfinance for 38 tickers inside it would make the build networked, slow,
rate-limit-flaky and non-reproducible. The price store already solved this
exact problem — mirror it.

Committing also buys: a diffable history of every ratio, reproducible builds,
and a free public dataset (the `prices/index.json` manifest already proves the
pattern).

### 3.2 Layout

```
data/fundamentals/<key>.json      # one file per ticker, key == price-store key
data/fundamentals/_universe.json  # optional: peer map + sector groupings
```

`<key>` is `prices.report_key(ticker)` — the same lowercase key the price store
uses (`amzn`, `2330.tw`, `0050`), so the two stores join for free.

JSON, not CSV: the shape is nested and irregular (statements + ratios +
holders). Written with **sorted keys, fixed float precision and a stable field
order** so an unchanged week produces a byte-identical file and git churn stays
near zero — the same determinism lesson as `_price_zip_bytes()`.

### 3.3 Schema (v1 sketch)

```jsonc
{
  "ticker": "AMZN",
  "key": "amzn",
  "kind": "equity",              // equity | financial | etf  ← gates which modules render
  "currency": "USD",
  "as_of": "2026-09-03",         // fetch date
  "sources": ["yfinance", "finviz"],

  "profile":   { "name", "sector", "industry", "employees", "exchange", "summary" },
  "quote":     { "price", "market_cap", "enterprise_value", "shares_out",
                 "float", "beta", "avg_volume_3m" },
  "valuation": { "pe_ttm", "pe_fwd", "peg", "ps", "pb", "p_tangible_book",
                 "p_fcf", "ev_ebitda", "ev_ebit", "ev_sales",
                 "earnings_yield", "fcf_yield" },
  "profitability": { "gross_margin", "operating_margin", "net_margin",
                     "fcf_margin", "roe", "roa", "roic", "roc_greenblatt" },
  "health":    { "cash", "total_debt", "cash_to_debt", "equity_to_asset",
                 "debt_to_equity", "debt_to_ebitda", "interest_coverage",
                 "current_ratio", "quick_ratio" },
  "dividend":  { "yield", "fwd_yield", "payout_ratio", "growth_3y",
                 "buyback_ratio", "shareholder_yield" },

  "annual":    [ { "fy": "2025", "revenue", "gross_profit", "operating_income",
                   "net_income", "eps_diluted", "ocf", "capex", "fcf",
                   "total_assets", "total_equity", "total_debt", "cash",
                   "shares_diluted", "dividends_paid", "buybacks" }, … ≤10 ],
  "quarterly": [ … same shape, ≤12 ],

  "estimates": { "eps_next_y", "revenue_next_y", "target_mean", "target_high",
                 "target_low", "analyst_count", "recommendation" },
  "ownership": { "insider_pct", "institution_pct",
                 "top_holders": [ { "name", "shares", "pct", "value" } ] },
  "insider_tx": [ { "date", "name", "type", "shares", "value" }, … ≤20 ]
}
```

Every leaf is nullable. A missing field renders as `—`, never as `0`.

Size: ~15–30 KB per ticker × 38 ≈ **~1 MB committed**, growing one annual row
per ticker per year.

### 3.4 The sanity gate

Copy `prices.gate()` (`prices.py:288`) in spirit — a bad fetch must never
overwrite a good file:

- reject if `market_cap` moves more than ~40% in one refresh *and* price did not
- reject if the annual history comes back **shorter** than what is stored
- reject if more than N previously-populated fields come back null
- **allow** restated statement values (they legitimately change), but log a
  restatement count the way `_restated_count()` does
- on rejection: keep the old file, exit non-zero-ish with a warning, let the
  workflow commit nothing

### 3.5 Fetch job

`scripts/update_fundamentals.py`, modelled line-for-line on
`update_prices.py`: same universe derivation (union of
`scripts/.ticker_schedule.json` and existing report directories), same
`--only-missing` / `--dry-run` / positional-ticker-subset CLI, lazy yfinance
import so the test suite stays offline.

`.github/workflows/update_fundamentals.yml`: **weekly** (statements only change
quarterly; ratios drift daily but are recomputable from the price store), say
Saturday 03:00 UTC, plus `workflow_dispatch`. Commits `data/fundamentals/`.
Daily is defensible if we want live P/E — but P/E can instead be *recomputed at
build time* from the stored EPS and the daily price store, which keeps the
weekly cadence and still shows a fresh ratio. **Recommend: weekly fetch, daily
recompute.**

---

## 4. The derived layer — where the interesting maths lives

`scripts/analysis/data/fundamental_analytics.py`, the exact analogue of
`price_analytics.py`: **pure stdlib, store-dict in → plain data out, no file
I/O**, so it is trivially unit-testable against a hand-written statement
fixture.

What it computes:

- **Growth**: revenue / EPS / FCF / EBITDA CAGR over 3, 5, 10 years; per-year
  series for the bar charts.
- **Margin trend series** for sparklines.
- **Piotroski F-Score** — 9 binary tests, all from two consecutive annual
  statements. Return the components, not just the total, so the page can show
  the breakdown.
- **Altman Z-Score** — with the correct variant per `kind`; refuse to emit it
  for `financial` and `etf`.
- **Beneish M-Score** — 8 ratios over two years.
- **ROIC** = NOPAT / (total debt + equity − cash), and Greenblatt ROC.
- **Historical valuation bands** — 5-year median and ±1σ of P/E, P/S and
  EV/EBITDA, mapped back onto price. *This is the honest substitute for GF
  Value*: "at the 5y median P/E of 38×, AMZN would be $X" is a number the
  reader can check, unlike a black-box intrinsic value.
- **Reverse DCF** (optional, phase 6): what FCF growth rate the current price
  implies at a 10% discount rate. One transparent number, no forecasting.
- **Signals** — a rule table producing `(severity, label, evidence)` triples:
  `⚠️ Debt-to-EBITDA 4.8× (>4)`, `✅ FCF positive 10 years running`,
  `⚠️ Beneish M −1.4 (>−1.78 → possible manipulation)`. Every signal carries
  the number that fired it.
- **Universe percentiles** — one pass over all 38 stores per build, so each
  ticker page can say where a metric sits *within our coverage*. Must be
  labelled as such, never as an industry rank.
- **Composite score** — 5 sub-scores (Value / Profitability / Growth / Health /
  Momentum, momentum from the price store) → 0–100. Document the weights on a
  methodology page. Name it something that is obviously ours.

**Gating by `kind` is not optional.** Of the 38 tickers, `QQQ VTI SOXX SOXQ
ROBO 0050` are ETFs and `BRK.B SOFI NU` are financials — margins, Altman Z,
inventory-based Piotroski tests and EV/EBITDA are meaningless or wrong for
them. Store `kind`, and have each module declare which kinds it supports.

---

## 5. Rendering — where the page goes

Three options considered:

| Option | Shape | Verdict |
|---|---|---|
| **A** Extend `docs/reports/<ticker>/index.md` | everything on the existing URL | The page's job is *navigation to reports*; it's already long, and it is rebuilt inside a loop that also copies ~1,600 report bodies. Bolting a 12-section data page on makes both jobs worse. |
| **B** New top-level section `docs/summary/<ticker>/` | peer to `prices/`, own nav tab + index table + JSON manifest | Mirrors the proven Price Data pattern; builds and fails independently; gets its own `.pages` nav; can be skipped in sample builds. |
| **C** Both | full page in B, compact strip in A | ✅ |

**Recommendation: C.** Build `docs/summary/<key>/index.md` as the real page,
and inject a compact "at a glance" metric strip + a link into the existing
report page right under the hero chart (where `target_price_block()` already
sits). Cross-link `prices/<key>/` ↔ `summary/<key>/` ↔ `reports/<ticker>/` so
the three per-ticker pages form a set.

### 5.1 Proposed page layout

```
# 🛒 Amazon.com Inc. (AMZN) — Summary
> Sector · Industry · Data as of 2026-09-03 · sources: yfinance, Finviz

┌ Quote strip ─────────────────────────────────────────────────────────┐
│ $254.92  +1.2%   Mkt cap 2.7T   EV 2.9T   P/E 34.1   Fwd P/E 28.4    │
│ 52w  ├────────────────●──────┤  161.38 — 264.11      Beta 1.14        │
└──────────────────────────────────────────────────────────────────────┘

## Score card          5 dials + composite  (Value/Profit/Growth/Health/Momentum)
## Signals             ✅ good  ⚠️ warning  🔴 severe — each with its number
## Valuation           table: metric | now | 5y median | percentile | verdict
                       + fair-value band chart (price vs P/E-band ribbon)
## Profitability       table + margin trend chart
## Growth              revenue / net income / FCF bars, 10 annual years
## Financial Strength  table + Piotroski / Altman / Beneish (components in ???)
## Dividend & Buyback  table + payout bars           [hidden when no dividend]
## Cash Flow           OCF / capex / FCF bars
## Analysts & Ownership target range vs price · recommendation · insider &
                       institutional % · recent insider trades
## Peers               comparison table across the mapped peer set
## Business            longBusinessSummary + segments
## AI Research         → latest fundamental / technical report + scenario targets
## Filings & News      → docs/sec/, docs/market_news/
## Data & Method       fundamentals.json download · methodology · disclaimer
```

Tables reuse the existing `.ptable` wrapper and `_pct_cell()` / `_num()` /
`_compact_volume()` helpers, so styling and responsive behaviour come free.

### 5.2 Charts

Extend `docs/javascripts/price-charts.js` rather than adding a file — it
already owns fetch, theming, palette-toggle re-render and resize. Two new
`data-kind` values:

- `bars` — categorical bars over fiscal years (revenue, net income, FCF, EPS)
- `dual` — bars + an overlaid line (revenue bars + margin line)

and one non-chart widget in CSS only: the score dial and the percentile bar,
which are just styled `<div>`s and need no JS.

The payload is `fundamentals.json`, written next to each page exactly like
`analytics.json` is today — pre-computed series, no maths in JS.

---

## 6. Concrete change list

**New files**

| Path | Purpose | ~LOC |
|---|---|---|
| `scripts/update_fundamentals.py` | networked fetch job, CI + local | 250 |
| `scripts/analysis/data/fundamentals.py` | store I/O, schema, sanity gate — pure stdlib | 350 |
| `scripts/analysis/data/fundamental_analytics.py` | all derived maths — pure stdlib | 500 |
| `docs/FUNDAMENTAL_STORE_DESIGN.md` | schema + invariants + methodology (the page links to it) | — |
| `.github/workflows/update_fundamentals.yml` | weekly cron, commits the store | 70 |
| `docs/stylesheets/summary.css` | metric cards, score dial, percentile bar, signal list | 200 |
| `tests/test_fundamentals.py` | store parse/serialise/gate round-trips | 200 |
| `tests/test_fundamental_analytics.py` | every score against a hand-built fixture | 400 |
| `tests/test_update_fundamentals.py` | universe derivation, CLI, dry-run | 150 |

**Modified files**

| Path | Change |
|---|---|
| `scripts/build_docs.py` | `build_summary(lang)`, `summary_index_page()`, `summary_ticker_page()`, `fundamentals_payload()`, `store_fundamentals()` cache (mirror `store_bars()`); ~30 new `STRINGS` keys × 2 languages; `summary` entry in `build_nav_pages()` + the root `.pages` nav; `main()` 9 → 10 steps per language; `clean_generated` list |
| `scripts/build_docs.py` (`build_reports`) | inject the compact at-a-glance strip + cross-link under the hero chart |
| `docs/javascripts/price-charts.js` | `bars` and `dual` kinds |
| `mkdocs.yml` | nothing — nav is generated |
| `tests/test_build_docs.py` | summary page renders, gracefully degrades with no store |
| `tests/js/` | new chart kinds |
| `CLAUDE.md`, `docs/ARCHITECTURE.md`, `README.md` | document the second store |

**Deliberately unchanged**: the LLM pipeline. The summary page is
deterministic, computed data. Keeping the LLM out of it is the point — the
report pages already carry the narrative, and a number that can be checked is
worth more next to prose than more prose.

---

## 7. Phasing

| Phase | Deliverable | Ships value? | Est. |
|---|---|---|---|
| **0** | Freeze the schema; write `FUNDAMENTAL_STORE_DESIGN.md`; decide the open questions in §9 | no | 0.5d |
| **1** | Store module + fetcher + gate + tests; commit the first snapshot for 38 tickers | no (data only) | 1–2d |
| **2** | `fundamental_analytics.py` + tests — pure functions, the biggest test surface | no | 1–2d |
| **3** | `build_summary()` rendering **tables only**, no new JS, EN only | ✅ a usable page | 1–2d |
| **4** | Charts: `bars`/`dual` kinds + the 4 chart blocks | ✅ | 1d |
| **5** | Score card, signals, universe percentiles (build-wide pass) | ✅ | 1d |
| **6** | Peers, ZH strings, nav, index table + `index.json` manifest, methodology page, disclaimer | ✅ | 1d |
| **7** | Cross-links from report & price pages; QA workflow check; perf measurement | ✅ | 0.5d |

Phase 3 is the first shippable point and everything before it is invisible —
worth front-loading the schema decision, because rewriting a committed store is
the expensive mistake here.

---

## 8. Risks

- **yfinance drift / rate limits.** The single biggest operational risk. Gate +
  keep-last-good + a smoke workflow like the existing `scraper_smoke.yml`.
  Consider a second source (Finviz is already scraped) for cross-checking
  headline ratios.
- **Statement shape varies by company.** yfinance's row labels are not stable
  across issuers; the extractor needs a label-alias map per field and must
  degrade to `null`, never guess.
- **Financials and ETFs.** ~9 of 38 tickers. Without `kind` gating the page
  will confidently print nonsense.
- **"Percentile" over 38 tickers is not an industry rank.** Label honestly or
  cut the module.
- **Repo growth.** ~1 MB now; churn is small only if serialisation is
  deterministic. Verify with a no-change re-run producing an empty diff before
  the first cron.
- **Build time / site size.** `docs/` is already 752 MB (`PERFORMANCE.md`) and
  the prices section added 38 × 2 pages. Summary adds another 76 pages plus a
  ~30 KB payload each — small, but measure it in phase 7 rather than assume.
- **Legal.** No GuruFocus scraping, no reuse of GF Score/GF Value naming or
  formulas. State every source on the page and keep the existing disclaimer
  admonition.

---

## 9. Open questions (need a decision before phase 1)

1. **Separate `/summary/` section, or extend the report page?** — recommendation
   above is both (full page + compact strip). Confirm.
2. **Universe** — all 38 price-store keys, or only the 36 in
   `.ticker_schedule.json`'s `fundamental` list? (Cheapest: mirror
   `update_prices.py`'s union rule exactly.)
3. **Composite score: yes or no?** It is the most GuruFocus-like element and
   also the most opinionated. Raw metrics + percentiles alone are defensible and
   much cheaper to justify.
4. **Refresh cadence** — weekly fetch with daily build-time ratio recompute
   (recommended), or a daily fetch?
5. **Peer map** — hand-written in `data/fundamentals/_universe.json`, or derived
   from `COMPANY_META["sector"]`? Hand-written is better; sector strings there
   are free-text ("Semiconductors", "ETF · Semiconductors").
