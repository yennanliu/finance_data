# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-11-03 |
| Bad reports, last 2 days | 19  (21.1%) |
| Bad reports, all scanned | 267 |
| CSV | [bad_reports_2026-11-03.csv](bad_reports_2026-11-03.csv) |
| Full summary | [summary_2026-11-03.txt](summary_2026-11-03.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-11-02, 2026-11-03)
Total scanned : 90
Bad reports   : 19  (21.1%)

Issue breakdown:
  DERIVATION              15  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  ARITHMETIC               6  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures

------------------------------------------------------------

All scanned reports
Total scanned : 1565
Bad reports   : 267  (17.1%)

Issue breakdown:
  ARITHMETIC             108  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DERIVATION             103  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  DUPLICATE               42  same ticker+type+date with a -2 / -3 suffix
  RR_MISMATCH             29  a stated R/R matches neither target from its own entry/stop
  MISSING_SECTIONS         7  fundamental report lacks one of chapters ## 1. … ## 11.
  PLACEHOLDER              6  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  NAN_VALUE                3  a $nan / nan% leaked from an empty data bar
  TOO_SHORT                2  fewer content lines than a real report has
  STALE_PRICE              2  a newer completed session existed before the report date
  REFUSAL                  1  the model refused instead of writing the report
  CUTOFF                   1  ends mid-sentence or mid-code-block (truncated)
  LEVEL_MISMATCH           1  a Ch.4 R1–S3 is not the computed level of the same label

Top 10 tickers by bad-report count:
  pl             17 / 51   bad
  tsla           14 / 51   bad
  intc           13 / 52   bad
  ktos           13 / 51   bad
  amd            12 / 51   bad
  avav           11 / 51   bad
  nbis           11 / 52   bad
  0050           10 / 51   bad
  rklb           10 / 51   bad
  spcx           10 / 52   bad

CSV written → qa/bad_reports_2026-11-03.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-11-03.csv](llm_review_2026-11-03.csv) |
| Full summary | [llm_review_2026-11-03.txt](llm_review_2026-11-03.txt) |

```

============================================================
Reports reviewed : 144
Ungrounded       : 3  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.50 / 5

Verdict breakdown (141 grounded):
  pass               7
  warn              67
  fail              67

Mean score by dimension:
  data_integrity   2.46
  completeness     3.33
  depth            2.57
  consistency      2.87
  language         3.96

Failed review (67):
  0050         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/0050/fundamental_analysis_2026-11-02_gemini.md
      → 報告中提到的加權 ROIC 17.5% 與 WACC 8.28% 的數據未能在其他章節中得到一致的支持。
  2330.tw      fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/2330.tw/fundamental_analysis_2026-11-02_gemini.md
      → 報告中加權合理價值 stated 為 $2,804.83，recomputed 為 $2,356.69，存在數據誠信問題。
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的加權合理價值 $486.29 與後續計算的 $463.59 不一致。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的加權合理價值 $380.00 與後續計算的 $383.21 不一致。
  goog         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/goog/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的加權合理價值 $347.55 與計算結果 $353.47 不一致。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的加權合理價值 $59.50 與 DCF 基準每股內在價值 $56.32 之間的安全邊際計算存在矛盾，MOS 為 -0.8% 與 -1.3% 不一致。
  ktos         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的加權合理價值 $35.40 與複算結果 $36.88 不一致。
  msft         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/msft/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的加權合理價值 $602.80 與 DCF 基準每股內在價值 $600.32 之間存在矛盾。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-11-02_gemini.md
      → 報告中提到的加權合理價值 $1,154.67 與後文計算的 $1,146.01 不一致。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的 TTM 營收 $1.36B 與最新單季營收年增 454.0% 的數據不一致，因為這意味著前一季營收應為 $0.25B，這不合理。
  nvda         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nvda/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的 TTM 營收 $302.97B 與最新單季 YoY +105.9% 的數據不一致，因為這意味著前一季的營收應為 $147.73B，但報告中並未提及此數據。
  onds         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/onds/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的TTM營業利益率為-140.4%，但在執行摘要中卻顯示為-194.5%，數據不一致。
  pl           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pl/fundamental_analysis_2026-11-02_gemini.md
      → 報告中提到的加權合理價值 $15.54 與 DCF 內在價值 $14.81 之間存在矛盾。
  pltr         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pltr/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的 MOS 為 -47.7%，但在 8.8 節中又顯示為 -91.3%，數據自相矛盾。
  qqq          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/qqq/fundamental_analysis_2026-11-02_gemini.md
      → 報告中提到的加權合理價值 $714.48 與更正後的 $710.62 之間存在矛盾。
  rklb         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/rklb/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的加權合理價值 $53.50 與複算結果 $56.10 存在不一致。
  robo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/robo/fundamental_analysis_2026-11-02_gemini.md
      → 報告中提到的加權合理價值 $86.50 與 DCF 內在價值 $85.20 之間存在矛盾。
  skhy         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/skhy/fundamental_analysis_2026-11-02_gemini.md
      → 報告中提到的最新單季營收年增327.9%與單季營業利益率79.7%缺乏合理性，這些數字不符合行業標準。
  sndk         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/sndk/fundamental_analysis_2026-11-02_gemini.md
      → 報告中提到的 TTM 營收 $28.97B 與 YoY +272.4% 的數據不合理，因為這意味著去年營收為 $7.78B，但該公司從未達到過此規模。
  sofi         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/sofi/fundamental_analysis_2026-11-03_gemini.md
      → 報告中提到的TTM FCF為-$8.79B，這與一般金融機構的現金流表現不符，顯示數據不合理。

Ungrounded verdicts (3) — reviewer noise, not report defects:
  meta         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/meta/technical_analysis_2026-11-02_gemini.md
  sofi         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/sofi/technical_analysis_2026-11-03_gemini.md
  spcx         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/spcx/technical_analysis_2026-11-02_gemini.md

CSV written → qa/llm_review_2026-11-03.csv (137 row(s))
```
