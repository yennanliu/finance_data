# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-10-20 |
| Bad reports found | 4 |
| CSV | [bad_reports_2026-10-20.csv](bad_reports_2026-10-20.csv) |
| Full summary | [summary_2026-10-20.txt](summary_2026-10-20.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================
Total scanned : 5808
Bad reports   : 4  (0.1%)

Issue breakdown:
  REFUSAL                  2
  TOO_SHORT                2
  CUTOFF                   1

Top 10 tickers by bad-report count:
  nbis            1 / 191  bad
  onds            1 / 190  bad
  vst             1 / 191  bad
  wdc             1 / 95   bad

CSV written → qa/bad_reports_2026-10-20.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps).

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-10-20.csv](llm_review_2026-10-20.csv) |
| Full summary | [llm_review_2026-10-20.txt](llm_review_2026-10-20.txt) |

```

============================================================
Reports reviewed : 128
Ungrounded       : 1  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.57 / 5

Verdict breakdown (127 grounded):
  pass              15
  warn              44
  fail              68

Mean score by dimension:
  data_integrity   2.57
  completeness     3.40
  depth            2.68
  consistency      2.86
  language         4.15

Failed review (68):
  0050         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/0050/fundamental_analysis_2026-10-19_gemini.md
      → 報告中提到的穿透式 ROIC 達 21.8% 與 WACC 8.82% 的差額為 12.98 個百分點，但在其他部分未能一致反映此數據。
  2330.tw      fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/2330.tw/fundamental_analysis_2026-10-19_gemini.md
      → 報告中提到的營收 YoY +50.9% 與其他數據不一致，缺乏合理性。
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-10-19_gemini.md
      → 報告中提到的 'Forward P/E 34.15x' 與 'Trailing P/E 137.26x' 的數據不一致，可能導致誤解。
  amzn         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amzn/fundamental_analysis_2026-10-19_gemini.md
      → 報告中提到的TTM營收達$775.68B與YoY +19.6%之數字未能在其他章節中得到一致性支持。
  avav         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-10-19_gemini.md
      → 報告中提到 FY2026 營收為 $1.98B，但在其他地方提到的數字與此不一致。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-10-19_gemini.md
      → 報告中提到的 'TTM 營收 $89.10B（YoY +85.5%）' 的增長率不合理，因為基期數據未提供。
  goog         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/goog/fundamental_analysis_2026-10-19_gemini.md
      → 報告中提到的TTM營收445.87B與YoY增長20.1%未能在歷史數據中得到支持。
  grab         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/grab/fundamental_analysis_2026-10-19_gemini.md
      → 報告中提到的 'TTM 營收 $3.73B（YoY +21.9%）' 與後續數據不一致，造成數據矛盾。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-10-19_gemini.md
      → 報告中提到的TTM ROIC為2.81%，但在其他部分提到的WACC為11.52%，顯示出經濟價值消耗狀態，這樣的數據不一致。
  ktos         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-10-19_gemini.md
      → 報告中提到的 P/E 倍數為 230x，顯然不合理，應扣分。
  mrvl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mrvl/fundamental_analysis_2026-10-19_gemini.md
      → 報告中提到的TTM營收達$9.45B（YoY +36.5%）與後續數據不一致，造成數據誠信問題。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-10-19_gemini.md
      → 報告中提到 FY2026 營收達 $133.19B（YoY +256.3%），但前一年 FY2025 營收為 $37.38B，這樣的增長率不合理。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-10-20_gemini.md
      → 報告中提到 FY2026 營收暴增至 $133.19B，年增率為 +379.3%，這在歷史上並不合理。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-10-20_gemini.md
      → 報告中提到的TTM營收增長454.0%與TTM營業現金流強勁放量至$5.26B的數據缺乏合理性，可能捏造。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-10-19_gemini.md
      → 報告中提到的TTM淨利率42.73%與其他數據不一致，造成數據誠信問題。
  nvda         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nvda/fundamental_analysis_2026-10-19_gemini.md
      → 報告中提到的 TTM 營收 $302.97B 與 YoY +105.9% 的數字不合理，因為這意味著去年營收為 $147.00B，這對於 NVDA 來說是不可能的。
  onds         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/onds/fundamental_analysis_2026-10-19_gemini.md
      → 報告中提到TTM營收爆炸性成長979%至$174.1M，但同時又提到FY2024的營收為$7.19M，這樣的增長率不合理。
  orcl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/orcl/fundamental_analysis_2026-10-19_gemini.md
      → 報告中提到的 Q1 FY27 營收年增率為 29.61%，但在其他地方卻顯示為 29.6%，存在數據不一致。
  pltr         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pltr/fundamental_analysis_2026-10-19_gemini.md
      → 報告中提到的 'Forward P/E 82.6x' 與 'P/S 75.8x' 的數據明顯不合理，這些倍數在軟體行業中屬於極端高位，缺乏合理的市場支持。
  qqq          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/qqq/fundamental_analysis_2026-10-19_gemini.md
      → 報告中提到的加權 ROIC 為 24.50%，但在其他地方提到的數字與此不一致。

Ungrounded verdicts (1) — reviewer noise, not report defects:
  onds         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/onds/technical_analysis_2026-10-19_gemini.md

CSV written → qa/llm_review_2026-10-20.csv (113 row(s))
```
