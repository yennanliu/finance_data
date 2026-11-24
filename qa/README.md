# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-11-24 |
| Bad reports, last 2 days | 16  (15.8%) |
| Bad reports, all scanned | 1011 |
| CSV | [bad_reports_2026-11-24.csv](bad_reports_2026-11-24.csv) |
| Full summary | [summary_2026-11-24.txt](summary_2026-11-24.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-11-23, 2026-11-24)
Total scanned : 101
Bad reports   : 16  (15.8%)

Issue breakdown:
  DCF_GAP                 13  the computed DCF value is more than 50% away from the price: a reading to review, not an arithmetic error
  RR_TOO_LOW               2  a recommended strategy's reward/risk to T1 is below 1 : 1.5, or its T1 is the current price
  DERIVATION               1  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)

------------------------------------------------------------

All scanned reports
Total scanned : 2887
Bad reports   : 1011  (35.0%)

Issue breakdown:
  RR_TOO_LOW             450  a recommended strategy's reward/risk to T1 is below 1 : 1.5, or its T1 is the current price
  ARITHMETIC             206  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DERIVATION             186  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  DUPLICATE              113  same ticker+type+date with a -2 / -3 suffix
  DCF_GAP                 94  the computed DCF value is more than 50% away from the price: a reading to review, not an arithmetic error
  RR_MISMATCH             29  a stated R/R matches neither target from its own entry/stop
  STORE_MISMATCH          28  the close the report was given is not the committed price store's close for that date
  STALE_PRICE             11  a newer completed session existed before the report date
  MISSING_SECTIONS         7  fundamental report lacks one of chapters ## 1. … ## 11. (## 1. … ## 8. for a fund)
  PLACEHOLDER              6  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  VALUATION_OVERRIDE       4  the §8.8 table is not the methods and weights the pipeline computed (front matter `valuation`)
  NAN_VALUE                3  a $nan / nan% leaked from an empty data bar
  TOO_SHORT                2  fewer content lines than a real report has
  REFUSAL                  1  the model refused instead of writing the report
  CUTOFF                   1  ends mid-sentence or mid-code-block (truncated)
  LEVEL_MISMATCH           1  a Ch.4 R1–S3 is not the computed level of the same label

Top 10 tickers by bad-report count:
  amd            50 / 93   bad
  tsla           49 / 92   bad
  ktos           43 / 93   bad
  pltr           42 / 93   bad
  amzn           41 / 93   bad
  grab           38 / 93   bad
  pl             38 / 93   bad
  2330.tw        37 / 93   bad
  vst            37 / 94   bad
  sofi           36 / 93   bad

CSV written → qa/bad_reports_2026-11-24.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-11-24.csv](llm_review_2026-11-24.csv) |
| Full summary | [llm_review_2026-11-24.txt](llm_review_2026-11-24.txt) |

```

============================================================
Reports reviewed : 166
Mean score       : 4.12 / 5

Verdict breakdown (166 grounded):
  pass             102
  warn              56
  fail               6
  PARSE_ERROR        2

Mean score by dimension:
  data_integrity   4.24
  completeness     4.55
  depth            4.17
  consistency      4.49
  language         4.91

Failed review (6):
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-11-23_openai.md
      → 報告第 3.3 節宣稱「毛利率 80.7%」與「營業利益率 74.6%」，記憶體製造業出現超過 70% 至 80% 的營業利潤率嚴重脫離產業現實。
  sndk         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/sndk/fundamental_analysis_2026-11-23_openai.md
      → 報告所列「TTM 營業利益率 72.5%、最新一季 79.6%」與「毛利率（TTM） 80.0%」，對記憶體製造業而言數據極度不合理且偏離產業現實。
  amd          market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/amd/market_news_2026-11-24_gemini.md
      → 報告中提到的 AMD 最新收盤價為 453.46 美元，但未提供來源，且可能與其他數據不一致。
  qqq          market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/qqq/market_news_2026-11-23_gemini.md
      → 報告中提到的最新交易價格為608.45美元，但未提供來源，可能存在數據誠信問題。
  skhy         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/skhy/market_news_2026-11-23_gemini.md
      → 報告中提到 SK hynix 的 HBM 業務毛利率為 80%，這一數字的合理性需進一步驗證。
  skhy         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/skhy/market_news_2026-11-24_gemini.md
      → 報告中提到 SK 海力士的營業利益率達 80%，這一數字在半導體行業中極為不尋常，可能不具可信性。

CSV written → qa/llm_review_2026-11-24.csv (64 row(s))
```
