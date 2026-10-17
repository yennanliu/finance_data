# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-10-17 |
| Bad reports found | 4 |
| CSV | [bad_reports_2026-10-17.csv](bad_reports_2026-10-17.csv) |
| Full summary | [summary_2026-10-17.txt](summary_2026-10-17.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================
Total scanned : 5624
Bad reports   : 4  (0.1%)

Issue breakdown:
  REFUSAL                  2
  TOO_SHORT                2
  CUTOFF                   1

Top 10 tickers by bad-report count:
  nbis            1 / 185  bad
  onds            1 / 184  bad
  vst             1 / 185  bad
  wdc             1 / 92   bad

CSV written → qa/bad_reports_2026-10-17.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps).

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-10-17.csv](llm_review_2026-10-17.csv) |
| Full summary | [llm_review_2026-10-17.txt](llm_review_2026-10-17.txt) |

```

============================================================
Reports reviewed : 128
Ungrounded       : 2  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.52 / 5

Verdict breakdown (126 grounded):
  pass               9
  warn              50
  fail              67

Mean score by dimension:
  data_integrity   2.53
  completeness     3.41
  depth            2.67
  consistency      2.84
  language         4.09

Failed review (67):
  0050         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/0050/fundamental_analysis_2026-10-16_gemini.md
      → 報告中提到的台積電營業利益率（42%-45%）與實際數據不符，造成數據誠信問題。
  2330.tw      fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/2330.tw/fundamental_analysis_2026-10-16_gemini.md
      → 報告中提到的2026Q2毛利率達67.72%與後文提到的60.3%存在矛盾。
  amzn         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amzn/fundamental_analysis_2026-10-16_gemini.md
      → 報告中提到的 'TTM 營收達 $7,756.8 億（YoY +19.6%）' 與後續數據不一致，造成數據誠信問題。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-10-16_gemini.md
      → 報告中提到的TTM營收$89.10B（YoY +85.5%）與後續數據不一致，造成數據誠信問題。
  goog         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/goog/fundamental_analysis_2026-10-16_openai.md
      → 報告中出現了大量無法理解的文字和符號，例如 '4減吞烧仓 она道咸3分177 ş|隆语季莖流吟ガ Log??? | Фото смесьالأ Tegغلت奖賞な字舍促母行苦冰克홍汽 |'
  grab         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/grab/fundamental_analysis_2026-10-16_gemini.md
      → 報告中提到的 TTM 營收 $3.73B 與 YoY +21.9% 的數據未能提供來源，且與其他數據存在矛盾。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-10-16_gemini.md
      → 報告中提到的 TTM 營收回升至 $57.03B 與 FY2023 營收 $54.23B 的數字存在矛盾。
  ktos         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-10-16_gemini.md
      → 報告中提到的 TTM 營收 $1.52B 與 FY2024 的 $1.14B 之間的年增率 30.5% 不合理，因為這意味著 FY2024 營收應為 $1.16B。
  meta         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/meta/fundamental_analysis_2026-10-16_gemini.md
      → 報告中提到的 'TTM 營收 $228.25B' 與 'FY2025 $200.97B' 的數字不一致。
  mrvl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mrvl/fundamental_analysis_2026-10-16_gemini.md
      → 報告中提到的TTM營收加速至$9.45B（YoY +36.5%），但未提供去年基期的具體數字，可能存在誤導。
  msft         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/msft/fundamental_analysis_2026-10-16_gemini.md
      → 報告中提到 FY2026 營收為 $331.84B，但在其他地方提到的數字與此不一致。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-10-16_gemini.md
      → 報告中提到 FY2026 營收達 $133.19B，年增率為 +256.3%，但該數字與前期基期不符，顯示數據不合理。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-10-16_gemini.md
      → 報告中提到 FY2025 營收 $10.63B（YoY +28.5%），但在其他地方提到 FY2025 營收為 $8.44B，數據矛盾。
  nvda         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nvda/fundamental_analysis_2026-10-16_gemini.md
      → 報告中提到的TTM營收$302.97B與YoY增長105.9%不合理，因為這意味著去年營收僅為$147.5B，這是該公司從未達到過的規模。
  onds         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/onds/fundamental_analysis_2026-10-16_gemini.md
      → 報告中提到的TTM營收爆發至$174.10M（YoY +1235.4%），但在其他章節中未能提供合理的基期數據支持此增長。
  orcl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/orcl/fundamental_analysis_2026-10-16_gemini.md
      → 報告中提到的淨負債 $132.07B 與流動性 $37.08B 的數據未能在其他章節中得到一致的支持。
  pltr         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pltr/fundamental_analysis_2026-10-16_gemini.md
      → 報告中提到的 P/S 值為 72.6x，但在相對估值分析中卻顯示為 76.8x，數據不一致。
  qqq          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/qqq/fundamental_analysis_2026-10-16_gemini.md
      → 報告中提到的 '底層成分股整體營收 YoY 預期 +13.5%' 與後續的 '穿透式聚合每股內在價值基準為 $756.24' 之間缺乏一致性。
  robo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/robo/fundamental_analysis_2026-10-16_gemini.md
      → 報告中提到的穿透營收預期 YoY +14.2% 與後續數據不一致，造成數據誠信問題。
  skhy         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/skhy/fundamental_analysis_2026-10-16_gemini.md
      → 報告中提到的 Q2 營收年增 256.8% 可能不合理，需確認基期數據。

Ungrounded verdicts (2) — reviewer noise, not report defects:
  rklb         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/rklb/technical_analysis_2026-10-16_gemini.md
  rklb         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/rklb/technical_analysis_2026-10-17_gemini.md

CSV written → qa/llm_review_2026-10-17.csv (119 row(s))
```
