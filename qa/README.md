# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-10-30 |
| Bad reports, last 2 days | 10  (10.9%) |
| Bad reports, all scanned | 215 |
| CSV | [bad_reports_2026-10-30.csv](bad_reports_2026-10-30.csv) |
| Full summary | [summary_2026-10-30.txt](summary_2026-10-30.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-10-29, 2026-10-30)
Total scanned : 92
Bad reports   : 10  (10.9%)

Issue breakdown:
  ARITHMETIC               5  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DERIVATION               3  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  DUPLICATE                1  same ticker+type+date with a -2 / -3 suffix
  LEVEL_MISMATCH           1  a Ch.4 R1–S3 is not the computed level of the same label

------------------------------------------------------------

All scanned reports
Total scanned : 1313
Bad reports   : 215  (16.4%)

Issue breakdown:
  ARITHMETIC              86  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DERIVATION              70  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  DUPLICATE               38  same ticker+type+date with a -2 / -3 suffix
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
  pl             14 / 43   bad
  tsla           12 / 43   bad
  intc           11 / 44   bad
  ktos           11 / 43   bad
  avav           10 / 43   bad
  0050            9 / 43   bad
  amd             9 / 43   bad
  mrvl            8 / 21   bad
  nbis            8 / 44   bad
  rklb            8 / 43   bad

CSV written → qa/bad_reports_2026-10-30.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-10-30.csv](llm_review_2026-10-30.csv) |
| Full summary | [llm_review_2026-10-30.txt](llm_review_2026-10-30.txt) |

```

============================================================
Reports reviewed : 147
Ungrounded       : 2  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.57 / 5

Verdict breakdown (145 grounded):
  pass               6
  warn              75
  fail              64

Mean score by dimension:
  data_integrity   2.53
  completeness     3.45
  depth            2.64
  consistency      2.96
  language         4.11

Failed review (64):
  2330.tw      fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/2330.tw/fundamental_analysis_2026-10-29_gemini.md
      → 報告中提到的 TTM 營收 4.94 兆元與最新單季營收年增 50.9% 的數據未能合理解釋其基期。
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-10-29_gemini.md
      → 報告中提到的加權合理價值 $548.81 與後續計算的 $551.86 不一致。
  amzn         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amzn/fundamental_analysis_2026-10-29_gemini.md
      → 報告中提到的加權合理價值 $295.00 與複算結果 $297.01 不一致。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-10-29_gemini.md
      → 報告中提到的加權合理價值 $403.49 與 DCF 基準每股內在價值 $402.16 之間存在矛盾。
  grab         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/grab/fundamental_analysis_2026-10-29_gemini.md
      → 報告中提到的 'TTM FCF 為 -$186.00M' 與後續的現金流分析不一致。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-10-29_gemini.md
      → 報告中提到的加權合理價值 $65.88 與後文的 $57.39 相矛盾。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-10-30_gemini.md
      → 報告中提到的加權合理價值 $59.13 與後文計算的 $58.61 不一致。
  ktos         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-10-29_gemini.md
      → 報告中提到的加權合理價值 $42.66 與程式複算的 $43.67 存在矛盾。
  meta         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/meta/fundamental_analysis_2026-10-29_gemini.md
      → 報告中提到的加權合理價值 $756.75 與 DCF 基準每股內在價值 $746.11 存在矛盾。
  mrvl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mrvl/fundamental_analysis_2026-10-29_gemini.md
      → 報告中提到的加權合理價值 $151.77 與後文更正為 $169.98 相矛盾。
  msft         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/msft/fundamental_analysis_2026-10-29_gemini.md
      → 報告中提到的加權合理價值 $600.41 與後文計算的 $595.89 不一致。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-10-29_gemini.md
      → 報告中提到的營業利益率達 80.7% 明顯不合理，且未提供合理的數據來源。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-10-29_gemini.md
      → 報告中提到的最新單季營收年增率454.0%與前一年基期不符，基期數據未提供。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-10-30_gemini.md
      → 報告中提到的加權合理價值 $182.16 與程式複算的 $184.38 存在矛盾。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-10-29_gemini.md
      → 報告中出現的數據如 'TTM FCF 為 -$1.67B' 與 '最新季度營收年增 52.1%' 之間存在矛盾，無法合理解釋。
  nvda         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nvda/fundamental_analysis_2026-10-29_gemini.md
      → 報告中提到的加權合理價值 $250.77 與後文計算的 $256.06 不一致。
  orcl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/orcl/fundamental_analysis_2026-10-29_gemini.md
      → 報告中提到的加權合理價值 $192.72 與後文計算的 $195.49 不一致。
  pltr         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pltr/fundamental_analysis_2026-10-29_gemini.md
      → 報告中提到的加權合理價值 $95.84 與更正後的 $105.12 之間存在矛盾。
  rklb         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/rklb/fundamental_analysis_2026-10-29_gemini.md
      → 報告中提到的加權合理價值 $43.08 與 DCF 基準每股內在價值 $35.34 的計算過程不一致，導致數據誠信問題。
  robo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/robo/fundamental_analysis_2026-10-29_gemini.md
      → 報告中提到的穿透 ROIC 為 14.8%，但在其他地方提到的 WACC 為 8.2%，這樣的數據組合可能不合理。

Ungrounded verdicts (2) — reviewer noise, not report defects:
  meta         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/meta/technical_analysis_2026-10-30_gemini.md
  onds         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/onds/technical_analysis_2026-10-29_gemini.md

CSV written → qa/llm_review_2026-10-30.csv (141 row(s))
```
