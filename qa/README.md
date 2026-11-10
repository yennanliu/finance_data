# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-11-10 |
| Bad reports, last 2 days | 12  (13.5%) |
| Bad reports, all scanned | 361 |
| CSV | [bad_reports_2026-11-10.csv](bad_reports_2026-11-10.csv) |
| Full summary | [summary_2026-11-10.txt](summary_2026-11-10.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-11-09, 2026-11-10)
Total scanned : 89
Bad reports   : 12  (13.5%)

Issue breakdown:
  DERIVATION               8  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  ARITHMETIC               4  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures

------------------------------------------------------------

All scanned reports
Total scanned : 2002
Bad reports   : 361  (18.0%)

Issue breakdown:
  DERIVATION             160  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  ARITHMETIC             137  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DUPLICATE               64  same ticker+type+date with a -2 / -3 suffix
  RR_MISMATCH             29  a stated R/R matches neither target from its own entry/stop
  MISSING_SECTIONS         7  fundamental report lacks one of chapters ## 1. … ## 11.
  PLACEHOLDER              6  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  STALE_PRICE              5  a newer completed session existed before the report date
  NAN_VALUE                3  a $nan / nan% leaked from an empty data bar
  TOO_SHORT                2  fewer content lines than a real report has
  REFUSAL                  1  the model refused instead of writing the report
  CUTOFF                   1  ends mid-sentence or mid-code-block (truncated)
  LEVEL_MISMATCH           1  a Ch.4 R1–S3 is not the computed level of the same label

Top 10 tickers by bad-report count:
  pl             19 / 65   bad
  intc           17 / 65   bad
  tsla           17 / 64   bad
  amd            16 / 65   bad
  ktos           16 / 65   bad
  rklb           16 / 65   bad
  avav           14 / 65   bad
  nbis           14 / 66   bad
  0050           13 / 65   bad
  avgo           13 / 66   bad

CSV written → qa/bad_reports_2026-11-10.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-11-10.csv](llm_review_2026-11-10.csv) |
| Full summary | [llm_review_2026-11-10.txt](llm_review_2026-11-10.txt) |

```

============================================================
Reports reviewed : 145
Ungrounded       : 7  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.46 / 5

Verdict breakdown (138 grounded):
  pass               6
  warn              62
  fail              70

Mean score by dimension:
  data_integrity   2.36
  completeness     3.33
  depth            2.52
  consistency      2.82
  language         3.95

Failed review (70):
  0050         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/0050/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的加權合理價值111.00 TWD與現價97.45 TWD的安全邊際12.2%計算不一致，應為13.9%。
  2330.tw      fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/2330.tw/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的TTM營收達4.94兆TWD，但在不同章節中對於營收年增率的描述存在矛盾。
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的加權合理價值 $388.94 與後續計算的 $399.14 不一致。
  amzn         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amzn/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的 TTM 營收 $797.46B 與年增 15.4% 的數據未能在其他章節中得到一致支持。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-11-09_gemini.md
      → 報告中提到的加權合理價值 $394.19 與計算結果 $398.32 不一致。
  goog         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/goog/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的加權合理價值 $347.53 與後文計算的 $351.40 不一致。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的加權合理價值 $57.21 與後續計算的 $59.06 相矛盾。
  meta         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/meta/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的加權合理價值 $786.10 與 DCF 內在價值 $792.42 之間存在矛盾。
  mrvl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mrvl/fundamental_analysis_2026-11-09_gemini.md
      → 報告中提到的 ROIC 為 6.3%，但在其他地方提到的 WACC 為 16.01%，顯示出經濟價值增加為負值，這可能不合理。
  msft         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/msft/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的 TTM 營收 $346.44B 與最新單季營收年增率 18.8% 之間的數據不一致。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-11-09_gemini.md
      → 報告中提到的加權合理價值 $151.78 與複算結果 $156.10 存在矛盾。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的加權合理價值 $163.66 與計算結果 $169.36 不一致。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的最新單季營收年增率52.1%與TTM營收13.17B美元的數據未能在其他章節中得到一致性驗證。
  nvda         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nvda/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的TTM營收$302.97B與最新季營收年增率105.9%所隱含的基期不合理，因為這意味著去年營收必須低於$147.5B，這對於NVIDIA來說是不可能的。
  onds         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/onds/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的TTM營收年增率979.3%與最新季營收年增率1235.4%存在矛盾。
  orcl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/orcl/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的加權合理價值 $152.02 與後續計算的 $155.56 不一致。
  pl           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pl/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的加權合理價值 $14.99 與後續計算的 $16.33 相矛盾。
  pltr         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pltr/fundamental_analysis_2026-11-10_gemini.md
      → 報告中出現的數據如「TTM 營收 $7.29B（YoY +87.1%）」與「TTM 自由現金流（FCF）達到 $4.05B」缺乏合理性，且未提供來源。
  qqq          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/qqq/fundamental_analysis_2026-11-09_gemini.md
      → 報告中出現的數據如加權合理價值 $745.02 與 DCF 每股內在價值 $755.70 之間存在矛盾。
  rklb         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/rklb/fundamental_analysis_2026-11-10_gemini.md
      → 報告中提到的加權合理價值 $38.15 與後續計算的 $42.79 相矛盾。

Ungrounded verdicts (7) — reviewer noise, not report defects:
  meta         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/meta/technical_analysis_2026-11-10_gemini.md
  nbis         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/nbis/technical_analysis_2026-11-09_gemini.md
  nvda         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/nvda/technical_analysis_2026-11-09_gemini.md
  onds         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/onds/technical_analysis_2026-11-10_gemini.md
  tsla         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/tsla/technical_analysis_2026-11-09_gemini.md
  tsm          fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/tsm/technical_analysis_2026-11-10_gemini.md
  vst          fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/vst/technical_analysis_2026-11-09_gemini.md

CSV written → qa/llm_review_2026-11-10.csv (139 row(s))
```
