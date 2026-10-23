# Technical Report — Review Checklist

*English · [繁體中文](TECHNICAL_REPORT_REVIEW.zh-TW.md)*

**Purpose:** list everything that shapes a `technical-analysis` report, from the
OHLCV we fetch to the page we publish, so that each part can be reviewed on its
own. Companion to `FUNDAMENTAL_REPORT_REVIEW.md`
([PR #82](https://github.com/yennanliu/finance_data/pull/82)); same layout.

**Worked examples:**
[`/reports/amzn/technical_analysis_2026-10-23_gemini/`](https://yennj12.js.org/finance_data/reports/amzn/technical_analysis_2026-10-23_gemini/)
(generated from a broken context, see §1.1) and
[`/reports/avav/technical_analysis_2026-10-22_gemini/`](https://yennj12.js.org/finance_data/reports/avav/technical_analysis_2026-10-22_gemini/)
(the clean case).

**Fact-checked:** the latest technical report of **all 27 tickers** under
`ai_gen_report/technical/`, against Yahoo daily OHLCV as of each report's commit
time, plus a price-freshness sweep of all 550 technical reports committed in
October. See [§7](#7-fact-check-every-tickers-latest-technical-report).

**Headline:** when the context is intact, the model copies it faithfully.
In clean-context reports, every indicator and 88 of 90 R/S levels match the
context to the cent; the other two are labelled as a 52-week low and a Fibonacci
level. The serious defects are upstream:
- **Empty last bar (8/27):** an empty last daily bar silently blanked the
  context for 8 of the 27 reports. The model then wrote a full report without
  the data, including invented support and resistance levels. 79 of October's
  550 reports carry the previous session's close.
- **0050 fabricated (21/21):** 0050 has been fully fabricated every day in
  October, at a price about 80% too high.
- **Non-standard RSI:** the pipeline's "RSI(14)" is not the RSI any charting
  site shows. It puts 7 of 24 tickers below 30 (oversold) where standard
  (Wilder) RSI has them in the neutral range.

---

## 0. Pipeline map — what there is to review

| § | Stage | Source of truth | Review question |
|---|-------|-----------------|-----------------|
| 1 | Data fetch | `scripts/analysis/data/sources.py` `fetch_data()` (`t.history(period="2y")`) | Is the last bar complete, and is it the last *finished* session? |
| 1 | Indicator maths | `scripts/analysis/data/technicals.py` (`compute_technicals`, `compute_levels`, `compute_moving_average_charts`) | Are the indicators the standard definitions the report names? |
| 1 | Context assembly | `scripts/analysis/context/__init__.py`, `technical-analysis` branch (L262+) | Does the model get every input the prompt asks it to use? |
| 2 | Prompt | `scripts/analysis/prompts/technical.txt` (rules 1–15, 9 chapters) | Are the instructions achievable from that context? |
| 3 | Model + params | `config/__init__.py` (`REPORT_TEMPERATURE` 0.3), `.ticker_schedule.json` defaults (gemini-3.8-flash, 32k tokens) | Does the budget fit a 9-chapter report? |
| 3 | Output format | the report (9 chapters, frontmatter) | Is the structure stable? |
| 4 | Strategy arithmetic | Ch.1 scorecard, Ch.8 strategy tables | Do R/R, probabilities and score routing recompute? |
| 5 | QA gates | `validate/__init__.py`, `review_report_quality.py` | Which defects below does QA catch? |
| 6 | Publishing / schedule | `build_docs.py`, `daily_analysis.yml` | Is what readers see current? |
| 7 | Fact-check | Yahoo OHLCV at commit time | Are the report's figures true? (§7) |

---

## 1. Data fetch & indicator maths

Files: `data/sources.py`, `data/technicals.py`.

### 1.1 An empty last bar blanks the whole context — **critical**

`fetch_data` returns Yahoo's daily history as-is, and `compute_technicals`
reads `close.iloc[-1]`. After the US close, Yahoo often publishes the new
session's bar with **volume but NaN open/high/low/close**. This lasts for
roughly an hour or two; on 2026-10-23 it covered every run committed between
00:14 and 01:05 UTC. Then:

- `收盤價` and `當前價格` render as `$nan`.
- Every rolling indicator (MA5–MA240, RSI, ATR, Bollinger, Stochastic) is `N/A`.
- `compute_levels` compares levels against `nan`, so **no R1–R3 / S1–S3 are
  emitted**.
- Only the EWM-based values survive: MACD, ADX/±DI, and the volume ratio,
  which uses the *new* day's volume against the previous day's price.

Reproduced exactly: rebuilding AMZN's context with an empty 10-22 bar yields
MACD 1.643 / 0.863 / +0.780, ADX 14.32, +DI 21.94 / −DI 15.75 and volume ratio
1.34x. Those are the very values the published report quotes, and the other
indicators come out as `N/A`.

The model does not stop. It writes the full 9 chapters anyway:
- **Price:** it takes the price from the weekly table, i.e. the previous close.
- **Levels:** it builds R/S from Fibonacci points and weekly closes.
- **Indicators:** it estimates RSI, MA and ATR itself (§7.3).

`last_completed_close()` (PR #84) and `quote_close()` (PR #85) fixed the
headline price only for the **fundamental** context (`_market_overview`).
`compute_technicals` still reads the raw `hist`, so this is **not fixed on
`main`**.

**Check / fix:**
- Drop trailing bars whose `Close` is NaN before any indicator is computed
  (`hist = hist[hist["Close"].notna()]`).
- Then apply `quote_close()` to append the official close, or skip the run.
- Refuse to generate when the snapshot price is NaN. A report built on `$nan`
  should be a failed run, not a published page.

### 1.2 0050 had no data at all — fixed by #84, unverified for technical

The 0050 technical report was generated from an empty history every day in
October. Bare `0050` returns 404 on Yahoo, and #84 now requests `0050.TW`.
The model filled the gap itself. The 10-23 report says so in its header
(「鑑於即時資料包缺失歷史報價，本報告依據…技術建模推演完整 OHLCV 基準數值」)
and then publishes a price of $192.50, MA200 $165.80, RSI 58.20 and six R/S
levels. The actual close was NT$108.15. **All 21 October 0050 reports** quote
prices between $192.5 and $198.5 (§7.4).

**Check:** confirm the first 0050 technical run after #84 quotes ~NT$106–108.
Separately, a context with no OHLCV should abort the run (same guard as §1.1).

### 1.3 "RSI(14)" is not Wilder's RSI

`compute_technicals` averages gains and losses with a **14-day simple mean**
(`rolling(14).mean()`), which is Cutler's RSI. Every charting site, and every
reader cross-checking the report, uses **Wilder's smoothing** (an EMA with α = 1/14).
On the 24 tickers with enough history:

| | count |
|---|---|
| \|SMA-RSI − Wilder RSI\| ≥ 5 points | 14 / 24 |
| ≥ 10 points | 4 / 24 (INTC 14.5 vs 36.4, RKLB 16.0 vs 30.2, TSM 26.1 vs 38.0, NU 65.7 vs 54.3) |
| oversold (<30) on SMA-RSI, neutral on Wilder | **7**: INTC, RKLB, TSM, MRVL, PL, ONDS, NBIS |

The reports then call these "超賣", which drives the strategy chapter. ATR uses
an SMA of true range as well, but the gap there is small (≤ 10%, except VST
9.41 vs 7.43). ADX already uses Wilder smoothing.

**Fix:** use `ewm(alpha=1/14, adjust=False)` for RSI and ATR. Alternatively,
label the values as Cutler/SMA in the context so the report doesn't present
them as standard.

### 1.4 Weekly table is labelled with a future date

`close.resample("W")` labels each week by its **Sunday**. The in-progress week
is therefore dated 2026-10-25 in a report generated on 10-23, and 21 of the
27 latest reports cite that date (e.g. PL: 「依據…2026-10-25 週線收盤價精確錨定」).
With an empty last bar, the "10-25" row actually holds 10-21's close.

**Fix:** label each week by its last trading day
(`groupby(pd.Grouper(freq="W"))` → `index.max()`), or use `resample("W-FRI")`.

### 1.5 No O/H/L in the context, but the prompt asks for candlesticks

The context carries closes only: monthly closes, 20 weekly closes, and the
52-week high and low. Ch.3 nevertheless asks for 「重要K線形態」, and all 27
reports describe candles or shadows (錘頭, 十字星, 吞噬, 上/下影線) that cannot
be derived from that data.

Example: SPCX calls the week labelled 10-18 a 「探底回升槌頭線 (Hammer)…留下明顯下影線」.
The real weekly bar was O 164.66 / H 167.07 / L 140.66 / C 146.03, a long
bearish body closing near its low. It closed *below* the S1 $146.24 that the
same row says 「確認有效守住」.

**Fix:** either add the last ~10 daily and ~8 weekly OHLC bars to the context,
or drop the K-line table from the prompt.

### 1.6 RSI divergence is a two-point heuristic

`divergence` compares the price and RSI at the first and last of 20 bars. The
result labels whatever happened over that window; it is not a pivot-based
divergence. The prompt (rule 7) asks the model to "明確判斷" divergence and
supplies only this flag. Low priority, but it should be described honestly in
the context (e.g. "20-bar direction comparison").

### 1.7 Dividend-adjusted history drifts

yfinance history is back-adjusted on each ex-dividend date, so earlier
reports' prices no longer match today's series. For example, ORCL's 10-01…10-09
reports sit about 0.4% above the adjusted closes. This is not a report error,
but any re-check must use unadjusted closes (`auto_adjust=False`) or the price
store.

---

## 2. Prompt — `prompts/technical.txt`

| Check | Status |
|---|---|
| Rule 13: levels must come from 「關鍵價位（由 OHLCV 計算）」 | ✅ obeyed when the block exists (§7.2). When the block is empty the model substitutes Fibonacci levels and weekly closes, which the rule allows only for "形態高度推算" levels |
| Rule 14: multi-timeframe convergence | ⚠️ not checked. Only Ch.8's stated direction was compared, against the scorecard (next row); Ch.7's prose was not |
| Rule 15: pattern confidence % | ✅ present. Patterns under 50% are flagged 「訊號不足」 |
| Strategy routing (≥60 long, ≤40 short, 40–60 range) | ✅ respected in all 27 |
| Length target 「300–500 行」 | ❌ all 27 exceed it (522–709 lines) |
| Composite score definition | ⚠️ undefined. The composite usually equals the mean of the six sub-scores, but differs by 5–8 points in ONDS (32 vs 38.3), RKLB (32 vs 40.0), SPCX (57.8 vs 64.5) and AVGO (45 vs 40.0) |
| R/R definition | ⚠️ undefined: which target? See §4 |
| Missing-data behaviour | ❌ no rule says what to do when the context is `N/A`/`nan`, so the model estimates. Add something like 「若關鍵數據為 N/A，該欄寫 N/A，不得自行估算」, as the fundamental prompt now does |
| K-line patterns (Ch.3) | ❌ not derivable from the context (§1.5) |

---

## 3. Model, parameters, output format

- 25 of the 27 are `gemini-3.8-flash`; MRVL (July) is `gemini-3.5-flash` and SKHY
  (August) is `gemini-3.7-flash`. No fallback to OpenAI occurred in the sample.
- All 27 have the 9 chapters and the summary box, and no refusals or
  truncation. Mermaid blocks per report: 9–12.
- Frontmatter carries no `price`, `price_date` or `data_sources_*` fields
  (the fundamental reports gained them in #84). The page therefore cannot show
  which session a technical report is based on, and QA cannot check it.

---

## 4. Strategy arithmetic — machine-checkable

We parsed 44 entry/stop/target plans from Ch.8:

| Check | Result |
|---|---|
| Stated R/R recomputes from entry, stop and one of the targets | 43 / 44. **TSM** plan A states 1 : 3.48 next to its own 「風險 $11.5，目標2獲利 $51.97」, which is 1 : 4.52 |
| Which target the R/R uses | mixed: about half use T1, half T2. Rarely labelled (PLTR's 「以 T2 計算」 is the exception). An R/R to T2 makes a plan look roughly twice as good |
| Plans recommended with R/R < 1 to T1 | NU plan B (0.46, also stated 0.46). SPCX plan B (0.56 to T1, stated 0.99 to T2) |
| Scenario probabilities sum to 100% | ✅ 26 / 26 that have the table (MRVL's July report predates it) |

**Fix:** define R/R in the prompt as `(T1 − entry) / (entry − stop)`, sign-aware
for shorts. Then add a post-generation check, as `validate/arithmetic.py` does
for §8.8.

---

## 5. QA gates — coverage

Stage 1 (`validate/__init__.py`) has **no technical-specific checks**. Every
defect in this document passed QA, and all 27 reports were published. Cheap,
deterministic additions:

1. **Before generation:** a NaN or missing last close, or an empty `hist`,
   should fail the run (§1.1, §1.2).
2. `$nan` or `nan%` anywhere in the report → flag.
3. The headline 「當前價格」 should match the context's close.
4. Each R1–R3 / S1–S3 value in Ch.4 tables should match the context's computed
   level of the same label (the parser in §7 does this already).
5. Stated R/R should recompute (§4).

Stage 2 (LLM review) cannot catch §1.1–§1.4: the judge never sees the context
or the market data.

---

## 6. Publishing & schedule

- **Stale "latest" reports:** MRVL and SKHY are no longer in the technical
  schedule. Their newest technical reports (2026-07-18, 2026-08-28) are still
  what their ticker pages open with. Either keep them in the schedule or mark
  the page as discontinued.
- **Timing:** the crons (`daily_analysis.yml`) fire from 21:30 UTC. Queueing
  delays mean most runs commit between 00:00 and 03:00 UTC, which overlaps the
  window in which Yahoo's new bar is still empty (§7.4).

---

## 7. Fact-check: every ticker's latest technical report

**Method:**
- **Data:** Yahoo daily OHLCV (`period=3y`) was truncated to the sessions that
  had closed at each report's **git commit time**.
- **Context:** three candidate contexts were rebuilt with the repo's own
  `compute_technicals`: *clean*, *empty last bar* (NaN OHLC, volume kept) and
  *one session stale*. Each report was matched to the candidate sharing the
  most decimal figures with it.
- **What was checked:**
  - indicators and R/S levels quoted in the report against that context
  - the headline price against the real last close
  - the R/R arithmetic and probability sums
- The checking scripts are not committed.

### 7.1 Scorecard

`ctx` = context the report was generated from (✅ clean, 🟥 empty last bar,
⬛ no data). `price Δ` = headline price vs the real last completed close at
commit time. `R/S` = Ch.4 levels equal to the context's level of the same
label. `ind.` = RSI/MA/ATR/ADX/MACD quoted equal to context.

| Ticker | Report | Commit (UTC) | ctx | price Δ | R/S | ind. | Notes |
|---|---|---|---|---|---|---|---|
| 0050 | 10-23 | 10-23 00:07 | ⬛ | **+78.0%** | 0/6 | ✗ | Whole report modelled. $192.50 vs NT$108.15 |
| 2330.TW | 10-23 | 10-23 00:09 | ✅ | 0.0% | — | ✅ | Ch.4 uses its own table layout (no R/S labels parsed) |
| AMD | 10-22 | 10-22 04:31 | ✅ | 0.0% | 6/6 | ✅ | RSI 35.1 (Wilder 45.1) |
| AMZN | 10-23 | 10-23 00:56 | 🟥 | **+4.8%** | 0/6 | ✗ | $262.37 vs $250.38. Bullish breakout plan written after a −4.6% day it never saw |
| AVAV | 10-23 | 10-23 01:56 | ✅ | 0.0% | 3/3 | ✅ | |
| AVGO | 10-22 | 10-22 06:09 | ✅ | 0.0% | 6/6 | ✅ | Composite 45 vs mean 40 |
| GOOG | 10-23 | 10-23 00:47 | 🟥 | **+3.2%** | 0/6 | ✗ | MA20 "$345.07" (real 340.72). RSI 47.5 (real 31.2) |
| GRAB | 10-23 | 10-23 00:39 | 🟥 | −1.1% | 0/4 | ✗ | Reports MA/BB/ATR as N/A, and says so |
| INTC | 10-22 | 10-22 05:36 | ✅ | 0.0% | 6/6 | ✅ | RSI 14.5 "extreme oversold" (Wilder 36.4) |
| KTOS | 10-23 | 10-23 02:01 | ✅ | 0.0% | 3/3 | ✅ | S1 = 52W low (context had no support level), sourced |
| META | 10-23 | 10-23 02:54 | ✅ | 0.0% | 6/6 | ✅ | |
| MRVL | 07-18 | 07-18 23:43 | ✅ | 0.0% | 6/6* | ✅ | *within $0.07 (data revised since). **3 months old**, off schedule |
| MSFT | 10-23 | 10-23 01:00 | 🟥 | **+2.3%** | 0/6 | ✗ | RSI 63.2 (real 52.1). "Strongly recommend long", score 70 |
| NBIS | 10-22 | 10-22 06:27 | ✅ | 0.0% | 6/6 | ✅ | |
| NU | 10-22 | 10-22 05:13 | ✅ | 0.0% | 6/6 | ✅ | Plan B R/R 0.46. RSI 65.7 (Wilder 54.3) |
| NVDA | 10-22 | 10-22 05:04 | ✅ | 0.0% | 5/5 | ✅ | |
| ONDS | 10-23 | 10-23 01:46 | ✅ | 0.0% | 6/6 | ✅ | Composite 32 vs mean 38.3 |
| ORCL | 10-22 | 10-22 05:29 | ✅ | 0.0% | 4/4 | ✅ | |
| PL | 10-23 | 10-23 00:15 | 🟥 | **+4.8%** | 0/4 | ✗ | Header admits 「即時報價欄位…顯示 $nan」. RSI 32.5 (real 23.5) |
| PLTR | 10-23 | 10-23 01:27 | ✅ | 0.0% | 6/6 | ✅ | |
| RKLB | 10-23 | 10-23 01:34 | ✅ | 0.0% | 4/4 | ✅ | Composite 32 vs mean 40. RSI 16.0 (Wilder 30.2) |
| SKHY | 08-28 | 08-28 00:21 | ✅ | 0.0% | 4/4 | ✅ | **2 months old**, off schedule. 35 bars, MA50/200 correctly N/A |
| SOFI | 10-23 | 10-23 01:05 | 🟥 | +0.9% | 0/4 | ✗ | RSI 「33.0 (前週) / nan (當週)」 |
| SPCX | 10-22 | 10-22 06:02 | ✅ | 0.0% | 5/6 | ✅ | R3 is a Fib level (labelled). Invented "hammer" (§1.5). Plan B R/R 0.56 to T1 |
| TSLA | 10-23 | 10-23 00:14 | 🟥 | **+3.2%** | 0/6 | ✗ | Headline 「依最新週收盤價確認」 |
| TSM | 10-23 | 10-23 00:42 | 🟥 | **+4.7%** | 0/6 | ✗ | RSI 45.2 (real 26.1). R/R 3.48 should be 4.52 |
| VST | 10-22 | 10-22 05:20 | ✅ | 0.0% | 6/6 | ✅ | |

### 7.2 Totals

| Check | Result |
|---|---|
| Context intact | 18 / 27 (8 empty last bar, 1 no data) |
| Headline price = last completed close | 18 / 27. The 9 misses are exactly the 9 broken contexts |
| Clean-context reports: indicators quoted = context | **18 / 18** (MRVL within $0.05; data revised since July) |
| Clean-context reports: R/S levels = context, same label | **88 / 90** (the 2 others are a labelled 52W low and a labelled Fib level; MRVL's 5 within $0.07) |
| Empty-bar reports: R/S levels = context | 0 / 42. There were none to quote |
| R/R recomputes | 43 / 44 |
| Probabilities sum to 100% | 26 / 26 |
| Score routing respected | 27 / 27 |
| Future-dated week cited (2026-10-25) | 21 / 27 |
| Candlestick claims without OHLC in context | 27 / 27 |

### 7.3 What the model writes when the context is blank

Real values below are as of the 10-22 close the report should have used, on
the pipeline's own (SMA) RSI:

| Ticker | Headline | Real close | RSI written | RSI real | Other |
|---|---|---|---|---|---|
| AMZN | 262.37 | 250.38 | 54.4 (weekly-table value) | 49.1 | ATR "$5.20–5.80" estimated from weekly ranges (real 7.11) |
| GOOG | 330.95 | 320.76 | 47.5 | 31.2 | MA20 345.07 (real 340.72) |
| MSFT | 532.95 | 521.08 | 63.2 | 52.1 | |
| PL | 13.71 | 13.08 | 32.5 | 23.5 | MA20 13.71 = its own price (real 15.79) |
| SOFI | 14.90 | 14.77 | 33.0 | 39.2 | |
| TSLA | 386.47 | 374.58 | 52.0 | 52.1 | |
| TSM | 431.89 | 412.35 | 45.2 | 26.1 | R/R error (§4) |
| GRAB | 2.82 | 2.85 | — | 37.6 | left N/A |

Six of the eight missed a 2–5% down day on 10-22, and the estimated RSI is off
by up to 19 points.

### 7.4 Scope: all 550 October technical reports

The headline price was compared against the last completed close at commit
time:

| Bucket | Reports | Where |
|---|---|---|
| Fresh | 439 | |
| Previous session's close | **79** | All committed 00:00–01:59 UTC (the empty-bar window). None after 02:00 |
| Other | 31 | 0050 every day (21 reports, $192.5–$198.5 vs NT$108–116). ORCL 10-01…10-09 (9 reports, +0.4%, dividend back-adjustment, §1.7, not an error). 2330.TW 10-13 (1 report, −2.0%) |

By commit hour: at 00 UTC, 40 of 93 reports were stale; at 01 UTC, 39 of 126;
at every other hour, 0 of 330.

### 7.5 What the fact-check shows

1. **The prompt's data discipline works.** Where the context had numbers, the
   reports quote them exactly: 18/18 on indicators and 88/90 on levels.
   Prompt tuning is not where the accuracy problem lies.
2. **The pipeline publishes reports it has no data for.** A NaN last bar, or a
   404 for 0050, produces a confident 600-line report rather than a failed run.
   This is the main fix.
3. **One indicator is mislabelled.** "RSI(14)" is computed in a way readers
   will not reproduce, and in 7 tickers that flips the oversold call.
4. **The context promises more than it carries:** candlesticks without OHLC,
   and a week dated in the future.

---

## Suggested follow-up PRs

1. **fix(technical): never compute from an incomplete bar.**
   - Drop trailing NaN-close rows.
   - Append `quote_close()` when it is a completed close.
   - Abort the run when no price or `hist` is available.
   - Record `price` / `price_date` / `data_sources_*` in the technical
     frontmatter.
   - Tests: an empty last bar, and an empty history.
2. **fix(technical): Wilder RSI/ATR, weekly labels by last trading day,**
   plus last 10 daily / 8 weekly OHLC bars in the context (or drop the K-line
   table).
3. **feat(qa): technical stage-1 checks:** `$nan`, headline vs context close,
   R/S label match, R/R recompute.
4. **prompt:** define R/R (to T1), define the composite score, add a N/A rule,
   and align the length target with reality.
5. **schedule:** decide what MRVL/SKHY technical pages should show.
