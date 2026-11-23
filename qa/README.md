# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-11-23 |
| Bad reports, last 2 days | 16  (16.7%) |
| Bad reports, all scanned | 1001 |
| CSV | [bad_reports_2026-11-23.csv](bad_reports_2026-11-23.csv) |
| Full summary | [summary_2026-11-23.txt](summary_2026-11-23.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-11-22, 2026-11-23)
Total scanned : 96
Bad reports   : 16  (16.7%)

Issue breakdown:
  DCF_GAP                 11  the computed DCF value is more than 50% away from the price: a reading to review, not an arithmetic error
  RR_TOO_LOW               4  a recommended strategy's reward/risk to T1 is below 1 : 1.5, or its T1 is the current price
  DERIVATION               1  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)

------------------------------------------------------------

All scanned reports
Total scanned : 2825
Bad reports   : 1001  (35.4%)

Issue breakdown:
  RR_TOO_LOW             450  a recommended strategy's reward/risk to T1 is below 1 : 1.5, or its T1 is the current price
  ARITHMETIC             206  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DERIVATION             186  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  DUPLICATE              113  same ticker+type+date with a -2 / -3 suffix
  DCF_GAP                 84  the computed DCF value is more than 50% away from the price: a reading to review, not an arithmetic error
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
  amd            49 / 91   bad
  tsla           48 / 90   bad
  ktos           42 / 91   bad
  pltr           41 / 91   bad
  amzn           40 / 91   bad
  pl             38 / 91   bad
  2330.tw        37 / 91   bad
  grab           37 / 91   bad
  sofi           36 / 91   bad
  vst            36 / 92   bad

CSV written → qa/bad_reports_2026-11-23.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-11-23.csv](llm_review_2026-11-23.csv) |
| Full summary | [llm_review_2026-11-23.txt](llm_review_2026-11-23.txt) |

```

============================================================
Reports reviewed : 156
Mean score       : 4.08 / 5

Verdict breakdown (156 grounded):
  pass              92
  warn              50
  fail              11
  PARSE_ERROR        3

Mean score by dimension:
  data_integrity   4.20
  completeness     4.50
  depth            4.14
  consistency      4.46
  language         4.87

Failed review (11):
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-11-22_openai.md
      → 報告引用嚴重脫離現實的財務數據，如記憶體製造商 TTM 營業利益率達「74.6%」、毛利率達「80.7%」。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-11-23_openai.md
      → 報告出現記憶體製造商營業利益率高達「74.6%」（第 3.3 節）甚至最新季達「80.7%」（第 11.5 節），毛利率達「80.7%」，數據明顯荒謬且嚴重偏離產業真實常態。
  goog         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/goog/market_news_2026-11-22_gemini.md
      → 報告中提到的股價 264.0 美元與其他數據（如本益比 15 倍）未能提供一致的背景資料，可能存在數據誠信問題。
  nu           market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/nu/market_news_2026-11-22_gemini.md
      → 報告日期標題為 2026-11-22，但內容中提到的報告日期為 2026-11-21，存在矛盾。
  nvda         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/nvda/market_news_2026-11-23_gemini.md
      → 報告中提到輝達市值蒸發達 2.7 兆美元，但未提供具體的數據來源或背景。
  orcl         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/orcl/market_news_2026-11-23_gemini.md
      → 報告中提到的最新收盤價101.19美元與報告日期不符，可能存在數據誠信問題。
  pltr         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/pltr/market_news_2026-11-22_gemini.md
      → 報告中提到PLTR股價最新收盤價為143.49 USD，但未提供該數據的來源，可能存在數據誠信問題。
  qqq          market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/qqq/market_news_2026-11-23_gemini.md
      → 報告中提到的最新交易價格為608.45美元，但未提供來源，可能存在數據誠信問題。
  skhy         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/skhy/market_news_2026-11-23_gemini.md
      → 報告中提到 SK hynix 的 HBM 業務毛利率為 80%，這一數字的合理性需進一步驗證。
  soxx         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/soxx/market_news_2026-11-22_gemini.md
      → 報告中提到 SOXL 單日暴跌 32%，但未提供具體數據來源，可能存在數據誠信問題。
  vst          market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/vst/market_news_2026-11-22_gemini.md
      → 報告中提到的股價從 128.38 美元滑落至 115.25 美元，但未提供具體的數據來源，可能存在數據誠信問題。

CSV written → qa/llm_review_2026-11-23.csv (64 row(s))
```
