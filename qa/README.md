# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-10-23 |
| Bad reports found | 2397 |
| CSV | [bad_reports_2026-10-23.csv](bad_reports_2026-10-23.csv) |
| Full summary | [summary_2026-10-23.txt](summary_2026-10-23.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================
Total scanned : 5991
Bad reports   : 2397  (40.0%)

Issue breakdown:
  ARITHMETIC            1702
  MISSING_SECTIONS       427
  RR_MISMATCH            256
  NAN_VALUE               14
  REFUSAL                  3
  TOO_SHORT                2
  CUTOFF                   1

Top 10 tickers by bad-report count:
  onds           92 / 196  bad
  grab           90 / 195  bad
  rklb           90 / 197  bad
  pl             88 / 196  bad
  ktos           87 / 196  bad
  tsla           83 / 196  bad
  avav           80 / 195  bad
  intc           79 / 198  bad
  nbis           78 / 197  bad
  amd            77 / 197  bad

CSV written → qa/bad_reports_2026-10-23.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps).

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-10-23.csv](llm_review_2026-10-23.csv) |
| Full summary | [llm_review_2026-10-23.txt](llm_review_2026-10-23.txt) |

```

============================================================
Reports reviewed : 137
Ungrounded       : 3  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.57 / 5

Verdict breakdown (134 grounded):
  pass              14
  warn              51
  fail              69

Mean score by dimension:
  data_integrity   2.63
  completeness     3.47
  depth            2.69
  consistency      2.89
  language         4.16

Failed review (69):
  2330.tw      fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/2330.tw/fundamental_analysis_2026-10-22_gemini.md
      → 報告中提到的 'Forward P/E 僅 16.0x' 與 'PEG 僅 0.68' 可能不合理，需確認數據來源。
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-10-22_gemini.md
      → 報告中提到的 'TTM 營收突破 $41.31B（YoY +50.1%）' 與後續數據不一致，造成數據誠信問題。
  avav         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-10-22_gemini.md
      → 報告中提到 FY2026 營收為 $1.98B，但在其他地方提到 FY2026 營收為 $2.00B，數字不一致。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-10-22_gemini.md
      → 報告中提到的營收 $89.10B（YoY +85.5%）與後續數據不一致，無法確認其真實性。
  goog         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/goog/fundamental_analysis_2026-10-22_gemini.md
      → 報告中提到的 GAAP 淨利率為 54.75%，這一數字顯然不合理，因為它包含了巨額非現金投資重估利益，應該進行校正。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-10-22_gemini.md
      → 報告中提到的 'GAAP 淨利受巨額資產減損壓抑（TTM -$11.29B）' 與後續的 'TTM FCF 轉正至 $4.87B' 之間存在矛盾。
  ktos         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-10-22_gemini.md
      → 報告中提到的營業利潤率僅 -0.2% 與 ROIC 0.82% 明顯低於行業標準，這些數字的合理性值得懷疑。
  msft         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/msft/fundamental_analysis_2026-10-22_gemini.md
      → 報告中提到 FY26 營收達 $331.84B，但在不同章節中對於營收增長的描述存在矛盾。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-10-22_gemini.md
      → 報告中提到 FY2026 營收達 $133.19B（YoY +256.3%），但這樣的增長率不合理，基期數據未能支持。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-10-22_gemini.md
      → 報告中提到TTM營收YoY增長454.0%，但未提供基期數據，可能捏造數據。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-10-22_gemini.md
      → 報告中提到的營業利潤率高達 50.2%，但在不同章節中出現的數字不一致。
  nvda         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nvda/fundamental_analysis_2026-10-22_gemini.md
      → 報告中提到的 TTM 營收 $302.97B (YoY +105.9%)，但該增長率與前一年數據不符，顯示數據誠信問題。
  onds         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/onds/fundamental_analysis_2026-10-22_gemini.md
      → 報告中提到TTM營收爆炸性增長1,235.4%至$174.10M，但前一年營收僅為$2.13M，這樣的增長率不合理。
  orcl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/orcl/fundamental_analysis_2026-10-22_gemini.md
      → 報告中提到的 Q1 2027 營收年增率 29.61% 與其他數據不一致，造成數據誠信問題。
  pl           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pl/fundamental_analysis_2026-10-22_gemini.md
      → 報告中提到的淨利率為 -95.1%，但在不同章節中對於獲利能力的評估存在矛盾。
  pltr         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pltr/fundamental_analysis_2026-10-22_gemini.md
      → 報告中提到的 'Forward P/E 83.5x' 與 '現價溢價 11.8%' 之間的計算不一致，顯示數據誤差。
  qqq          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/qqq/fundamental_analysis_2026-10-22_gemini.md
      → 報告中提到的 '穿透 ROIC 達 24.3%' 與 'WACC（8.82%）' 的數據未能在其他章節中得到一致支持。
  skhy         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/skhy/fundamental_analysis_2026-10-22_gemini.md
      → 報告中提到TTM營收年增256.8%，但基期數據顯示2023年營收為32.77T KRW，這樣的增長率不合理。
  skhy         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/skhy/fundamental_analysis_2026-10-23_gemini.md
      → 報告中提到的TTM營收189.17T KRW與最新季度年增256.8%所隱含的去年基期不合理，因為這意味著去年營收僅為53.06T KRW，這在半導體行業中不具可行性。
  soxq         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/soxq/fundamental_analysis_2026-10-22_gemini.md
      → 報告中提到的穿透營收預期 CAGR +17.8% 與後續的預測數據不一致。

Ungrounded verdicts (3) — reviewer noise, not report defects:
  mrvl         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mrvl/fundamental_analysis_2026-10-22_openai.md
  ktos         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/ktos/technical_analysis_2026-10-23_gemini.md
  pl           fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/pl/technical_analysis_2026-10-22_gemini.md

CSV written → qa/llm_review_2026-10-23.csv (123 row(s))
```
