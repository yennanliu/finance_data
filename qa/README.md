# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-11-07 |
| Bad reports, last 2 days | 23  (22.5%) |
| Bad reports, all scanned | 327 |
| CSV | [bad_reports_2026-11-07.csv](bad_reports_2026-11-07.csv) |
| Full summary | [summary_2026-11-07.txt](summary_2026-11-07.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-11-06, 2026-11-07)
Total scanned : 102
Bad reports   : 23  (22.5%)

Issue breakdown:
  DERIVATION              14  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  ARITHMETIC               8  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DUPLICATE                6  same ticker+type+date with a -2 / -3 suffix
  STALE_PRICE              1  a newer completed session existed before the report date

------------------------------------------------------------

All scanned reports
Total scanned : 1817
Bad reports   : 327  (18.0%)

Issue breakdown:
  DERIVATION             139  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  ARITHMETIC             126  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DUPLICATE               59  same ticker+type+date with a -2 / -3 suffix
  RR_MISMATCH             29  a stated R/R matches neither target from its own entry/stop
  MISSING_SECTIONS         7  fundamental report lacks one of chapters ## 1. … ## 11.
  PLACEHOLDER              6  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  STALE_PRICE              5  a newer completed session existed before the report date
  NAN_VALUE                3  a $nan / nan% leaked from an empty data bar
  TOO_SHORT                2  fewer content lines than a real report has
  REFUSAL                  1  the model refused instead of writing the report
  CUTOFF                   1  ends mid-sentence or mid-code-block (truncated)
  LEVEL_MISMATCH           1  a Ch.4 R1–S3 is not the computed level of the same label

Top 10 tickers by bad-report count:
  pl             18 / 59   bad
  tsla           16 / 59   bad
  intc           15 / 60   bad
  ktos           15 / 59   bad
  amd            14 / 59   bad
  0050           13 / 59   bad
  avav           13 / 59   bad
  nbis           13 / 60   bad
  rklb           13 / 59   bad
  onds           12 / 59   bad

CSV written → qa/bad_reports_2026-11-07.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-11-07.csv](llm_review_2026-11-07.csv) |
| Full summary | [llm_review_2026-11-07.txt](llm_review_2026-11-07.txt) |

```

============================================================
Reports reviewed : 161
Ungrounded       : 2  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.38 / 5

Verdict breakdown (159 grounded):
  pass               4
  warn              66
  fail              89

Mean score by dimension:
  data_integrity   2.22
  completeness     3.20
  depth            2.47
  consistency      2.74
  language         3.84

Failed review (89):
  0050         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/0050/fundamental_analysis_2026-11-06_gemini.md
      → 報告中提到的 '加權合理價值為 105.00 TWD' 與 '現價為 92.30 TWD' 的數據未能在其他章節中得到一致的支持。
  2330.tw      fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/2330.tw/fundamental_analysis_2026-11-06_gemini.md
      → 報告中提到的加權合理價值 NT$2,866.50 與 DCF 基準每股內在價值 NT$2,842.15 之間的差異未解釋清楚，可能造成數據誠信問題。
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-11-06_gemini-2.md
      → 報告中提到的TTM營收$45.44B與YoY增長41.9%不一致，因為這意味著去年營收約$32.06B，但報告中未提供該數據的來源或合理性。
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-11-06_gemini.md
      → 報告中提到的加權合理價值 $485.45 與後文計算的 $494.85 不一致。
  avav         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-11-06_gemini-2.md
      → 報告中提到的加權合理價值 $157.94 與後續計算的 $162.08 不一致。
  avav         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-11-06_gemini.md
      → 報告中提到的加權合理價值 $135.32 與更正後的 $139.82 之間存在矛盾。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-11-07_gemini.md
      → 報告中提到的加權合理價值 $357.78 與後文計算的 $363.75 不一致。
  goog         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/goog/fundamental_analysis_2026-11-06_gemini.md
      → 報告中提到的加權合理價值 $357.26 與計算結果 $353.28 不一致。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-11-06_gemini.md
      → 報告中提到的加權合理價值 $53.30 與複算結果 $55.31 不一致。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-11-07_gemini.md
      → 報告中提到的 TTM ROIC 為 1.3%，但在其他地方提到的 WACC 為 14.80%，顯示出資本效率的矛盾。
  ktos         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-11-06_gemini-2.md
      → 報告中多處數據不一致，例如加權合理價值在不同章節顯示為 $38.48 和 $42.36。
  ktos         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-11-06_gemini.md
      → 報告中提到的加權合理價值 $29.74 與複算結果 $30.00 不一致。
  meta         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/meta/fundamental_analysis_2026-11-06_gemini-2.md
      → 報告中提到的 TTM 營收 $241.61B 與 YoY +27.5% 的數據不一致，因為這意味著去年營收應為 $189.48B，但報告未提供該數據。
  meta         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/meta/fundamental_analysis_2026-11-06_gemini.md
      → 報告中提到的加權合理價值 $711.23 與後續計算的 $726.16 不一致。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-11-06_gemini.md
      → 報告中提到的TTM營收$133.19B與YoY增長256.3%不合理，基期數據不符。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-11-07_gemini.md
      → 報告中提到的營業利益率達 80.7% 可能不合理，需確認是否符合行業標準。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-11-06_gemini.md
      → 報告中提到的加權合理價值 $128.53 與後續更正的 $143.32 之間存在矛盾。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-11-07_gemini.md
      → 報告中提到的加權合理價值 $157.06 與計算結果 $165.23 不一致，顯示數據誠信問題。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-11-06_gemini-2.md
      → 報告中提到的加權合理價值 $15.54 與後文的 $15.97 相矛盾。
  nvda         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nvda/fundamental_analysis_2026-11-06_gemini-2.md
      → 報告中提到的加權合理價值 $257.72 與後文計算的 $259.16 不一致。

Ungrounded verdicts (2) — reviewer noise, not report defects:
  goog         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/goog/technical_analysis_2026-11-06_gemini.md
  nbis         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/nbis/technical_analysis_2026-11-07_gemini.md

CSV written → qa/llm_review_2026-11-07.csv (157 row(s))
```
