# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-10-13 |
| Bad reports found | 2 |
| CSV | [bad_reports_2026-10-13.csv](bad_reports_2026-10-13.csv) |
| Full summary | [summary_2026-10-13.txt](summary_2026-10-13.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================
Total scanned : 6182
Bad reports   : 2  (0.0%)

Issue breakdown:
  REFUSAL                  2

Top 10 tickers by bad-report count:
  nbis            1 / 204  bad
  wdc             1 / 94   bad

CSV written → qa/bad_reports_2026-10-13.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps).

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-10-13.csv](llm_review_2026-10-13.csv) |
| Full summary | [llm_review_2026-10-13.txt](llm_review_2026-10-13.txt) |

```

============================================================
Reports reviewed : 141
Ungrounded       : 1  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.46 / 5

Verdict breakdown (140 grounded):
  pass              15
  warn              44
  fail              81

Mean score by dimension:
  data_integrity   2.39
  completeness     3.24
  depth            2.55
  consistency      2.71
  language         3.82

Failed review (81):
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到的 'Forward P/E 37.8x' 與 'PEG 0.61' 的數據未能在其他章節中得到支持，顯示數據不一致。
  amzn         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amzn/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到的TTM營收$775.68B與YoY增長19.6%未能在其他數據中得到一致性支持。
  avav         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到 FY2026 GAAP 淨虧損達 -$265.12M，但在其他地方卻未能提供足夠的背景或解釋，導致數據的可信度受到質疑。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-10-12_gemini.md
      → 報告中提到的TTM營收$89.10B與YoY +85.5%不合理，因為這意味著去年營收為$48.00B，該數字不符合實際情況。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到的 TTM 營收 $89.10B (YoY +85.5%) 似乎不合理，因為這樣的增長率在半導體行業中極為罕見。
  goog         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/goog/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到的 GAAP 淨利率高達 54.75% 是因為包含了大量未實現的投資收益，這可能導致數據失真。
  grab         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/grab/fundamental_analysis_2026-10-12_gemini.md
      → 報告中提到的 'TTM 營收達 $37.31 億' 與 'FY2025 的 $33.70 億' 之間存在矛盾。
  meta         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/meta/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到的 'TTM 營收達 $228.25B（YoY +28.0%）' 與後續數據不一致，造成數據誠信問題。
  msft         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/msft/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到的 FY2026 營收 $331.84B 與其他數據不一致，導致數據誠信問題。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-10-12_gemini.md
      → 報告中提到 FY2026 營收達 $133.19B（YoY +256.3%），但這樣的增長率不合理。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-10-12_gemini.md
      → 報告中提到的TTM營收爆發成長506.9%與TTM營收達$1.36B的數字不合理，因為這意味著去年基期的營收極低，且未提供合理的基期數據。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到的TTM營收454%增長，基期數據不明，可能不合理。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到的 'TTM 營收成長 44.3%' 與 'Q2 2026 淨利 $1.06B (YoY +66.3%)' 之間存在矛盾。
  nvda         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nvda/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到的TTM營收達302.97B（YoY +105.9%）與後續數據不一致，顯示出數據誠信問題。
  onds         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/onds/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到TTM營業利潤率為-166.3%，但在其他章節中未能提供合理的解釋或背景。
  orcl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/orcl/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到的 'TTM FCF 為負（-$45.85B）' 與 'TTM OCF 達 $46.94B 創新高' 之間存在矛盾。
  pl           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pl/fundamental_analysis_2026-10-12_gemini.md
      → 報告中提到的 TTM 淨虧損達 $359.87M 與其他數據不一致，造成數據誠信問題。
  pltr         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pltr/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到的 Q2 2026 營收 YoY +92.83% 與後文提到的 TTM 營收達 $6.16B 之間存在矛盾，因為這樣的增長率不符合該基期的數據。
  qqq          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/qqq/fundamental_analysis_2026-10-12_gemini.md
      → 報告中提到的底層企業加權營收 CAGR 13.8% 與加權 ROIC 24.2% 的數據未能在其他章節中得到一致支持。
  rklb         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/rklb/fundamental_analysis_2026-10-13_gemini.md
      → 報告中提到的 'TTM ROIC 為 -8.84%' 與 'WACC 11.85%' 之間的關係未能合理解釋，導致數據誠信不足。

Ungrounded verdicts (1) — reviewer noise, not report defects:
  nu           fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/nu/technical_analysis_2026-10-13_gemini.md

CSV written → qa/llm_review_2026-10-13.csv (126 row(s))
```
