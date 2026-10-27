# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-10-27 |
| Bad reports, last 2 days | 12  (14.6%) |
| Bad reports, all scanned | 424 |
| CSV | [bad_reports_2026-10-27.csv](bad_reports_2026-10-27.csv) |
| Full summary | [summary_2026-10-27.txt](summary_2026-10-27.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-10-26, 2026-10-27)
Total scanned : 82
Bad reports   : 12  (14.6%)

Issue breakdown:
  ARITHMETIC              10  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  PLACEHOLDER              1  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  MISSING_SECTIONS         1  fundamental report lacks one of chapters ## 1. … ## 11.
  RR_MISMATCH              1  a stated R/R matches neither target from its own entry/stop

------------------------------------------------------------

All scanned reports
Total scanned : 1129
Bad reports   : 424  (37.6%)

Issue breakdown:
  ARITHMETIC             364  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DUPLICATE               36  same ticker+type+date with a -2 / -3 suffix
  RR_MISMATCH             29  a stated R/R matches neither target from its own entry/stop
  PLACEHOLDER              5  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  MISSING_SECTIONS         5  fundamental report lacks one of chapters ## 1. … ## 11.
  NAN_VALUE                3  a $nan / nan% leaked from an empty data bar
  TOO_SHORT                2  fewer content lines than a real report has
  STALE_PRICE              2  a newer completed session existed before the report date
  REFUSAL                  1  the model refused instead of writing the report
  CUTOFF                   1  ends mid-sentence or mid-code-block (truncated)

Top 10 tickers by bad-report count:
  pl             21 / 37   bad
  grab           18 / 37   bad
  ktos           18 / 37   bad
  avav           17 / 37   bad
  avgo           16 / 38   bad
  onds           16 / 37   bad
  rklb           16 / 37   bad
  mrvl           15 / 18   bad
  vst            15 / 38   bad
  amd            14 / 37   bad

CSV written → qa/bad_reports_2026-10-27.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-10-27.csv](llm_review_2026-10-27.csv) |
| Full summary | [llm_review_2026-10-27.txt](llm_review_2026-10-27.txt) |

```

============================================================
Reports reviewed : 127
Mean score       : 2.56 / 5

Verdict breakdown (127 grounded):
  pass               7
  warn              64
  fail              55
  PARSE_ERROR        1

Mean score by dimension:
  data_integrity   2.56
  completeness     3.37
  depth            2.63
  consistency      2.96
  language         4.02

Failed review (55):
  0050         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/0050/fundamental_analysis_2026-10-26_gemini.md
      → 報告中提到的「穿透 ROIC 達 21.8%」與「WACC 8.8%」的數據未能在其他章節中得到一致支持。
  2330.tw      fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/2330.tw/fundamental_analysis_2026-10-26_gemini.md
      → 報告中提到的TTM營收4.94T TWD與最新單季營收年增50.9%之數據未能自圓其說，缺乏合理的基期數據支持。
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-10-26_gemini.md
      → 報告中提到的加權合理價值 $357.65 與後文計算的 $346.45 不一致。
  avav         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-10-26_gemini.md
      → 報告中提到的 TTM 營收 $2.00B 與單季年增放緩至 5.7% 的數據存在矛盾，因為這樣的增長率不應該出現在如此高的基數上。
  grab         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/grab/fundamental_analysis_2026-10-26_gemini.md
      → 報告中提到的加權合理價值 $3.70 與程式複算的 $3.86 不一致。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-10-26_gemini.md
      → 報告中提到的加權合理價值 $57.94 與後文計算的 $59.56 不一致。
  ktos         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-10-26_gemini.md
      → 報告中提到的 TTM 營業利益率僅 1.2%，但在執行摘要中卻提到最新季度營業利益率為 -0.3%，數據不一致。
  meta         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/meta/fundamental_analysis_2026-10-26_gemini.md
      → 報告中提到的加權合理價值 $775.12 與後續計算的 $762.62 不一致。
  mrvl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mrvl/fundamental_analysis_2026-10-26_gemini.md
      → 報告中提到的加權合理價值 $151.72 與複算結果 $147.88 不一致。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-10-27_gemini.md
      → 報告中提到的TTM營收$1.36B與最新單季營收$582.30M的年增率454.0%不合理，因為這意味著去年營收極低，且未提供去年基期數據。
  onds         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/onds/fundamental_analysis_2026-10-26_gemini.md
      → 報告中提到的 TTM 營業利益率為 -140.4%，這一數字顯然不合理。
  orcl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/orcl/fundamental_analysis_2026-10-26_gemini.md
      → 報告中提到的加權合理價值 $157.06 與更正後的 $169.45 之間存在矛盾。
  pl           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pl/fundamental_analysis_2026-10-26_gemini.md
      → 報告中提到的加權合理價值 $16.65 與複算結果 $17.70 不一致。
  pltr         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pltr/fundamental_analysis_2026-10-26_gemini.md
      → 報告中提到的加權合理價值 $111.83 與其他數據不一致，MOS 為 -76.6% 與報告中其他數據矛盾。
  qqq          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/qqq/fundamental_analysis_2026-10-26_gemini.md
      → 報告中提到的加權合理價值 $793.63 與 DCF 內在價值 $794.13 之間的差異未解釋清楚，可能造成數據誤解。
  rklb         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/rklb/fundamental_analysis_2026-10-26_gemini.md
      → 報告中提到的加權合理價值 $30.01 與複算結果 $32.19 存在矛盾。
  robo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/robo/fundamental_analysis_2026-10-26_gemini.md
      → 報告中提到的底層成分股加權營收 YoY 為 11.8%，但在其他章節中未能提供一致的數據支持。
  skhy         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/skhy/fundamental_analysis_2026-10-26_gemini.md
      → 報告中提到的單季營業利益率達 76.3%，但在其他地方提到的營業利益率卻顯示為 68.0%。
  sndk         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/sndk/fundamental_analysis_2026-10-26_gemini.md
      → 報告中提到的 TTM 營收 $20.25B 與 YoY +175.3% 的數字不合理，因為這意味著去年營收為 $7.36B，但該數字未在報告中出現。
  soxq         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/soxq/fundamental_analysis_2026-10-26_gemini.md
      → 報告中提到的加權合理價值 $98.00 與複算結果 $96.53 存在矛盾。

CSV written → qa/llm_review_2026-10-27.csv (120 row(s))
```
