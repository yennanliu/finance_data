# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-10-31 |
| Bad reports, last 2 days | 14  (15.1%) |
| Bad reports, all scanned | 226 |
| CSV | [bad_reports_2026-10-31.csv](bad_reports_2026-10-31.csv) |
| Full summary | [summary_2026-10-31.txt](summary_2026-10-31.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-10-30, 2026-10-31)
Total scanned : 93
Bad reports   : 14  (15.1%)

Issue breakdown:
  ARITHMETIC              10  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DERIVATION               7  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  DUPLICATE                1  same ticker+type+date with a -2 / -3 suffix

------------------------------------------------------------

All scanned reports
Total scanned : 1376
Bad reports   : 226  (16.4%)

Issue breakdown:
  ARITHMETIC              94  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DERIVATION              76  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  DUPLICATE               39  same ticker+type+date with a -2 / -3 suffix
  RR_MISMATCH             29  a stated R/R matches neither target from its own entry/stop
  PLACEHOLDER              6  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  MISSING_SECTIONS         6  fundamental report lacks one of chapters ## 1. … ## 11.
  NAN_VALUE                3  a $nan / nan% leaked from an empty data bar
  TOO_SHORT                2  fewer content lines than a real report has
  STALE_PRICE              2  a newer completed session existed before the report date
  REFUSAL                  1  the model refused instead of writing the report
  CUTOFF                   1  ends mid-sentence or mid-code-block (truncated)
  LEVEL_MISMATCH           1  a Ch.4 R1–S3 is not the computed level of the same label

Top 10 tickers by bad-report count:
  pl             15 / 45   bad
  intc           12 / 46   bad
  tsla           12 / 45   bad
  ktos           11 / 45   bad
  avav           10 / 45   bad
  0050            9 / 45   bad
  amd             9 / 45   bad
  rklb            9 / 45   bad
  spcx            9 / 46   bad
  mrvl            8 / 22   bad

CSV written → qa/bad_reports_2026-10-31.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-10-31.csv](llm_review_2026-10-31.csv) |
| Full summary | [llm_review_2026-10-31.txt](llm_review_2026-10-31.txt) |

```

============================================================
Reports reviewed : 148
Ungrounded       : 2  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.49 / 5

Verdict breakdown (146 grounded):
  pass               3
  warn              74
  fail              69

Mean score by dimension:
  data_integrity   2.49
  completeness     3.38
  depth            2.58
  consistency      2.90
  language         4.01

Failed review (69):
  0050         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/0050/fundamental_analysis_2026-10-30_gemini.md
      → 報告中提到的 '穿透每股內在價值為 116.80 TWD' 與 '現價折價 10.15%' 的計算不一致。
  2330.tw      fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/2330.tw/fundamental_analysis_2026-10-30_gemini.md
      → 報告中提到的營業利益率58.0%與58.7%存在矛盾。
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-10-30_gemini.md
      → 報告中提到的加權合理價值 $431.69 與 DCF 基準每股內在價值 $412.39 之間存在矛盾。
  amzn         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amzn/fundamental_analysis_2026-10-30_gemini.md
      → 報告中提到的 TTM 營收 $797.46B 與其他數據不一致，導致數據誠信問題。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-10-31_gemini.md
      → 報告中提到的加權合理價值 $388.94 與後文計算的 $392.93 不一致。
  grab         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/grab/fundamental_analysis_2026-10-30_gemini.md
      → 報告中提到的加權合理價值 $3.76 與重新計算的 $3.82 不一致。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-10-30_gemini-2.md
      → 報告中提到的加權合理價值 $60.28 與計算過程中的 $61.81 不一致。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-10-30_gemini.md
      → 報告中提到的加權合理價值 $59.13 與後文計算的 $58.61 不一致。
  ktos         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-10-30_gemini.md
      → 報告中提到的加權合理價值 $34.42 與後文計算的 $32.67 不一致。
  mrvl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mrvl/fundamental_analysis_2026-10-30_gemini.md
      → 報告中提到的 TTM ROIC 僅為 6.3%，低於 WACC 15.98%，顯示資本效率偏低，這與報告的買入評級相矛盾。
  msft         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/msft/fundamental_analysis_2026-10-30_gemini.md
      → 報告中提到的加權合理價值 $593.63 與後文計算的 $596.76 不一致。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-10-30_gemini.md
      → 報告中提到的營業利益率高達80.7%不符合行業常規，缺乏合理性。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-10-30_gemini.md
      → 報告中提到的加權合理價值 $182.16 與複算結果 $184.38 不一致。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-10-30_gemini.md
      → 報告中提到的加權合理價值 $15.01 與後文計算的 $15.45 不一致。
  nvda         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nvda/fundamental_analysis_2026-10-30_gemini.md
      → 報告中提到的 TTM 營收 $302.97B 與最新單季營業利益率 66.2% 的數據不一致，且無法查證其來源。
  onds         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/onds/fundamental_analysis_2026-10-30_gemini.md
      → 報告中提到的加權合理價值 $6.48 與程式複算的 $7.68 存在矛盾。
  orcl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/orcl/fundamental_analysis_2026-10-30_gemini.md
      → 報告中提到的加權合理價值 $168.00 與程式複算的 $172.49 相矛盾。
  pl           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pl/fundamental_analysis_2026-10-30_gemini.md
      → 報告中提到的加權合理價值 $14.12 與複算結果 $15.35 相矛盾。
  pltr         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pltr/fundamental_analysis_2026-10-30_gemini.md
      → 報告中提到的加權合理價值 $132.22 與後文計算的 $129.14 不一致。
  qqq          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/qqq/fundamental_analysis_2026-10-30_gemini.md
      → 報告中提到的加權合理價值 $712.35 與 DCF 內在價值 $718.52 之間存在矛盾。

Ungrounded verdicts (2) — reviewer noise, not report defects:
  nbis         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/nbis/technical_analysis_2026-10-30_gemini.md
  nu           fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/nu/technical_analysis_2026-10-31_gemini.md

CSV written → qa/llm_review_2026-10-31.csv (145 row(s))
```
