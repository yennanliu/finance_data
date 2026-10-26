# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-10-26 |
| Bad reports, last 2 days | 8  (9.9%) |
| Bad reports, all scanned | 412 |
| CSV | [bad_reports_2026-10-26.csv](bad_reports_2026-10-26.csv) |
| Full summary | [summary_2026-10-26.txt](summary_2026-10-26.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-10-25, 2026-10-26)
Total scanned : 81
Bad reports   : 8  (9.9%)

Issue breakdown:
  ARITHMETIC               8  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures

------------------------------------------------------------

All scanned reports
Total scanned : 1068
Bad reports   : 412  (38.6%)

Issue breakdown:
  ARITHMETIC             354  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DUPLICATE               36  same ticker+type+date with a -2 / -3 suffix
  RR_MISMATCH             28  a stated R/R matches neither target from its own entry/stop
  PLACEHOLDER              4  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  MISSING_SECTIONS         4  fundamental report lacks one of chapters ## 1. … ## 11.
  NAN_VALUE                3  a $nan / nan% leaked from an empty data bar
  TOO_SHORT                2  fewer content lines than a real report has
  STALE_PRICE              2  a newer completed session existed before the report date
  REFUSAL                  1  the model refused instead of writing the report
  CUTOFF                   1  ends mid-sentence or mid-code-block (truncated)

Top 10 tickers by bad-report count:
  pl             20 / 35   bad
  ktos           18 / 35   bad
  avav           17 / 35   bad
  grab           17 / 35   bad
  avgo           16 / 36   bad
  onds           16 / 35   bad
  rklb           15 / 35   bad
  vst            15 / 36   bad
  amd            14 / 35   bad
  mrvl           14 / 17   bad

CSV written → qa/bad_reports_2026-10-26.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-10-26.csv](llm_review_2026-10-26.csv) |
| Full summary | [llm_review_2026-10-26.txt](llm_review_2026-10-26.txt) |

```

============================================================
Reports reviewed : 126
Mean score       : 2.51 / 5

Verdict breakdown (126 grounded):
  pass               3
  warn              67
  fail              56

Mean score by dimension:
  data_integrity   2.46
  completeness     3.39
  depth            2.57
  consistency      2.94
  language         3.94

Failed review (56):
  0050         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/0050/fundamental_analysis_2026-10-25_gemini.md
      → 報告中提到的穿透 ROIC 為 18.60%，但在其他章節中未能一致支持此數字。
  amzn         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amzn/fundamental_analysis_2026-10-25_gemini.md
      → 報告中提到的TTM營收$775.68B與最新季營收年增19.6%所隱含的基期數據不一致。
  avav         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-10-25_gemini.md
      → 報告中提到的加權合理價值 $172.48 與複算結果 $345.20 相矛盾。
  goog         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/goog/fundamental_analysis_2026-10-25_gemini.md
      → 報告中提到的加權合理價值 $362.59 與後續計算的 $360.46 不一致。
  grab         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/grab/fundamental_analysis_2026-10-25_gemini.md
      → 報告中提到的加權合理價值 $3.44 與 DCF 基準每股內在價值 $3.33 之間存在矛盾。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-10-25_gemini.md
      → 報告中提到的加權合理價值 $75.89 與複算結果 $74.43 不一致。
  ktos         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-10-25_gemini.md
      → 報告中提到的加權合理價值 $38.45 與後續計算的 $37.88 不一致。
  msft         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/msft/fundamental_analysis_2026-10-25_gemini.md
      → 報告中提到的加權合理價值 $591.24 與 DCF 基準每股內在價值 $583.56 之間存在矛盾。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-10-25_gemini.md
      → 報告中提到的營業利益率達到80.7%與TTM ROIC 86.2%是否合理，需進一步驗證。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-10-25_gemini.md
      → 報告中提到的加權合理價值 $196.35 與後文計算的 $192.07 不一致。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-10-25_gemini.md
      → 報告中提到的TTM營收$13.17B與最新單季營收年增52.1%所隱含的基期不一致，顯示數據誠信問題。
  onds         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/onds/fundamental_analysis_2026-10-25_gemini.md
      → 報告中提到的加權合理價值 $7.61 與程式複算的 $8.52 相矛盾。
  orcl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/orcl/fundamental_analysis_2026-10-25_gemini.md
      → 報告中提到的加權合理價值 $157.08 與後續計算的 $159.59 不一致。
  pl           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pl/fundamental_analysis_2026-10-25_gemini.md
      → 報告中提到的加權合理價值 $15.54 與重新計算的 $15.99 存在矛盾。
  pltr         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pltr/fundamental_analysis_2026-10-25_gemini.md
      → 報告中提到的加權合理價值 $157.07 與後續計算的 $152.29 相矛盾。
  qqq          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/qqq/fundamental_analysis_2026-10-25_gemini.md
      → 報告中提到的加權合理價值 $712.33 與 DCF 基準每股內在價值 $715.20 之間存在矛盾。
  rklb         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/rklb/fundamental_analysis_2026-10-25_gemini.md
      → 報告中提到的加權合理價值 $45.64 與複算結果 $41.64 存在矛盾。
  robo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/robo/fundamental_analysis_2026-10-25_gemini.md
      → 報告中提到的加權合理價值 $86.50 與 DCF 基準每股內在價值 $87.82 之間存在矛盾。
  skhy         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/skhy/fundamental_analysis_2026-10-25_gemini.md
      → 報告中提到的營業利益率達 76.3% 與 TTM 營收 189.17T KRW 的數據不合理，未能提供合理的基期支持。
  sndk         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/sndk/fundamental_analysis_2026-10-25_gemini.md
      → 報告中提到的加權合理價值 $1,878.50 與計算出的 $1,866.28 存在不一致。

CSV written → qa/llm_review_2026-10-26.csv (123 row(s))
```
