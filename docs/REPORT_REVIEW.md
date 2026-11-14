# Report Review — Fundamental and Technical Reports

繁體中文版：[REPORT_REVIEW.zh-TW.md](REPORT_REVIEW.zh-TW.md)

A review of the published fundamental and technical reports, scored against the
[InvestSkill](https://github.com/yennanliu/InvestSkill) rubric, with a ranked
list of what to improve.

| | |
|---|---|
| **Reviewed** | 2026-11-14, at commit `e89c59ccc` |
| **Scope** | The latest report of every ticker: 38 fundamental (30 companies, 8 ETFs) and 26 technical |
| **Models** | `gpt-6-luna` wrote all 38 fundamental and 24 of the 26 technical reports. The other 2 are `gemini-3.8-flash` |
| **Rubric** | InvestSkill v1.14.1: `stock-eval`, `technical-analysis`, `result-validator`, and the output contract that `fact-check` enforces |
| **Method** | One report of each type read in full (NVDA, 2026-11-14). Every pattern found there was then counted across all 64 reports by script |

**What this review did not do.** No figure was checked against an SEC filing.
The counts below come from the report text, the report front matter, and the
price and fundamentals stores in `data/`. The earlier filing-level fact-checks
are in PR #82 (fundamental) and PR #86 (technical).

---

## 1. Verdict

Both report types are **usable but not yet reliable enough to act on**. The
writing is disciplined: figures are quoted from the data, gaps are marked
`N/A` instead of invented, and every report says what would prove it wrong.
The weak points are in the numbers behind the conclusion:

- **Fundamental:** the rating is decided by valuation weights that the model
  picks itself, and the DCF sits far below the market price in 27 of 30 company
  reports.
- **Technical:** the "weekly" indicators are daily values, and 11 of 26 reports
  recommend a trade whose reward is smaller than its risk.

### Score against `result-validator`

Scored on the two NVDA reports. These are one reviewer's reading of one sample
each, so treat them as a baseline, not a measurement.

| Dimension (0–20) | Fundamental | Technical | Main reason for lost points |
|---|---:|---:|---|
| Data quality | 10 | 10 | No `Data & Sources` header, which caps this dimension at 10 |
| Methodology | 13 | 16 | Fundamental: WACC 16.26% and assumed multiples. Technical: unbacked probabilities |
| Signal consistency | 6 | 2 | The two reports disagree (Buy vs. bearish 18/100) and neither mentions the other. No insider, institutional or sector context |
| Risk coverage | 16 | 14 | Catalysts are generic. No dated events such as the next earnings release |
| Reasoning transparency | 16 | 18 | Fundamental rates Buy while its own DCF says −48% |
| **Total (0–100)** | **61** | **60** | Tier: **MEDIUM**. "Usable but has notable gaps" |

### Output contract

`result-validator` checks three things before it scores anything.

| Contract item | Fundamental | Technical |
|---|---|---|
| `Data & Sources` header (as-of, source, retrieval, confidence) | Partial. Sources and price date are in the front matter. No confidence, no as-of date per source | Partial. Same |
| Thesis invalidation section | Yes (§11.6) | Yes (§8, reverse-risk triggers). No "re-run when" list |
| Signal block with machine-readable footer | No. Rating and score are prose only | No. Score and direction are prose only |

---

## 2. What already works

Keep these. They are the reason the reports score MEDIUM and not LOW.

- **Figures computed in Python and quoted by the model** (`fundamental_facts.py`,
  the `VERIFIED FIGURES` block).
- **The §8.8 recheck.** The weighted fair value is recomputed and written back.
  8 of the 38 latest reports were corrected this way.
- **Honest gaps.** The NVDA technical report found no support below the price
  and wrote `N/A` rather than inventing one.
- **Price, price date and levels in front matter**, so QA can compare them with
  the market record.
- **Shown arithmetic.** Every reward/risk ratio and every DCF step can be redone
  with a calculator.

---

## 3. Fundamental report — what to improve

Ordered by how much each item changes the conclusion a reader takes away.

### F1. The model chooses the valuation weights, and the weights decide the rating

The rating follows the margin of safety, which follows the weighted fair value
in §8.8. The model sets those weights per report.

| Evidence | |
|---|---|
| DCF weight across the 30 company reports | From **10%** (VST) to **70%** (SPCX) |
| ORCL | DCF $23.17 against a price of $125.35 (−82%), yet rated **Buy** |
| NVDA | DCF $83.99 against $162.85 (−48%), yet rated **Buy** on a forward P/E "× 20x, an assumed multiple" |

**Fix.** Set the weights in Python by company type (profitable, loss-making,
cyclical, financial) and pass them in the `VERIFIED FIGURES` block. The model
explains the weights. It does not choose them.

### F2. The DCF is far below the price in almost every report

| Evidence (30 company reports) | |
|---|---|
| DCF below the market price | **27 of 30** |
| DCF more than 40% below | **21 of 30** |
| Median gap | **−57%** |
| Examples | MSFT −52%, GOOG −51%, META −75%, TSLA −94% |
| Ratings that result | Sell 14, Reduce 5, Hold 6, Buy 5 |

A model that values most large companies at half their price or less is more
likely biased than right. Three causes are visible in the reports:

1. **Raw beta in CAPM.** 12 of 30 reports discount at a WACC of 15% or more.
   NVDA uses beta 2.25, which gives 16.26%.
2. **A five-year forecast with a Gordon terminal value** at that discount rate.
3. **Understated cash** (see F3).

**Fix.** Use an adjusted beta (for example Blume: ⅔ × raw + ⅓) with a ceiling,
and flag any WACC outside a stated band. Add a stage-1 QA check that warns when
the DCF is more than 50% away from the price, so the gap is reviewed and not
just published.

### F3. "Verified" cash leaves out marketable securities

`fundamentals.py` maps short-term investments from two XBRL tags only. Companies
that report them under another tag get none.

| Evidence | |
|---|---|
| Store tickers with no short-term investments in the last 8 quarters | 14 of 24 (AMZN, GOOG, META, NVDA, PLTR, UBER and others) |
| NVDA, verified cash | **$22.44B** |
| NVDA, cash and short-term investments from StockAnalysis, same report | **$62.47B** |
| Effect | The report treats NVDA as **$10.92B net debt**. That figure feeds the DCF bridge and ROIC |

Some of the 14 may truly hold none. NVDA clearly does not.

**Fix.** Add the missing tags to `INSTANT_CONCEPTS` (`MarketableSecuritiesCurrent`
is the likely one; confirm against each company's XBRL facts), rebuild the store,
and add a check that compares store cash with Yahoo's `totalCash`.

### F4. ETFs are run through the company template

The 8 ETF reports (0050, QQQ, ROBO, SMH, SOXQ, SOXX, VTI, WQTM) are about 1,000
lines each and contain **417 to 461 `N/A`** each. Company reports contain 38 to
144. QQQ's rating is "Hold, margin of safety 0%", because the report uses the
market price as its own fair value.

**Fix.** Add an ETF prompt and context branch built on InvestSkill's
`etf-analysis`: expense ratio, tracking difference, holdings concentration,
overlap, distributions. Fetch holdings. Until then, skip the fundamental run for
funds.

### F5. Some valuation methods return the price they are meant to test

| Report | Method | Problem |
|---|---|---|
| NVDA | EV/EBITDA, 15% weight | "Held at the current multiple", so it returns $163.90 against a price of $162.85 |
| MU | FCF yield, 10% weight | Uses the current yield, so it returns $799.00 against $798.44 |
| NU | "Relative valuation", 25% weight | Is the analyst consensus, which is also listed at 5%. Consensus carries 30% in total against a 10% cap |
| UBER | Forward P/E and EV/EBITDA | "Estimated; peer multiples not provided" |
| GRAB | FCF yield, 5% weight | The value is `N/A` but the weight is kept |

**Fix.** Compute peer-median multiples in Python and require each method to use
them. Reject in QA any method within 2% of the price, any `N/A` method with a
weight, and any source counted twice.

### F6. The DCF tables are estimated by the model, not calculated

In the NVDA report the sensitivity grid moves in uneven steps, the worked
example gives $91.5 where the grid shows $91.96, and the reverse DCF is labelled
"approximate trial values". One sentence still carries the model's own
correction: "…低於目前 TTM FCF/營收 = 41.9%不對；實際計算約 41.9%…".

The site also shows a second fair value. `intrinsic_value.py` drives the Market
Data page with a different model (10% discount rate, two stages), so one ticker
has two intrinsic values that are never reconciled.

**Fix.** Compute the forecast, sensitivity grid and reverse DCF in Python and
have the report quote them. Use one model for the site and the report, or state
on both pages why they differ.

### F7. The §8.8 recheck skips reports it could check

`arithmetic_check` is `unparsed` for 6 of 30 company reports (2330.TW, AMZN,
AVGO, MSFT, ORCL, SPCX). The validator reads the one-line formula under the
table, and these reports laid the formula out differently. Their tables are
well formed. Read directly, all six sum to the stated value.

**Fix.** Recompute from the table rows (value × weight) and use the prose
formula only as a fallback.

### F8. Analysis that `stock-eval` expects and the reports lack

| Missing | Reports that have it |
|---|---|
| Piotroski F-Score | 0 of 38 |
| Porter's five forces | 0 of 38 |
| Insider ownership and transactions | 0 of 38 |
| Working-capital days (DSO, DIO, DPO) | 1 of 38 |
| Earnings beat/miss history | `N/A`. The estimate column arrives as `nan` |
| Segment revenue | `N/A`. No segment data is fetched |
| Sector metrics | SOFI and NU are lenders valued with an operating-company DCF |

The F-Score and working-capital days need only fields the store already holds,
so they belong in `fundamental_facts.py`. Banks need the sector pack: NIM,
efficiency ratio, charge-offs, P/TBV.

### F9. The template asks for content the data cannot support

- **Charts with made-up numbers.** Five reports draw a market-share pie marked
  "illustrative" (NVDA: 70 / 15 / 15).
- **Empty sections.** NVDA's TAM box, its "industry average" and "S&P 500
  average" columns, and its DuPont diagram are all `N/A`. Total assets and equity
  are in the data, so the DuPont factors could be computed.
- **Scenario targets that are not derived.** NVDA's bear and bull targets are
  $100 and $300, with no formula linking them to the stated assumptions.
- **Three scorecards.** §1.1 has 5 rows, §1.2 has 8 and §11.1 has 6, with
  different scores for similar items and no formula for the total.
- **Pipeline wording.** 35 of 38 reports say "資料包" (the data pack), a median
  of 14 times each.

**Fix.** Make each section conditional on its data, keep one scorecard with a
defined formula, and tell the model to name the source rather than "the data
pack".

### F10. No provenance header and no machine-readable rating

Neither `rating` nor the composite score is in the front matter, so the site
and QA cannot read them. **Fix.** Add `rating`, `score` and `fair_value` to the
front matter, and render a short `Data & Sources` block from fields the
pipeline already has (`data_sources_ok`, `price_date`, latest filing period).

---

## 4. Technical report — what to improve

### T1. The "weekly" indicators are daily indicators

`technicals.py` builds the 20-week table from the **daily** RSI and MACD
histogram, sampled on each week's last trading day. The columns are headed just
"RSI" and "MACD柱". Reports then call them weekly.

| Evidence | |
|---|---|
| NVDA report | "週 RSI 24.9" and "週 MACD 柱 −4.124", both equal to the daily values |
| Recomputed from the price store (bars to 2026-11-12) | Daily RSI 26.0, **true weekly RSI 33.4**. Daily histogram −4.16, **true weekly −6.28** |
| Reports that use "週 RSI" or "週 MACD" wording | 21 of 26 |
| Monthly indicators | None are computed |

The multi-timeframe chapter therefore rests on one timeframe. In the NVDA case
the daily RSI is oversold and the weekly RSI is not.

**Fix.** Compute RSI, MACD and moving averages on the weekly and monthly bars
and label every column with its timeframe. Add the 3-timeframe alignment score
(X/3) from the skill.

### T2. Trades with poor reward for the risk are recommended

| Evidence | |
|---|---|
| Reports with a strategy whose reward/risk to the first target is below 1 | **At least 11 of 26** |
| Lowest | NVDA strategy A, **1 : 0.39**, ranked first choice (🥇) |
| Its stated win rate | 55%, which gives an expected loss of about 0.24 of the risk per trade |
| First target set to the current close | NVDA and MSFT |

Stage-1 QA checks that each ratio matches its prices. It does not check whether
the trade is worth taking.

**Fix.** Add a prompt rule and a validator check: no strategy below 1 : 1.5 to
the first target, otherwise the report says "no trade at this level". A target
may not equal the current price.

### T3. Probabilities have no basis

Scenario probabilities (NVDA: 65 / 20 / 15), strategy win rates and pattern
confidence are the model's estimates. The reports say so, but the numbers still
read as measurements.

**Fix.** Compute base rates in Python from the 10-year price store (for example
the 20-day forward return after RSI below 30 with ADX above 40), or replace the
percentages with High / Medium / Low.

### T4. No market context

| Missing | Reports that have it |
|---|---|
| Relative strength against a benchmark or sector ETF | 2 of 26 mention one. None compute it |
| Next earnings date or other dated event | 0 of 26 |
| Price gaps | Not detected. NVDA opened 13% below the prior close on 2026-11-12, and the report calls that bar a "long bullish candle" |

**Fix.** Add to the context: relative strength against SPY and the sector ETF
(both are in the price store), detected gaps from the daily bars, and the next
earnings date.

### T5. Levels run out when the price is at a low

Supports come from swing lows in the last 252 bars. With NVDA near its 52-week
low the report has no S1 to S3 and no downside target, although the store holds
ten years of bars.

**Fix.** When fewer than two supports are found, widen the lookback to two and
then five years, and add classic pivot points as a fallback.

### T6. Too long, and the charts add little

| Evidence | |
|---|---|
| Reports over the prompt's own 500–700 line target | 24 of 26 (median 818) |
| The most repeated price in one report | Printed 24 to 43 times |
| Diagrams per report | About 10 Mermaid and 10 ASCII blocks |
| ASCII price chart | Misdrawn. NVDA's January close of $190.68 sits on the $170 row |

The site already renders an interactive K-line chart on the same page.

**Fix.** Drop the hand-drawn ASCII price chart and the decorative Mermaid
flowcharts. Keep tables. State each figure once, in the chapter that owns it.

### T7. Indicators the skill lists and the reports lack

Ichimoku cloud, volume profile (POC, value area), VWAP, accumulation /
distribution and pivot points. All can be computed from the bars already
fetched. Options flow needs a new data source and is out of scope.

### T8. No machine-readable signal, and prompt wording leaks

The composite score and direction are not in the front matter, and `levels`
lists resistances only when no support exists. Five reports cite their source
as "題示" ("given in the prompt"). **Fix.** Add `score` and `signal` to the
front matter, and tell the model to write "Yahoo Finance" as the source.

---

## 5. Suggested order

Each row is small enough to be one PR.

| Priority | Change | Fixes | Where |
|---|---|---|---|
| **P0** | Map the missing marketable-securities tags and rebuild the store | F3 | `data/fundamentals.py` |
| **P0** | Compute real weekly and monthly indicators and label them | T1 | `data/technicals.py` |
| **P0** | Minimum reward/risk rule in the prompt and the validator | T2 | `prompts/technical.txt`, `validate/technical.py` |
| **P0** | Recheck §8.8 from the table rows | F7 | `validate/arithmetic.py` |
| **P1** | Fixed valuation weights and peer multiples from Python | F1, F5 | `fundamental_facts.py`, `prompts/fundamental.txt` |
| **P1** | Adjusted beta, WACC band, and a QA warning for large DCF gaps | F2 | `fundamental_facts.py`, `check_report_quality.py` |
| **P1** | Python DCF, sensitivity grid and reverse DCF | F6 | `data/intrinsic_value.py` |
| **P1** | ETF prompt and context branch | F4 | `prompts/`, `context/__init__.py` |
| **P1** | Relative strength, gaps and earnings date in the context | T4 | `data/technicals.py` |
| **P2** | `rating`, `score`, `signal` in front matter, and a `Data & Sources` block | F10, T8 | `pipeline.py` |
| **P2** | Conditional sections, one scorecard, shorter technical template | F9, T6 | both prompts |
| **P2** | F-Score, working-capital days, bank metrics, base rates, wider level lookback | F8, T3, T5, T7 | `fundamental_facts.py`, `technicals.py` |

After each P0 or P1 change, regenerate one ticker and compare it with this
baseline: the 61 and 60 scores in §1 and the counts in §3 and §4.

---

## 6. How to reproduce

- **Rubric.** `claude plugin update us-stock-analysis@invest-skill`, then read
  `skills/stock-eval`, `skills/technical-analysis` and `skills/result-validator`.
- **Sample.** The latest file in each `ai_gen_report/{fundamental,technical}/<ticker>/`.
- **Counts.** Read from the report text: the §8.8 table (method, value, weight),
  the §1.5 rating box, the strategy table in chapter 8 of the technical report,
  and the front matter.
- **Weekly RSI.** Wilder RSI(14) on `data/prices/nvda.csv`, daily closes
  against weekly last closes.
