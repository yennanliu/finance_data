# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-11-05 |
| Bad reports, last 2 days | 18  (18.2%) |
| Bad reports, all scanned | 298 |
| CSV | [bad_reports_2026-11-05.csv](bad_reports_2026-11-05.csv) |
| Full summary | [summary_2026-11-05.txt](summary_2026-11-05.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-11-04, 2026-11-05)
Total scanned : 99
Bad reports   : 18  (18.2%)

Issue breakdown:
  DERIVATION              12  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  ARITHMETIC               8  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  STALE_PRICE              2  a newer completed session existed before the report date

------------------------------------------------------------

All scanned reports
Total scanned : 1690
Bad reports   : 298  (17.6%)

Issue breakdown:
  DERIVATION             121  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  ARITHMETIC             117  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DUPLICATE               52  same ticker+type+date with a -2 / -3 suffix
  RR_MISMATCH             29  a stated R/R matches neither target from its own entry/stop
  MISSING_SECTIONS         7  fundamental report lacks one of chapters ## 1. … ## 11.
  PLACEHOLDER              6  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  STALE_PRICE              4  a newer completed session existed before the report date
  NAN_VALUE                3  a $nan / nan% leaked from an empty data bar
  TOO_SHORT                2  fewer content lines than a real report has
  REFUSAL                  1  the model refused instead of writing the report
  CUTOFF                   1  ends mid-sentence or mid-code-block (truncated)
  LEVEL_MISMATCH           1  a Ch.4 R1–S3 is not the computed level of the same label

Top 10 tickers by bad-report count:
  pl             17 / 55   bad
  tsla           15 / 55   bad
  intc           14 / 56   bad
  amd            13 / 55   bad
  ktos           13 / 55   bad
  0050           12 / 55   bad
  avav           12 / 55   bad
  nbis           12 / 56   bad
  rklb           11 / 55   bad
  onds           10 / 55   bad

CSV written → qa/bad_reports_2026-11-05.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-11-05.csv](llm_review_2026-11-05.csv) |
| Full summary | [llm_review_2026-11-05.txt](llm_review_2026-11-05.txt) |

```

============================================================
Reports reviewed : 163
Ungrounded       : 5  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.56 / 5

Verdict breakdown (158 grounded):
  pass               9
  warn              77
  fail              72

Mean score by dimension:
  data_integrity   2.47
  completeness     3.41
  depth            2.59
  consistency      2.94
  language         4.03

Failed review (72):
  0050         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/0050/fundamental_analysis_2026-11-04_gemini.md
      → 報告中提到的底層成分股 ROIC 達 19.8%，但在其他章節中未能提供足夠的數據支持此數字的合理性。
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-11-04_gemini.md
      → 報告中提到的加權合理價值 $481.56 與計算結果 $485.64 不一致。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-11-04_gemini.md
      → 報告中提到的加權合理價值 $388.94 與後續計算的 $398.00 不一致。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-11-05_gemini.md
      → 報告中提到的加權合理價值 $391.80 與計算結果 $397.20 不一致。
  goog         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/goog/fundamental_analysis_2026-11-04_gemini.md
      → 報告中提到的加權合理價值 $357.29 與後續計算的 $360.66 不一致。
  grab         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/grab/fundamental_analysis_2026-11-04_gemini.md
      → 報告中提到的加權合理價值 $4.34 與複算結果 $4.39 存在不一致。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-11-04_gemini.md
      → 報告中提到的 TTM ROIC 僅為 1.3%，顯著低於 WACC 15.01%，顯示資本配置無法產生價值。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-11-05_gemini.md
      → 報告中提到的加權合理價值 $57.48 與後續計算的 $58.39 相矛盾。
  meta         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/meta/fundamental_analysis_2026-11-04_gemini.md
      → 報告中提到的加權合理價值 $714.47 與後續計算的 $726.14 不一致。
  mrvl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mrvl/fundamental_analysis_2026-11-04_gemini.md
      → 報告中提到的加權合理價值 $146.40 與後續計算的 $159.30 相矛盾。
  msft         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/msft/fundamental_analysis_2026-11-04_gemini.md
      → 報告中提到的加權合理價值 $625.00 與後文計算的 $620.84 不一致。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-11-04_gemini.md
      → 報告中提到的加權合理價值 $1,059.88 與程式複算的 $1,068.71 存在矛盾。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-11-04_gemini.md
      → 報告中提到的加權合理價值 $181.33 與計算結果 $192.54 不一致。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-11-05_gemini.md
      → 報告中提到的TTM營收年增454.0%與TTM營業利潤率-0.2%存在矛盾，無法同時成立。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-11-04_gemini.md
      → 報告中提到的加權合理價值 $16.80 與 DCF 基準每股內在價值 $16.62 之間存在矛盾。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-11-05_gemini.md
      → 報告中提到的加權合理價值 $17.48 與後文的 $17.99 不一致。
  onds         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/onds/fundamental_analysis_2026-11-05_gemini.md
      → 報告中提到的 TTM 營收 $174.10M 與 YoY 增長 979.3% 的數字不合理，因為這意味著去年營收僅為 $16.06M，這對於一個已上市公司來說不合常理。
  orcl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/orcl/fundamental_analysis_2026-11-04_gemini.md
      → 報告中提到的 TTM 自由現金流為 -$28.72B，這與預測期的自由現金流數據不一致。
  pl           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pl/fundamental_analysis_2026-11-04_gemini.md
      → 報告中提到的 P/S 12.0x 與歷史 79 百分位的比較缺乏具體數據支持。
  qqq          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/qqq/fundamental_analysis_2026-11-04_gemini.md
      → 報告中出現的數據如加權合理價值 $774.22 與 DCF 內在價值 $777.62 之間存在矛盾。

Ungrounded verdicts (5) — reviewer noise, not report defects:
  nu           fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/nu/technical_analysis_2026-11-04_gemini.md
  pl           fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/pl/technical_analysis_2026-11-05_gemini.md
  spcx         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/spcx/technical_analysis_2026-11-05_gemini.md
  tsm          fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/tsm/technical_analysis_2026-11-04_gemini.md
  vst          fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/vst/technical_analysis_2026-11-05_gemini.md

CSV written → qa/llm_review_2026-11-05.csv (154 row(s))
```
