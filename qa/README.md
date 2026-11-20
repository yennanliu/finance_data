# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-11-20 |
| Bad reports, last 2 days | 17  (15.7%) |
| Bad reports, all scanned | 942 |
| CSV | [bad_reports_2026-11-20.csv](bad_reports_2026-11-20.csv) |
| Full summary | [summary_2026-11-20.txt](summary_2026-11-20.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-11-19, 2026-11-20)
Total scanned : 108
Bad reports   : 17  (15.7%)

Issue breakdown:
  DCF_GAP                 15  the computed DCF value is more than 50% away from the price: a reading to review, not an arithmetic error
  STALE_PRICE              2  a newer completed session existed before the report date

------------------------------------------------------------

All scanned reports
Total scanned : 2635
Bad reports   : 942  (35.7%)

Issue breakdown:
  RR_TOO_LOW             445  a recommended strategy's reward/risk to T1 is below 1 : 1.5, or its T1 is the current price
  ARITHMETIC             206  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DERIVATION             185  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  DUPLICATE              100  same ticker+type+date with a -2 / -3 suffix
  DCF_GAP                 54  the computed DCF value is more than 50% away from the price: a reading to review, not an arithmetic error
  RR_MISMATCH             29  a stated R/R matches neither target from its own entry/stop
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
  amd            46 / 85   bad
  tsla           45 / 84   bad
  ktos           39 / 85   bad
  pltr           38 / 85   bad
  2330.tw        37 / 85   bad
  amzn           37 / 85   bad
  pl             36 / 85   bad
  sofi           35 / 85   bad
  spcx           35 / 86   bad
  avgo           34 / 86   bad

CSV written → qa/bad_reports_2026-11-20.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-11-20.csv](llm_review_2026-11-20.csv) |
| Full summary | [llm_review_2026-11-20.txt](llm_review_2026-11-20.txt) |

```

============================================================
Reports reviewed : 180
Mean score       : 4.15 / 5

Verdict breakdown (180 grounded):
  pass             106
  warn              67
  fail               3
  PARSE_ERROR        4

Mean score by dimension:
  data_integrity   4.28
  completeness     4.53
  depth            4.16
  consistency      4.51
  language         4.93

Failed review (3):
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-11-19_openai.md
      → 報告列出 TTM 營業利益率「74.6%」與最新一季營業利益率「80.7%」，毛利率高達「80.7%」，嚴重違背半導體記憶體製造商的實際營運水準與產業常態。
  amd          market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/amd/market_news_2026-11-20_gemini.md
      → 報告中提到「單日市值劇烈蒸發 670 億美元」，但未提供具體數據來源，存在數據誠信問題。
  spcx         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/spcx/market_news_2026-11-19_gemini.md
      → 報告中提到的 '1,205 億美元' 合約金額與 '120.5 億美元' 的數字不一致。

CSV written → qa/llm_review_2026-11-20.csv (74 row(s))
```
