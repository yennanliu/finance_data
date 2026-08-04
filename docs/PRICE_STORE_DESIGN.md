# Price Store & Unified Chart — Design

**Status:** phases 1–3 and 4a implemented — the store is live, the docs build
derives every chart payload from it, technical report pages render the shared
widget pinned to their own date, and the Plotly/PNG generator is gone. Phase 4b
(deleting the 208 MB of already-committed chart payload) is deliberately gated on
verifying phase 3 on the deployed site, since it is the only irreversible step.
**Rationale and measurements:** [`CHART_UNIFICATION_EVAL.md`](CHART_UNIFICATION_EVAL.md).
**Written:** 2026-08-04, against commit `5e0e699b`.

One committed 10-year OHLCV store per ticker becomes the single source of truth
for every chart on the site. All chart payloads are *derived* from it at docs-build
time; none are committed. The per-report Plotly + PNG pipeline is deleted.

---

## 1. Goals / non-goals

**Goals**

- G1 — Technical report pages render the same interactive k-line chart as the
  ticker index page, from the same data.
- G2 — Price history is stored once per ticker at 10-year depth, so any window
  (30D … 10Y) can be sliced without refetching or a schema change.
- G3 — Nightly updates produce a small, human-reviewable diff.
- G4 — Splits, dividend re-adjustments and upstream corrections require no
  special-case code.
- G5 — Report charts are *as-of accurate*: a report dated `D` shows the chart as
  it stood on `D`.
- G6 — Remove plotly / kaleido / mplfinance from the analysis critical path.

**Non-goals**

- Rendering charts in the raw `.md` as viewed on github.com. Explicitly out of
  scope (eval §4).
- Intraday / sub-daily bars.
- Rewriting git history to reclaim the ~208 MB already committed. The working
  tree shrinks; history is left alone.
- Feeding the store into `compute_technicals()`. Attractive, listed as a future
  option in §9, deliberately not in this plan.

---

## 2. Target architecture

```
                    ┌──────────────────────────────────────────┐
  yfinance ────────►│ scripts/analysis/data/prices.py          │
  (full 10y,        │   fetch_history()   → DataFrame          │
   nightly)         │   load_store()      → list[Bar]          │
                    │   merge_and_write()  (atomic, gated)     │
                    └───────────────┬──────────────────────────┘
                                    │  committed source of truth
                                    ▼
                    data/prices/<ticker>.csv        (~121 KB × 38 ≈ 4.6 MB)
                                    │
                    ┌───────────────┴───────────────┐
                    │  derived at docs-build time    │  (never committed)
                    ▼                                ▼
   docs/reports/<ticker>/kline.json      (future) technical context / QA
                    │
                    ▼
   .kline-widget  ──►  docs/javascripts/kline-chart.js  (+ Lightweight Charts)
        ▲                    ▲
        │                    └── already loaded site-wide (mkdocs.yml:153,160-161)
        │
   injected by build_docs.py on:
     • ticker index pages        data-src="kline.json"     (live, no as-of)
     • technical report pages    data-src="../kline.json"  data-as-of="<report date>"
```

Two crons, unchanged in shape:

| Workflow | Time (UTC) | Change |
|---|---|---|
| `update_kline_data.yml` | 03:30 | now updates `data/prices/*.csv` instead of `ai_gen_report/kline/*.json` |
| `deploy.yml` | 04:00 | `build_docs.py` now derives `kline.json` into `docs/` |

`data/**` is not in `deploy.yml`'s push-trigger paths (`.github/workflows/deploy.yml:13-22`),
exactly as `ai_gen_report/kline/` isn't today — so committing the store still does
not fire an extra deploy. Note `docs/javascripts/**` *is* a trigger, so phase-3
JS changes auto-deploy on push.

---

## 3. The store

### 3.1 Layout

```
data/prices/
  amd.csv
  2330.tw.csv
  0050.csv
  ...
```

Filenames use the existing `report_key()` convention (lowercased ticker, matching
the report directory names), so `data/prices/<key>.csv` ↔
`ai_gen_report/*/<key>/` ↔ `docs/reports/<key>/` line up without a mapping table.
`data/` already exists for small reference lists (32 KB), so this introduces no
new top-level directory.

### 3.2 Schema

```csv
date,open,high,low,close,volume,div,split
2026-07-29,505.10,519.88,502.31,516.00,28110000,,
2026-07-30,516.00,520.14,505.20,510.28,31840000,0.0,
2026-07-31,510.28,515.62,475.76,476.15,26520000,,4.0
```

| Column | Type | Notes |
|---|---|---|
| `date` | ISO `YYYY-MM-DD` | primary key, ascending, unique |
| `open,high,low,close` | decimal | as returned with `auto_adjust=False`; rounded by the existing `_round_price` rule (2dp, 4dp under $1) |
| `volume` | integer | `0` where upstream reports NaN, matching current behaviour |
| `div` | decimal or empty | cash dividend on that date; empty when none |
| `split` | decimal or empty | split ratio on that date; empty when none |

Header row always present. `\n` endings. No quoting (no field can contain a comma).
`div`/`split` are event columns rather than `adj_close` deliberately — see eval §5.3.

### 3.3 Invariants

These are the load-bearing properties. Each gets a test.

- **I1 — Byte-stable.** `write(read(f)) == f` byte-for-byte. Serialisation must be
  deterministic: fixed column order, one rounding implementation shared by the
  fetch and read paths, no float `repr` leakage. Violating I1 rewrites every line
  nightly and silently degrades the design back to what it replaced.
- **I2 — Idempotent.** Running the updater twice in a day leaves the file
  unchanged the second time.
- **I3 — Sorted & unique.** Dates strictly ascending, no duplicates.
- **I4 — Capped.** At most `KEEP_YEARS = 10` of bars; older rows are trimmed from
  the head. Trimming is the *only* routine edit to existing bytes, and it moves
  ~1 line/day at the top of the file.
- **I5 — Atomic.** Write to a temp file in the same directory, then `os.replace`.
  No partial files, ever.
- **I6 — Gated.** Never write a fetch that fails the sanity checks in §3.5.

### 3.4 Update algorithm

Nightly, per ticker:

```
1. bars_new   = fetch_history(symbol, years=10)      # full fetch, auto_adjust=False
2. gate(bars_new, bars_old)                          # §3.5 — abort this ticker on failure
3. bars_old   = load_store(key)                      # [] if the file is absent
4. merged     = upsert(bars_old, bars_new)           # bars_new wins on date collision
5. merged     = trim(merged, KEEP_YEARS)
6. write_if_changed(key, merged)                     # serialise, compare bytes, atomic replace
```

`bars_new` winning every collision is what makes splits, dividend re-adjustments
and upstream corrections a non-event: the restated history simply overwrites the
stored one, and that night's diff is large instead of one line. On an ordinary day
`merged` differs from `bars_old` by exactly one appended line (plus one trimmed
head line), so the diff is one line in each direction.

`upsert` keeps stored bars whose dates fall outside the fetched range. That only
matters if a fetch returns a short window; with a full 10y fetch it is a no-op
safeguard.

### 3.5 The sanity gate

A self-healing writer is also a self-destroying writer when upstream is wrong.
Abort the ticker (log, non-zero counter, leave the existing file untouched) if:

| Check | Threshold |
|---|---|
| Empty / missing fetch | any |
| Bar count regression | `len(bars_new) < 0.9 × len(overlapping stored bars)` |
| NaN or ≤0 in any of O/H/L/C | any |
| `high < low`, or close outside `[low, high]` | any |
| Non-monotonic or duplicate dates in the fetch | any |

The open/close containment check carries a **0.5 % tolerance**
(`OHLC_TOLERANCE`). Yahoo occasionally reports a close a fraction of a cent
outside the day's range through its own adjustment rounding, and a hard
comparison would freeze that ticker's updates indefinitely over noise. Wide
enough to absorb rounding, far too tight to admit a genuinely bad bar.

The job's existing "exit non-zero only if *nothing* succeeded" policy
(`generate_kline_data.py:209`) is kept, so one bad ticker doesn't fail the run
while a total outage still fails loudly.

A large diff is intentionally *not* a gate — it's the legitimate signal of a
split. It is logged instead (`⟳ RESTATED amd — 2,511 existing bars rewritten`),
so the cron log and the commit diff together form the audit trail. Any bad
rewrite is one `git revert` away.

**Provisional bars.** The `restated` signal deliberately ignores the *newest*
stored bar. 03:30 UTC is after the US close but mid-session in Taipei, so TW
tickers store a provisional bar that the next run corrects — a fetched bar
always wins, so it self-heals, but counting it would report `restated` nightly
and drain the signal of the meaning it exists for. This timing predates the
store; the old JSON job had exactly the same behaviour.

### 3.6 Module API

`scripts/analysis/data/prices.py` — cohesive with the existing data layer and
importable by both entry points as `from analysis.data.prices import …`
(`scripts/` is `sys.path[0]` for `python scripts/*.py`; this mirrors how
`build_docs.py:676` already shares `analysis.utils.mermaid`).

```python
KEEP_YEARS = 10
STORE_DIR  = ROOT / "data" / "prices"
FIELDS     = ("date", "open", "high", "low", "close", "volume", "div", "split")

# ── read path: pure stdlib, no third-party imports, offline-safe ──
def fmt_price(v) -> str                          # canonical price text
def fmt_event(v) -> str                          # canonical div/split text ("" when none)
def serialise(bars) -> str                       # the one canonical writer
def parse(text: str) -> list[dict]
def store_path(key, store_dir=None) -> Path
def load_store(key, store_dir=None) -> list[dict]      # [] when absent
def write_store(key, bars, store_dir=None) -> bool     # True only if bytes changed
def upsert(old, new) -> list[dict]               # fetch wins on collision
def trim(bars, years=KEEP_YEARS) -> list[dict]
def window(bars, *, days=None, as_of=None, lookback=0) -> list[dict]

# ── write path: yfinance imported lazily inside ──
def fetch_history(symbol, years=KEEP_YEARS) -> list[dict] | None
def gate(new, old) -> str | None                 # None == ok, else the reason
def update(key, symbol=None, years=KEEP_YEARS, store_dir=None) -> tuple[str, str]
#   → ("created" | "appended" | "restated" | "unchanged" | "skipped" | "failed", detail)

# ── ticker helpers (shared with the CLI) ──
def report_key(t) -> str; def to_yf_symbol(t) -> str; def currency_for(sym) -> str
```

The read path importing nothing beyond the standard library is a hard
requirement: `build_docs.py` must stay offline and dependency-light, and the test
suite must exercise the store without pandas or yfinance.

`window(..., lookback=N)` returns `N` extra bars *before* the requested range so
client-side moving averages are fully defined at the left edge — that's how MA200
becomes correct across a 360D window (G3 in the eval).

---

## 4. Derived payload

`build_docs.py` writes `docs/reports/<ticker>/kline.json` (and nothing to
`ai_gen_report/`). Same shape the widget already consumes, so `kline-chart.js`
needs no parser change:

```json
{"ticker":"AMD","symbol":"AMD","currency":"USD","updated":"2026-08-04",
 "bars":[{"t":"2025-01-02","o":..,"h":..,"l":..,"c":..,"v":..}, ...]}
```

Window: **560 bars** — 360 trading days of visible range plus 200 bars of
lookback so MA200 is defined at the left edge of the widest range. ~42 KB/ticker
uncompressed, ~1.6 MB across 38 tickers, none of it committed.

If a 5Y/MAX range is ever wanted, derive a tiered payload — daily bars for the
recent ~2y, weekly beyond — which keeps the file ~40 KB at any depth. Out of
scope now; the store makes it a build-time change only.

`ai_gen_report/kline/` is deleted and `.gitignore` gains `docs/reports/` coverage
already (it's ignored today), so the derived JSON is untracked by construction.

---

## 5. Widget changes

`docs/javascripts/kline-chart.js` — additive only. New per-widget `data-*`
attributes, each falling back to today's module constants:

| Attribute | Default | Effect |
|---|---|---|
| `data-as-of="YYYY-MM-DD"` | none | drop bars after this date, before building. **Required on report pages.** |
| `data-ma="30,60,200"` | `20,60,120` | which MA overlays to build; `+` suffix marks default-on (e.g. `30+,60+,200`) |
| `data-range="180"` | `180` | initially selected range button |
| `data-ranges="30,180,360"` | `30,180,360` | which range buttons to show |

Implementation notes:

- `as-of` filtering happens in `initAll()` between `fetch` and `build(node, data)`,
  so `build()` keeps its "these are the bars" contract and every downstream
  computation (MAs, volume colours, readout, range clamps) is automatically
  as-of correct.
- `palette().ma` gains entries for periods 30 and 200 (both currently absent).
- If `as-of` truncation leaves fewer than 2 bars, the existing `is-empty` /
  "chart unavailable" path already handles it.

---

## 6. Injection in `build_docs.py`

`kline_block()` (`build_docs.py:394`) is generalised:

```python
def kline_block(ticker, *, src="kline.json", as_of=None, ma=None,
                range_=None, ranges=None) -> str
```

Call sites:

| Page | Call |
|---|---|
| Ticker index (`docs/reports/<t>/index.md`) | unchanged defaults — live chart |
| Technical report body | `src="../kline.json"`, `as_of=<date parsed from filename>`, `ma="30+,60+,200"` |

The report date already comes out of the filename via the existing `_file_date()`
helper used by `within_retention()`.

**Legacy stripping.** In `copy_file()`, for technical report markdown, remove:

1. the `<details markdown="1">…📊 靜態圖表…</details>` block, and
2. the Plotly block — `<script src="…plotly…">` through the closing `</script>`
   of the `candlestick-chart` div,

then prepend the widget block. Doing this at copy time means all 1,313 existing
reports get the new chart with no source rewrite, and the change is reversible by
reverting one function. The one-off source cleanup (phase 4) is then purely a
disk-space measure, not a correctness requirement.

---

## 7. Deletions

| Target | Note |
|---|---|
| `scripts/analysis/data/charts.py` | whole module: `generate_plotly_candlestick_chart`, `_generate_mplfinance_chart`, `generate_candlestick_chart` |
| `pipeline.py:22` `build_technical_chart_embed` + its call at `:107` | reports are saved as pure LLM output again |
| re-exports in `data/__init__.py:7,12` and `utils/data_fetch.py:22` | |
| `plotly`, `kaleido`, `mplfinance` in `pyproject.toml` | verify no other importer first |
| `ai_gen_report/kline/` | replaced by the store |
| 1,299 `technical_chart_*.png` (147 MB) | one-off |
| Plotly blocks in 1,313 `.md` (61.7 MB) | one-off, via a `maintain_ai_gen_report.py` subcommand |
| `maintain_ai_gen_report.py:61` `technical_chart_` handling | after the PNGs are gone |
| `fix_static_chart_embed()` (`build_docs.py:771`) | only if no other report type embeds raw-HTML images — check first |

---

## 8. Phases

Each phase is independently committable and leaves the site working.

### Phase 1 — the store ✅ done
- `scripts/analysis/data/prices.py` (§3.6) + `tests/test_prices.py` (49 tests).
- `scripts/update_prices.py` — the CLI, with `--only-missing` and `--dry-run`.
- `update_kline_data.yml` runs it and commits `data/prices/`.

**Two deviations from the plan as written, both simplifications:**

1. A **new** `scripts/update_prices.py` rather than a rewritten
   `generate_kline_data.py`. The old script keeps producing
   `ai_gen_report/kline/*.json` until phase 2 switches `build_docs.py` over, so
   phase 1 changes nothing user-visible and the site cannot go stale mid-migration.
   Both scripts run in the workflow for now; the legacy step is deleted in phase 2.
2. **No `--backfill` flag.** Since the full history is fetched every run, a first
   run *is* the backfill — one code path instead of two.

**Verified:** 37 CSVs written (the universe is 37, not 38 — one stale `kline`
JSON had no corresponding report directory), **3.3 MB** total, largest 2,512 bars.
An immediate second run reported `unchanged` for all 35 US tickers and left
`git status` clean, confirming I1 + I2 against real Yahoo data rather than only
fixtures. The two TW tickers appended a provisional bar, as expected mid-session.

### Phase 2 — derive the payload ✅ done
- `build_docs.py` derives `docs/reports/<ticker>/kline.json` from the store:
  `kline_bars()` → `kline_payload()` → `write_kline_payload()`, a 560-bar window
  (`KLINE_VISIBLE_BARS` + `KLINE_LOOKBACK_BARS`).
- `_current_price()` (feeds the price-target table) reads the store.
- `kline_block()` generalised now rather than in phase 3, since the signature
  change belongs with the rest of the payload work: `src` / `as_of` / `ma`.
- Deleted `scripts/generate_kline_data.py`, `ai_gen_report/kline/` (38 files),
  `SRC_KLINE` and the workflow's legacy step. `okf/datasets/kline-data.md`
  re-documented for the CSV store.
- `prices` is imported at `build_docs.py` module scope. Safe: the `analysis`
  package defers every heavy dependency to inside its functions, so the import
  costs 8 ms and pulls neither pandas nor yfinance — the docs build stays
  offline and dependency-light.

**Verified:** the derived payload matches the retired JSON **bar for bar** — 300
overlapping bars, zero price mismatches, zero volume mismatches — while carrying
560 bars (back to 2024-05-08) instead of 300, at 42 KB. `_current_price` reads
correctly for US and TW tickers off the real store. `docs/reports/` is
gitignored, so the derived payload is untracked by construction. No user-visible
change, as intended.

> A sample build showed no price-target table for AMD, which looked like a
> regression but is a sampling artifact: `SAMPLE_LIMIT` had picked AMD's
> 2026-06-06 fundamental, whose scenario table isn't parseable (0 scenarios). The
> real newest report (2026-08-03) yields 3 scenarios and renders the table. Worth
> remembering when reading sample-build output.

### Phase 3 — the report-page chart ✅ done
- `kline-chart.js`: `parseMa()` / `parseRanges()` / `readOpts()` read the
  per-widget attributes; `build(node, data, opts)` takes them instead of the
  module constants. As-of truncation happens in `initAll()` between `fetch` and
  `build`, so moving averages, volume colours, the readout and range clamping are
  all as-of correct without any of them knowing about as-of.
- `maColor()` with a neutral fallback, plus MA30/50/200 palette entries.
- `report_chart_block()` + `REPORT_MA = "30+,60+,200"`, injected via a new
  `chart_block` parameter on `copy_file()` — placed after the front matter and
  header table, above the report body, exactly where the Plotly embed used to sit.
- `strip_legacy_chart_embed()` removes the baked-in PNG `<details>` block and the
  inline Plotly document (plotly emits a whole `<html>` document, so the embed is
  one well-delimited block). Applied to all copied markdown, not just when a
  chart is injected — the pipeline no longer emits it and a dead 3 MB CDN fetch
  helps no one.
- `daily_analysis.yml` seeds the store for a first-time ticker
  (`update_prices.py "$TICKER" --only-missing`, `continue-on-error`).

**One addition beyond the plan:** the footer shows `As of <date>` / `資料截至`
instead of `Updated <date>` when `as_of` is set. Reporting the store's own
freshness stamp on a chart pinned to a past date would claim a currency the
chart doesn't have.

**Verified** against 59 built AMD technical pages: every page's `data-as-of`
equals its own filename date (59/59, no mismatches); zero residual
`candlestick-chart` / `plot.ly` / `technical_chart_` references; no widget on
fundamental pages; built markdown 50 % smaller (5.5 MB → 2.8 MB for AMD alone).
Regex coverage was checked across the whole corpus first: 1,313 Plotly embeds and
1,311 PNG blocks matched, **zero** files left with residual chart markup, and no
`fundamental/` or `stock/` report carries an embed at all.

### Phase 4a — stop generating chart markup ✅ done
Non-destructive: nothing already committed is touched, so this needs no
production verification first.

- Deleted `scripts/analysis/data/charts.py`, `build_technical_chart_embed()` and
  its call in `pipeline.py`, and the re-exports in `data/__init__.py` and
  `utils/data_fetch.py`.
- Dropped `plotly`, `matplotlib` and `mplfinance` from `pyproject.toml`,
  `tests.yml` and `daily_analysis.yml`. No importer of any of them remained.
- Deleted `tests/test_chart.py` (9 tests for code that no longer exists) and the
  two volume-less chart cases in `test_data_fetch_net.py`.
- `docs/ARCHITECTURE.md` re-documented.

**Verified:** 398 tests green; `pipeline.__all__` and `analysis.data.__all__` are
clean; importing the pipeline still pulls no pandas. New technical reports are now
pure LLM output.

### Phase 4b — the one-off cleanup ⏸ gated
**Deliberately not done in this pass.** Deleting 1,299 PNGs (147 MB) and
stripping inline Plotly from 1,313 committed reports (61.7 MB) is the one
irreversible step in the migration — recoverable from git history, but not from
the working tree. It buys disk space only: `strip_legacy_chart_embed()` already
means no reader ever sees the legacy markup.

- **Gate:** phase 3 verified on the deployed site (report-page charts render,
  as-of dates correct, no console errors).
- Then: delete the PNGs, strip the embeds from `ai_gen_report/technical/**.md`
  via a `maintain_ai_gen_report.py` subcommand, and drop the `technical_chart_`
  handling at `maintain_ai_gen_report.py:61`.
- Also then: check whether any other report type still embeds raw-HTML images
  before removing `fix_static_chart_embed()` — no `fundamental/` or `stock/`
  report carries a chart embed today, but the helper may serve other images.

### Phase 5 — tests ✅ done
**432 passing, 1 skipped** (was 391 before this work; 11 obsolete tests deleted).

| File | Coverage |
|---|---|
| `tests/test_prices.py` (new, 59) | I1 byte-stability round-trip incl. the $1-boundary flip-flop and scientific-notation traps; I2 idempotence; I3 sort/dedup; I4 trimming (leap day, clock-independence); upsert-wins-on-collision; **simulated split**; every gate rule incl. the rounding tolerance; `window()` with `as_of` + `lookback`; `fetch_history()` against a fake `yfinance` (column mapping, NaN rows, NaN volume, zero events, `auto_adjust=False`/`actions=True`, and that its output both passes `gate()` and round-trips through the store) |
| `tests/test_update_prices.py` (new, 18) | CLI: ticker discovery (union, dedup, missing and corrupt schedule), every status path, `--only-missing`, `--dry-run` writing nothing, and the exit-code policy — non-zero on a total outage, zero when one ticker of several fails |
| `tests/test_build_docs.py` (73) | payload derivation, window capping, TWD mapping, idempotent writes, `kline_block()` attributes, `../kline.json` on report pages, `report_chart_block()` only for technical reports, legacy embed stripping (incl. idempotence), and `copy_file()` swapping a legacy embed for the widget with front matter intact |
| `tests/test_generate_analysis.py` (12) | generated reports contain **no** chart markup for technical *or* fundamental, no PNG is written, and `build_technical_chart_embed` is gone from `pipeline.__all__` |
| `tests/js/kline_chart_harness.mjs` + `tests/test_kline_chart_js.py` (new, 32 assertions) | the widget itself — see below |
| deleted | `tests/test_chart.py` (9 tests for `charts.py`), 2 chart cases in `test_data_fetch_net.py` |

All offline: the store's read path is stdlib-only, every fetch is mocked, and the
JS harness has no npm dependencies.

#### Testing the widget
`kline-chart.js` was the one piece pytest cannot reach, and it owns the as-of
contract. `tests/js/dom_shim.mjs` provides the small slice of DOM the widget
actually uses plus a fake Lightweight Charts that records what it was asked to
draw; the harness runs the **shipping file** — not a copy — and asserts on the
result. Covered: as-of truncation (candles, volume, readout, header price, footer
label), `data-ma` parsing incl. the `+` default-on suffix and unparseable input,
`data-range`/`data-ranges` incl. a range outside the offered set, `zh`
localisation, empty and fully-truncated payloads degrading to the "unavailable"
state, and range-button clicks driving the chart.

The harness was **mutation-tested** while being written — disabling as-of
truncation, ignoring `data-ma`, and swapping the footer label each produced
failures. Two weaknesses surfaced that way and were fixed: asserting MA
*visibility* alone couldn't distinguish the report preset from the defaults
(both are `[on, on, off]`), so the legend labels are asserted too; and the shim's
HTML parser flattened the tree on a stray `</i>`, which had made the legend
assertions read `[""]` rather than fail loudly.

---

## 8b. End-to-end verification (AMD, run locally 2026-08-04)

`tests/js/render_report_page.mjs` closes the loop: it scrapes the widget `<div>`
out of a **built** page, loads the **derived** `kline.json`, drives the shipping
widget over both, prints what the chart drew, and exits non-zero if the as-of
contract is violated — so it can gate a release rather than merely inform one.

The run: store refresh → report generation → docs build → widget render.

| Step | Result |
|---|---|
| `update_prices.py AMD` (real Yahoo fetch) | `unchanged`, 2,512 bars — idempotent against live data |
| `generate_analysis.py amd --analysis-type technical-analysis` | real `fetch_data` (26 keys, 500 rows of history), real context (7,228 chars), real publish; **LLM call stubbed — no provider key locally** |
| generated report | **378 bytes**, versus ~74 KB for the same report a day earlier. No `candlestick-chart`, `plot.ly`, `technical_chart_`, `<details>` or `<html>`. Mermaid quoted at source |
| `build_docs.py` | `kline.json` derived (560 bars, 2024-05-08 → 2026-08-03, 42 KB); widget injected as `data-src="../kline.json" data-as-of="2026-08-04" data-ma="30+,60+,200"` |
| widget render, 60 pages | **60/60 built and passed**, MA200 defined across the whole visible range (361 points of 361 visible bars — the 200-bar lookback earning its keep) |

as-of truncation on the real payload, with the drop count falling monotonically as
reports get newer — 2026-06-02 → 42 bars dropped, 06-10 → 36, 06-28 → 25,
08-04 → 0 (nothing to drop: the newest bar is the 08-03 close).

**A bug in the e2e script itself, found and fixed during the run:** the widget
truncates `data.bars` in place, so the first version measured the drop count
*after* rendering and reported "0 past as-of, 0 dropped" for a page that had
visibly dropped 42 bars. The truncation was working; the assertion was vacuous.
It now snapshots the payload before rendering and passes a clone to the widget.

**Not covered locally:** no real browser was involved — no mkdocs, selenium or
chromedriver installed, and no provider key for a live LLM call. The widget's
*logic* is verified against the real payload; its *pixels* are not. A headless
Chrome pass over `mkdocs serve` is the remaining gap, and is the natural gate for
phase 4b.

## 9. Deferred, with triggers

| Item | Trigger to revisit |
|---|---|
| **Change-detecting sentinel** (incremental fetch + compare all overlapping bars; consistent ratio → restatement → full refetch; newest-bar-only mismatch → ordinary revision; inconsistent → anomaly + QA flag) — plus a weekly full-refetch reconciliation into a temp dir, diffed against the store, to prove the fast path never drifted | when the nightly full fetch becomes the bottleneck — roughly a few hundred tickers, or a `update_kline_data.yml` runtime approaching its 20-minute timeout |
| **`compute_technicals()` reads the store** (`context/__init__.py:156,197`) — 42 fewer yfinance history calls/day, reports reproducible from committed data | needs two things resolved first: the store refreshes at 03:30 UTC while analysis jobs run across the whole day, so staleness policy matters; and `sources.py:363` fetches `history(period="2y")` with yfinance's *default* `auto_adjust` (True in current versions) whereas the store is `auto_adjust=False` — adjustment semantics must be reconciled or technicals will shift |
| **Tiered / 5Y-MAX payloads** (daily recent + weekly beyond) | when someone asks for a range beyond 360D |
| **Store QA checks** (trading-day gaps, unexplained >25% overnight moves without a `split` value) folded into `qa_report_quality.yml` | after phase 4, once the store has a few weeks of history |
| **Total-return charts** from the `div` column | on request; the schema already supports it |

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| I1 breaks silently and every night rewrites every line | round-trip test in CI; phase-1 acceptance check is "second run leaves `git status` clean" |
| A bad upstream fetch overwrites good history | sanity gate (§3.5) + atomic writes + `git revert`; large rewrites are logged explicitly |
| Report pages differ from the chart the LLM described | `data-as-of` is mandatory; asserted in phase-3 acceptance |
| A report older than the 10y store shows an empty chart | retention is 120 days, so unreachable in practice; the `is-empty` path handles it gracefully |
| New ticker's first report has no chart | `--only-missing` step in `daily_analysis.yml` |
| Removing `fix_static_chart_embed()` breaks another report type's images | check other report types for raw-HTML `<img>` before deleting; otherwise keep it |
| Instant-nav chart leak on report pages | existing `live[]` teardown already covers it; asserted in phase-3 acceptance |

## 11. Rollback

Phase-scoped and cheap:

- **Phases 1–2** — revert the commits; `ai_gen_report/kline/` comes back with them
  and the site is unchanged either way.
- **Phase 3** — revert `kline_block()`/`copy_file()`; the stripping is build-time
  only, so the 1,313 committed reports still contain their original Plotly and
  render exactly as before.
- **Phase 4** — the destructive one. Deletion of the PNGs and inline Plotly is
  recoverable from git history but not from the working tree, so it lands **only
  after phase 3 is verified in production**.
