# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-11-12 |
| Bad reports, last 2 days | 17  (17.0%) |
| Bad reports, all scanned | 393 |
| CSV | [bad_reports_2026-11-12.csv](bad_reports_2026-11-12.csv) |
| Full summary | [summary_2026-11-12.txt](summary_2026-11-12.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-11-11, 2026-11-12)
Total scanned : 100
Bad reports   : 17  (17.0%)

Issue breakdown:
  DERIVATION              11  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  ARITHMETIC               6  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  STALE_PRICE              2  a newer completed session existed before the report date

------------------------------------------------------------

All scanned reports
Total scanned : 2128
Bad reports   : 393  (18.5%)

Issue breakdown:
  DERIVATION             175  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  ARITHMETIC             145  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DUPLICATE               77  same ticker+type+date with a -2 / -3 suffix
  RR_MISMATCH             29  a stated R/R matches neither target from its own entry/stop
  MISSING_SECTIONS         7  fundamental report lacks one of chapters ## 1. … ## 11.
  STALE_PRICE              7  a newer completed session existed before the report date
  PLACEHOLDER              6  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  NAN_VALUE                3  a $nan / nan% leaked from an empty data bar
  TOO_SHORT                2  fewer content lines than a real report has
  REFUSAL                  1  the model refused instead of writing the report
  CUTOFF                   1  ends mid-sentence or mid-code-block (truncated)
  LEVEL_MISMATCH           1  a Ch.4 R1–S3 is not the computed level of the same label

Top 10 tickers by bad-report count:
  pl             20 / 69   bad
  intc           19 / 69   bad
  rklb           18 / 69   bad
  amd            17 / 69   bad
  ktos           17 / 69   bad
  tsla           17 / 68   bad
  0050           16 / 69   bad
  avav           15 / 69   bad
  nbis           15 / 70   bad
  spcx           15 / 70   bad

CSV written → qa/bad_reports_2026-11-12.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-11-12.csv](llm_review_2026-11-12.csv) |
| Full summary | [llm_review_2026-11-12.txt](llm_review_2026-11-12.txt) |

```

============================================================
Reports reviewed : 165
Ungrounded       : 3  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.44 / 5

Verdict breakdown (162 grounded):
  pass               2
  warn              78
  fail              82

Mean score by dimension:
  data_integrity   2.34
  completeness     3.32
  depth            2.54
  consistency      2.85
  language         3.93

Failed review (82):
  0050         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/0050/fundamental_analysis_2026-11-11_gemini.md
      → 報告中提到的「成分股加權營收 CAGR 14.2%」與「底層資產加權 ROIC（16.8%）顯著高於 WACC（8.25%）」的數據未能提供來源，可能存在數據誠信問題。
  2330.tw      fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/2330.tw/fundamental_analysis_2026-11-11_gemini.md
      → 報告中提到的加權合理價值 2707.97 TWD 與 DCF 基準每股內在價值 2663.63 TWD 之間存在矛盾。
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-11-11_gemini.md
      → 報告中提到的加權合理價值 $518.35 與後續計算的 $512.71 不一致。
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-11-12_gemini.md
      → 報告中提到的加權合理價值 $621.57 與後續計算的 $612.12 不一致。
  avav         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-11-12_gemini.md
      → 報告中提到的加權合理價值 $146.40 與後文計算的 $153.76 相矛盾。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-11-12_gemini.md
      → 報告中提到的 'Forward P/E 17.7x' 與 'PEG 0.33' 的數據未能在其他章節中得到一致的支持。
  goog         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/goog/fundamental_analysis_2026-11-12_gemini.md
      → 報告中提到的加權合理價值 $338.35 與 DCF 內在價值 $344.20 之間存在矛盾。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-11-11_gemini.md
      → 報告中提到的加權合理價值 $57.50 與後續計算的 $56.24 不一致。
  ktos         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-11-12_gemini.md
      → 報告中提到的加權合理價值 $31.06 與程式複算的 $33.14 不一致。
  meta         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/meta/fundamental_analysis_2026-11-11_gemini.md
      → 報告中提到的加權合理價值 $752.62 與 DCF 基準每股內在價值 $736.21 之間的差異未有合理解釋。
  meta         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/meta/fundamental_analysis_2026-11-12_gemini.md
      → 報告中提到的加權合理價值 $729.83 與 DCF 基準每股內在價值 $745.20 之間存在矛盾。
  msft         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/msft/fundamental_analysis_2026-11-12_gemini.md
      → 報告中提到的加權合理價值 $597.26 與後文的 $581.54 相矛盾。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-11-11_gemini.md
      → 報告中提到的加權合理價值 $1,180.37 與後文計算的 $1,167.67 不一致。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-11-12_gemini.md
      → 報告中提到的加權合理價值 $187.97 與後續計算的 $196.88 不一致。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-11-11_gemini.md
      → 報告中提到的加權合理價值 $15.54 與後續計算的 $15.63 不一致。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-11-12_gemini.md
      → 報告中提到的 Forward P/E 僅 11.27x 與其他數據不一致，應為 11.3x。
  nvda         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nvda/fundamental_analysis_2026-11-11_gemini.md
      → 報告中提到的加權合理價值 $203.22 與後續計算的 $218.50 不一致。
  nvda         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nvda/fundamental_analysis_2026-11-12_gemini.md
      → 報告中提到的加權合理價值 $215.34 與後文計算的 $216.97 不一致。
  onds         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/onds/fundamental_analysis_2026-11-12_gemini.md
      → 報告中加權合理價值 $6.78 與程式複算更正後的 $7.92 相矛盾。
  orcl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/orcl/fundamental_analysis_2026-11-11_gemini.md
      → 報告中提到的加權合理價值 $166.30 與 DCF 基準每股內在價值 $160.00 的計算過程不夠清晰，缺乏詳細推導。

Ungrounded verdicts (3) — reviewer noise, not report defects:
  0050         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/0050/technical_analysis_2026-11-11_gemini.md
  goog         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/goog/technical_analysis_2026-11-11_gemini.md
  pltr         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/pltr/technical_analysis_2026-11-11_gemini.md

CSV written → qa/llm_review_2026-11-12.csv (163 row(s))
```
