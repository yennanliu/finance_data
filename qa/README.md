# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-11-19 |
| Bad reports, last 2 days | 18  (16.5%) |
| Bad reports, all scanned | 931 |
| CSV | [bad_reports_2026-11-19.csv](bad_reports_2026-11-19.csv) |
| Full summary | [summary_2026-11-19.txt](summary_2026-11-19.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-11-18, 2026-11-19)
Total scanned : 109
Bad reports   : 18  (16.5%)

Issue breakdown:
  DCF_GAP                 15  the computed DCF value is more than 50% away from the price: a reading to review, not an arithmetic error
  STALE_PRICE              2  a newer completed session existed before the report date
  VALUATION_OVERRIDE       1  the §8.8 table is not the methods and weights the pipeline computed (front matter `valuation`)

------------------------------------------------------------

All scanned reports
Total scanned : 2573
Bad reports   : 931  (36.2%)

Issue breakdown:
  RR_TOO_LOW             445  a recommended strategy's reward/risk to T1 is below 1 : 1.5, or its T1 is the current price
  ARITHMETIC             206  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DERIVATION             185  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  DUPLICATE              100  same ticker+type+date with a -2 / -3 suffix
  DCF_GAP                 44  the computed DCF value is more than 50% away from the price: a reading to review, not an arithmetic error
  RR_MISMATCH             29  a stated R/R matches neither target from its own entry/stop
  STALE_PRICE             10  a newer completed session existed before the report date
  MISSING_SECTIONS         7  fundamental report lacks one of chapters ## 1. … ## 11. (## 1. … ## 8. for a fund)
  PLACEHOLDER              6  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  VALUATION_OVERRIDE       4  the §8.8 table is not the methods and weights the pipeline computed (front matter `valuation`)
  NAN_VALUE                3  a $nan / nan% leaked from an empty data bar
  TOO_SHORT                2  fewer content lines than a real report has
  REFUSAL                  1  the model refused instead of writing the report
  CUTOFF                   1  ends mid-sentence or mid-code-block (truncated)
  LEVEL_MISMATCH           1  a Ch.4 R1–S3 is not the computed level of the same label

Top 10 tickers by bad-report count:
  amd            45 / 83   bad
  tsla           44 / 82   bad
  ktos           38 / 83   bad
  2330.tw        37 / 83   bad
  pltr           37 / 83   bad
  amzn           36 / 83   bad
  pl             36 / 83   bad
  sofi           35 / 83   bad
  spcx           35 / 84   bad
  avgo           34 / 84   bad

CSV written → qa/bad_reports_2026-11-19.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-11-19.csv](llm_review_2026-11-19.csv) |
| Full summary | [llm_review_2026-11-19.txt](llm_review_2026-11-19.txt) |

```

============================================================
Reports reviewed : 181
Mean score       : 4.11 / 5

Verdict breakdown (181 grounded):
  pass             107
  warn              67
  fail               5
  PARSE_ERROR        2

Mean score by dimension:
  data_integrity   4.28
  completeness     4.50
  depth            4.14
  consistency      4.47
  language         4.93

Failed review (5):
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-11-18_openai.md
      → 報告出現嚴重捏造且荒謬的財務數據，如宣稱 Micron TTM 營收達 $133.19B、營業利益率高達 74.6% 與最新季度達 80.7%，完全偏離半導體記憶體產業實際現實。
  skhy         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/skhy/fundamental_analysis_2026-11-18_openai.md
      → 報告引用「TTM 營業利益率 76.8%」與「淨利率 70.1%」，屬於半導體記憶體製造業極度不合理且失真的獲利數字。
  onds         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/onds/market_news_2026-11-18_gemini.md
      → 報告中提到的股價在財報後遭遇強烈拋售，最新交易日收在 4.39 美元，但未提供該數字的來源。
  spcx         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/spcx/market_news_2026-11-19_gemini.md
      → 報告中提到的 '1,205 億美元' 合約金額與 '120.5 億美元' 的數字不一致。
  wdc          market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/wdc/market_news_2026-11-18_gemini.md
      → 報告中提到WDC股價面臨17%的劇烈回檔，但未提供具體數據來源。

CSV written → qa/llm_review_2026-11-19.csv (74 row(s))
```
