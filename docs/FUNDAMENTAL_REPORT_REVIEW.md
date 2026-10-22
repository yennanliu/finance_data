# Fundamental Report — Review Checklist

**Purpose:** list everything that shapes a `fundamental-analysis` report, from the
data we fetch to the page we publish, so that each part can be reviewed on its
own. Each section names the files involved, what to check, and any problems
already found in a real report.

**Worked example:**
[`/reports/amd/fundamental_analysis_2026-10-21_gemini/`](https://yennj12.js.org/finance_data/reports/amd/fundamental_analysis_2026-10-21_gemini/)
(source: `ai_gen_report/fundamental/amd/fundamental_analysis_2026-10-21_gemini.md`,
75 KB, 11 chapters, 15 Mermaid blocks, 214 table rows).

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

---

## 1. Data fetch & context

Files: `utils/data_fetch.py`, `context/__init__.py` (L312–378), `data/prices.py`, `data/fundamentals.py`

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
  10-19 reports both state WACC = 9.41%, and on 10-20 it was 10.97%. Fix: replace
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
| Prompt-example anchoring (`9.41%`) | ❌ — trivially addable | ❌ |
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

---

## Suggested review order / follow-up PRs

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
