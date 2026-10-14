# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-10-14 |
| Bad reports found | 2 |
| CSV | [bad_reports_2026-10-14.csv](bad_reports_2026-10-14.csv) |
| Full summary | [summary_2026-10-14.txt](summary_2026-10-14.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================
Total scanned : 6243
Bad reports   : 2  (0.0%)

Issue breakdown:
  REFUSAL                  2

Top 10 tickers by bad-report count:
  nbis            1 / 206  bad
  wdc             1 / 95   bad

CSV written → qa/bad_reports_2026-10-14.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps).

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-10-14.csv](llm_review_2026-10-14.csv) |
| Full summary | [llm_review_2026-10-14.txt](llm_review_2026-10-14.txt) |

```

============================================================
Reports reviewed : 158
Ungrounded       : 3  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.43 / 5

Verdict breakdown (155 grounded):
  pass              15
  warn              43
  fail              97

Mean score by dimension:
  data_integrity   2.22
  completeness     3.34
  depth            2.59
  consistency      2.66
  language         3.81

Failed review (97):
  0050         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/0050/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到的穿透 ROIC 為 23.8%，但在其他章節中未能提供一致的數據支持。
  amd          unknown                      /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-10-13_gemini-2.md
      → 報告中提到的 'Forward P/E 154.5x' 與後文 'Forward P/E 38.5x' 互相矛盾。
  amzn         unknown                      /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amzn/fundamental_analysis_2026-10-13_gemini-2.md
      → 報告中出現多處數據不一致，例如執行摘要中提到的營業利益率為 13.7%，而在其他章節中卻有不同的數字。
  amzn         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amzn/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到的TTM營收$775.68B與YoY增長19.6%未能在其他章節中得到一致的支持。
  avav         unknown                      /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-10-13_gemini-2.md
      → 報告中提到 FY2026 營收為 $1.98B，但在其他地方提到 FY2026 營收為 $2,253.78M，數字不一致。
  avav         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到 FY2026 GAAP 淨虧損達 -$265.12M，但在其他部分卻未能清楚解釋該數字的來源及合理性。
  avgo         unknown                      /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-10-13_gemini-2.md
      → 報告中提到的 TTM 營收達 $89.10B（YoY +85.5%），但這樣的增長率不合理，因為前一年營收未達到此規模。
  goog         unknown                      /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/goog/fundamental_analysis_2026-10-13_gemini-2.md
      → 報告中提到的營業利潤率在不同章節出現矛盾，例如 34.0% 和 32.03%。
  goog         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/goog/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到的 GAAP 淨利率 54.75% 受非經常性投資評價收益影響，未能清楚說明其對核心業務的影響。
  grab         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/grab/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到的 GAAP 營業利益率為 3.7%，但在其他地方卻顯示為 2.4%，存在矛盾。
  intc         unknown                      /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-10-13_gemini-2.md
      → 報告中提到的 'TTM ROE 為 -10.7%' 與 'ROIC 為 2.76%' 之間的矛盾，顯示出數據不一致。
  ktos         unknown                      /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-10-13_gemini-2.md
      → 報告中提到的 'TTM FCF 為 -$118.3M' 與 'TTM 營收 YoY +25.5%' 的數據不一致，顯示出現矛盾。
  ktos         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到的 TTM 營業利益率為 -0.2%，但在不同章節中未能一致解釋其影響。
  mrvl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mrvl/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到的 'Forward P/E 36.5x' 與 'EV/EBITDA 高達 82.3x' 的數據顯示出明顯的估值不合理，這些數字不符合行業標準。
  msft         unknown                      /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/msft/fundamental_analysis_2026-10-13_gemini-2.md
      → 報告中提到的 FY2026 營收 $331.84B 與 YoY +17.8% 的數字不合理，因為這意味著 FY2025 營收為 $281.72B，但報告中未提供 FY2025 的具體數字。
  msft         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/msft/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到的 FY2026 營收 $331.84B 與其他數據不一致，導致數據誠信問題。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到 FY2026 營收為 $133.19B，年增率為 +256.3%，但這樣的增長率與前一年 $37.38B 的基數不合理。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到TTM營收為$1.36B，但在不同章節中對於營收增長的描述存在矛盾。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-10-14_gemini.md
      → 報告中提到的營收年增率454.0%與TTM營收1.36B的數字不合理，因為這意味著去年營收僅為246M，這在報告中未曾提及。
  nu           unknown                      /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-10-13_gemini-2.md
      → 報告中提到的 'TTM 營收成長 52.1%' 與 'FY2024 營收 $5.51B' 之間的增長率不一致。

Ungrounded verdicts (3) — reviewer noise, not report defects:
  meta         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/meta/fundamental_analysis_2026-10-13_gemini-2.md
  pltr         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pltr/fundamental_analysis_2026-10-13_gemini-2.md
  onds         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/onds/technical_analysis_2026-10-13_gemini.md

CSV written → qa/llm_review_2026-10-14.csv (143 row(s))
```
