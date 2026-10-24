# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-10-24 |
| Bad reports, last 2 days | 30  (34.9%) |
| Bad reports, all scanned | 399 |
| CSV | [bad_reports_2026-10-24.csv](bad_reports_2026-10-24.csv) |
| Full summary | [summary_2026-10-24.txt](summary_2026-10-24.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-10-23, 2026-10-24)
Total scanned : 86
Bad reports   : 30  (34.9%)

Issue breakdown:
  ARITHMETIC              23  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DUPLICATE                3  same ticker+type+date with a -2 / -3 suffix
  STALE_PRICE              2  a newer completed session existed before the report date
  NAN_VALUE                2  a $nan / nan% leaked from an empty data bar
  PLACEHOLDER              1  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  RR_MISMATCH              1  a stated R/R matches neither target from its own entry/stop

------------------------------------------------------------

All scanned reports
Total scanned : 947
Bad reports   : 399  (42.1%)

Issue breakdown:
  ARITHMETIC             343  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DUPLICATE               34  same ticker+type+date with a -2 / -3 suffix
  RR_MISMATCH             28  a stated R/R matches neither target from its own entry/stop
  MISSING_SECTIONS         4  fundamental report lacks one of chapters ## 1. … ## 11.
  PLACEHOLDER              3  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  NAN_VALUE                3  a $nan / nan% leaked from an empty data bar
  TOO_SHORT                2  fewer content lines than a real report has
  STALE_PRICE              2  a newer completed session existed before the report date
  REFUSAL                  1  the model refused instead of writing the report
  CUTOFF                   1  ends mid-sentence or mid-code-block (truncated)

Top 10 tickers by bad-report count:
  pl             18 / 31   bad
  grab           17 / 31   bad
  avav           16 / 31   bad
  avgo           16 / 32   bad
  ktos           16 / 31   bad
  onds           15 / 31   bad
  vst            15 / 32   bad
  amd            14 / 31   bad
  rklb           14 / 31   bad
  meta           13 / 31   bad

CSV written → qa/bad_reports_2026-10-24.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-10-24.csv](llm_review_2026-10-24.csv) |
| Full summary | [llm_review_2026-10-24.txt](llm_review_2026-10-24.txt) |

```

============================================================
Reports reviewed : 135
Ungrounded       : 3  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.48 / 5

Verdict breakdown (132 grounded):
  pass               6
  warn              56
  fail              69
  PARSE_ERROR        1

Mean score by dimension:
  data_integrity   2.41
  completeness     3.34
  depth            2.61
  consistency      2.81
  language         3.99

Failed review (69):
  0050         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/0050/fundamental_analysis_2026-10-23_gemini.md
      → 報告中提到的加權合理價值 $108.52 與 DCF 基準每股內在價值 $107.85 之間的差異未解釋清楚。
  2330.tw      fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/2330.tw/fundamental_analysis_2026-10-23_gemini.md
      → 報告中提到的加權合理價值 $3,228.34 與複算結果 $3,186.60 存在差異，顯示數據不一致。
  amzn         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amzn/fundamental_analysis_2026-10-23_gemini.md
      → 報告中提到的加權合理價值 $306.77 與 DCF 基準每股內在價值 $299.00 之間的差異未有合理解釋。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-10-23_openai.md
      → 估值核心數字嚴重自相矛盾：8.5 節計算得出每股內在價值為 $136.23（現價溢價 +136%），但 1.0、1.5 與 8.8 節卻宣稱基準內在價值為 $368.55 且 MOS 為 +16.0%。
  goog         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/goog/fundamental_analysis_2026-10-23_gemini.md
      → 報告中加權合理價值 $387.65 與程式複算結果 $383.03 不一致。
  grab         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/grab/fundamental_analysis_2026-10-23_gemini.md
      → 報告中提到的加權合理價值 $3.71 與程式複算的 $3.87 不一致。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-10-23_gemini.md
      → 報告中提到的加權合理價值 $53.30 與複算結果 $54.84 不一致。
  ktos         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-10-23_gemini.md
      → 報告中提到的加權合理價值 $48.24 與程式複算的 $50.22 存在矛盾。
  meta         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/meta/fundamental_analysis_2026-10-23_gemini.md
      → 報告中提到的加權合理價值 $743.08 與複算結果 $751.44 不一致。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-10-23_gemini.md
      → 報告中提到的加權合理價值 $1,053.80 與程式複算的 $1,068.84 存在不一致。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-10-23_gemini.md
      → 報告中提到的加權合理價值 $157.65 與程式複算的 $162.82 相矛盾。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-10-23_gemini.md
      → 報告中提到的加權合理價值 $18.42 與計算結果 $18.19 不一致。
  onds         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/onds/fundamental_analysis_2026-10-23_gemini.md
      → 報告中提到的加權合理價值 $8.72 與重新計算的 $8.79 存在矛盾。
  orcl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/orcl/fundamental_analysis_2026-10-23_gemini.md
      → 報告中提到的加權合理價值 $157.06 與複算結果 $160.15 不一致。
  pl           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pl/fundamental_analysis_2026-10-23_gemini.md
      → 加權合理價值在報告中標示為 $15.54，但計算過程顯示應為 $15.98，存在數據誠信問題。
  pltr         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pltr/fundamental_analysis_2026-10-23_gemini.md
      → 報告中提到的 P/E 倍數 169.6x 與 P/S 82.1x 在相對估值分析中被標示為極端高位，但未提供具體的歷史數據對比。
  qqq          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/qqq/fundamental_analysis_2026-10-23_gemini.md
      → 報告中提到的加權合理價值 $791.73 與 DCF 基準每股內在價值 $793.63 之間存在矛盾。
  rklb         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/rklb/fundamental_analysis_2026-10-23_gemini.md
      → 報告中加權合理價值 stated 為 $35.03，但程式複算結果為 $34.83，存在數據不一致問題。
  skhy         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/skhy/fundamental_analysis_2026-10-23_gemini-2.md
      → 報告中提到的單季營業利潤率高達 76.3%，但未提供合理的基期數據支持此數字的可行性。
  skhy         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/skhy/fundamental_analysis_2026-10-23_gemini.md
      → 報告中提到的 TTM 營收 189.17T KRW 與最新季度年增 256.8% 的數據不合理，因為這意味著去年同期營收為 53.00T KRW，這是該公司從未達到過的規模。

Ungrounded verdicts (3) — reviewer noise, not report defects:
  avav         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/avav/technical_analysis_2026-10-24_gemini.md
  nbis         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/nbis/technical_analysis_2026-10-23_gemini.md
  pl           fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/pl/technical_analysis_2026-10-23_gemini.md

CSV written → qa/llm_review_2026-10-24.csv (129 row(s))
```
