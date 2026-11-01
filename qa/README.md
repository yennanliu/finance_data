# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-11-01 |
| Bad reports, last 2 days | 15  (16.3%) |
| Bad reports, all scanned | 240 |
| CSV | [bad_reports_2026-11-01.csv](bad_reports_2026-11-01.csv) |
| Full summary | [summary_2026-11-01.txt](summary_2026-11-01.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-10-31, 2026-11-01)
Total scanned : 92
Bad reports   : 15  (16.3%)

Issue breakdown:
  DERIVATION               7  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  ARITHMETIC               6  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DUPLICATE                3  same ticker+type+date with a -2 / -3 suffix
  MISSING_SECTIONS         1  fundamental report lacks one of chapters ## 1. … ## 11.

------------------------------------------------------------

All scanned reports
Total scanned : 1439
Bad reports   : 240  (16.7%)

Issue breakdown:
  ARITHMETIC              99  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DERIVATION              83  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
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
  pl             15 / 47   bad
  intc           12 / 48   bad
  ktos           12 / 47   bad
  tsla           12 / 47   bad
  avav           11 / 47   bad
  amd            10 / 47   bad
  spcx           10 / 48   bad
  0050            9 / 47   bad
  mrvl            9 / 23   bad
  nbis            9 / 48   bad

CSV written → qa/bad_reports_2026-11-01.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-11-01.csv](llm_review_2026-11-01.csv) |
| Full summary | [llm_review_2026-11-01.txt](llm_review_2026-11-01.txt) |

```

============================================================
Reports reviewed : 146
Ungrounded       : 1  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.47 / 5

Verdict breakdown (145 grounded):
  pass               3
  warn              71
  fail              71

Mean score by dimension:
  data_integrity   2.42
  completeness     3.34
  depth            2.59
  consistency      2.88
  language         3.97

Failed review (71):
  0050         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/0050/fundamental_analysis_2026-10-31_gemini.md
      → 報告中提到的 '底層成份股加權 ROIC 達 18.5%' 與 'WACC 7.50%' 的數據未能提供合理的來源或驗證。
  2330.tw      fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/2330.tw/fundamental_analysis_2026-10-31_gemini.md
      → 報告中提到的加權合理價值3160.00 TWD與DCF內在價值3251.52 TWD之間存在矛盾。
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-10-31_gemini.md
      → 報告中提到的加權合理價值 $424.33 與後文計算的 $416.95 不一致。
  avav         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-10-31_gemini.md
      → 報告中提到的加權合理價值 $155.67 與複算結果 $157.59 存在不一致。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-10-31_gemini.md
      → 報告中提到的加權合理價值 $388.94 與後續更正為 $392.93 的數字不一致。
  grab         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/grab/fundamental_analysis_2026-10-31_gemini.md
      → 報告中提到的加權合理價值 $3.88 與後文計算的 $3.85 不一致。
  ktos         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-10-31_gemini.md
      → 報告中提到的加權合理價值 $38.93 與計算出的 $38.81 不一致。
  meta         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/meta/fundamental_analysis_2026-10-31_gemini.md
      → 報告中提到的加權合理價值 $727.85 與後文計算出的 $716.65 不一致。
  mrvl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mrvl/fundamental_analysis_2026-10-31_gemini.md
      → 報告中提到的 MOS 為 -15.5%，但在其他地方計算為 -18.4%，存在數據不一致。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-10-31_gemini.md
      → 報告中提到的TTM ROIC高達86.2%與WACC 16.02%相比，顯示出極高的資本效率，但這樣的數字在記憶體行業中極為罕見，可能不具可信性。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-10-31_gemini-2.md
      → 報告中提到的加權合理價值 $157.07 與複算結果 $163.84 存在矛盾。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-10-31_gemini.md
      → 報告中提到的加權合理價值 $14.28 與後續更正為 $14.69 的數字不一致，造成數據誠信問題。
  nvda         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nvda/fundamental_analysis_2026-10-31_gemini.md
      → 報告中提到的 TTM 營收 $302.97B 與最新季年增 105.9% 的數據不一致，因為這意味著前一季的營收應為 $147.92B，但實際上不符合該數字。
  pl           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pl/fundamental_analysis_2026-10-31_gemini.md
      → 報告中提到的TTM營收378.28M與YoY增長44.1%與其他數據不一致。
  pltr         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pltr/fundamental_analysis_2026-10-31_gemini.md
      → 報告中提到的加權合理價值 $108.45 與後續計算的 $112.84 不一致。
  qqq          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/qqq/fundamental_analysis_2026-10-31_gemini.md
      → 報告中提到的加權合理價值 $705.80 與 DCF 基準每股內在價值 $708.20 之間存在矛盾。
  rklb         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/rklb/fundamental_analysis_2026-10-31_gemini.md
      → 報告中提到的加權合理價值 $44.59 與後續更正為 $43.29 的數字不一致，造成數據誠信問題。
  skhy         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/skhy/fundamental_analysis_2026-10-31_gemini.md
      → 報告中提到的TTM營收189.17T KRW與最新單季營收年增256.8%不一致，顯示數據誠信問題。
  sndk         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/sndk/fundamental_analysis_2026-10-31_gemini.md
      → 報告中提到的 TTM 營收增長率 272.4% 與最新單季增長率 377.9% 之間的數據不一致，可能存在誤導。
  sofi         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/sofi/fundamental_analysis_2026-10-31_gemini.md
      → 報告中提到的加權合理價值 $23.23 與後文計算的 $23.08 不一致。

Ungrounded verdicts (1) — reviewer noise, not report defects:
  uber         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/uber/technical_analysis_2026-10-31_gemini.md

CSV written → qa/llm_review_2026-11-01.csv (143 row(s))
```
