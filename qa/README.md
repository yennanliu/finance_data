# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-11-14 |
| Bad reports, last 2 days | 6  (5.8%) |
| Bad reports, all scanned | 413 |
| CSV | [bad_reports_2026-11-14.csv](bad_reports_2026-11-14.csv) |
| Full summary | [summary_2026-11-14.txt](summary_2026-11-14.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-11-13, 2026-11-14)
Total scanned : 103
Bad reports   : 6  (5.8%)

Issue breakdown:
  DERIVATION               2  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  ARITHMETIC               2  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  STALE_PRICE              1  a newer completed session existed before the report date
  DUPLICATE                1  same ticker+type+date with a -2 / -3 suffix

------------------------------------------------------------

All scanned reports
Total scanned : 2256
Bad reports   : 413  (18.3%)

Issue breakdown:
  DERIVATION             184  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)
  ARITHMETIC             148  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DUPLICATE               85  same ticker+type+date with a -2 / -3 suffix
  RR_MISMATCH             29  a stated R/R matches neither target from its own entry/stop
  STALE_PRICE              8  a newer completed session existed before the report date
  MISSING_SECTIONS         7  fundamental report lacks one of chapters ## 1. … ## 11.
  PLACEHOLDER              6  unfilled template placeholder ({ticker}, [INSERT …, $XXX)
  NAN_VALUE                3  a $nan / nan% leaked from an empty data bar
  TOO_SHORT                2  fewer content lines than a real report has
  REFUSAL                  1  the model refused instead of writing the report
  CUTOFF                   1  ends mid-sentence or mid-code-block (truncated)
  LEVEL_MISMATCH           1  a Ch.4 R1–S3 is not the computed level of the same label

Top 10 tickers by bad-report count:
  pl             20 / 73   bad
  intc           19 / 73   bad
  rklb           19 / 73   bad
  ktos           18 / 73   bad
  tsla           18 / 72   bad
  0050           17 / 73   bad
  amd            17 / 73   bad
  avav           16 / 73   bad
  nbis           15 / 74   bad
  onds           15 / 73   bad

CSV written → qa/bad_reports_2026-11-14.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-11-14.csv](llm_review_2026-11-14.csv) |
| Full summary | [llm_review_2026-11-14.txt](llm_review_2026-11-14.txt) |

```

============================================================
Reports reviewed : 170
Ungrounded       : 1  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 3.66 / 5

Verdict breakdown (169 grounded):
  pass              78
  warn              62
  fail              27
  PARSE_ERROR        2

Mean score by dimension:
  data_integrity   3.79
  completeness     4.22
  depth            3.74
  consistency      4.01
  language         4.70

Failed review (27):
  avav         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-11-13_gemini.md
      → 報告中提到的加權合理價值 $146.46 與後文計算的 $145.48 不一致。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-11-13_openai.md
      → 報告聲稱 MU 股價為 $798.44、市值 $903.37B、TTM 營收高達 $133.19B，與 Micron 真實規模（營收約數百億美元、股價百餘美元）嚴重脫節，屬嚴重數據幻覺。
  sndk         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/sndk/fundamental_analysis_2026-11-13_openai.md
      → 數據存在極端且不合理之異常，記憶體製造商最新季度營業利益率達 79.6%、TTM 達 72.5% 且 ROIC 達 141.2%，背離半導體產業常理與現實。
  soxx         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/soxx/fundamental_analysis_2026-11-13_openai.md
      → 報告全篇大量充斥未填值的佔位符，如第 8.3 節自由現金流預測表中「FCFF」、「NOPAT」等全數填寫為「N/A」。
  nvda         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/nvda/market_news_2026-11-13_gemini.md
      → 報告中提到的目標價由 500 美元降至 200 美元，缺乏合理的數據支持，可能存在數據誠信問題。
  nvda         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/nvda/market_news_2026-11-14_gemini.md
      → 報告中提到輝達最新收盤價為 162.85 美元，但未提供來源，可能存在數據誠信問題。
  soxq         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/soxq/market_news_2026-11-13_gemini.md
      → 報告中提到的股價 82.71 美元未提供來源，可能存在數據誠信問題。
  0050         technical_analysis           /home/runner/work/finance_data/finance_data/ai_gen_report/technical/0050/technical_analysis_2026-11-13_gemini.md
      → 報告中提到的當前價格 $103.20 與報告日期的收盤價不一致，存在數據誠信問題。
  2330.tw      technical_analysis           /home/runner/work/finance_data/finance_data/ai_gen_report/technical/2330.tw/technical_analysis_2026-11-13_gemini.md
      → 報告中出現的數據如 '當前價格：$2340.00 TWD' 與 '價格：2340.0' 不一致。
  amd          technical_analysis           /home/runner/work/finance_data/finance_data/ai_gen_report/technical/amd/technical_analysis_2026-11-13_gemini.md
      → 報告中提到的支撐位 S1 為 $498.70，但在其他部分提到的價格區間與此不一致。
  avgo         technical_analysis           /home/runner/work/finance_data/finance_data/ai_gen_report/technical/avgo/technical_analysis_2026-11-13_gemini.md
      → 報告中提到的阻力位 R1 ($366.55) 與 MA200 ($366.39) 的數據存在矛盾。
  goog         technical_analysis           /home/runner/work/finance_data/finance_data/ai_gen_report/technical/goog/technical_analysis_2026-11-13_gemini.md
      → 報告中出現了多處數據不一致，例如在技術評分卡中顯示的綜合評分為 35/100，但在其他部分卻未能一致反映此評分。
  intc         technical_analysis           /home/runner/work/finance_data/finance_data/ai_gen_report/technical/intc/technical_analysis_2026-11-13_gemini.md
      → 報告中提到的支撐位 S1: $51.51 與阻力位 R1: $95.68 的數據未能在其他章節中得到一致的解釋。
  ktos         technical_analysis           /home/runner/work/finance_data/finance_data/ai_gen_report/technical/ktos/technical_analysis_2026-11-13_gemini.md
      → 報告中提到的 '52週區間位置僅 3.1%' 與其他數據不一致。
  nu           technical_analysis           /home/runner/work/finance_data/finance_data/ai_gen_report/technical/nu/technical_analysis_2026-11-13_gemini.md
      → 報告中提到的支撐位 S1 $11.78 與 S2 $11.51 的解釋不一致，存在矛盾。
  nvda         technical_analysis           /home/runner/work/finance_data/finance_data/ai_gen_report/technical/nvda/technical_analysis_2026-11-13_gemini.md
      → 報告中提到的支撐位 S1 ($163.90) 與報告結論中的關鍵支撐不一致。
  onds         technical_analysis           /home/runner/work/finance_data/finance_data/ai_gen_report/technical/onds/technical_analysis_2026-11-13_gemini.md
      → 報告中提到的支撐位 S1 為 $4.38，但在其他部分提到的目標價計算中卻出現了 $2.64，這造成了數據不一致。
  orcl         technical_analysis           /home/runner/work/finance_data/finance_data/ai_gen_report/technical/orcl/technical_analysis_2026-11-13_gemini.md
      → 報告中提到的支撐位 S1 ($122.76) 與阻力位 R1 ($147.63) 的計算過程不明確，缺乏數據支持。
  pl           technical_analysis           /home/runner/work/finance_data/finance_data/ai_gen_report/technical/pl/technical_analysis_2026-11-13_gemini.md
      → 報告中提到的均線空頭排列（MA20 < MA50 < MA200）與其他指標的解讀存在矛盾。
  pltr         technical_analysis           /home/runner/work/finance_data/finance_data/ai_gen_report/technical/pltr/technical_analysis_2026-11-13_gemini.md
      → 報告中提到的 MA20 價格為 $183.26，但在其他部分提到價格低於 MA20，存在矛盾。

Ungrounded verdicts (1) — reviewer noise, not report defects:
  nbis         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/nbis/technical_analysis_2026-11-13_gemini.md

CSV written → qa/llm_review_2026-11-14.csv (92 row(s))
```
