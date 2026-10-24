# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-10-24 |
| Bad reports found | 365 |
| CSV | [bad_reports_2026-10-24.csv](bad_reports_2026-10-24.csv) |
| Full summary | [summary_2026-10-24.txt](summary_2026-10-24.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================
Total scanned : 945
Bad reports   : 365  (38.6%)

Issue breakdown:
  ARITHMETIC             327  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  RR_MISMATCH             28  a stated R/R matches neither target from its own entry/stop
  MISSING_SECTIONS         4  fundamental report lacks one of chapters ## 1. … ## 11.
  PLACEHOLDER              3  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  NAN_VALUE                3  a $nan / nan% leaked from an empty data bar
  TOO_SHORT                2  fewer content lines than a real report has
  STALE_PRICE              2  a newer completed session existed before the report date
  REFUSAL                  1  the model refused instead of writing the report
  CUTOFF                   1  ends mid-sentence or mid-code-block (truncated)

Top 10 tickers by bad-report count:
  grab           17 / 31   bad
  pl             16 / 31   bad
  avav           15 / 31   bad
  ktos           15 / 31   bad
  avgo           14 / 31   bad
  onds           14 / 31   bad
  amd            13 / 31   bad
  mrvl           13 / 15   bad
  mu             13 / 15   bad
  rklb           13 / 31   bad

CSV written → qa/bad_reports_2026-10-24.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-10-24.csv](llm_review_2026-10-24.csv) |
| Full summary | [llm_review_2026-10-24.txt](llm_review_2026-10-24.txt) |

```

============================================================
Reports reviewed : 133
Ungrounded       : 2  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.33 / 5

Verdict breakdown (131 grounded):
  warn              52
  fail              78
  PARSE_ERROR        1

Mean score by dimension:
  data_integrity   2.05
  completeness     3.28
  depth            2.51
  consistency      2.68
  language         4.05

Failed review (78):
  2330.tw      fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/2330.tw/fundamental_analysis_2026-10-23_gemini.md
      → 報告中加權合理價值 stated 為 $3,228.34，與重新計算的 $3,186.60 相差 1.31%。
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-10-23_gemini.md
      → 報告中提到的加權合理價值 $479.69 與複算結果 $471.23 不一致。
  amzn         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amzn/fundamental_analysis_2026-10-23_gemini.md
      → 報告中提到的加權合理價值 $306.77 與 DCF 基準每股內在價值 $299.00 之間的關聯性不明確，缺乏清晰的推導過程。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-10-23_openai.md
      → 報告出現多處未填值的模板佔位符，如「淨現金（正）：$XXX.XB」、「利息費用 $X」、「$X 兆」及「$XXB」。
  goog         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/goog/fundamental_analysis_2026-10-23_gemini.md
      → 報告中加權合理價值 $387.65 與複算結果 $383.03 不一致，顯示數據誠信問題。
  grab         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/grab/fundamental_analysis_2026-10-23_gemini.md
      → 報告中加權合理價值 $3.71 與複算結果 $3.87 不一致，顯示數據誠信問題。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-10-23_gemini.md
      → 報告中加權合理價值寫為 $53.30，但程式複算結果為 $54.84，存在數據不一致。
  ktos         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-10-23_gemini.md
      → 報告中加權合理價值標示為 $48.24，但程式複算顯示應為 $50.22，存在數據不一致問題。
  meta         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/meta/fundamental_analysis_2026-10-23_gemini.md
      → 報告中加權合理價值 $743.08 與複算結果 $751.44 相差 -1.11%，顯示數據不一致。
  mrvl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mrvl/fundamental_analysis_2026-10-23_gemini.md
      → 報告中加權合理價值 $238.45 與複算結果 $245.92 不一致。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-10-23_gemini.md
      → 報告中提到的加權合理價值 $1,053.80 與複算結果 $1,068.84 存在不一致。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-10-23_gemini.md
      → 報告中加權合理價值 $157.65 與複算值 $162.82 相差 -3.18%，顯示數據不一致。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-10-23_gemini.md
      → 報告中加權合理價值 $18.42 與複算值 $18.19 相差 1.26%，數據不一致。
  onds         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/onds/fundamental_analysis_2026-10-23_gemini.md
      → 報告中加權合理價值 stated 為 $8.72，但複算結果顯示應為 $8.79，存在數據誠信問題。
  orcl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/orcl/fundamental_analysis_2026-10-23_gemini.md
      → 報告中加權合理價值標示為 $157.06，但程式複算顯示應為 $160.15，存在數據誠信問題。
  pl           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pl/fundamental_analysis_2026-10-23_gemini.md
      → 報告中加權合理價值寫為 $15.54，但程式複算結果為 $15.98，存在數據不一致問題。
  qqq          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/qqq/fundamental_analysis_2026-10-23_gemini.md
      → 報告中提到的加權合理價值 $791.73 與 DCF 基準每股內在價值 $793.63 之間存在矛盾。
  rklb         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/rklb/fundamental_analysis_2026-10-23_gemini.md
      → 報告中加權合理價值寫為 $35.03，但程式複算顯示應為 $34.83，存在數據不一致。
  robo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/robo/fundamental_analysis_2026-10-23_gemini.md
      → 報告中提到的 P/B Ratio 為 247.0x，顯示數據失真，與行業標準不符。
  skhy         unknown                      /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/skhy/fundamental_analysis_2026-10-23_gemini-2.md
      → 報告中提到的最新單季營收年增 256.8% 可能不合理，因為這樣的增長率在半導體行業中極為罕見。

Ungrounded verdicts (2) — reviewer noise, not report defects:
  pl           fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/pl/technical_analysis_2026-10-23_gemini.md
  sofi         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/sofi/technical_analysis_2026-10-23_gemini.md

CSV written → qa/llm_review_2026-10-24.csv (133 row(s))
```
