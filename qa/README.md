# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-10-18 |
| Bad reports found | 4 |
| CSV | [bad_reports_2026-10-18.csv](bad_reports_2026-10-18.csv) |
| Full summary | [summary_2026-10-18.txt](summary_2026-10-18.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================
Total scanned : 5685
Bad reports   : 4  (0.1%)

Issue breakdown:
  REFUSAL                  2
  TOO_SHORT                2
  CUTOFF                   1

Top 10 tickers by bad-report count:
  nbis            1 / 187  bad
  onds            1 / 186  bad
  vst             1 / 187  bad
  wdc             1 / 93   bad

CSV written → qa/bad_reports_2026-10-18.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps).

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-10-18.csv](llm_review_2026-10-18.csv) |
| Full summary | [llm_review_2026-10-18.txt](llm_review_2026-10-18.txt) |

```

============================================================
Reports reviewed : 128
Ungrounded       : 3  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.58 / 5

Verdict breakdown (125 grounded):
  pass              15
  warn              44
  fail              66

Mean score by dimension:
  data_integrity   2.67
  completeness     3.38
  depth            2.70
  consistency      2.90
  language         4.14

Failed review (66):
  0050         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/0050/fundamental_analysis_2026-10-17_gemini.md
      → 報告中提到的穿透加權 ROIC 為 24.6%，但在其他地方提到的 WACC 為 9.25%，這樣的數據組合是否合理值得懷疑。
  2330.tw      fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/2330.tw/fundamental_analysis_2026-10-17_gemini.md
      → 報告中提到的營業利益率58.7%與其他數據不一致，造成數據誠信問題。
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-10-17_gemini.md
      → 報告中提到的TTM營收年增50.1%與TTM營收達$41.31B的數據存在矛盾，因為這樣的年增率應該導致更高的基數。
  amzn         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amzn/fundamental_analysis_2026-10-17_gemini.md
      → 報告中提到的TTM營業利益率達13.7%與FY2022的2.4%相比，顯示出不合理的增長幅度，缺乏合理依據。
  avav         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-10-17_gemini.md
      → 報告中提到 FY2026 營收為 $1.98B，但在不同章節中對於營收增長的描述存在矛盾。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-10-17_gemini.md
      → 報告中提到的TTM營收$89.10B與YoY +85.5%不合理，因為這意味著去年營收為$48.00B，這與報告中其他數據矛盾。
  grab         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/grab/fundamental_analysis_2026-10-17_gemini.md
      → 報告中提到的 'TTM 營收 $3.73B（YoY +21.9%）' 與後續數據不一致，造成數據矛盾。
  mrvl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mrvl/fundamental_analysis_2026-10-17_gemini.md
      → 報告中提到的TTM營收$9.45B與YoY成長36.5%未能提供合理的基期數據支持。
  msft         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/msft/fundamental_analysis_2026-10-17_gemini.md
      → 報告中提到 FY2026 營收為 $3,318 億，但在其他地方提到的數字不一致。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-10-17_gemini.md
      → 報告中提到 FY2026 營收達 $133.19B（YoY +256.3%），但這樣的增長率與前一年 $15.54B 的基數不合理。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-10-17_gemini.md
      → 報告中提到的TTM營收成長454.0%與TTM自由現金流為-$9.61B的數據存在矛盾，無法合理解釋如此高的營收成長卻伴隨著巨額的現金流虧損。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-10-17_gemini.md
      → 報告中提到的 FY2025 營收 $10.63B 與 FY2026 營收 $13.82B 的增長率不一致，前者顯示年增率為 +28.5%，後者卻顯示為 +30.0%。
  nvda         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nvda/fundamental_analysis_2026-10-17_gemini.md
      → 報告中提到的TTM營收302.97B（YoY +105.9%）與後續數據不一致，造成數據誠信問題。
  onds         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/onds/fundamental_analysis_2026-10-17_gemini.md
      → 報告中提到TTM營收爆炸成長979.2%達$1.741億，但在後文中又提到TTM營收為$174.10M，數字不一致。
  orcl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/orcl/fundamental_analysis_2026-10-17_gemini.md
      → 報告中提到的TTM營收$71.78B與YoY增長29.6%不一致，因為這意味著去年營收應為$55.46B，但報告中未提供該數據。
  pl           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pl/fundamental_analysis_2026-10-17_gemini.md
      → 報告中提到的營收年增率為58.1%，但在其他地方卻顯示為44.1%，存在矛盾。
  pltr         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pltr/fundamental_analysis_2026-10-17_gemini.md
      → 報告中提到的 'TTM 營收突破 $6.16B（YoY +78.9%）' 與 '最新季度營收年增率高達 92.83%' 之間存在矛盾。
  qqq          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/qqq/fundamental_analysis_2026-10-17_gemini.md
      → 報告中提到的 '底層成分股 TTM 綜合營收年增 13.8%' 與 '底層企業 FCF 轉換率高達 112.4%' 之數據未能提供來源，且可能不合理。
  rklb         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/rklb/fundamental_analysis_2026-10-17_gemini.md
      → 報告中提到的TTM營收$769.15M與YoY增長62.0%未能提供合理的基期數據支持。
  robo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/robo/fundamental_analysis_2026-10-17_gemini.md
      → 報告中提到的 ROIC 為 14.8%，但在其他地方提到的 WACC 為 9.2%，這樣的數據不一致。

Ungrounded verdicts (3) — reviewer noise, not report defects:
  avav         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/avav/technical_analysis_2026-10-17_gemini.md
  pl           fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/pl/technical_analysis_2026-10-17_gemini-2.md
  sofi         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/sofi/technical_analysis_2026-10-18_gemini.md

CSV written → qa/llm_review_2026-10-18.csv (113 row(s))
```
