# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-11-02 |
| Bad reports, last 2 days | 11  (12.2%) |
| Bad reports, all scanned | 251 |
| CSV | [bad_reports_2026-11-02.csv](bad_reports_2026-11-02.csv) |
| Full summary | [summary_2026-11-02.txt](summary_2026-11-02.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-11-01, 2026-11-02)
Total scanned : 90
Bad reports   : 11  (12.2%)

Issue breakdown:
  DERIVATION               7  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  ARITHMETIC               4  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures

------------------------------------------------------------

All scanned reports
Total scanned : 1503
Bad reports   : 251  (16.7%)

Issue breakdown:
  ARITHMETIC             103  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DERIVATION              90  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
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
  pl             16 / 49   bad
  tsla           13 / 49   bad
  intc           12 / 50   bad
  ktos           12 / 49   bad
  amd            11 / 49   bad
  avav           11 / 49   bad
  nbis           10 / 50   bad
  spcx           10 / 50   bad
  0050            9 / 49   bad
  mrvl            9 / 24   bad

CSV written → qa/bad_reports_2026-11-02.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-11-02.csv](llm_review_2026-11-02.csv) |
| Full summary | [llm_review_2026-11-02.txt](llm_review_2026-11-02.txt) |

```

============================================================
Reports reviewed : 144
Ungrounded       : 1  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.53 / 5

Verdict breakdown (143 grounded):
  pass               5
  warn              75
  fail              63

Mean score by dimension:
  data_integrity   2.44
  completeness     3.37
  depth            2.60
  consistency      2.93
  language         3.96

Failed review (63):
  amzn         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amzn/fundamental_analysis_2026-11-01_gemini.md
      → 報告中出現多處數據不一致，例如加權合理價值在不同章節中顯示為 $284.87 和 $281.33。
  avav         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-11-01_gemini.md
      → 報告中提到的 'TTM 營業利潤率為 -12.6%' 與 '最新單季收斂至 -2.3%' 之間存在矛盾。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-11-01_gemini.md
      → 報告中提到的加權合理價值 $388.94 與後續計算的 $397.63 相矛盾。
  goog         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/goog/fundamental_analysis_2026-11-01_gemini.md
      → 報告中提到的加權合理價值 $375.00 與後文計算的 $367.01 不一致。
  grab         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/grab/fundamental_analysis_2026-11-01_gemini.md
      → 報告中提到的 'TTM 營業利益率回升至 8.9%' 與 'TTM 營業利益率 8.9%' 前後矛盾。
  ktos         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-11-01_gemini.md
      → 報告中提到的加權合理價值 $38.93 與後文計算的 $41.30 相矛盾。
  meta         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/meta/fundamental_analysis_2026-11-01_gemini.md
      → 報告中提到的加權合理價值 $721.37 與 DCF 基準每股內在價值 $725.00 之間存在矛盾。
  msft         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/msft/fundamental_analysis_2026-11-01_gemini.md
      → 報告中提到的加權合理價值 $606.87 與後文計算的 $603.31 不一致。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-11-01_gemini.md
      → 報告中提到的TTM營業利益率達80.7%與TTM ROIC 86.2%是否合理，需進一步驗證。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-11-02_gemini.md
      → 報告中提到的加權合理價值 $1,154.67 與後文計算的 $1,146.01 不一致。
  nvda         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nvda/fundamental_analysis_2026-11-01_gemini.md
      → 報告中提到的加權合理價值 $243.68 與後續計算的 $247.26 不一致。
  onds         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/onds/fundamental_analysis_2026-11-01_gemini.md
      → 報告中加權合理價值標示為 $6.87，但程式複算結果為 $7.72，存在數據不一致。
  pl           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pl/fundamental_analysis_2026-11-01_gemini.md
      → 報告中提到的加權合理價值 $14.61 與後續計算的 $13.88 相矛盾。
  robo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/robo/fundamental_analysis_2026-11-01_gemini.md
      → 報告中提到的 P/B Ratio 為 246.27x，顯然不合理，應為異常值。
  skhy         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/skhy/fundamental_analysis_2026-11-01_gemini.md
      → 報告中提到的 TTM 營收 189.17T KRW 與最新季營收年增 327.9% 的數字不合理，因為這意味著去年營收為 56.00T KRW，這對於 SK hynix 來說是不可能的。
  sndk         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/sndk/fundamental_analysis_2026-11-01_gemini.md
      → 報告中提到TTM營收$28.97B（YoY +272.4%），但該增長率不合理，基期數據未能支持。
  soxq         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/soxq/fundamental_analysis_2026-11-01_gemini.md
      → 報告中提到的加權合理價值 $96.48 與 DCF 基準每股內在價值 $97.81 之間存在矛盾。
  tsla         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/tsla/fundamental_analysis_2026-11-01_gemini.md
      → 報告中加權合理價值 $222.04 與複算結果 $204.05 不一致，顯示數據誠信問題。
  tsm          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/tsm/fundamental_analysis_2026-11-01_gemini.md
      → 報告中提到的加權合理價值 $488.86 與後文計算的 $485.46 不一致。
  vti          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/vti/fundamental_analysis_2026-11-01_gemini.md
      → 報告中提到的加權合理價值 $429.50 與 DCF 內在價值 $432.00 之間存在矛盾。

Ungrounded verdicts (1) — reviewer noise, not report defects:
  meta         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/meta/technical_analysis_2026-11-02_gemini.md

CSV written → qa/llm_review_2026-11-02.csv (139 row(s))
```
