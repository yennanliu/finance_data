# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-10-28 |
| Bad reports, last 2 days | 10  (11.2%) |
| Bad reports, all scanned | 432 |
| CSV | [bad_reports_2026-10-28.csv](bad_reports_2026-10-28.csv) |
| Full summary | [summary_2026-10-28.txt](summary_2026-10-28.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-10-27, 2026-10-28)
Total scanned : 89
Bad reports   : 10  (11.2%)

Issue breakdown:
  ARITHMETIC               8  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  PLACEHOLDER              1  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  MISSING_SECTIONS         1  fundamental report lacks one of chapters ## 1. … ## 11.
  DUPLICATE                1  same ticker+type+date with a -2 / -3 suffix
  RR_MISMATCH              1  a stated R/R matches neither target from its own entry/stop

------------------------------------------------------------

All scanned reports
Total scanned : 1190
Bad reports   : 432  (36.3%)

Issue breakdown:
  ARITHMETIC             371  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DUPLICATE               37  same ticker+type+date with a -2 / -3 suffix
  RR_MISMATCH             29  a stated R/R matches neither target from its own entry/stop
  PLACEHOLDER              6  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  MISSING_SECTIONS         6  fundamental report lacks one of chapters ## 1. … ## 11.
  NAN_VALUE                3  a $nan / nan% leaked from an empty data bar
  TOO_SHORT                2  fewer content lines than a real report has
  STALE_PRICE              2  a newer completed session existed before the report date
  REFUSAL                  1  the model refused instead of writing the report
  CUTOFF                   1  ends mid-sentence or mid-code-block (truncated)

Top 10 tickers by bad-report count:
  pl             22 / 39   bad
  ktos           19 / 39   bad
  grab           18 / 39   bad
  avav           17 / 39   bad
  onds           17 / 39   bad
  rklb           17 / 39   bad
  avgo           16 / 40   bad
  mrvl           15 / 19   bad
  vst            15 / 40   bad
  amd            14 / 39   bad

CSV written → qa/bad_reports_2026-10-28.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-10-28.csv](llm_review_2026-10-28.csv) |
| Full summary | [llm_review_2026-10-28.txt](llm_review_2026-10-28.txt) |

```

============================================================
Reports reviewed : 142
Ungrounded       : 2  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.56 / 5

Verdict breakdown (140 grounded):
  pass               5
  warn              76
  fail              59

Mean score by dimension:
  data_integrity   2.52
  completeness     3.44
  depth            2.61
  consistency      2.96
  language         4.07

Failed review (59):
  2330.tw      fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/2330.tw/fundamental_analysis_2026-10-27_gemini.md
      → 報告中提到的營業利益率達 58.7% 與後文提到的 58.0% 存在矛盾。
  amzn         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amzn/fundamental_analysis_2026-10-27_openai.md
      → 報告於第 8.8 節「分析師共」處直接中斷截斷，完全缺失第 9、10、11 章核心結論與投資建議。
  avav         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-10-27_gemini.md
      → 報告中提到的 TTM 營業利益率為 -12.6%，但在其他章節中卻未能一致反映此數據。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-10-28_gemini.md
      → 報告中提到的TTM營收年增率85.5%與TTM營收年增48.7%存在矛盾。
  goog         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/goog/fundamental_analysis_2026-10-27_gemini.md
      → 報告中提到的加權合理價值 $379.24 與 DCF 基準每股內在價值 $375.00 的計算過程不一致，導致數據誠信問題。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-10-27_gemini.md
      → 報告中提到的加權合理價值 $53.30 與後文計算的 $56.97 不一致。
  ktos         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-10-27_gemini.md
      → 報告中提到的加權合理價值 $44.78 與複算結果 $41.97 不一致。
  meta         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/meta/fundamental_analysis_2026-10-27_gemini.md
      → 報告中提到的 TTM FCF Yield 為 1.81%，但在其他部分提到的 FCF 轉換率為 38.1%，這兩者之間存在矛盾。
  mrvl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mrvl/fundamental_analysis_2026-10-27_gemini.md
      → 報告中提到的加權合理價值 $163.78 與後文計算的 $171.34 相矛盾。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-10-27_gemini.md
      → 報告中提到的 TTM 營收 $1.36B 與最新單季營收 $582.30M 的年增率 454.0% 似乎不合理，因為這樣的增長率暗示去年基期極低，且未提供足夠背景資料。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-10-28_gemini.md
      → 報告中提到的加權合理價值 $203.10 與後文計算的 $207.09 不一致。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-10-27_gemini.md
      → 報告中提到的加權合理價值 $15.54 與更正後的 $16.00 之間存在矛盾。
  nvda         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nvda/fundamental_analysis_2026-10-27_gemini.md
      → 報告中提到的加權合理價值 $257.77 與後續計算的 $260.99 不一致。
  onds         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/onds/fundamental_analysis_2026-10-27_gemini.md
      → 報告中提到的加權合理價值 $7.67 與程式複算的 $8.48 不一致。
  orcl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/orcl/fundamental_analysis_2026-10-27_gemini.md
      → 報告中提到的加權合理價值 $157.08 與更正後的 $160.87 之間存在矛盾。
  pl           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pl/fundamental_analysis_2026-10-27_gemini.md
      → 報告中提到的加權合理價值 $15.82 與程式複算的 $16.31 存在矛盾。
  pltr         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pltr/fundamental_analysis_2026-10-27_gemini.md
      → 報告中提到的加權合理價值 $157.17 與後文計算的 $151.45 不一致。
  rklb         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/rklb/fundamental_analysis_2026-10-27_gemini.md
      → 報告中提到的加權合理價值 $35.48 與後續計算的 $41.51 不一致。
  robo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/robo/fundamental_analysis_2026-10-27_gemini.md
      → 報告中提到的加權合理價值 $86.87 與 DCF 基準內在價值 $87.20 之間存在矛盾。
  skhy         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/skhy/fundamental_analysis_2026-10-27_gemini.md
      → 報告中提到的加權合理價值 $222.18 與複算結果 $226.50 存在矛盾。

Ungrounded verdicts (2) — reviewer noise, not report defects:
  nbis         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/nbis/technical_analysis_2026-10-27_gemini.md
  nu           fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/nu/technical_analysis_2026-10-27_gemini.md

CSV written → qa/llm_review_2026-10-28.csv (137 row(s))
```
