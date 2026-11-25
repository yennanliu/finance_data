# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-11-25 |
| Bad reports, last 2 days | 18  (15.8%) |
| Bad reports, all scanned | 1022 |
| CSV | [bad_reports_2026-11-25.csv](bad_reports_2026-11-25.csv) |
| Full summary | [summary_2026-11-25.txt](summary_2026-11-25.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-11-24, 2026-11-25)
Total scanned : 114
Bad reports   : 18  (15.8%)

Issue breakdown:
  DCF_GAP                 17  the computed DCF value is more than 50% away from the price: a reading to review, not an arithmetic error
  STALE_PRICE              1  a newer completed session existed before the report date

------------------------------------------------------------

All scanned reports
Total scanned : 2950
Bad reports   : 1022  (34.6%)

Issue breakdown:
  RR_TOO_LOW             450  a recommended strategy's reward/risk to T1 is below 1 : 1.5, or its T1 is the current price
  ARITHMETIC             206  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DERIVATION             186  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  DUPLICATE              113  same ticker+type+date with a -2 / -3 suffix
  DCF_GAP                104  the computed DCF value is more than 50% away from the price: a reading to review, not an arithmetic error
  RR_MISMATCH             29  a stated R/R matches neither target from its own entry/stop
  STORE_MISMATCH          28  the close the report was given is not the committed price store's close for that date
  STALE_PRICE             12  a newer completed session existed before the report date
  MISSING_SECTIONS         7  fundamental report lacks one of chapters ## 1. … ## 11. (## 1. … ## 8. for a fund)
  PLACEHOLDER              6  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  VALUATION_OVERRIDE       4  the §8.8 table is not the methods and weights the pipeline computed (front matter `valuation`)
  NAN_VALUE                3  a $nan / nan% leaked from an empty data bar
  TOO_SHORT                2  fewer content lines than a real report has
  REFUSAL                  1  the model refused instead of writing the report
  CUTOFF                   1  ends mid-sentence or mid-code-block (truncated)
  LEVEL_MISMATCH           1  a Ch.4 R1–S3 is not the computed level of the same label

Top 10 tickers by bad-report count:
  amd            51 / 95   bad
  tsla           50 / 94   bad
  ktos           44 / 95   bad
  pltr           43 / 95   bad
  amzn           42 / 95   bad
  grab           39 / 95   bad
  pl             38 / 95   bad
  vst            38 / 96   bad
  2330.tw        37 / 95   bad
  sofi           36 / 95   bad

CSV written → qa/bad_reports_2026-11-25.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-11-25.csv](llm_review_2026-11-25.csv) |
| Full summary | [llm_review_2026-11-25.txt](llm_review_2026-11-25.txt) |

```

============================================================
Reports reviewed : 192
Mean score       : 4.16 / 5

Verdict breakdown (192 grounded):
  pass             114
  warn              69
  fail               3
  PARSE_ERROR        6

Mean score by dimension:
  data_integrity   4.31
  completeness     4.52
  depth            4.15
  consistency      4.52
  language         4.89

Failed review (3):
  amd          market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/amd/market_news_2026-11-24_gemini.md
      → 報告中提到的 AMD 最新收盤價為 453.46 美元，但未提供來源，可能存在數據誠信問題。
  orcl         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/orcl/market_news_2026-11-25_gemini.md
      → 報告中提到甲骨文股價重挫 4.31% 至 109.5 美元，但未提供該數據的來源，可能存在數據誠信問題。
  skhy         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/skhy/market_news_2026-11-24_gemini.md
      → 報告中提到 SK 海力士的營業利益率達 80%，這一數字的合理性存疑。

CSV written → qa/llm_review_2026-11-25.csv (78 row(s))
```
