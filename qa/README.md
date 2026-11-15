# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-11-15 |
| Bad reports, last 2 days | 35  (34.0%) |
| Bad reports, all scanned | 885 |
| CSV | [bad_reports_2026-11-15.csv](bad_reports_2026-11-15.csv) |
| Full summary | [summary_2026-11-15.txt](summary_2026-11-15.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-11-14, 2026-11-15)
Total scanned : 103
Bad reports   : 35  (34.0%)

Issue breakdown:
  RR_TOO_LOW              20  a recommended strategy's reward/risk to T1 is below 1 : 1.5, or its T1 is the current price
  DUPLICATE                9  same ticker+type+date with a -2 / -3 suffix
  DCF_GAP                  7  the computed DCF value is more than 50% away from the price: a reading to review, not an arithmetic error
  VALUATION_OVERRIDE       1  the §8.8 table is not the methods and weights the pipeline computed (front matter `valuation`)
  ARITHMETIC               1  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures

------------------------------------------------------------

All scanned reports
Total scanned : 2320
Bad reports   : 885  (38.1%)

Issue breakdown:
  RR_TOO_LOW             445  a recommended strategy's reward/risk to T1 is below 1 : 1.5, or its T1 is the current price
  ARITHMETIC             206  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DERIVATION             184  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  DUPLICATE               94  same ticker+type+date with a -2 / -3 suffix
  RR_MISMATCH             29  a stated R/R matches neither target from its own entry/stop
  STALE_PRICE              8  a newer completed session existed before the report date
  DCF_GAP                  7  the computed DCF value is more than 50% away from the price: a reading to review, not an arithmetic error
  MISSING_SECTIONS         7  fundamental report lacks one of chapters ## 1. … ## 11. (## 1. … ## 8. for a fund)
  PLACEHOLDER              6  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  NAN_VALUE                3  a $nan / nan% leaked from an empty data bar
  TOO_SHORT                2  fewer content lines than a real report has
  VALUATION_OVERRIDE       1  the §8.8 table is not the methods and weights the pipeline computed (front matter `valuation`)
  REFUSAL                  1  the model refused instead of writing the report
  CUTOFF                   1  ends mid-sentence or mid-code-block (truncated)
  LEVEL_MISMATCH           1  a Ch.4 R1–S3 is not the computed level of the same label

Top 10 tickers by bad-report count:
  amd            41 / 75   bad
  tsla           40 / 74   bad
  pl             35 / 75   bad
  spcx           35 / 76   bad
  2330.tw        34 / 75   bad
  avgo           34 / 76   bad
  ktos           34 / 75   bad
  sofi           34 / 75   bad
  intc           33 / 75   bad
  nu             33 / 76   bad

CSV written → qa/bad_reports_2026-11-15.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-11-15.csv](llm_review_2026-11-15.csv) |
| Full summary | [llm_review_2026-11-15.txt](llm_review_2026-11-15.txt) |

```

============================================================
Reports reviewed : 160
Mean score       : 4.23 / 5

Verdict breakdown (160 grounded):
  pass             102
  warn              53
  fail               1
  PARSE_ERROR        4

Mean score by dimension:
  data_integrity   4.38
  completeness     4.58
  depth            4.22
  consistency      4.54
  language         4.92

Failed review (1):
  nvda         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/nvda/market_news_2026-11-14_gemini.md
      → 報告中提到的股價跌破165美元，但未提供具體的數據來源或確認。

CSV written → qa/llm_review_2026-11-15.csv (58 row(s))
```
