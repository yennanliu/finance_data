# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-11-04 |
| Bad reports, last 2 days | 27  (24.3%) |
| Bad reports, all scanned | 286 |
| CSV | [bad_reports_2026-11-04.csv](bad_reports_2026-11-04.csv) |
| Full summary | [summary_2026-11-04.txt](summary_2026-11-04.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-11-03, 2026-11-04)
Total scanned : 111
Bad reports   : 27  (24.3%)

Issue breakdown:
  DERIVATION              15  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  ARITHMETIC              10  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DUPLICATE               10  same ticker+type+date with a -2 / -3 suffix
  STALE_PRICE              1  a newer completed session existed before the report date

------------------------------------------------------------

All scanned reports
Total scanned : 1629
Bad reports   : 286  (17.6%)

Issue breakdown:
  ARITHMETIC             114  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DERIVATION             112  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  DUPLICATE               52  same ticker+type+date with a -2 / -3 suffix
  RR_MISMATCH             29  a stated R/R matches neither target from its own entry/stop
  MISSING_SECTIONS         7  fundamental report lacks one of chapters ## 1. … ## 11.
  PLACEHOLDER              6  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  STALE_PRICE              3  a newer completed session existed before the report date
  NAN_VALUE                3  a $nan / nan% leaked from an empty data bar
  TOO_SHORT                2  fewer content lines than a real report has
  REFUSAL                  1  the model refused instead of writing the report
  CUTOFF                   1  ends mid-sentence or mid-code-block (truncated)
  LEVEL_MISMATCH           1  a Ch.4 R1–S3 is not the computed level of the same label

Top 10 tickers by bad-report count:
  pl             17 / 53   bad
  tsla           14 / 53   bad
  amd            13 / 53   bad
  intc           13 / 54   bad
  ktos           13 / 53   bad
  avav           12 / 53   bad
  nbis           12 / 54   bad
  0050           11 / 53   bad
  rklb           11 / 53   bad
  onds           10 / 53   bad

CSV written → qa/bad_reports_2026-11-04.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-11-04.csv](llm_review_2026-11-04.csv) |
| Full summary | [llm_review_2026-11-04.txt](llm_review_2026-11-04.txt) |

```

============================================================
Reports reviewed : 175
Ungrounded       : 2  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.54 / 5

Verdict breakdown (173 grounded):
  pass              10
  warn              83
  fail              80

Mean score by dimension:
  data_integrity   2.49
  completeness     3.38
  depth            2.60
  consistency      2.88
  language         3.99

Failed review (80):
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的加權合理價值 $486.29 與後續計算的 $463.59 相矛盾。
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-11-04_gemini.md
      → 報告中提到的加權合理價值 $481.56 與計算結果 $485.64 不一致。
  amzn         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amzn/fundamental_analysis_2026-11-03_gemini-2.md
      → 報告中提到的加權合理價值 $287.65 與後文計算出的 $290.18 不一致。
  avav         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-11-03_gemini-2.md
      → 報告中提到的加權合理價值 $116.65 與後續計算的 $132.91 相矛盾。
  avav         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的加權合理價值 $164.11 與後文計算的 $166.37 不一致。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的加權合理價值 $380.00 與後續計算的 $383.21 不一致。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-11-04_gemini.md
      → 報告中提到的加權合理價值 $388.94 與後續計算的 $398.00 不一致。
  goog         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/goog/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的加權合理價值 $347.55 與計算結果 $353.47 不一致。
  grab         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/grab/fundamental_analysis_2026-11-03_gemini-2.md
      → 報告中提到的 TTM 營收 $3.73B 與最新單季營收年增 21.9% 的數據不一致，可能導致數據誠信問題。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的加權合理價值 $59.50 與現價 $59.97 的安全邊際 MOS 為 -0.8%，但在 DCF 模型中計算的 MOS 為 -1.3%，存在數據不一致。
  ktos         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的加權合理價值 $35.40 與程式複算的 $36.88 不一致。
  mrvl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mrvl/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的加權合理價值 $168.32 與後續計算的 $177.53 相矛盾。
  msft         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/msft/fundamental_analysis_2026-11-03_gemini-2.md
      → 報告中提到的加權合理價值 $591.24 與後續計算的 $594.83 不一致。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的加權合理價值 $1,059.39 與後續計算的 $1,141.52 相矛盾。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-11-04_gemini.md
      → 報告中提到的加權合理價值 $1,059.88 與程式複算的 $1,068.71 存在矛盾。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的 TTM 營收 $1.36B 與最新單季營收年增 454.0% 的數據不一致，顯示數據誠信問題。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-11-04_gemini.md
      → 報告中提到的加權合理價值 $181.33 與計算結果 $192.54 不一致。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-11-04_gemini.md
      → 報告中提到的加權合理價值 $16.80 與 DCF 基準每股內在價值 $16.62 之間存在矛盾。
  nvda         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nvda/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的TTM營收$302.97B與最新單季YoY +105.9%之數據不一致，因為這意味著前一季的營收應為$147.73B，這並不符合歷史數據。
  onds         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/onds/fundamental_analysis_2026-11-03_gemini-2.md
      → 報告中提到的加權合理價值 $7.13 與複算結果 $8.26 不一致。

Ungrounded verdicts (2) — reviewer noise, not report defects:
  avgo         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/avgo/technical_analysis_2026-11-04_gemini.md
  nu           fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/nu/technical_analysis_2026-11-04_gemini.md

CSV written → qa/llm_review_2026-11-04.csv (165 row(s))
```
