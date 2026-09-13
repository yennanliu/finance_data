# Financial Metrics on the Company Page — Feasibility Survey

**Question:** the per-ticker page (e.g. [`/reports/amzn/`](reports/amzn/index.md))
today shows a hero k-line chart, a scenario price-target table and a list of
generated reports. [Growin's financial-metrics
page](https://www.growin.ai/zh/my/analysis/NVDA/financial-metrics) shows
something we don't: ~19 charts of *reported fundamentals* — revenue, EPS,
margins, cash flow, valuation multiples, ROE/ROA/ROIC — on quarterly / TTM /
annual toggles over 3Y / 5Y / 10Y.

Can we build that? And can the underlying data live in `data/` as a committed,
diff-friendly store the way `data/prices/` does?

**Answer:** yes to both, for most of it. 13 of the 19 charts need nothing but
reported financial statements, which SEC's XBRL API gives away free with
10–16 years of quarterly history. 5 more are *derived* from those statements
joined against the price store we already have — no new data at all. Only 2
(analyst-surprise) need an estimates feed, and 1 (revenue by segment) is
genuinely hard. And the store shape is a near-copy of `data/prices/<key>.csv`:
same key convention, same invariants, ~1 MB for the whole universe.

The honest catch is **coverage**: 22 of our 36 tickers file US-GAAP XBRL. Four
(TSM, GRAB, NU, NBIS) are foreign private issuers that file IFRS annually and
return *zero* `us-gaap` facts. Nine are ETFs or a Taiwan listing with no
financial statements at all. Any approach has to answer for those 14.

**Surveyed:** 2026-09-14 · every number below is a real measurement against the
live SEC API or the working tree at commit `d9744b0bc`.
**Status:** survey only. No code changed. If accepted, the build plan belongs in
a sibling `FUNDAMENTALS_STORE_DESIGN.md`, the way
[`CHART_UNIFICATION_EVAL.md`](CHART_UNIFICATION_EVAL.md) preceded
[`PRICE_STORE_DESIGN.md`](PRICE_STORE_DESIGN.md).

---

## 1. What the target actually contains

From the three reference screenshots, Growin's NVDA page is 19 charts in four
groups, above a `季度 / 近四季 / 年度` period toggle and a `3Y / 5Y / 10Y` range
toggle. Sorted by *what data it needs* rather than by how it looks:

### Tier 1 — plain financial statements (13 charts)

| Chart | Shape | Inputs |
|---|---|---|
| 營收 Revenue | bars + YoY line, dual axis | revenue |
| 每股盈餘 EPS | bars + YoY line | basic EPS |
| 稀釋每股盈餘 Diluted EPS | bars + YoY line | diluted EPS |
| 營業利益 Operating income | bars + YoY line | operating income |
| 淨利 Net income | bars + YoY line | net income |
| 營業費用 Operating expenses | stacked bars | R&D, SG&A |
| 現金流 Cash flow | grouped bars | OCF, FCF (= OCF − capex) |
| 現金 & 債務 Cash & debt | grouped bars | cash & ST investments, total debt |
| 流動合約負債 Current contract liabilities | bars | contract liability, current |
| 三率圖 Three margins | 3 lines | gross / operating / net margin |
| 經營報酬率 ROE · ROA · ROIC | 3 lines | net income, equity, assets, debt |
| ROS | area | net income ÷ revenue |
| *(implicit)* TTM roll-up | — | any of the above, 4-quarter sum |

Every one of these is a ratio or a rename of a line item that appears in a 10-K
or 10-Q. Nothing proprietary, nothing estimated.

### Tier 2 — statements × price (5 charts)

| Chart | Inputs |
|---|---|
| 股價營收比 P/S | price × shares ÷ TTM revenue |
| 股價淨值比 P/B | price × shares ÷ equity |
| EV/Sales | (mkt cap + debt − cash) ÷ TTM revenue |
| EV/EBITDA | (mkt cap + debt − cash) ÷ TTM EBITDA |
| 本益比河流圖 PE river | monthly price, overlaid with TTM-EPS × six historical P/E percentiles |

These need **no new data source**. They are a join of a fundamentals store
against `data/prices/<key>.csv`, which already holds 10 years of daily closes
for all 38 keys. The PE river chart in particular is exactly the kind of thing
`price_analytics.py` already does for drawdown and rolling volatility.

### Tier 3 — analyst estimates (2 charts)

| Chart | Inputs |
|---|---|
| EPS 驚喜比率 EPS surprise | consensus EPS estimate vs actual |
| 營收驚喜比率 Revenue surprise | consensus revenue estimate vs actual |

Consensus estimates are not in any SEC filing — they are a vendor product.
Partially available free: `yfinance`'s `Ticker.earnings_history` carries
`epsestimate` / `epsactual` / `surprisepercent`, and **we already fetch it**
(`sources.py:478`, rendered into `earnings_text` for the LLM and then discarded).
Revenue surprise needs `revenue_estimate`, which yfinance exposes less reliably.

### Tier 4 — segment disaggregation (1 chart)

| Chart | Inputs |
|---|---|
| 營收分佈 Revenue by segment | per-segment revenue (Data Center / Gaming / ProViz / Auto…) |

This is the hard one — see §4.5. Recommend deferring it.

---

## 2. What the repo already has, and throws away

This is the most striking finding of the survey.

`scripts/analysis/data/sources.py:348` `fetch_data()` runs on **every report
generation** — 61 cron slots a day — and already pulls:

```python
"income":     t.financials,             # 4 annual periods,   45 line items
"income_q":   t.quarterly_financials,   # 6 quarterly periods, 46 line items
"balance":    t.balance_sheet,          # 5 annual periods,   61 line items
"balance_q":  t.quarterly_balance_sheet,
"cashflow":   t.cashflow,               # 5 annual periods,   52 line items
"cashflow_q": t.quarterly_cashflow,
"earnings_text":  ...,   # 8 quarters of EPS estimate / actual / surprise%
"finviz_data":    ...,   # P/E, P/S, P/B, ROA, ROE, ROI, margins, Debt/Eq
"stockanalysis_data": ..., # annual + quarterly income statement, balance sheet
"roic_data":      ...,   # up to 7 tables of 10Y+ value metrics
```

(Shapes above are a live measurement of AMZN on 2026-09-14.)

All of it is flattened to text, pasted into an LLM prompt, and dropped. Nothing
is persisted. The site therefore has no structured fundamentals even though the
pipeline touches them 61 times a day.

That is the same situation the price data was in before
`PRICE_STORE_DESIGN.md` — data fetched per-report, used once, thrown away — and
the fix has the same shape.

### What's missing from what we already fetch

yfinance's window is **shallow**: 4 annual and 6 quarterly periods. Growin's
3Y toggle needs 12 quarters; the 10Y toggle needs 40. So the existing fetch
covers roughly the last 18 months and nothing before it. Everything hinges on
whether we can backfill.

---

## 3. Where the data can come from

Six candidate sources, measured.

### 3.1 SEC XBRL `companyfacts` API — the strong candidate

```
GET https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json
```

Free, no key, no rate-limit pain (10 req/s, one call per ticker), and we already
have `scripts/edgar_common.py:34` `get_cik()` plus a working
`User-Agent`-header convention.

Measured on AMZN (CIK 0001018724):

| Metric | Value |
|---|---|
| Response size | 4.48 MB |
| Taxonomies | `dei`, `us-gaap`, `ecd`, `ffd` |
| `us-gaap` concepts | 545 |
| `NetIncomeLoss` data points | 422 |
| Quarterly-duration points | 192 |
| Date span | 2007-12-31 → 2026-06-30 |

Each fact carries `{start, end, val, accn, fy, fp, form, filed, frame}` — which
means we get the fiscal-period label (`fy`/`fp`) *for free*, and can dedupe
restatements by `filed`. That matters: AVGO's fiscal quarters end on dates like
`2026-08-02`, so a calendar-derived label would be wrong.

**Four warts, all real, all surmountable:**

1. **Concepts drift within a company.** Measured:

   | Ticker | `Revenues` | `SalesRevenueNet` | `RevenueFromContractWithCustomer…` |
   |---|---|---|---|
   | MSFT | 14 qtrs, 2007→2010 | 35 qtrs, 2009→2018 | 34 qtrs, 2016→2026 |
   | AVGO | 8 qtrs, 2017→2018 | 2 qtrs | 30 qtrs, 2018→2026 |
   | NVDA | 65 qtrs (16 years) | — | — |
   | AMZN | absent | absent | 72 qtrs |

   ASC 606 adoption in 2018 swapped the revenue tag industry-wide. A single
   concept name gives MSFT 14 quarters; a **coalesce chain across candidates,
   resolved per period** gives it the full 2007→2026 run. This is the single
   largest piece of work in the whole proposal, and it is a curated mapping
   table plus tests — not an unbounded problem.

2. **No Q4 quarterly fact.** Measured on AMZN: the last December-ending
   quarterly revenue point is `2020-12-31`. Filers stopped tagging Q4 as a
   discrete period because the 10-K reports the full year. Q4 must be **derived**
   as `FY − (Q1 + Q2 + Q3)`, per concept, per fiscal year. Standard practice,
   needs a test.

3. **Duplicates.** Up to **4 points per (concept, period)** on AMZN, from
   amendments and comparative restatements in later filings. Dedupe by latest
   `filed`, tie-break on `accn`.

4. **Not every company tags every concept.** AMZN has no
   `ResearchAndDevelopmentExpense` (they report "Technology and infrastructure");
   SOFI has no `GrossProfit`. A chart must be able to render as *absent* rather
   than as zero.

### 3.2 SEC XBRL — the IFRS problem

Measured, and it is worse than expected:

| Ticker | `us-gaap` concepts | Taxonomy present |
|---|---|---|
| NVDA | 627 | us-gaap |
| MSFT | 562 | us-gaap |
| SOFI | 474 | us-gaap |
| AVGO | 434 | us-gaap |
| PLTR | 356 | us-gaap |
| **TSM** | **0** | `ifrs-full` |
| **NU** | **0** | `ifrs-full` |
| **GRAB** | **1** | `ifrs-full` |

Foreign private issuers file 20-F under IFRS. A `us-gaap` mapping covers **0%**
of them. The facts *are* there under `ifrs-full` (`Revenue`,
`ProfitLossAttributableToOwnersOfParent`, …), so a second mapping recovers them —
but 20-F is **annual only**, so these tickers get annual bars and no quarterly
series regardless of effort.

### 3.3 yfinance — shallow but normalised

Already a dependency, already called 61×/day, and its row labels are *already
normalised* across GAAP/IFRS (`Total Revenue`, `Operating Income`, `Diluted
EPS`, `Free Cash Flow`) — which is exactly the mapping work §3.1 makes us do by
hand, done for us. It also covers TSM, GRAB, NU and 2330.TW.

Measured (AMZN, 2026-09-14):

| Property | `financials` | `quarterly_financials` |
|---|---|---|
| Periods | **4** | **6** |
| Line items | 45 | 46 |
| Span | 2022→2025 | 2025-03 → 2026-06 |

The fatal limitation is the window: no backfill is possible. A store fed only by
yfinance starts with 6 quarters and gains one every ~90 days — the 3Y toggle is
usable in ~18 months, the 10Y toggle in 2034.

There is a subtlety worth naming, though: **an accreting store does not need a
deep source to *stay* deep.** Once a quarter is written it is permanent. So
yfinance is a perfectly good *maintenance* feed; it is only inadequate as a
*backfill* feed. That observation is what makes Approach D work.

### 3.4 StockAnalysis.com scrape — already wired, already fragile

`sources.py:131` `fetch_stockanalysis()` scrapes annual + quarterly income
statement and balance sheet, capped at 25/15/20 rows, into positional text. It
covers foreign filers and has long history. But it is `soup.find_all("table")[0]`
against an unversioned page — it breaks silently on any layout change (there is a
`scraper_smoke.yml` workflow precisely because of this), and scraping a
commercial site into a *committed, republished dataset* is a materially
different proposition from scraping it into a throwaway LLM prompt. Their terms
should be read before this becomes a publishing pipeline.

### 3.5 Finviz / roic.ai — snapshots, not series

`fetch_finviz()` returns a point-in-time snapshot (current P/E, ROE, margins) —
useful for a "key stats" table, useless for a 10-year chart. `fetch_roic()`
returns 10Y+ tables but as untyped `table_0…table_6` positional scrapes with no
header contract. Same ToS caveat as §3.4.

### 3.6 Paid APIs — the escape hatch

Financial Modeling Prep, Finnhub, Polygon and Tiingo all sell normalised
statements *plus* the estimates (Tier 3) and, in some tiers, the segment
breakdown (Tier 4) that SEC makes hard. Roughly $20–100/month. This buys away
almost all of the engineering in §3.1–3.2 and is the only realistic path to
Tier 4.

It also introduces the first **paid dependency and API secret** in a repo whose
data layer is currently free and whose tests are fully offline. That is a real
change in the project's character, not just its budget.

### 3.7 Source comparison

| Source | Cost | History | Quarterly | GAAP | IFRS | ETF | Estimates | Segments | Fragility |
|---|---|---|---|---|---|---|---|---|---|
| SEC companyfacts | free | 10–16Y | ✅ | ✅ | ⚠️ annual | ❌ | ❌ | ❌ | very low |
| yfinance | free | **4–6 periods** | ✅ | ✅ | ✅ | ❌ | ⚠️ EPS only | ❌ | medium |
| StockAnalysis | free | ~10Y | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | **high** |
| Finviz | free | snapshot | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | high |
| roic.ai | free | 10Y+ | ⚠️ | ✅ | ✅ | ❌ | ❌ | ❌ | high |
| Paid API | $20–100/mo | 10–30Y | ✅ | ✅ | ✅ | ❌ | ✅ | ⚠️ some | low |

---

## 4. Coverage across our 36-ticker universe

From `scripts/.ticker_schedule.json`:

| Class | Count | Tickers | Best available |
|---|---|---|---|
| US filers (10-K/10-Q, us-gaap) | **22** | AMD AMZN AVAV AVGO GOOG INTC KTOS META MRVL MSFT MU NVDA ONDS ORCL PL PLTR RKLB SNDK SOFI TSLA VST WDC | full quarterly, 10Y+ |
| Foreign private issuers (20-F, IFRS) | **4** | TSM GRAB NU NBIS | annual only |
| Taiwan listing (no SEC) | **1** | 2330.TW | yfinance / TWSE only |
| ETFs / funds | **6** | 0050 QQQ ROBO SOXQ SOXX VTI | **none — by definition** |
| Unidentified (absent from `COMPANY_META`) | **3** | SKHY SPCX WQTM | unknown; likely funds |

So the realistic headline is: **22 tickers get the full Growin-grade treatment,
5 get a reduced annual version, and 9 get nothing** — and the page must degrade
to *no section at all* for the last group rather than to an empty chart. The
existing `COMPANY_META` comment (`build_docs.py:570`) already establishes the
house position here: for SKHY/SPCX/WQTM, *"a guessed company name on a data page
is worse than none."* Same rule applies to a guessed financial statement.

### 4.5 Why segment revenue is the hard one

`companyfacts` **flattens away XBRL dimensions.** Measured on AMZN, the only
segment-flavoured concepts present are `NumberOfOperatingSegments`,
`NumberOfReportableSegments`, `SegmentReportingSegmentOperatingProfitLoss` and
`SegmentExpenditureAdditionToLongLivedAssets` — counts and totals, no per-segment
revenue. The AWS-vs-North-America-vs-International split exists only as
dimensional facts in the filing's raw XBRL instance, tagged against a
`StatementBusinessSegmentsAxis` with company-specific members.

Recovering it means one of: parsing each filing's XBRL instance + calculation
linkbase; ingesting SEC's quarterly *Financial Statement Data Sets* ZIPs and
joining `num.txt` against the segment dimension; or buying it (§3.6). All three
are substantially more work than everything else in this document combined, and
the member names are not standardised across companies — "Data Center" is
NVDA's word, not a taxonomy term.

**Recommendation: cut 營收分佈 from scope.** It is 1 chart of 19 and it is most
of the risk.

---

## 5. Can it be a `data/` store like `data/prices/`?

Yes, and the fit is unusually clean. The price store's design decisions transfer
almost unchanged.

### 5.1 Layout

```
data/
  prices/                    ← exists: 38 files, 3.3 MB
    amzn.csv
  fundamentals/              ← proposed
    amzn.csv                 quarterly reported statements
    nvda.csv
```

Same `report_key()` convention, so `data/fundamentals/<key>.csv` ↔
`data/prices/<key>.csv` ↔ `ai_gen_report/*/<key>/` ↔ `docs/reports/<key>/` line
up with no mapping table — exactly the argument `PRICE_STORE_DESIGN.md` §3.1
makes.

### 5.2 Schema — wide, one row per fiscal period

```csv
period_end,fy,fp,form,filed,revenue,gross_profit,operating_income,net_income,eps_basic,eps_diluted,rnd_expense,sga_expense,ocf,capex,cash_and_equiv,short_term_investments,total_debt,total_assets,total_equity,shares_diluted,contract_liability_current
2026-03-31,2026,Q1,10-Q,2026-05-01,155667000000,,18405000000,17127000000,1.61,1.59,,,17000000000,25000000000,...
2026-06-30,2026,Q2,10-Q,2026-07-31,167700000000,,19200000000,62647000000,5.87,5.77,,,...
```

| Column | Notes |
|---|---|
| `period_end` | ISO date, primary key, ascending, unique — mirrors `prices.csv`'s `date` |
| `fy` / `fp` | fiscal year + `Q1…Q4`/`FY`, straight from XBRL — **not** derived from the calendar |
| `form` / `filed` | provenance; `filed` is the dedupe key for restatements |
| metric columns | fixed order, empty when the company doesn't tag the concept |

**Why wide rather than long** (`period_end,metric,value`):

- A new quarter is **one appended line**, the same property that makes the price
  store's nightly diff readable. Long format would append ~20 lines per quarter.
- A restatement **edits one line** — again identical to the price store, where a
  fetched bar always wins over a stored one.
- The cost is that adding a metric rewrites every line once. That is a rare,
  deliberate, reviewable event; the price store accepted the same trade for its
  `div`/`split` columns.

### 5.3 Invariants — reuse I1–I6 verbatim

`PRICE_STORE_DESIGN.md` §3.3 already defines the load-bearing properties, and
all six apply unchanged: **I1** byte-stable round-trip, **I2** idempotent,
**I3** sorted & unique, **I4** capped (`KEEP_YEARS = 10` → ~40 rows), **I5**
atomic `os.replace`, **I6** gated. The sanity gate (§3.5) needs its own
thresholds — reject a fetch whose period count regresses, whose revenue is
negative, or whose latest period is older than the stored one — but the *shape*
of the gate is the same.

One genuinely new invariant is needed:

- **I7 — derived Q4 is marked.** A Q4 row computed as `FY − (Q1+Q2+Q3)` is not a
  reported figure. Either carry a `derived` flag column or reconstruct it at read
  time rather than storing it. Storing an arithmetic result next to reported ones
  without saying so is the kind of quiet dishonesty this repo's docs otherwise
  avoid.

### 5.4 Size

Measured basis: `data/prices/` is 3.3 MB for 38 tickers × ~2,500 daily bars.

Fundamentals are three orders of magnitude sparser — ~40 quarters instead of
~2,500 days:

| | Per ticker | 22 US filers | Whole universe |
|---|---|---|---|
| Rows | ~44 (40Q + 4 restated) | ~970 | ~1,100 |
| Bytes/row | ~230 (21 numeric cols) | | |
| **Total** | **~10 KB** | **~220 KB** | **~260 KB** |

That is **8% the size of the price store** and 0.03% of `ai_gen_report/`
(402 MB). Storage is a non-issue. The nightly diff is zero on ~87 days out of
90 and one line on the other three — better behaved than the price store, which
touches every ticker every night.

### 5.5 Refresh cadence

Fundamentals change 4× a year, not daily. A nightly full-universe fetch would be
36 pointless HTTP calls a day. Two sane options:

- **Weekly cron**, `update_fundamentals.yml` modelled on `update_kline_data.yml`
  (same `python-env` + `commit-and-push` composite actions, same
  `concurrency` group pattern). Simple; at most 7 days stale.
- **Earnings-triggered**: `Ticker.calendar` gives the next earnings date; refresh
  only tickers within a few days of one. Cheaper and fresher, but adds a
  scheduling dependency for little gain at 36 tickers.

Recommend weekly. The `commit-and-push` action's `git diff --cached --stat` line
makes an unexpected full-file rewrite obvious, exactly as it does for prices.

---

## 6. Derived metrics do **not** belong in the store

This is the single most important design point, and the repo has already decided
it once — `PRICE_STORE_DESIGN.md` §12, *"Why the maths is in Python"*:

> Every statistic on these pages comes from `analysis/data/price_analytics.py`,
> which is pure stdlib […] `price-charts.js` fetches `analytics.json` and draws
> it; it computes nothing.

The same rule settles a lot of scope questions here:

| Quantity | Stored? | Why |
|---|---|---|
| revenue, net income, OCF, assets | **stored** | reported; the store is the record |
| gross / operating / net margin | derived | ratio of two stored columns |
| YoY growth, TTM roll-up | derived | window function over stored rows |
| ROE, ROA, ROIC, ROS | derived | ratios of stored columns |
| P/S, P/B, EV/Sales, EV/EBITDA | derived | **join** of the store against `data/prices/` |
| PE river bands | derived | TTM EPS × historical multiple percentiles |

So a `scripts/analysis/data/fundamental_analytics.py` — pure stdlib, sibling to
`price_analytics.py`, taking the same `list[dict]` shape `load_store()` returns —
computes every Tier 1 ratio and every Tier 2 multiple, and is asserted in
`tests/test_fundamental_analytics.py` against hand-worked arithmetic exactly as
`tests/test_price_analytics.py` does today.

**Consequence: all five Tier 2 valuation charts cost zero new data.** They are a
function of two stores we would then both have.

---

## 7. The rendering gap

`docs/javascripts/price-charts.js` (263 lines) draws one series per widget, in
one of three kinds:

```
data-kind = "area" | "line" | "histogram"
```

Growin's charts need three shapes it doesn't have:

| Needed | Used by | Lightweight Charts support |
|---|---|---|
| Bars over time | revenue, EPS, operating income, net income | `addHistogramSeries` ✅ |
| Bars + line, **dual axis** | all six YoY charts | second `priceScaleId` ✅ |
| Multiple lines on one chart | 三率圖, ROE/ROA/ROIC | multiple `addLineSeries` ✅ |
| Stacked bars | opex (R&D + SG&A) | ⚠️ no native stack — pre-stack in Python |

All of it is achievable with the **already-vendored** Lightweight Charts build
(`lightweight-charts.standalone.production.js`) — no new library, no CDN. The
stacked case is handled the way §6 implies anyway: Python emits cumulative
values, JS draws two histogram series.

Realistic JS scope: extend `pchart` with `data-kind="bars"`, `"bars+line"` and
`"multiline"`, plus a `data-series` that accepts a comma-separated list. The
existing `retheme()` / `destroy()` / `document$` lifecycle and the
`tests/js/price_charts_harness.mjs` harness (186 lines, with a `dom_shim.mjs`)
carry over — this is an extension of a proven widget, not a new one.

The period/range toggles (`季度 / 近四季 / 年度`, `3Y / 5Y / 10Y`) are a UI
control the widget doesn't have. Cheapest honest version: emit all three period
bases into `fundamentals.json` at build time and let the toggle switch payload
keys client-side — no recomputation in JS, consistent with §6.

---

## 8. Approaches

### A — Parse the numbers out of the generated reports

Reuse what the LLM already wrote into `ai_gen_report/*/<ticker>/*.md`.

- **Pro:** zero new data sources; the numbers are already on disk.
- **Con:** they are *LLM-transcribed*, unverifiable, inconsistently formatted,
  and absent for any quarter nobody happened to write about. Publishing an
  LLM's retyping of a financial statement as structured data is a different
  and worse claim than publishing the filing.
- **Effort:** small. **Verdict: reject.** This fails the same standard
  `COMPANY_META` applies to company names.

### B — yfinance-only store

Persist what `fetch_data()` already pulls, into `data/fundamentals/<key>.csv`.

- **Pro:** no new dependency, no new network surface, no ToS question; row
  labels are pre-normalised across GAAP *and* IFRS, so TSM/GRAB/NU/2330.TW come
  along free; the store accretes, so it deepens on its own.
- **Con:** starts at **6 quarters**. The 3Y toggle is thin for ~18 months and
  the 10Y toggle is empty until the 2030s. yfinance's normalisation is
  undocumented and can shift under us.
- **Effort:** **small** — ~1 store module + 1 workflow + tests. Call it 2–3 days.
- **Verdict:** the right *floor*, the wrong *ceiling*.

### C — SEC XBRL companyfacts store

Backfill and maintain from `data.sec.gov`.

- **Pro:** free, authoritative (it *is* the filing), 10–16 years of quarterly
  history on day one, stable schema, no ToS concern, and `edgar_common.get_cik()`
  already exists. Restatement provenance (`filed`, `accn`) comes built in.
- **Con:** the four warts of §3.1 — concept drift, derived Q4, duplicates,
  per-company gaps — each needing a curated mapping and a test. Covers **22 of
  36** tickers; zero coverage of TSM/GRAB/NU until an IFRS mapping is added.
- **Effort:** **medium** — concept mapping table, Q4 derivation, dedupe, gate,
  store module, analytics module, workflow, tests. Call it 5–8 days.
- **Verdict:** the strongest single source.

### D — C for backfill + B for maintenance  ← **recommended**

Backfill 10 years from XBRL once; keep it current from whichever source has the
period first; prefer XBRL when both have it.

- **Pro:** depth *and* breadth. XBRL gives 22 tickers a decade of history on day
  one; yfinance fills the 5 IFRS/TW tickers and covers the 1–6 week gap between
  an earnings release and the 10-Q filing. Because the store accretes (§3.3),
  yfinance's shallow window is sufficient for steady state. Degrades gracefully:
  if one source breaks, the other keeps the store current and the gate refuses
  the bad write.
- **Con:** two ingest paths means a **precedence rule** that has to be written
  down and tested (`source` column; XBRL wins on collision, the way a fetched
  bar wins in the price store), and two mappings to maintain.
- **Effort:** **medium-plus** — C, plus a source-precedence layer and its tests.
  Call it 7–10 days, of which C is most of it.

### E — Third-party scrape (StockAnalysis / roic.ai)

- **Pro:** broad coverage including foreign filers and Taiwan, pre-normalised,
  long history; scrapers already exist in `sources.py`.
- **Con:** positional `find_all("table")[0]` parsing, silent breakage (hence
  `scraper_smoke.yml`), and — decisively — republishing a commercial site's
  dataset is a materially different act from quoting it into a prompt.
- **Effort:** small to build, **unbounded to maintain**.
- **Verdict:** acceptable as a *fallback* behind D's gate; not as a primary.

### F — Paid API

- **Pro:** buys away almost all of §3.1–3.2, and is the only practical route to
  Tier 3 estimates and Tier 4 segments. One clean client, one schema.
- **Con:** $20–100/month; introduces the first paid dependency and API secret in
  the data layer; vendor lock-in on a dataset we'd be publishing.
- **Effort:** **small** to integrate (2–3 days), ongoing to pay for.
- **Verdict:** revisit only if Tier 3/4 turn out to matter.

### Summary

| | Coverage | Depth day 1 | Cost | Fragility | Effort | Tier 3 | Tier 4 |
|---|---|---|---|---|---|---|---|
| A reports | 36 | — | free | n/a | S | ❌ | ❌ |
| B yfinance | **27** | 6 qtrs | free | med | **S** | ⚠️ | ❌ |
| C XBRL | 22 | **10–16Y** | free | **low** | M | ❌ | ❌ |
| **D C+B** | **27** | **10–16Y** | free | low | M+ | ⚠️ | ❌ |
| E scrape | 27 | ~10Y | free | **high** | S | ❌ | ❌ |
| F paid | 27 | 10–30Y | $$ | low | S | ✅ | ⚠️ |

(Coverage counts tickers with any financial statements at all; the 9
ETF/unidentified keys are out of reach for every option.)

---

## 9. Recommended shape, if this goes ahead

Phased so that each phase is independently valuable and independently
revertible — the pattern `PRICE_STORE_DESIGN.md` §8 used.

| Phase | Deliverable | Effort |
|---|---|---|
| **1** | `data/fundamentals/<key>.csv` + `analysis/data/fundamentals.py` (read/serialise/upsert/gate, I1–I7) + XBRL backfill CLI + `tests/test_fundamentals.py` | 3–4 d |
| **2** | `analysis/data/fundamental_analytics.py` — TTM, YoY, margins, ROE/ROA/ROIC/ROS + hand-worked tests | 2 d |
| **3** | `update_fundamentals.yml` weekly cron, reusing `python-env` + `commit-and-push` | 0.5 d |
| **4** | `price-charts.js` gains `bars` / `bars+line` / `multiline`; harness tests extended | 2 d |
| **5** | `build_docs.build_fundamentals()` → a **Financials** section on `/reports/<ticker>/`, plus `fundamentals.json` + CSV download, EN + ZH | 2–3 d |
| **6** | Tier 2 valuation charts (P/S, P/B, EV/Sales, EV/EBITDA, PE river) — pure join, no new data | 1–2 d |
| **7** | yfinance maintenance path + source precedence (completes Approach D) | 1–2 d |
| — | *deferred:* Tier 3 estimates (needs a feed), Tier 4 segments (§4.5) | — |

Phases 1–3 deliver a committed, tested, published dataset with no UI. Phases 4–6
deliver the page. Phase 7 closes the coverage gap. **~11–15 days total** for
16 of the 19 charts.

### Where it lands on the page

`build_docs.py:1306` assembles the per-ticker page as: heading → hero k-line →
*"More charts"* link → price-target table → `---` → Latest Reports cards →
Available Reports. A **Financials** section slots naturally between the
price-target table and the `---`, guarded on the ticker having a store file —
mirroring how the *"More charts"* link is already guarded on
`ticker in priced_keys` so a sample build doesn't emit a dangling link.

There is a second, arguably better option: give fundamentals **its own section**
under `docs/fundamentals/`, mirroring `docs/prices/`, with an overview table and
a page per ticker — and put only a two-line summary plus a cross-link on the
report page. That keeps the report page from growing to 19 charts and reuses the
`build_prices()` structure almost verbatim. Worth deciding before Phase 5.

---

## 10. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Concept mapping silently picks the wrong tag and publishes a wrong revenue | **high** | Gate on cross-checks (revenue ≥ gross profit ≥ operating income; Q1+Q2+Q3+Q4 ≈ FY within tolerance); assert known values for 3–4 tickers in tests |
| Derived Q4 presented as reported | medium | I7 — flag it, and label it in the UI |
| Restatement rewrites history under a published report | medium | Accepted, same as the price store's split caveat (§3.4 there); `filed`/`accn` preserve provenance |
| yfinance normalisation shifts | medium | XBRL is primary under D; the gate rejects a regressing fetch |
| ToS exposure from republishing scraped data | medium | Approach E stays a fallback, or is dropped |
| Scope creep into segments/estimates | medium | Explicitly deferred in §4.5 and §8 |
| Page becomes a 19-chart wall | low | §9 alternative — its own section, like `docs/prices/` |

---

## 11. Open questions for the owner

1. **Coverage floor.** Is 22-of-36 with full depth acceptable, or is covering
   TSM/GRAB/NU/2330.TW a requirement? The answer picks C vs D.
2. **Placement.** Financials section *on* the report page, or its own
   `docs/fundamentals/` section with a cross-link (§9)?
3. **Tier 3 estimates.** Do the two surprise-ratio charts matter enough to pull
   in a feed? If yes, F becomes much more attractive than D.
4. **Budget.** Is a $20–100/month data subscription on the table at all? If
   flatly no, F is out and Tier 4 is permanently out with it.
5. **ETF pages.** Confirm the section simply does not render for the 9
   ETF/unidentified keys — consistent with the existing "no guessed data"
   position in `COMPANY_META`.

---

## 12. Bottom line

The data is obtainable, it is free for the 22 tickers that matter most, and the
store is a near-copy of a pattern this repo has already built, tested and
documented once. `data/fundamentals/<key>.csv` would add ~260 KB — 8% of the
price store — and unlock 16 of Growin's 19 charts, five of which cost no new
data at all because the price store already exists.

The work is real but bounded, and it concentrates in one place: a curated XBRL
concept mapping with tests behind it. The two things to *not* do are parsing
numbers out of LLM prose (§8A) and chasing segment disaggregation (§4.5).
