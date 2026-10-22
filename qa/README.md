# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-10-22 |
| Bad reports found | 4 |
| CSV | [bad_reports_2026-10-22.csv](bad_reports_2026-10-22.csv) |
| Full summary | [summary_2026-10-22.txt](summary_2026-10-22.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================
Total scanned : 5929
Bad reports   : 4  (0.1%)

Issue breakdown:
  REFUSAL                  2
  TOO_SHORT                2
  CUTOFF                   1

Top 10 tickers by bad-report count:
  nbis            1 / 195  bad
  onds            1 / 194  bad
  vst             1 / 195  bad
  wdc             1 / 97   bad

CSV written → qa/bad_reports_2026-10-22.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps).

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-10-22.csv](llm_review_2026-10-22.csv) |
| Full summary | [llm_review_2026-10-22.txt](llm_review_2026-10-22.txt) |

```

============================================================
Reports reviewed : 135
Ungrounded       : 3  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.55 / 5

Verdict breakdown (132 grounded):
  pass              15
  warn              46
  fail              71

Mean score by dimension:
  data_integrity   2.56
  completeness     3.36
  depth            2.64
  consistency      2.87
  language         4.11

Failed review (71):
  0050         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/0050/fundamental_analysis_2026-10-21_gemini.md
      → 報告中提到的穿透 ROIC 為 24.8%，但在其他章節中未能一致確認此數字。
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-10-21_gemini.md
      → 報告中提到的 'TTM 營收 $41.31B（YoY +50.1%）' 與 'FY2023 $22.68B（YoY: -3.9%）' 數據矛盾。
  amzn         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amzn/fundamental_analysis_2026-10-21_gemini.md
      → 報告中提到的TTM營收達$775.68B（YoY +19.6%）與後續數據不一致，造成數據誠信問題。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-10-21_gemini.md
      → 報告中提到的TTM營收$89.10B與YoY增長85.5%不合理，因為這意味著去年營收為$48.00B，這對於Broadcom來說是不可能的。
  goog         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/goog/fundamental_analysis_2026-10-21_gemini.md
      → 報告中提到的 GAAP 淨利率 54.75% 受業外投資收益影響，需校正，但未提供具體數據來源。
  grab         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/grab/fundamental_analysis_2026-10-21_gemini.md
      → 報告中提到 FY25 營收 $3.37B，但在其他地方提到 FY25 營收為 $3.73B，數據不一致。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-10-21_gemini.md
      → 報告中提到的 GAAP 淨虧損 $-11.03B 與 TTM 自由現金流 $4.87B 的數據存在矛盾。
  meta         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/meta/fundamental_analysis_2026-10-21_gemini.md
      → 報告中提到的TTM營收228.25B與YoY增長28.0%不一致，因為這意味著去年營收約178.63B，但報告中未提供該數據。
  mrvl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mrvl/fundamental_analysis_2026-10-21_gemini.md
      → 報告中提到的TTM營收$9.45B與YoY增長36.5%不一致，因為前一年營收未提供。
  msft         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/msft/fundamental_analysis_2026-10-21_gemini.md
      → 報告中提到的 FY2026 營收 $331.84B 與其他數據不一致，導致數據誠信問題。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-10-21_gemini.md
      → 報告中提到 FY2026 營收達 $133.19B（YoY +256.3%），但該增長率不合理，因為基期 FY2025 營收為 $37.38B，無法支持如此高的增長。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-10-21_gemini.md
      → 報告中多處數據顯示不合理，例如TTM營收增長454%與TTM毛利率74.3%是否真實。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-10-21_gemini.md
      → 報告中提到 FY2025 營收 $10.63B (YoY +28.5%)，但在其他地方提到 FY2025 GAAP 淨利潤達到 $2.87B (YoY +45.5%)，數據不一致。
  nvda         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nvda/fundamental_analysis_2026-10-21_gemini.md
      → 報告中提到的TTM營收$302.97B與YoY增長105.9%不合理，因為這意味著去年營收僅為$147.5B，這對於NVIDIA來說是不可能的。
  onds         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/onds/fundamental_analysis_2026-10-21_gemini.md
      → 報告中提到TTM營收爆發式成長979.2%至$1.741億，但在不同章節中對於營收的描述存在矛盾。
  orcl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/orcl/fundamental_analysis_2026-10-21_gemini.md
      → 報告中提到 FY26 營收為 $67.36B，但在其他地方提到 FY27 營收為 $79.48B，這樣的增長率不合理。
  pltr         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pltr/fundamental_analysis_2026-10-21_gemini.md
      → 報告中多處數據不合理，例如營收 YoY 增長率達 92.83% 的基期數據未能合理解釋。
  qqq          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/qqq/fundamental_analysis_2026-10-21_gemini.md
      → 報告中提到的底層成份股加權 ROIC 為 22.8%，但在其他章節中提到的數字不一致。
  rklb         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/rklb/fundamental_analysis_2026-10-21_gemini.md
      → 報告中提到的 P/S 為 44.62x，這一數字在其他章節中未能得到一致的支持。
  robo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/robo/fundamental_analysis_2026-10-21_gemini.md
      → 報告中提到的加權營業利益率擴張至 19.2% 與其他數據不一致，缺乏明確來源。

Ungrounded verdicts (3) — reviewer noise, not report defects:
  avav         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/avav/technical_analysis_2026-10-22_gemini.md
  nbis         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/nbis/technical_analysis_2026-10-21_gemini.md
  onds         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/onds/technical_analysis_2026-10-21_gemini.md

CSV written → qa/llm_review_2026-10-22.csv (120 row(s))
```
