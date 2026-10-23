# Fundamental Report — Review Checklist

*English · [繁體中文](FUNDAMENTAL_REPORT_REVIEW.zh-TW.md)*

**Purpose:** list everything that shapes a `fundamental-analysis` report, from the
data we fetch to the page we publish, so that each part can be reviewed on its
own. Each section names the files involved, what to check, and any problems
already found in a real report.

**Worked example:**
[`/reports/amd/fundamental_analysis_2026-10-21_gemini/`](https://yennj12.js.org/finance_data/reports/amd/fundamental_analysis_2026-10-21_gemini/)
(source: `ai_gen_report/fundamental/amd/fundamental_analysis_2026-10-21_gemini.md`,
75 KB, 11 chapters, 15 Mermaid blocks, 214 table rows).

**Fact-checked:** the latest fundamental report of **all 37 tickers**, figure by
figure, against SEC XBRL filings, statements and market data. See
[§12](#12-fact-check-every-tickers-latest-fundamental-report-vs-filings).

---

## 0. Pipeline map — what there is to review

| # | Stage | Source of truth | Review question |
|---|-------|-----------------|-----------------|
| 1 | Data fetch | `scripts/analysis/utils/data_fetch.py` | Is the raw data correct, fresh, and complete? |
| 2 | Context assembly | `scripts/analysis/context/__init__.py` (the *"all other types"* branch, L312+) | Does the model get every input the prompt asks it to use? |
| 3 | Prompt | `scripts/analysis/prompts/fundamental.txt` (1029 lines) | Are the instructions consistent, achievable, and free of anchors? |
| 4 | System message | `scripts/analysis/prompts/gemini_system.txt` / `openai_system.txt` | Does it agree with the prompt? |
| 5 | Model + params | `scripts/analysis/config/providers.py`, `config/__init__.py`, `utils/llm.py` | Do the model, token budget, temperature and fallback chain fit an 11-chapter report? |
| 6 | Output format | the report itself (11 chapters, frontmatter) | Is the structure stable enough for readers *and* for `build_docs.py` parsers? |
| 7 | Valuation arithmetic | Ch.1 dashboard, Ch.7.3, Ch.8 | Do the numbers recompute, and do Ch.1 and Ch.8 agree? |
| 8 | Run-to-run stability | `ai_gen_report/fundamental/<t>/` (one report per ticker per day) | Do the conclusions move only when the inputs move? |
| 9 | QA gates | `scripts/analysis/validate/__init__.py`, `review_report_quality.py`, `prompts/qa_review.txt` | Which of the defects above does QA actually catch? |
| 10 | Publishing | `scripts/build_docs.py` (`report_meta_block`, `ticker_hero_block`, `parse_scenario_targets`, `scenario_rail`) | Does the published page show the report's numbers correctly? |
| 11 | Schedule / cost | `.github/workflows/daily_analysis.yml`, `scripts/.ticker_schedule.json` | Is daily regeneration of every ticker worth it? |
| 12 | Fact-check | SEC XBRL `companyfacts`, statements, market close | Are the report's figures true? (all 37 tickers in §12) |

---

## 1. Data fetch & context

Files: `utils/data_fetch.py`, `context/__init__.py` (L312–378), `data/prices.py`, `data/fundamentals.py`

- [ ] **🔴 Single-quarter fields that read as TTM** (confirmed in §12). The
  `PROFITABILITY & GROWTH` block (`context/__init__.py:52–56`) passes yfinance
  `info` fields with labels that don't say which period they cover.
  `revenueGrowth`, `earningsGrowth` and `operatingMargins` all describe the
  **latest quarter**. `earningsQuarterlyGrowth` is that quarter's change
  *year over year*, but it is labelled "(QoQ)". The context also prints
  TTM statements, so the model joins the two. All three reports write
  "TTM 營收 … (YoY +X%)" (TTM revenue with a YoY rate) and "TTM 營業利益率 X%"
  (TTM operating margin), using the quarterly values.
  Fix: label each field with its period, or compute TTM growth and margins from
  the statements ourselves.
- [ ] **🔴 `Free Cash Flow` is yfinance's "levered FCF"**, not OCF − capex
  (`context/__init__.py:70`). TSLA: $4.84B vs $5.76B. AMD: $8.84B vs $8.40B.
  In the TSLA and AMD reports, the model then **made up a capex figure** so that
  the FCF table adds up to the yfinance number. Across all tickers, FCF is
  wrong in 18 of 25 reports that state it, and capex is back-solved in 5
  (§12.3).
- [ ] **🔴 Ratios mix currencies for ADRs.** TSM (TWD) and SKHY (KRW) are quoted
  in USD, and yfinance's `info` ratios divide local-currency cash flows by a
  USD market cap. The reports print "FCF Yield 56.25%" / "EV/EBITDA 4.08x"
  (TSM) and "FCF Yield 53.4%" / "Forward P/E 4.16x" (SKHY). When
  `financialCurrency ≠ currency`, convert the figures or leave these fields out.
- [ ] **🔴 The SEC fundamentals store never holds the current fiscal year.**
  `fundamentals.fiscal_years()` (`data/fundamentals.py:352`) returns only
  *completed* fiscal years, and `discrete_quarters()` keeps quarters inside
  them. Q1–Q3 of a year in progress are therefore always dropped. As of
  2026-10-23, AMD / TSLA / PLTR stop at 2025-12. SEC already has their 2026
  10-Qs (TSLA's Q3 was filed 2026-10-22). Every ticker's last row is its last
  fiscal year-end, so the Market Data page is up to three quarters stale, and
  `update_fundamentals.py` reports "unchanged".
- [ ] **Inputs the prompt requires but the context does not supply.** The
  fundamental branch sends annual/quarterly IS, annual BS, annual + quarterly CF,
  `info` ratios, Finviz / StockAnalysis / Roic.ai text, earnings, upgrades and news.
  The prompt then demands:
    - **Peer multiples** (rule 4: "2-3 家直接競爭對手的估值倍數"; §7.1). No peer data is
      fetched, so these numbers come from model memory. In the AMD example, §8.8
      weights a "同業 Forward P/E (38.0x) 參考 NVDA" at 25%.
    - **WACC inputs** (risk-free rate, ERP, cost of debt, tax rate). Only `beta` is
      provided.
    - **DCF inputs** (D&A, ΔWC, interest expense, diluted share count). These are
      not in `bs_rows` / `cf_rows`.
    - **Historical valuation range** (§7.2). We already compute P/E bands in
      `data/fundamentals/` (Market Data → Valuation), but the context never reads
      that store.
- [ ] **Two sources of truth.** The report's figures come from a live yfinance
  fetch. The Market Data tab on the same ticker page comes from the committed
  `data/prices` + `data/fundamentals` stores. Decide whether the context should
  read the stores, so the report and the page cannot disagree.
- [ ] **Scraper failures are invisible to readers.** If Finviz, StockAnalysis or
  Roic.ai fails, the context gets `(no data)`. The report header still claims
  "數據來源：Yahoo Finance, Finviz, StockAnalysis, Roic.ai", because that line is
  hardcoded at `fundamental.txt:90`. We should either record which sources
  actually returned data (in the frontmatter or the header) or drop the claim.
- [ ] **Truncation.** The business summary is cut to 500 chars. `df_to_text`
  sends only 4Y annual / 4Q quarterly data, which is short for an 11-chapter
  report with a 5–10Y DCF.
- [ ] **Non-US tickers and ETFs** (`0050`, `2330.TW`, …) go through the same
  branch and prompt. Check currency, units (TWD vs USD) and whether the 11-chapter
  stock template makes sense for an ETF.
- [ ] **News comes from untrusted text** (RSS / scraped headlines). See the
  prompt-injection note in CLAUDE.md. The generator has the same exposure that
  the QA judge does.

## 2. Prompt — `prompts/fundamental.txt`

- [ ] **Example numbers anchor the output.** Rule 18 (L75–76) uses
  `WACC = … = 9.41%` and `$325` as its worked example. **165 of the 795**
  fundamental reports dated 2026-10 contain the string `9.41%`. AMD's 10-18 and
  10-19 reports both state WACC = 9.41%, and on 10-20 it was 10.97%. On
  2026-10-22 alone, 6 of 36 reports used WACC = 9.41% (AMZN, AVAV, GOOG, NBIS,
  SOXQ, SPCX; §12.3). Fix: replace
  the example figures with obviously symbolic values (`X.X%`), or with values no
  real company would produce.
- [ ] **TOC template vs actual chapters.** The template (L94–105) elides rows
  with `...`. The AMD TOC lists 10 rows and leaves out Ch.11 投資建議, even
  though the body has 11 chapters.
- [ ] **Length budget vs mandated content.** "7000-10000 字" (L50) has to cover
  11 chapters, over 50 sub-sections, a 10-step DCF with every formula written
  out, and a sensitivity grid. Real reports run 72–83 KB. Check that the
  "犧牲順序" (what to cut first) actually leads to complete Ch.11s, or reduce
  the mandated sub-sections.
- [ ] **Mermaid / ASCII requirements cost tokens but give readers little.**
  The prompt asks for "大量使用" (heavy use of) ASCII boxes and progress bars,
  and these often duplicate a table that sits next to them (e.g. AMD §1.1 + §1.2
  + §1.4). Decide which visuals earn their place. Mermaid is also the main
  stage-1 failure class (`check_mermaid.py`).
- [ ] **Rating ↔ buy-zone logic is not specified.** AMD 10-21 is rated **買入**
  (Buy) with MOS +9.7%, which its own legend marks 🔴 "有限偏窄" (limited). Its
  "合理佈局買入區間" (buy zone) of $490–550 lies entirely *below* the $552.72
  price. The prompt should define how the rating follows from MOS / upside
  thresholds.
- [ ] **Analyst consensus inside "fair value".** AMD §8.8 gives
  "華爾街分析師平均目標價" 15% of the weighted fair value. That makes the
  "independent" valuation partly circular. Decide whether consensus belongs in
  the triangulation or only alongside it.
- [ ] **Unverifiable claims the prompt invites.** Examples: market share (§2.2),
  TAM (§9.2), "第 39 百分位" (§8.8). None of these come from the context. Require
  such figures to be labelled as estimates, as rule 15 already does for DCF
  inputs.
- [ ] **"取報告日 {today} 收盤價" (use the report-date close) cannot be met by
  the early slots.** Crons at 02:00–03:30 UTC run before that day's US session,
  so 10 reports dated 2026-10-22 carry the 10-21 close (§12.3 item 5). Have the
  context supply the price *with its own date*, and say that date in the report.
- [ ] **US-only framing.** "頂級美股投資研究分析師" (a top US-equity research
  analyst) is used for Taiwanese tickers too.

## 3. System message — `prompts/gemini_system.txt`

- [ ] **Contradicts the prompt:** "一次性輸出完整的 **10 章**報告" (L64) vs 11
  chapters, and "8000–12000 字" (L43) vs "7000-10000 字". One of the two files
  should own length and structure.
- [ ] **"絕對不要拒絕" + "基於…專業知識進行專業推演"** (never refuse; fill gaps
  from your own professional knowledge) pushes the model to invent data rather
  than flag it. This may be a root cause of the fabrication that stage-2 QA finds
  (e.g. `mu` $90.27B TTM revenue). It conflicts with "只引用可從提供的財務數據中確認的數字"
  (only cite figures confirmed by the provided data) in the same file.
- [ ] Check that `openai_system.txt` makes the same promises, so a fallback
  report is held to the same rules.

## 4. Model & generation parameters

Files: `config/providers.py`, `config/__init__.py`, `utils/llm.py`

- [ ] **Temperature 0.7** (`llm.py:198,275`) for a report whose job is
  reproducible arithmetic. A lower value should shrink the run-to-run spread
  described in §7.
- [ ] **Token budget.** The default is 32k, Gemini clamps at 65,536, and the
  OpenAI fallback (`gpt-4o`) tops out at 16,384. A fallback report is therefore
  likely to be truncated (see the comment in `providers.py`). Count how often
  fallback fires and how often its output passes stage 1.
- [ ] **🔴 A refusal is returned as a successful report.** After the last
  refusal retry, `run_claude` / `run_openai` / `run_gemini` log "Returning last
  response" and return the refusal (`utils/llm.py:192,265,371`).
  `run_with_fallback` then saves it. MRVL's newest published report (2026-10-22,
  OpenAI fallback) is the single line "抱歉，我無法協助滿足此要求。" (Sorry, I
  can't help with this request). The runner should raise, so the chain moves on
  or the run fails.
- [ ] **Recovery paths.** Check how often truncation and degeneration retries
  (`run_gemini`) fire, and whether a retried report is marked as such in the
  frontmatter.
- [ ] **Frontmatter completeness.** Today it records provider and model. We
  could add prompt version/hash, temperature, the data-source success map and
  the price used, so that reports can be compared across prompt changes.

## 5. Report format (reader-facing)

- [ ] **Chapter skeleton**: 1 執行摘要 · 2 公司概覽 · 3 損益表 · 4 資產負債表 ·
  5 現金流 · 6 獲利能力 · 7 相對估值 · 8 DCF · 9 催化劑 · 10 風險 · 11 投資建議.
  Is the order right for a reader? Ch.11 repeats Ch.1, and Ch.8 alone is about a
  third of the report.
- [ ] **Executive summary**: can a reader get rating, fair value, MOS, top risks
  and the "what would change my mind" conditions in 30 seconds without scrolling
  past §1.0?
- [ ] **Duplication**: the same headline figures (TTM revenue, FCF, MOS) appear
  in the TOC, §1.0, §1.1, §1.4, §1.5, Ch.8 and Ch.11. Each copy is another chance
  for a mismatch.
- [ ] **Tables**: are 🟢🟡🔴 and ★ ratings used consistently, and does
  `responsive-tables.js` right-align figure columns correctly?
- [ ] **Language**: check for Traditional Chinese only, with no simplified
  leakage. Mermaid quadrant and mindmap charts must be English (a prompt rule).
- [ ] **Disclaimer**: present at the end. Check that the wording matches the
  site-level disclaimer.
- [ ] **Mobile**: wide ASCII boxes (the AMD §8.8 box overflows 66 columns) and
  wide sensitivity tables.

## 6. Valuation arithmetic — machine-checkable

The prompt already fixes these definitions (rule 16 and §8.10), so most of them
can be checked deterministically with no LLM.

- [ ] **Premium/discount sign.** AMD 10-21 says "DCF $576.45｜現價溢價 **+4.1%**" with
  the price at $552.72. Correct value: 552.72 / 576.45 − 1 = **−4.1%**, a
  *discount*. The sign is wrong in the TOC, in §1.0 and in the §1.5 ASCII box.
- [ ] **🔴 The weighted fair value is the sum of its own terms.** TSLA
  2026-10-22 prints `$147.71 + $16.43 + $42.53 + $57.36 + $60.21 = $334.34`.
  Those terms add up to **$324.24**. AMD 2026-10-22 prints
  `$229.76 + $110.32 + $77.75 + $95.73 + $63.76 = $580.45`, which adds up to
  **$577.32**. Each product is right; only the total is wrong. The headline
  value, the MOS and the rating all inherit the wrong total. Both reports'
  §8.10 "複算檢核表" (recalculation checklist) re-check the *scenario* weights
  but never re-add §8.8, and they still mark MOS as ✅ consistent. The prompt's
  §8.10 list should include re-adding the §8.8 sum.
  **Across all 36 reports with a §8.8, 25 are off by more than 0.5%** (§12.3).
  9 of them replace the computed sum with an invented "adjustment": "取穩健", "精確微調", "區域匯率緩衝", "四捨五入至整數位"
  (conservative, fine-tuning, an FX buffer, rounding).
- [ ] **MOS / upside** recompute from fair value and price, and agree between
  §1.0 and §8.8. (AMD 10-21 passes: 9.75% ≈ 9.7%, 10.8%.)
- [ ] **Weights sum to 100%** in §8.6 (scenarios) and §8.8 (triangulation), and
  the weighted sum equals the stated value. (AMD 10-21 passes: $612.44.)
- [ ] **WACC > g** in every sensitivity cell. Cells with WACC ≤ g must read `N/A`.
- [ ] **Price used = close on the report date** in `data/prices/<t>.csv`. (AMD
  10-21 passes: $552.72 = 2026-10-21 close.)
- [ ] **Derived balance-sheet figures** (net cash = cash − debt; FCF = OCF −
  capex) are consistent with each other.
- [ ] **ROIC vs ROE plausibility.** AMD reports ROE 10.2% and ROIC 15.6% while
  holding net cash. That is possible (ROIC excludes goodwill) but it needs a
  sentence of explanation.

**Suggested follow-up:** add an `ARITHMETIC` issue type to stage 1
(`validate/__init__.py`) that parses the §1.0 dashboard and §8.8 table and
recomputes MOS, upside, premium sign and weight sums. These are the errors that
regex cannot catch today and that the LLM judge did not flag. Its AMD 10-21
verdict instead calls TTM $41.31B vs FY2023 $22.68B a "contradiction".

## 7. Run-to-run stability (same ticker, consecutive days)

AMD, five daily runs on near-identical financial data:

| Date | Price | WACC | Headline value | Rating |
|------|-------|------|----------------|--------|
| 10-18 | $528.75 | 9.41% | weighted $612.30 | Buy |
| 10-19 | $538.05 | 9.41% | DCF $621.50 / weighted $618.70 | Buy |
| 10-20 | $534.74 | 10.97% | target $642.00 | Buy |
| 10-21 | $552.72 | 11.8% | DCF $576.45 / weighted $612.44 | Buy |
| 10-22 | $507.93 | 10.76% | weighted $580.45 | Buy |

- [ ] WACC moves 9.41% → 11.8% in three days with the same beta and capital
  structure. Over the same runs, ROIC moves from 10.9% (10-19) to 15.6% (10-21).
- [ ] The rating is stable but the inputs are not. A reader comparing days sees
  noise presented as analysis.
- [ ] Options: (a) compute WACC, ROIC, MOS and the premium in Python and pass
  them into the context as fixed facts, leaving the model to interpret them;
  (b) lower the temperature; (c) generate less often and show a "changes since
  last report" diff.
- [ ] The headline label drifts too (加權目標價 / 基準目標價 / 加權合理價值), so
  `parse_scenario_targets` and readers cannot rely on a single term.

## 8. QA gates — coverage

| Defect class | Stage 1 (regex) | Stage 2 (LLM judge) |
|--------------|-----------------|---------------------|
| Empty / refusal / truncated / placeholder / Mermaid | ✅ | — |
| Missing chapter (e.g. no Ch.11) | ⚠️ only via generic `CUTOFF` | partially (`completeness`) |
| Arithmetic / sign errors (§6) | ❌ | ❌ (not caught on AMD 10-21) |
| Fabricated figures (not in context) | ❌ | ✅ sometimes (`mu`) |
| Mislabelled period (quarter shown as TTM, §12) | ❌ | ❌ — the judge never sees the source data |
| Balancing figures invented to match a total (§12) | ❌ | ❌ |
| Prompt-example anchoring (`9.41%`) | ❌ — trivially addable | ❌ |
| Refusal published (MRVL, §12.3) | ✅ `REFUSAL`, but in the nightly audit, after it is live | — |
| Wrong price (0050: NT$195 vs NT$106.90) | ❌ — checkable against `data/prices/` | ❌ |
| Currency-mixed ratios (TSM, SKHY) | ❌ | ❌ |
| Run-to-run drift (§7) | ❌ | ❌ (grades one report at a time) |
| Ch.1 ↔ Ch.8 disagreement | ❌ | ✅ (`consistency`) |

- [ ] Add a per-type required-headings check (`## 1.` … `## 11.`) to stage 1.
- [ ] Give the judge the *context* as well as the report, so "fabricated" can be
  judged against the inputs instead of the judge's own memory.
- [ ] Review `qa_review.txt` against the fundamental-specific rules (MOS
  definition, single value basis) so the judge grades what the prompt asked for.

## 9. Publishing — `scripts/build_docs.py`

- [ ] `parse_scenario_targets()` (L1444) reads the §7.3 Bear/Base/Bull table to
  draw the ticker page's **Price Target** rail. Any prompt change to that table's
  columns can silently drop the block (it returns `[]`). Pin this with a fixture
  from a current report.
- [ ] `report_meta_block` reads model and date from the frontmatter. If more
  provenance fields are added (§4), surface them here.
- [ ] Hero KPIs come from `price_analytics.summary()` while the report has its
  own price. Check that both agree on the report date.
- [ ] The ZH tree mirrors index pages only, and the report is ZH-only. Confirm
  the EN shell (nav, meta-bar chips) reads well around ZH body text.

## 10. Schedule & cost

- [ ] 36 fundamental slots a day means every scheduled ticker gets a full 75 KB
  report **daily**, while its financial statements change quarterly. Consider
  weekly (or earnings-triggered) generation plus a daily price-only refresh of
  MOS and upside, computed in Python.
- [ ] **Unscheduled tickers keep a stale "latest" report.** IONQ is not in
  `.ticker_schedule.json`, so its newest fundamental report is 2026-08-15 and its
  ticker page still shows it as current. Mark reports older than N days as
  stale on the page.
- [ ] Retention is 120 days (`REPORT_RETENTION_DAYS`), which means about 120
  near-duplicate AMD reports on the site.

## 11. Tests touching this path

`tests/test_prompts.py`, `test_context.py`, `test_context_branches.py`,
`test_generate_analysis.py`, `test_llm.py`, `test_llm_providers.py`,
`test_check_report_quality.py`, `test_review_report_quality.py`,
`test_build_docs.py` (scenario parsing).

- [ ] No test asserts that the prompt and system message agree on chapter count
  or length.
- [ ] No test asserts that the context contains every input the prompt names
  (peers, WACC inputs).

## 12. Fact-check: every ticker's latest fundamental report vs filings

**Scope.** I checked the newest fundamental report for each of the 37 tickers
in `ai_gen_report/fundamental/`. 36 are dated 2026-10-22; IONQ's newest is
2026-08-15. Each figure was checked against the best primary source available:

| Source | Tickers | What is checked |
|---|---|---|
| SEC XBRL `companyfacts` (10-Q / 10-K) | 24 US filers: AMD AMZN AVAV AVGO GOOG INTC IONQ KTOS META MRVL MSFT MU NVDA ONDS ORCL PL PLTR RKLB SNDK SOFI SPCX TSLA VST WDC | price, revenue + growth, operating margin, FCF, §8.8 arithmetic |
| yfinance quarterly statements (no XBRL 10-Q) | 6 foreign filers: 2330.TW TSM GRAB NBIS NU SKHY | same, but the source is secondary |
| price + arithmetic only | 7 ETFs: 0050 QQQ ROBO SOXQ SOXX VTI WQTM | price, §8.8 arithmetic |

**Method.**

- **TTM** = previous fiscal year + current YTD − prior-year YTD, taken from
  the latest filing made on or before the report date. SpaceX's Q3 10-Q was
  filed on 2026-10-22, and its report correctly uses it.
- **FCF** = operating cash flow − purchases of property & equipment.
- **Price** = close on the report date. For the 02:00–03:30 UTC cron slots,
  that is the *previous* US session.
- **§8.8** = the stated weighted fair value vs the sum of its own
  `value × weight` terms.

The extraction scripts (`seclib.py`, `factcheck_all.py`, `s88.py`) were run
outside the repo. Every ❌ below was read in context, not just matched by a
regex.

Legend: ✅ matches (±1%) · ⚠️ small gap, ambiguous label or definition choice ·
❌ wrong · — no such claim in the report.

### 12.1 Scorecard

"Growth" and "Op margin" mean the figures the report presents as TTM.
"vs" gives the actual value.

| Ticker | Source | Price | Growth | Op margin | FCF | §8.8 total vs its terms | Notes |
|---|---|---|---|---|---|---|---|
| 0050 | ETF | ❌ NT$195.00 vs NT$106.90 | — | — | — | ⚠️ −0.37% | price appears in no input |
| 2330.TW | yfinance | ✅ | ❌ +50.9% is latest-quarter YoY | ⚠️ 58.7% = quarterly field | ⚠️ NT$1.20T (yfinance) | ❌ −1.27% | |
| AMD | SEC | ✅ | ❌ +50.1% vs +39.5% | ❌ 17.2% vs 15.7% | ❌ $8.84B vs $8.40B, capex back-solved | ❌ +0.54% | §12.5 |
| AMZN | SEC | ✅ | ❌ +19.6% vs +15.8% | ❌ 13.7% vs 12.1% | ❌ $3.22B vs −$11.6B | ❌ −2.47%, override | WACC 9.41% |
| AVAV | SEC | ✅ | ✅ FY2026 +140.9% | — | ✅ | ❌ +2.82%, override | WACC 9.41% |
| AVGO | SEC | ✅ | ❌ +85.5% vs +48.7% | ❌ 54.3% vs 48.0% | ❌ $30.6B vs $39.4B | ❌ −1.27%, mis-added then override | |
| GOOG | SEC | ✅ | ❌ +24.2% vs +20.1% | ⚠️ 34.0% vs 33.1% | ❌ $22.67B vs $53.27B, capex back-solved | ❌ +0.55% | WACC 9.41% |
| GRAB | yfinance | ✅ | ❌ +21.9% is latest-quarter YoY | ❌ 2.1% vs 8.9% | ❌ +$502.6M vs −$186M | ❌ −2.89%, override | |
| INTC | SEC | ✅ | ✅ labelled Q2 | — | ❌ $4.87B vs $2.83B | ❌ +1.38% | |
| IONQ | SEC | — (report 2026-08-15) | ❌ +286.8% vs +370.6% | ✅ −408.2% | ❌ −$88M vs −$480M | ❌ −3.69% | not scheduled; 2 months old |
| KTOS | SEC | ✅ | ⚠️ labelled latest Q; thesis calls it TTM | ❌ −0.2% vs +1.2% | ⚠️ −$118M vs −$130M | ❌ −1.69% | |
| META | SEC | ✅ | ✅ +28.0% vs +27.7% | ⚠️ 34.8% (TTM 38.1%, Q 30.9%) | ❌ $21.55B vs $40.98B | ❌ +1.66% | |
| MRVL | SEC | ❌ **the report is a refusal** (267 bytes, "抱歉，我無法協助…", "Sorry, I can't help…") | | | | | published as MRVL's latest |
| MSFT | SEC | ✅ | ✅ FY26 +17.8% | — | ✅ $66.99B | ⚠️ +0.18% | |
| MU | SEC | ⚠️ 10-21 close | ✅ FY +256.3% | ❌ 80.7% is Q4; FY 74.6% | ❌ $29.14B vs $58.96B, capex back-solved | ⚠️ −0.35%, override | |
| NBIS | yfinance | ✅ | ⚠️ labelled latest Q; thesis calls it TTM | — | ❌ −$9.61B vs ≈ −$5.89B | ❌ −1.29%, override | WACC 9.41% |
| NU | yfinance | ✅ | ✅ labelled latest Q | ⚠️ "TTM 50.2%" is a quarterly field (a bank) | — | ❌ −0.72%, override | TTM revenue $8.44B vs $13.18B summed quarters ⚠️ |
| NVDA | SEC | ✅ | ❌ +105.9% vs +83.4% | ⚠️ 66.2% vs 65.2% | ❌ TTM $41.81B vs $127.0B (FY $96.68B ✅) | ❌ +0.91% | |
| ONDS | SEC | ✅ | ❌ +1,235% vs +979% | ❌ −166.3% vs −140.4% | ❌ −$69M vs −$170M | ❌ +1.24%, override | |
| ORCL | SEC | ✅ | ✅ labelled Q1 | ⚠️ 35.6% (TTM 32.1%) | ❌ −$45.85B vs −$28.72B | ❌ −2.19% | |
| PL | SEC | ✅ | ⚠️ labelled latest Q; thesis calls it TTM | — | ❌ $51.8M vs $24.6M, capex back-solved | ❌ **−12.27%** | MOS moves to another band |
| PLTR | SEC | ✅ | ❌ +92.8% vs +78.9% | ❌ 47.1% vs 42.8% | ⚠️ $3.36B ✅, yield ❌ | ✅ +0.04% | §12.6 |
| QQQ | ETF | ⚠️ 10-21 close | — | — | — | ⚠️ −0.23% | |
| RKLB | SEC | ✅ | ✅ TTM +52.5% | ⚠️ −24.6% is Q (TTM −29.1%) | ❌ −$252M vs −$370M | ❌ +1.10% | |
| ROBO | ETF | ⚠️ 10-21 close | — | — | — | ⚠️ −0.33% | |
| SKHY | yfinance | ⚠️ 10-21 close | ❌ +256.8% is latest-quarter YoY | ❌ 76.3% vs 68.0% | ❌ ₩55.8T vs ≈ ₩90.4T | ❌ −1.75% | KRW/USD mixed in ratios |
| SNDK | SEC | ⚠️ 10-21 close | ✅ FY +175.3% | ✅ labelled Q4 | ✅ $11.49B | ⚠️ −0.33% | |
| SOFI | SEC | ✅ | ⚠️ +40.9% ✅ in one place, +42.6% (Q) in another | — | — | ❌ −0.70% | |
| SOXQ | ETF | ⚠️ 10-21 close | — | — | — | ✅ −0.05% | WACC 9.41% |
| SOXX | ETF | ⚠️ 10-21 close | — | — | — | ❌ −0.72%, override | |
| SPCX | SEC | ✅ | ✅ Q3 +161.4%, TTM $32.04B | — | — | ❌ −4.09% | WACC 9.41% |
| TSLA | SEC | ✅ | ❌ +25.5% vs +11.8% | ❌ 1.4% vs 4.2% | ❌ $4.84B vs $5.76B, capex back-solved | ❌ +3.12% | §12.4 |
| TSM | yfinance | ✅ | ❌ +50.9% is latest-quarter YoY | ⚠️ 58.7% | ⚠️ NT$1.20T | ❌ −0.88% | TWD/USD mixed in ratios |
| VST | SEC | ✅ | — | ❌ "TTM 13.8%" vs 18.5% | ❌ **$37M vs $2.25B** | ❌ +0.84% | |
| VTI | ETF | ⚠️ 10-21 close | — | — | — | ✅ +0.05% | |
| WDC | SEC | ⚠️ 10-21 close | ✅ FY +35.7% | ⚠️ 35.6% vs FY 34.5% | — | ⚠️ −0.31% | |
| WQTM | ETF | ⚠️ 10-21 close | — | — | — | ⚠️ −0.13% | |

### 12.2 Totals by check

| Check | ✅ | ⚠️ | ❌ | Base |
|---|---|---|---|---|
| Price | 24 | 10 (previous close, pre-open slot) | 1 (0050) | 35 dated reports with a price (IONQ, MRVL excluded) |
| Revenue growth label | 11 | 4 (both labels in one report) | 13 | 28 equity reports that state growth |
| Operating margin | 2 | 9 | 11 | 22 reports that state a margin |
| FCF | 3 | 4 | 18 | 25 reports that state FCF |
| §8.8 total = Σ own terms | 3 | 8 (0.1–0.5%) | 25 (> 0.5%) | 36 reports with a §8.8 |

### 12.3 Defect classes, most common first

1. **§8.8 totals that don't equal their own terms: 25 of 36 reports.** There
   are two kinds:
   - **Silent mis-addition (17).** The printed subtotals are correct but the
     total is not, e.g. META `$340.07 + $153.10 + $110.25 + $81.50 + $83.31
     = $781.02` (it adds up to $768.23). Reports: 2330.TW, AMD, GOOG, INTC,
     IONQ, KTOS, META, NVDA, ORCL, PL, RKLB, SKHY, SOFI, SPCX, TSLA, TSM, VST.
   - **Override with an invented reason (8, plus MU at ⚠️).** The report gets
     the sum right, then replaces it:
     - AMZN: $312.29 → $304.58, "考慮保守原則…折讓" (a conservative discount)
     - AVAV: $172.13 → $176.99, "精確微調" (precise fine-tuning)
     - AVGO: adds to "$482.19" (the terms make $422.19), then "下修權重後鎖定為
       $416.80" (locked at $416.80 after cutting weights)
     - GRAB: $4.848 → $4.71, "區域匯率緩衝" (a regional FX buffer)
     - NBIS: $230.97 → $228.00, "四捨五入至整數位" (rounded to a whole number)
     - NU: $19.396 → $19.26, "保守調整權重尾差" (conservative weight adjustment)
     - ONDS: $10.504 → $10.63, "四捨五入" (rounding)
     - SOXX: $556.50 → $552.50, "嚴格取整" (strict rounding)
     - MU: $1,353.31 → $1,348.60, "微調取整" (fine-tuned rounding)

   The worst gap is PL (−12.3%). Correcting it moves PL's MOS from 15.7% to
   26.1%, which crosses the report's own 🟡/🟢 band, while its rating is
   持有/謹慎觀望 (hold / cautious).
2. **FCF is wrong in 18 of 25 reports that state it.** The context's
   `Free Cash Flow` is yfinance's figure, and the model copies it as TTM FCF.
   That figure is not OCF − capex. It can be off by a large factor:
   - VST: $37M vs $2.25B
   - NVDA: $41.8B vs $127.0B
   - GOOG: $22.7B vs $53.3B
   - META: $21.6B vs $41.0B

   It can also have the wrong sign: GRAB +$503M vs −$186M; AMZN $3.22B vs
   −$11.6B.
   **In 5 reports the model then backs out a capex figure that doesn't exist
   in any filing**, so that the table adds up:
   - TSLA: $13.84B vs $12.92B
   - AMD: $1.24B vs $1.68B
   - MU: $60.53B vs $30.71B
   - GOOG: ≈$163B vs $132.4B
   - PL: ≈$66M vs $93M

   NVDA goes further and explains the gap it created ("暫時性收縮…應收帳款",
   a temporary dip because of receivables) right next to a correct FY2026 FCF
   of $96.68B.
3. **Latest-quarter growth presented as TTM growth: 13 of 28, plus 4 mixed.**
   This is the `revenueGrowth` labelling bug (§1). It overstates growth by
   3.8pp (AMZN) up to 36.8pp (AVGO: +85.5% vs +48.7%), and by 256pp for ONDS
   (+1,235% vs +979%). IONQ is the reverse
   case: the quarterly rate *understates* its TTM growth. Where the report says
   "最新季度" (latest quarter), the figure is correct (INTC, ORCL, NU, and
   KTOS/PL/NBIS in their opening sentence). Those three then repeat it as
   "TTM YoY" in the thesis line.
4. **Quarterly operating margin presented as TTM: 11 ❌ + 9 ⚠️ of 22.** MU is
   internally inconsistent: it writes "營業利益達 $99.34B，營業利益率…80.7%"
   (operating income $99.34B, operating margin 80.7%) on revenue of $133.19B,
   which is 74.6%.
5. **The price is the previous close for 10 reports.** These are the 02:00–03:30
   UTC slots (MU, WDC, SNDK, SOXX, VTI, QQQ, SKHY, SOXQ, ROBO, WQTM), which run
   before that day's US session. The price is the correct latest close, but the
   filename date and the prompt's "報告日收盤價" (report-date close) say
   otherwise. 10-22 was a −6 to −9% day for memory names, so by the time
   MU / SNDK / WDC / SKHY were published their MOS was already 4.2–6.5pp too
   *low* (e.g. SNDK 23.8% at the 10-21 close vs 30.3% at the 10-22 close).
6. **Currency mixing on ADRs whose financials are not in USD (TSM, SKHY).**
   yfinance ratios divide TWD or KRW cash flows by a USD market cap. TSM prints
   "FCF Yield 56.25%" and "EV/EBITDA 4.08x"; SKHY prints "FCF Yield 53.4%" and
   "Forward P/E 4.16x". The report then argues from these numbers.
7. **Pipeline failures that reach readers.**
   - **MRVL**: Gemini failed, the OpenAI fallback refused five times, and
     `run_openai` *returned the refusal as a success*
     (`utils/llm.py:265`: "Returning last response"; the Claude and Gemini
     runners do the same at L192 and L371). `run_with_fallback` saved it, and
     MRVL's newest published report is the single line
     "抱歉，我無法協助滿足此要求。" (Sorry, I can't help with this request).
     Stage 1 flags `REFUSAL`, but only in the nightly audit, after publishing.
   - **0050**: the report uses "現價 NT$195.00" 22 times while the ETF trades
     at NT$106.90. NT$195 appears in no input (the price store and yfinance
     both say about NT$107). It is close to 0050's pre-split price, so it most
     likely comes from model memory, and every valuation figure in the report
     is on that wrong scale.
   - **IONQ**: not in the schedule, so its "latest" report is two months old.
8. **Prompt anchoring, still visible:** WACC = **9.41%**, the prompt's own
   example (§2), appears in 6 of 36 reports from a single day (AMZN, AVAV,
   GOOG, NBIS, SOXQ, SPCX).

**What checks out:** where a number is copied straight from the context it is
nearly always right:

- 24 of 25 report-date prices
- every TTM revenue *level* checked against SEC
- MSFT, SNDK, AVAV and SPCX across the board

SPCX even used a 10-Q filed the same day.

### 12.4 Detail: TSLA

| Claim in report | Report | Actual | Source | |
|---|---|---|---|---|
| Price (10-22 close) | $374.58 | $374.58 | price store | ✅ |
| TTM revenue | $103.62B | $103.62B | SEC | ✅ |
| TTM revenue growth | YoY +25.5% | **+11.8%** ($103.62B vs $92.72B) | SEC | ❌ +25.5% is Q2's YoY |
| Net income growth | "淨利潤年減 3.0%" (net income down 3.0% YoY) | TTM **−37.3%** ($3.80B vs $6.07B) | SEC | ❌ −3.0% is yfinance `earningsGrowth` (quarterly) |
| TTM operating margin | 1.4% | **4.2%** ($4.37B / $103.62B) | SEC | ❌ 1.4% is Q2 alone |
| 2025 R&D | $6.41B | $6.41B | SEC 10-K | ✅ |
| Q2 2026 capex / FCF | $5.80B / −$1.10B | $5.79B / −$1.09B | SEC (YTD differencing) | ✅ |
| TTM OCF | $18.68B | $18.69B | SEC | ✅ |
| TTM capex | $13.84B | **$12.92B** | SEC | ❌ backed out so that OCF − capex = $4.84B |
| TTM FCF | $4.84B | **$5.76B** (OCF − capex) | SEC | ❌ $4.84B is yfinance levered FCF |
| Net cash | $27.44B | $43.52B cash+ST inv − $16.08B debt incl. leases | SEC / yfinance | ✅ |
| Current ratio | 1.94x | 1.94x | SEC | ✅ |
| Trailing / forward P/E | 346.8x / 171.1x | 346.8x / 171.1x | yfinance | ✅ |
| Weighted fair value (§8.8) | $334.34 | **$324.24** (its own terms) | arithmetic | ❌ |
| MOS | −12.0% | **−15.5%** with the corrected sum | arithmetic | ❌ |
| DCF premium | +18.7% | 374.58 / 315.69 − 1 = +18.7% | arithmetic | ✅ |

### 12.5 Detail: AMD

| Claim in report | Report | Actual | Source | |
|---|---|---|---|---|
| Price (10-22 close) | $507.93 | $507.93 | price store | ✅ |
| TTM revenue | $41.31B | $41.31B | SEC | ✅ |
| TTM revenue growth | YoY +50.1% | **+39.5%** ($41.31B vs $29.60B) | SEC | ❌ +50.1% is Q2's YoY |
| Q2 revenue, YoY / QoQ | $11.54B, +50.1% / +12.5% | $11.54B, +50.1% / +12.5% | SEC | ✅ |
| FY2024 revenue | $25.79B | $25.79B | SEC | ✅ |
| FY2024 operating margin | 8.1% | **7.4%** | SEC | ⚠️ |
| TTM operating margin | 17.2% | **15.7%** ($6.49B / $41.31B) | SEC | ❌ 17.2% is Q2 alone |
| Q2 diluted EPS | $1.39 | $1.38 | SEC | ⚠️ rounding |
| Q2 EPS YoY | +159.5% | +155.6% (1.38 / 0.54) | SEC | ⚠️ yfinance `earningsGrowth` |
| TTM OCF | $10.08B | $10.08B | SEC | ✅ |
| TTM capex | $1.24B | **$1.68B** | SEC | ❌ backed out so that OCF − capex = $8.84B |
| TTM FCF | $8.84B | **$8.40B** | SEC | ❌ yfinance levered FCF |
| Cash + ST investments | $13.11B | $13.11B | SEC | ✅ |
| Total debt | $4.28B | $3.23B (+ leases ≈ $4.28B) | SEC / yfinance | ⚠️ includes leases; not stated |
| Net cash | $8.84B | $9.89B excl. leases / $8.84B incl. leases | | ⚠️ same as TTM FCF, by coincidence |
| Weighted fair value (§8.8) | $580.45 | **$577.32** (its own terms) | arithmetic | ❌ |
| MOS / upside | +12.5% / +14.3% | **+12.0% / +13.7%** with the corrected sum | arithmetic | ❌ (rating unchanged) |
| DCF discount | −10.6% | 507.93 / 568.10 − 1 = −10.6% | arithmetic | ✅ (the 10-21 sign error is gone) |

### 12.6 Detail: PLTR

| Claim in report | Report | Actual | Source | |
|---|---|---|---|---|
| Price / market cap | $196.19 / $471.46B | $196.19 / $471.46B | price store / yfinance | ✅ |
| TTM revenue | $6.16B | $6.16B | SEC | ✅ |
| TTM revenue growth | YoY +92.8% | **+78.9%** ($6.16B vs $3.44B) | SEC | ❌ +92.8% is Q2's YoY |
| TTM operating margin | 47.1% | **42.8%** ($2.64B / $6.16B) | SEC | ❌ 47.1% is Q2 alone |
| TTM net income | $3.02B | $3.02B | SEC | ✅ |
| TTM OCF / capex / FCF | $3.40B / $0.04B / $3.36B | $3.40B / $0.04B / $3.36B | SEC | ✅ computed correctly here |
| FCF yield | 0.46% | **0.71%** ($3.36B / $471.46B) | arithmetic | ❌ 0.46% uses yfinance's $2.16B, which contradicts the report's own $3.36B |
| Deferred revenue | $1.03B | $1.10B (`ContractWithCustomerLiability`) | SEC | ⚠️ not in context; from model memory |
| Net cash | $9.20B | $9.41B cash+securities − $0.21B leases | SEC / yfinance | ✅ |
| Current ratio | 7.23x | 7.23x | SEC | ✅ |
| Weighted fair value (§8.8) | $182.20 | $182.13 (its own terms) | arithmetic | ⚠️ rounded up; the report says so ("≈") |
| MOS / DCF premium | −7.7% / +11.8% | −7.7% / +11.8% | arithmetic | ✅ |

### 12.7 What the fact-check shows

1. **The model copies well and derives badly.** Figures transcribed from the
   context pass. Every recurring error is in a number the model has to *derive*
   (a total, an FCF, the period a growth rate covers) or in one the context
   labels ambiguously.
2. **Most ❌ can be fixed upstream, in code we own:**

   | Fix | Where | Removes |
   |---|---|---|
   | Label each `info` field with its period; compute TTM growth, TTM margin and OCF − capex from the statements | `context/__init__.py` | growth (13), margin (11) and FCF (18) ❌, plus the 5 back-solved capex figures |
   | Compute the §8.8 total, MOS, upside and premium in Python, or check them in stage 1 (`ARITHMETIC`) | `context/`, `validate/` | 25 §8.8 ❌, and the 9 invented "adjustments" |
   | Raise instead of returning a refusal after the last retry | `utils/llm.py:192,265,371` | MRVL |
   | Convert ADR financials to the quote currency, or drop yfinance ratios when `financialCurrency ≠ currency` | `context/` | TSM, SKHY ratio errors |
   | Print the price's own date, not the cron's UTC date, and drop "報告日收盤價" from the prompt | `fundamental.txt`, `context/` | 10 price ⚠️ |
   | Give the price to the model as a fixed fact and check it against the price store | `validate/` | 0050 |
3. **Ratings mostly survive; headline numbers do not.** Only PL's MOS crosses
   one of the report's own bands once corrected. But the figures a reader
   quotes from §1.0 (growth, margin, FCF, fair value) are wrong in most reports.

---

## Suggested review order / follow-up PRs

0. **Highest value, from the §12 fact-check (see the table in §12.7):**
   - In `context/__init__.py`, label every yfinance `info` field with its
     period, and replace `Free Cash Flow` with OCF − capex plus TTM growth and
     margins computed from the statements.
   - Compute the §8.8 total, MOS and upside in Python.
   - Make the LLM runners raise on a final refusal.
   - Fix `fundamentals.fiscal_years()` so the store includes quarters of the
     current fiscal year.
1. **Quick wins (prompt only):** remove the anchoring example numbers; make
   `gemini_system.txt` agree with the prompt (11 chapters, one length budget);
   spell out the Ch.11 TOC row; define rating thresholds.
2. **Stage-1 checks:** required headings, plus the `ARITHMETIC` checks from §6.
3. **Context:** feed the committed price/fundamentals stores and pre-computed
   WACC / ROIC / MOS inputs; add peer multiples; record data-source success in
   the frontmatter.
4. **Generation:** lower temperature; record prompt hash and params in the
   frontmatter.
5. **Product:** decide regeneration cadence and on-page de-duplication (§5, §10).
