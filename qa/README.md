# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-11-17 |
| Bad reports, last 2 days | 9  (9.6%) |
| Bad reports, all scanned | 905 |
| CSV | [bad_reports_2026-11-17.csv](bad_reports_2026-11-17.csv) |
| Full summary | [summary_2026-11-17.txt](summary_2026-11-17.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-11-16, 2026-11-17)
Total scanned : 94
Bad reports   : 9  (9.6%)

Issue breakdown:
  DCF_GAP                  9  the computed DCF value is more than 50% away from the price: a reading to review, not an arithmetic error

------------------------------------------------------------

All scanned reports
Total scanned : 2447
Bad reports   : 905  (37.0%)

Issue breakdown:
  RR_TOO_LOW             445  a recommended strategy's reward/risk to T1 is below 1 : 1.5, or its T1 is the current price
  ARITHMETIC             206  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DERIVATION             185  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  DUPLICATE               94  same ticker+type+date with a -2 / -3 suffix
  RR_MISMATCH             29  a stated R/R matches neither target from its own entry/stop
  DCF_GAP                 25  the computed DCF value is more than 50% away from the price: a reading to review, not an arithmetic error
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
  amd            43 / 79   bad
  tsla           42 / 78   bad
  ktos           36 / 79   bad
  2330.tw        35 / 79   bad
  pl             35 / 79   bad
  pltr           35 / 79   bad
  sofi           35 / 79   bad
  spcx           35 / 80   bad
  amzn           34 / 79   bad
  avgo           34 / 80   bad

CSV written → qa/bad_reports_2026-11-17.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-11-17.csv](llm_review_2026-11-17.csv) |
| Full summary | [llm_review_2026-11-17.txt](llm_review_2026-11-17.txt) |

```

============================================================
Reports reviewed : 153
Mean score       : 4.20 / 5

Verdict breakdown (153 grounded):
  pass              97
  warn              51
  fail               4
  PARSE_ERROR        1

Mean score by dimension:
  data_integrity   4.32
  completeness     4.55
  depth            4.19
  consistency      4.53
  language         4.90

Failed review (4):
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-11-16_openai.md
      → 報告列出 MU 的 TTM 營收為 $133.19B、營業利益率高達 74.6%（最新一季 80.7%）及淨利 $84.97B，對記憶體製造商而言嚴重偏離真實與合理產業財務常理。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-11-17_openai.md
      → 記憶體製造商之 TTM 營業利益率達「74.6%」（最新一季更列「80.7%」）及毛利率「80.7%」，屬於評審指引中明定的典型不合理失真數據。
  sndk         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/sndk/fundamental_analysis_2026-11-16_openai.md
      → 報告宣稱記憶體製造商 SNDK 最新單季營業利益率達 79.6%、TTM 達 72.5%，且 DCF 模型第 10 年仍假設 61.2% 的營業利益率，屬於嚴重背離半導體與儲存製造業常理的極端不合理數字。
  onds         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/onds/market_news_2026-11-17_gemini.md
      → 報告中提到的 1.675 億美元營收與 1,550% 年增幅的數據未能提供合理的基期支持，可能存在數據誠信問題。

CSV written → qa/llm_review_2026-11-17.csv (56 row(s))
```
