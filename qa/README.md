# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-10-29 |
| Bad reports, last 2 days | 4  (4.5%) |
| Bad reports, all scanned | 436 |
| CSV | [bad_reports_2026-10-29.csv](bad_reports_2026-10-29.csv) |
| Full summary | [summary_2026-10-29.txt](summary_2026-10-29.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-10-28, 2026-10-29)
Total scanned : 88
Bad reports   : 4  (4.5%)

Issue breakdown:
  ARITHMETIC               3  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  LEVEL_MISMATCH           1  a Ch.4 R1–S3 is not the computed level of the same label

------------------------------------------------------------

All scanned reports
Total scanned : 1251
Bad reports   : 436  (34.9%)

Issue breakdown:
  ARITHMETIC             374  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DUPLICATE               37  same ticker+type+date with a -2 / -3 suffix
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
  pl             22 / 41   bad
  ktos           19 / 41   bad
  grab           18 / 41   bad
  avav           17 / 41   bad
  onds           17 / 41   bad
  rklb           17 / 41   bad
  avgo           16 / 42   bad
  mrvl           15 / 20   bad
  vst            15 / 42   bad
  amd            14 / 41   bad

CSV written → qa/bad_reports_2026-10-29.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-10-29.csv](llm_review_2026-10-29.csv) |
| Full summary | [llm_review_2026-10-29.txt](llm_review_2026-10-29.txt) |

```

============================================================
Reports reviewed : 141
Ungrounded       : 1  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.62 / 5

Verdict breakdown (140 grounded):
  pass               7
  warn              79
  fail              53
  PARSE_ERROR        1

Mean score by dimension:
  data_integrity   2.65
  completeness     3.42
  depth            2.69
  consistency      3.08
  language         4.14

Failed review (53):
  0050         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/0050/fundamental_analysis_2026-10-28_gemini.md
      → 報告中提到的加權合理價值 123.50 TWD 與 DCF 內在價值 122.80 TWD 之間的差異未解釋，可能造成數據誠信問題。
  2330.tw      fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/2330.tw/fundamental_analysis_2026-10-28_gemini.md
      → 報告中提到的加權合理價值 NT$3,260.67 與 DCF 基準每股內在價值 NT$3,251.34 之間存在不一致。
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-10-28_gemini.md
      → 報告中提到的 P/E 比率為 148.7x，這在半導體行業中顯得不合理，應該進一步驗證。
  avav         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-10-28_gemini.md
      → 報告中提到的加權合理價值 $157.08 與後續計算的 $150.74 相矛盾。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-10-29_gemini.md
      → 報告中提到的加權合理價值 $403.49 與 DCF 基準每股內在價值 $402.16 之間存在矛盾。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-10-29_gemini.md
      → 報告中提到的加權合理價值 $57.39 與 DCF 基準每股內在價值 $58.28 之間存在矛盾。
  ktos         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-10-28_gemini.md
      → 報告中提到的加權合理價值 $35.79 與後續計算的 $39.32 相矛盾。
  meta         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/meta/fundamental_analysis_2026-10-28_gemini.md
      → 報告中提到的加權合理價值 $712.39 與計算結果 $725.19 不一致。
  mrvl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mrvl/fundamental_analysis_2026-10-28_gemini.md
      → 報告中提到的加權合理價值 $269.95 與後續計算的 $277.49 不一致。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-10-28_gemini.md
      → 報告中提到的 FY2026 營業利益率達 80.7%，這一數字不合理，且未提供足夠的數據支持。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-10-28_gemini.md
      → 報告中提到的加權合理價值 $203.10 與更正後的 $207.09 之間存在矛盾。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-10-29_gemini.md
      → 報告中提到的最新單季營收年增率454.0%與前一年基期不符，顯示數據誠信問題。
  nvda         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nvda/fundamental_analysis_2026-10-28_gemini.md
      → 報告中提到的TTM營收年增83.4%與最新單季營收年增105.9%存在矛盾。
  onds         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/onds/fundamental_analysis_2026-10-28_gemini.md
      → 報告中提到的 TTM 營收 $174.10M 與最新季營收年增 1235.4% 的數據不一致，前者顯示的增長率不合理。
  pltr         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pltr/fundamental_analysis_2026-10-28_gemini.md
      → 報告中提到的加權合理價值 $119.82 與後文計算的 $113.92 不一致。
  rklb         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/rklb/fundamental_analysis_2026-10-28_gemini.md
      → 報告中提到的加權合理價值 $59.32 與後文計算的 $58.90 不一致。
  skhy         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/skhy/fundamental_analysis_2026-10-28_gemini.md
      → 報告中提到的TTM營業利益率68.0%與執行摘要中的76.3%不一致。
  sndk         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/sndk/fundamental_analysis_2026-10-28_gemini.md
      → 報告中提到的 FY2026 營收 $20.25B (YoY +175.3%)，但未提供合理的基期數據支持。
  soxq         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/soxq/fundamental_analysis_2026-10-28_gemini.md
      → 報告中提到的加權合理價值 $106.66 與 DCF 內在價值 $107.82 之間存在矛盾。
  spcx         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/spcx/fundamental_analysis_2026-10-29_gemini.md
      → 報告中提到的加權合理價值 $182.50 與後文的 $185.16 相矛盾。

Ungrounded verdicts (1) — reviewer noise, not report defects:
  nbis         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/nbis/technical_analysis_2026-10-28_gemini.md

CSV written → qa/llm_review_2026-10-29.csv (134 row(s))
```
