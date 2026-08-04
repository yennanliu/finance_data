# Chart Unification — Feasibility Evaluation

**Question:** the per-ticker index page already renders an interactive k-line chart
(30D / 180D / 360D, MA overlays) from a shared OHLCV JSON. Can the **technical
report pages** reuse that same data and renderer instead of baking their own
Plotly HTML + PNG into every report? And can the underlying price data become an
incrementally-maintained store that any window can be sliced from?

**Answer:** yes to both. The renderer is already loaded site-wide, data coverage
is already complete, and the change is mostly deletion.

**Evaluated:** 2026-08-04 · all sizes are real measurements of the working tree at
commit `5e0e699b`.
**Status:** evaluation accepted; build plan in [`PRICE_STORE_DESIGN.md`](PRICE_STORE_DESIGN.md).

---

## 1. Executive summary

Two chart pipelines exist side by side and share nothing:

| | Index-page hero chart | Technical-report chart |
|---|---|---|
| Data source | `ai_gen_report/kline/<ticker>.json` | `data["hist"]`, re-fetched per report |
| Window | 300 daily bars (~14 months) | `hist.tail(200)` |
| Renderer | `docs/javascripts/kline-chart.js` + vendored Lightweight Charts | `scripts/analysis/data/charts.py` → Plotly HTML + kaleido PNG |
| Injected by | `build_docs.py:394` `kline_block()` at build time | `pipeline.py:22` baked into the `.md` at generation time |
| MA overlays | 20 / 60 / 120 (togglable) | 30 / 60 / 200 (fixed) |
| Ranges | 30D / 180D / 360D toggle | fixed 200 bars |
| Payload in git | **860 KB total, all 38 tickers** | **61.7 MB inline Plotly + 147 MB PNG** |
| Page weight | ~50 KB vendored library, shared/cached | ~46 KB inline JSON + ~3 MB Plotly CDN fetch |

The report-side pipeline costs roughly **250,000×** more bytes per rendered chart
than the shared one, produces a *less* capable chart (no range toggle, no MA
toggle, no crosshair readout), and is on the critical path of every technical
analysis job via kaleido — a dependency that already needed an mplfinance
fallback because it is unreliable.

Unifying on the shared pipeline removes ~208 MB from the working tree, stops
~3.4 MB/day of new chart payload, drops three heavy rendering dependencies, and
gives report pages a *better* chart than they have now.

---

## 2. Measurements

### 2.1 Shared k-line data (current)

| Metric | Value |
|---|---|
| Tickers with `kline/<ticker>.json` | 38 |
| Total size | 860 KB |
| Example (`amd.json`) | 22,690 B / 300 bars → **~76 B per bar** |
| Fetch | `yf.Ticker.history(period="2y", auto_adjust=False)`, trimmed to `KEEP_BARS = 300` |
| Refresh | `update_kline_data.yml`, cron 03:30 UTC, commits the JSON |
| Consumed by | `build_docs.py` → copied to `docs/reports/<ticker>/kline.json`, fetched page-relative |

### 2.2 Report-side chart payload (current)

| Metric | Value |
|---|---|
| `ai_gen_report/technical/` total | **259 MB** |
| Technical `.md` files | 1,427 files, **97.4 MB** |
| …of which inline Plotly blocks | **61.7 MB (63% of all technical markdown)** |
| Files carrying a Plotly block | 1,313 of 1,427 |
| Average Plotly block | **46 KB per report** |
| `technical_chart_*.png` | 1,299 files, **147 MB** (avg ~115 KB) |
| PNGs inside the 120-day publish retention | **1,299 of 1,299 → all 147 MB is copied into `docs/` and deployed** |

### 2.3 Growth rate

21 technical jobs/day (`CLAUDE.md`: 42 jobs/day = 21 tickers × 2 types):

```
21 × 46 KB  (Plotly)  ≈ 1.0 MB/day
21 × 115 KB (PNG)     ≈ 2.4 MB/day
                      ─────────────
                      ≈ 3.4 MB/day  ≈ 1.2 GB/year
```

Under the shared pipeline the marginal cost of a report's chart is **zero bytes** —
the JSON already exists and is already refreshed by an existing cron.

---

## 3. Why the reuse is cheap

Three properties of the current code make this a small change rather than a port:

1. **The renderer is already on every page.** `mkdocs.yml:153` loads
   `stylesheets/kline.css`; `mkdocs.yml:160-161` loads the vendored Lightweight
   Charts build and `kline-chart.js`, site-wide. A technical report page can
   render the widget **today** with no new assets — only a `<div>` is missing.

2. **`kline-chart.js` is already generic.** It scans for
   `.kline-widget:not([data-kline-ready])` on every MkDocs Material `document$`
   emission, reads `data-ticker` / `data-src` off each node, and builds one
   independent controller per widget (with theme re-colouring and instant-nav
   teardown already handled). Per-widget behaviour is a matter of reading more
   `data-*` attributes — additive, no restructuring.

3. **Data coverage is already a superset.** All **27** ticker directories under
   `ai_gen_report/technical/` have a `kline/<ticker>.json` (38 exist).
   `generate_kline_data.py:82` `discover_tickers()` derives its universe from the
   union of `.ticker_schedule.json` and existing report directories, so coverage
   stays automatic as tickers are added.

---

## 4. Gaps that must be closed

| # | Gap | Fix | Cost |
|---|---|---|---|
| G1 | Report pages sit one directory deeper (`/reports/amd/technical_analysis_X/`), so a page-relative `kline.json` resolves wrong. MkDocs rewrites relative paths in Markdown but **not** in raw HTML. | Emit `data-src="../kline.json"`; the depth is known at build time. | trivial |
| G2 | A shared, always-current JSON would show **today's** prices under text written about a past snapshot. | `data-as-of="<report date>"` → truncate bars to ≤ that date. Retention is 120 days (`build_docs.py:69`) so the window always covers published reports. **Required, not optional.** | ~10 lines JS |
| G3 | Widget offers MA 20/60/120; report chart uses MA 30/60/200. With 300 stored bars, MA200 is only defined over the most recent 100. | Per-widget `data-ma="30,60,200"`, and enough stored history to define MA200 across the whole visible range. | small |
| G4 | 1,313 existing reports have Plotly baked into the committed markdown. | Strip on copy in `build_docs.py` (works retroactively, reversible) **and** a one-off cleanup of the source files. | ~15 lines + script |
| G5 | A brand-new ticker's first report has no `kline.json` until the 03:30 UTC cron runs. | Add `generate_kline_data.py <ticker> --only-missing` as a step in `daily_analysis.yml`. | trivial |

**Explicitly not a gap:** the chart disappearing from the raw `.md` as rendered on
github.com. The widget only works on the docs site, and the `<details>` PNG is
what github.com renders today. **Decision: we do not care about the github.com
view** — this is what makes the PNG pipeline pure deletion rather than a
"keep one PNG per ticker" compromise.

Also not a gap: analysis quality. The chart is presentation only. `data["hist"]`
is fetched for `compute_technicals()` (`context/__init__.py:156,197`)
independently of chart rendering, so deleting the chart code changes no report
text.

---

## 5. Should the price data become an incremental store?

Yes. The current model re-fetches 2 years and rewrites a fixed 300-bar sliding
window every night. That fixes the available window at build time: a 360D range
toggle is the most the payload can support, MA200 is under-defined at the long
end, and any future range (1Y / 3Y / 5Y) needs a schema change.

A committed **10-year store** decouples what is *stored* from what is *served*:

| | Sliding-window JSON (now) | 10-year CSV store (proposed) |
|---|---|---|
| Window available | fixed 300 bars | any slice up to 10y |
| Size | 860 KB (38 tickers) | **~4.6 MB** (2,520 bars × ~48 B/line × 38) |
| Bytes per bar | ~76 (compact JSON) | ~48 (CSV line) |
| Daily commit diff | whole file per ticker | 1 appended line per ticker |
| Reviewable | no (single-line JSON) | yes, line-by-line in the diff |
| Derived payloads | is the payload | feeds `kline.json`, and optionally `compute_technicals` |

CSV over JSON specifically because JSON must be rewritten whole; CSV's existing
rows stay byte-identical, so the nightly commit is an append.

> **Framing correction, recorded honestly:** an earlier draft of this analysis
> quoted "860 KB/day → 1.8 KB/day" as the headline win. That figure describes
> **working-tree and commit-diff churn**; git's delta compression at pack time
> narrows the on-disk gap considerably. Treat it as a claim about diff
> reviewability, not repo size. The durable wins — independent of compression —
> are the sliceable 10-year window, reviewable diffs, one source of truth feeding
> several derived artifacts, and derived `kline.json` leaving git entirely.

### 5.1 The splits hazard, and why it dissolves

An append-only store of Yahoo prices is not self-consistent across a stock split.
Yahoo's historical OHLC is **split-adjusted retroactively** (`Adj Close` adds
dividend adjustment on top), so on a split every historical bar is restated.
Today's job self-heals because it rewrites everything nightly; a naively
append-only store would silently keep pre-split bars next to post-split ones.

The resolution is to notice that **fetch strategy and write strategy are
independent**:

- *Fetch:* full 10y, or incremental (`start = last_stored_date − 10d`)
- *Write:* full rewrite, or merge-and-write-only-what-changed

The git-churn goal is met entirely by the **write** side. And full fetching is
essentially free at this scale: the existing job already pulls `period="2y"` for
38 tickers inside a 20-minute timeout, and 10y is the same one call per ticker
with more rows in the response.

**Therefore: fetch full 10y nightly, write incrementally.** After a split,
upstream hands over the whole restated history; it is written out and that day's
diff is simply large. No split detection, no epsilon, no ratio heuristics, no
adjustment bookkeeping — and the store is verified byte-for-byte against upstream
every night by construction. Dividend re-adjustments, exchange corrections and
bad historical bars are covered by the same mechanic.

This is also robust to our own assumptions: if Yahoo's adjustment semantics
differ from the description above in some case, a full nightly fetch still writes
exactly what upstream says. It never has to reason about adjustment at all.

A change-detecting sentinel (compare all overlapping bars; consistent ratio →
restatement → full refetch) is only needed if the universe grows large enough
that full fetching becomes the bottleneck. Deferred, with the trigger condition
recorded in the design doc.

### 5.2 What has to be right instead

Removing the splits problem shifts the risk onto three concrete invariants,
which are cheap to enforce and easy to test:

1. **Byte-stable serialisation** — unchanged bars must serialise identically on
   every run (same rounding, column order, line endings). If this slips, every
   night rewrites every line and the design silently collapses into the model it
   replaced.
2. **A sanity gate before writing** — self-healing is also self-destroying if
   upstream is wrong. Refuse to write when a fetch returns fewer bars than the
   store already holds, or contains NaN/zero closes.
3. **Atomic writes** — temp file + rename, so an interrupted run cannot leave a
   half-written store.

### 5.3 One schema refinement

Store dividend and split **event columns**, not `adj_close`. `adj_close` is
retroactively restated on *every dividend*, so each payer would rewrite its whole
file quarterly. Event columns support the same total-return derivation with zero
restatement, because plain OHLC is untouched by dividends.

---

## 6. Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Technical report pages reuse the shared k-line data + renderer | §3 — renderer already loaded, coverage already complete |
| D2 | Delete the Plotly HTML **and** PNG pipeline outright | §4 — the github.com view is explicitly out of scope |
| D3 | Introduce a committed CSV price store, **10-year cap** | §5 — ~4.6 MB, covers every window we'd realistically serve; raisable later by one flag |
| D4 | **Fetch full 10y nightly, write incrementally** | §5.1 — makes splits and every other restatement a non-event |
| D5 | Store `div` / `split` event columns, not `adj_close` | §5.3 — avoids quarterly full-file restatement |
| D6 | `kline.json` becomes a build artifact derived by `build_docs.py`, removed from git | derived data should not be committed; keeps the docs build offline |
| D7 | `data-as-of` truncation is mandatory for report-page charts | G2 — otherwise old reports show today's prices |
| D8 | Defer the change-detecting sentinel | §5.1 — unnecessary while full fetching is cheap |

---

## 7. Effort

| Phase | Work | Effort |
|---|---|---|
| 1 | `scripts/prices.py` store module + backfill; `generate_kline_data.py` rewritten against it | ~half day |
| 2 | `build_docs.py` derives `kline.json` from the store; drop it from git | small |
| 3 | Per-widget `data-as-of` / `data-ma` / `data-range`; generalised `kline_block()`; inject on technical report pages | ~half day |
| 4 | Strip legacy embeds on copy; delete `charts.py` + `pipeline.py:22`; one-off cleanup (−208 MB) | small, mostly deletion |
| 5 | Tests: new `test_prices.py`, rework `test_chart.py` (28 refs), extend `test_build_docs.py` | moderate |

**Total ≈ 1–1.5 days.** Phases 1–2 are invisible to the site (the JSON keeps
landing in the same place, just derived), so they land and get verified before
anything user-facing changes in phase 3.

Full breakdown, schemas and acceptance criteria: [`PRICE_STORE_DESIGN.md`](PRICE_STORE_DESIGN.md).

---

## 8. Expected outcome

| Metric | Before | After |
|---|---|---|
| Chart payload in working tree | ~208 MB (61.7 MB Plotly + 147 MB PNG) | ~4.6 MB store, 0 committed derived data |
| New chart bytes per day | ~3.4 MB | 0 (store grows ~1.8 KB/day) |
| Report page chart JS | ~3 MB Plotly from CDN | shared vendored ~50 KB, already cached |
| Report chart features | fixed 200 bars, fixed MAs | 30/180/360 toggle, togglable MAs, crosshair OHLC readout, as-of correct |
| Rendering deps on the analysis critical path | plotly, kaleido, mplfinance | none |
| Windows servable | 360D max | any slice up to 10y |
