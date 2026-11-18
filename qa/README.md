# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-11-18 |
| Bad reports, last 2 days | 21  (18.4%) |
| Bad reports, all scanned | 919 |
| CSV | [bad_reports_2026-11-18.csv](bad_reports_2026-11-18.csv) |
| Full summary | [summary_2026-11-18.txt](summary_2026-11-18.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-11-17, 2026-11-18)
Total scanned : 114
Bad reports   : 21  (18.4%)

Issue breakdown:
  DCF_GAP                 16  the computed DCF value is more than 50% away from the price: a reading to review, not an arithmetic error
  DUPLICATE                6  same ticker+type+date with a -2 / -3 suffix
  VALUATION_OVERRIDE       1  the §8.8 table is not the methods and weights the pipeline computed (front matter `valuation`)
  STALE_PRICE              1  a newer completed session existed before the report date

------------------------------------------------------------

All scanned reports
Total scanned : 2509
Bad reports   : 919  (36.6%)

Issue breakdown:
  RR_TOO_LOW             445  a recommended strategy's reward/risk to T1 is below 1 : 1.5, or its T1 is the current price
  ARITHMETIC             206  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DERIVATION             185  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  DUPLICATE              100  same ticker+type+date with a -2 / -3 suffix
  DCF_GAP                 34  the computed DCF value is more than 50% away from the price: a reading to review, not an arithmetic error
  RR_MISMATCH             29  a stated R/R matches neither target from its own entry/stop
  STALE_PRICE              9  a newer completed session existed before the report date
  MISSING_SECTIONS         7  fundamental report lacks one of chapters ## 1. … ## 11. (## 1. … ## 8. for a fund)
  PLACEHOLDER              6  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  VALUATION_OVERRIDE       3  the §8.8 table is not the methods and weights the pipeline computed (front matter `valuation`)
  NAN_VALUE                3  a $nan / nan% leaked from an empty data bar
  TOO_SHORT                2  fewer content lines than a real report has
  REFUSAL                  1  the model refused instead of writing the report
  CUTOFF                   1  ends mid-sentence or mid-code-block (truncated)
  LEVEL_MISMATCH           1  a Ch.4 R1–S3 is not the computed level of the same label

Top 10 tickers by bad-report count:
  amd            44 / 81   bad
  tsla           43 / 80   bad
  ktos           37 / 81   bad
  2330.tw        36 / 81   bad
  pl             36 / 81   bad
  pltr           36 / 81   bad
  amzn           35 / 81   bad
  sofi           35 / 81   bad
  spcx           35 / 82   bad
  avgo           34 / 82   bad

CSV written → qa/bad_reports_2026-11-18.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-11-18.csv](llm_review_2026-11-18.csv) |
| Full summary | [llm_review_2026-11-18.txt](llm_review_2026-11-18.txt) |

```

============================================================
Reports reviewed : 188
Mean score       : 4.14 / 5

Verdict breakdown (188 grounded):
  pass             117
  warn              64
  fail               6
  PARSE_ERROR        1

Mean score by dimension:
  data_integrity   4.33
  completeness     4.51
  depth            4.19
  consistency      4.50
  language         4.93

Failed review (6):
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-11-17_openai.md
      → 報告宣稱美光（MU）TTM 營收達 $133.19B、毛利率達 80.7%、營業利益率達 74.6%，為典型記憶體製造商不可能達到的荒謬捏造數字。
  sndk         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/sndk/fundamental_analysis_2026-11-17_openai.md
      → 記憶體製造商出現 TTM 毛利率 80.0% 與營業利益率 72.5%（第 3.3 節），數字明顯背離記憶體產業真實財務結構與常理。
  onds         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/onds/market_news_2026-11-18_gemini.md
      → 報告中提到的股價在財報後遭遇強烈拋售，最新交易日收在 4.39 美元，但未提供該數字的來源。
  orcl         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/orcl/market_news_2026-11-17_gemini.md
      → 報告中提到的 ORCL 股價在 2026 年內重挫達 34%，但未提供具體的數據來源，造成數據誠信問題。
  skhy         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/skhy/market_news_2026-11-17_gemini.md
      → 報告中提到的80%利潤率缺乏合理性，可能導致數據誠信問題。
  tsm          market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/tsm/market_news_2026-11-18_gemini.md
      → 報告日期標示為 2026-11-17，但標題為 2026-11-18，存在日期不一致的問題。

CSV written → qa/llm_review_2026-11-18.csv (71 row(s))
```
