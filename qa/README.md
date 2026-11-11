# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-11-11 |
| Bad reports, last 2 days | 27  (23.9%) |
| Bad reports, all scanned | 381 |
| CSV | [bad_reports_2026-11-11.csv](bad_reports_2026-11-11.csv) |
| Full summary | [summary_2026-11-11.txt](summary_2026-11-11.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-11-10, 2026-11-11)
Total scanned : 113
Bad reports   : 27  (23.9%)

Issue breakdown:
  DUPLICATE               13  same ticker+type+date with a -2 / -3 suffix
  DERIVATION              12  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  ARITHMETIC               6  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  STALE_PRICE              1  a newer completed session existed before the report date

------------------------------------------------------------

All scanned reports
Total scanned : 2065
Bad reports   : 381  (18.5%)

Issue breakdown:
  DERIVATION             167  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  ARITHMETIC             141  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DUPLICATE               77  same ticker+type+date with a -2 / -3 suffix
  RR_MISMATCH             29  a stated R/R matches neither target from its own entry/stop
  MISSING_SECTIONS         7  fundamental report lacks one of chapters ## 1. … ## 11.
  PLACEHOLDER              6  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  STALE_PRICE              6  a newer completed session existed before the report date
  NAN_VALUE                3  a $nan / nan% leaked from an empty data bar
  TOO_SHORT                2  fewer content lines than a real report has
  REFUSAL                  1  the model refused instead of writing the report
  CUTOFF                   1  ends mid-sentence or mid-code-block (truncated)
  LEVEL_MISMATCH           1  a Ch.4 R1–S3 is not the computed level of the same label

Top 10 tickers by bad-report count:
  pl             20 / 67   bad
  intc           18 / 67   bad
  amd            17 / 67   bad
  rklb           17 / 67   bad
  tsla           17 / 66   bad
  ktos           16 / 67   bad
  0050           15 / 67   bad
  avav           15 / 67   bad
  nbis           14 / 68   bad
  spcx           14 / 68   bad

CSV written → qa/bad_reports_2026-11-11.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-11-11.csv](llm_review_2026-11-11.csv) |
| Full summary | [llm_review_2026-11-11.txt](llm_review_2026-11-11.txt) |

```

============================================================
Reports reviewed : 178
Ungrounded       : 3  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.44 / 5

Verdict breakdown (175 grounded):
  pass               3
  warn              82
  fail              90

Mean score by dimension:
  data_integrity   2.29
  completeness     3.32
  depth            2.50
  consistency      2.79
  language         3.93

Failed review (90):
  0050         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/0050/fundamental_analysis_2026-11-10_gemini-2.md
      → 報告中提到的 'TTM 隱含本益比 26.07x' 與 '估值略高於歷史中位數' 之間存在矛盾。
  0050         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/0050/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的加權合理價值111.00 TWD與現價97.45 TWD的安全邊際12.2%計算不一致，應為13.9%。
  2330.tw      fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/2330.tw/fundamental_analysis_2026-11-10_gemini-2.md
      → 報告中提到的營業利益率從58.0%上升至58.7%，但在不同章節中出現矛盾。
  2330.tw      fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/2330.tw/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的TTM營收達4.94兆TWD，與其他數據不一致。
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的加權合理價值 $388.94 與後續計算的 $399.14 相矛盾。
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-11-11_gemini.md
      → 報告中提到的加權合理價值518.35與後文計算的512.71不一致。
  amzn         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amzn/fundamental_analysis_2026-11-10_gemini-2.md
      → 報告中提到的 TTM 營收 $797.46B 與最新季營業利益率 13.9% 之間的關聯性未明確說明。
  amzn         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amzn/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的 TTM 營收 $797.46B 與年增 15.4% 的數據未能在其他章節中得到一致性驗證。
  avav         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-11-10_gemini-2.md
      → 報告中提到的加權合理價值 $151.72 與後文計算的 $154.45 不一致。
  avav         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的加權合理價值 $157.06 與後續計算的 $163.88 不一致。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的加權合理價值 $388.94 與 DCF 基準每股內在價值 $379.79 之間的差異未有合理解釋。
  goog         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/goog/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的加權合理價值 $347.53 與後文計算的 $351.40 不一致。
  grab         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/grab/fundamental_analysis_2026-11-10_gemini-2.md
      → 報告中提到的加權合理價值 $4.42 與 DCF 基準每股內在價值 $4.48 之間存在矛盾。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的加權合理價值 $57.21 與後續計算的 $59.06 相矛盾。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-11-11_gemini.md
      → 報告中提到的加權合理價值 $57.50 與後續計算的 $56.24 不一致。
  mrvl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mrvl/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的加權合理價值 $185.12 與後文計算的 $189.37 不一致。
  msft         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/msft/fundamental_analysis_2026-11-10_gemini-2.md
      → 報告中提到的加權合理價值 $602.82 與 DCF 基準每股內在價值 $591.95 之間存在矛盾。
  msft         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/msft/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的 TTM ROIC 為 29.7%，但在其他地方提到的 WACC 為 10.06%，這樣的數據組合可能導致不合理的評估。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的加權合理價值 $163.66 與計算結果 $169.36 不一致。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-11-11_gemini.md
      → 報告中提到的 P/S Ratio (TTM) 為 26.9x，與同業相比顯示顯著高溢價，但未提供具體數據來源。

Ungrounded verdicts (3) — reviewer noise, not report defects:
  2330.tw      fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/2330.tw/technical_analysis_2026-11-11_gemini.md
  onds         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/onds/technical_analysis_2026-11-10_gemini.md
  orcl         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/orcl/technical_analysis_2026-11-10_gemini.md

CSV written → qa/llm_review_2026-11-11.csv (175 row(s))
```
