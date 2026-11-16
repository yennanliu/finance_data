# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-11-16 |
| Bad reports, last 2 days | 11  (11.8%) |
| Bad reports, all scanned | 896 |
| CSV | [bad_reports_2026-11-16.csv](bad_reports_2026-11-16.csv) |
| Full summary | [summary_2026-11-16.txt](summary_2026-11-16.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-11-15, 2026-11-16)
Total scanned : 93
Bad reports   : 11  (11.8%)

Issue breakdown:
  DCF_GAP                  9  the computed DCF value is more than 50% away from the price: a reading to review, not an arithmetic error
  VALUATION_OVERRIDE       1  the §8.8 table is not the methods and weights the pipeline computed (front matter `valuation`)
  DERIVATION               1  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)

------------------------------------------------------------

All scanned reports
Total scanned : 2383
Bad reports   : 896  (37.6%)

Issue breakdown:
  RR_TOO_LOW             445  a recommended strategy's reward/risk to T1 is below 1 : 1.5, or its T1 is the current price
  ARITHMETIC             206  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DERIVATION             185  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  DUPLICATE               94  same ticker+type+date with a -2 / -3 suffix
  RR_MISMATCH             29  a stated R/R matches neither target from its own entry/stop
  DCF_GAP                 16  the computed DCF value is more than 50% away from the price: a reading to review, not an arithmetic error
  STALE_PRICE              8  a newer completed session existed before the report date
  MISSING_SECTIONS         7  fundamental report lacks one of chapters ## 1. … ## 11. (## 1. … ## 8. for a fund)
  PLACEHOLDER              6  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  NAN_VALUE                3  a $nan / nan% leaked from an empty data bar
  VALUATION_OVERRIDE       2  the §8.8 table is not the methods and weights the pipeline computed (front matter `valuation`)
  TOO_SHORT                2  fewer content lines than a real report has
  REFUSAL                  1  the model refused instead of writing the report
  CUTOFF                   1  ends mid-sentence or mid-code-block (truncated)
  LEVEL_MISMATCH           1  a Ch.4 R1–S3 is not the computed level of the same label

Top 10 tickers by bad-report count:
  amd            42 / 77   bad
  tsla           41 / 76   bad
  2330.tw        35 / 77   bad
  ktos           35 / 77   bad
  pl             35 / 77   bad
  sofi           35 / 77   bad
  spcx           35 / 78   bad
  avgo           34 / 78   bad
  pltr           34 / 77   bad
  amzn           33 / 77   bad

CSV written → qa/bad_reports_2026-11-16.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-11-16.csv](llm_review_2026-11-16.csv) |
| Full summary | [llm_review_2026-11-16.txt](llm_review_2026-11-16.txt) |

```

============================================================
Reports reviewed : 150
Mean score       : 4.18 / 5

Verdict breakdown (150 grounded):
  pass              93
  warn              48
  fail               5
  PARSE_ERROR        4

Mean score by dimension:
  data_integrity   4.34
  completeness     4.52
  depth            4.21
  consistency      4.52
  language         4.93

Failed review (5):
  sndk         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/sndk/fundamental_analysis_2026-11-15_openai.md
      → 報告列示記憶體製造商 SNDK 之 TTM 毛利率達 80.0%、營業利益率達 72.5%（最新單季達 79.6%），嚴重偏離半導體儲存產業常態與真實財務邏輯。
  0050         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/0050/market_news_2026-11-15_gemini.md
      → 報告中提到的 'No news for 0050 in the past two years' 與市場實際情況可能不符，存在數據誠信問題。
  onds         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/onds/market_news_2026-11-15_gemini.md
      → 報告中提到的單季營收達到創紀錄的 1.675 億美元，按年暴增 1,550%，但未提供去年基期的具體數字，可能存在數據誠信問題。
  orcl         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/orcl/market_news_2026-11-16_gemini.md
      → 報告中提到的最新收盤價 125.35 美元與報告日期不符，應為 2026-11-16。
  qqq          market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/qqq/market_news_2026-11-15_gemini.md
      → 報告中提到的QQQ最新收盤價為679.89 USD，但未提供來源，可能存在數據誠信問題。

CSV written → qa/llm_review_2026-11-16.csv (57 row(s))
```
