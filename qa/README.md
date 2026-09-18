# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-09-18 |
| Bad reports found | 2 |
| CSV | [bad_reports_2026-09-18.csv](bad_reports_2026-09-18.csv) |
| Full summary | [summary_2026-09-18.txt](summary_2026-09-18.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================
Total scanned : 4647
Bad reports   : 2  (0.0%)

Issue breakdown:
  REFUSAL                  2

Top 10 tickers by bad-report count:
  nbis            1 / 153  bad
  wdc             1 / 69   bad

CSV written → qa/bad_reports_2026-09-18.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps).

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-09-18.csv](llm_review_2026-09-18.csv) |
| Full summary | [llm_review_2026-09-18.txt](llm_review_2026-09-18.txt) |

```

============================================================
Reports reviewed : 117
Ungrounded       : 21  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.72 / 5

Verdict breakdown (96 grounded):
  pass              34
  warn               8
  fail              54

Mean score by dimension:
  data_integrity   3.05
  completeness     3.47
  depth            2.92
  consistency      3.19
  language         4.17

Failed review (54):
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處捏造數據，例如加權合理價值 $619.64 的來源不明。
  goog         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/goog/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現的數據如營收 YoY 成長率與其他數字未提供來源，缺乏數據誠信。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處數據不一致，例如不同章節對於營收的描述存在矛盾。
  meta         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/meta/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現的數據如TTM營收228.25B的來源未明確標示，缺乏數據誠信。
  mrvl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mrvl/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處數據未標明來源，缺乏數據誠信。
  msft         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/msft/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處捏造數據，無法查證的數字如 'FY26 營收 $331.84B'。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處捏造數據，例如 TTM 營收達 $90.27B（YoY +345.7%）不符合實際情況。
  onds         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/onds/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處捏造數據，例如營收增長率 1235.4% 不具合理性。
  pl           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pl/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處未標明來源的具體數字，如營收增長率和毛利率等，缺乏數據誠信。
  qqq          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/qqq/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現的數據如 '加權合理價值 $734.05' 和 '基準每股內在價值 $723.53' 需有明確來源，否則無法確認其真實性。
  rklb         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/rklb/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處未標明來源的數據，例如 'TTM 營收達 $769.15M'。
  robo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/robo/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現了多個未標註來源的具體數字，例如加權合理價值 $91.24 和 DCF 內在價值 $90.58。
  sndk         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/sndk/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現的數據如營收增長率175.3%缺乏來源脈絡，可能為捏造。
  soxq         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/soxq/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處捏造數據，如股息率 31.0% 被標示為異常失真，且無法提供具體來源。
  soxx         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/soxx/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處未標明來源的具體數字，例如加權合理價值 $532.50。
  spcx         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/spcx/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處捏造數據，例如營收年增率 91.9% 的來源不明。
  tsla         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/tsla/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處數據不一致，例如營業利益率在不同章節的數字不一致。
  vti          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/vti/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現的數據如 '加權合理價值 $388.75' 和 '現價 $371.26' 似乎缺乏來源脈絡。
  wqtm         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/wqtm/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處未填值的佔位符，如 'N/A' 和 'TBD'。
  mu           market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/mu/market_news_2026-09-17_gemini.md
      → 報告中提到的股價 977.5 美元缺乏來源脈絡，可能為捏造數據。

Ungrounded verdicts (21) — reviewer noise, not report defects:
  0050         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/0050/fundamental_analysis_2026-09-17_gemini.md
  2330.tw      fail   /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/2330.tw/fundamental_analysis_2026-09-17_gemini.md
  amzn         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amzn/fundamental_analysis_2026-09-17_gemini.md
  avav         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-09-17_gemini.md
  avgo         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-09-17_gemini.md
  grab         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/grab/fundamental_analysis_2026-09-17_gemini.md
  ktos         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-09-17_gemini.md
  nbis         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-09-17_gemini.md
  nu           fail   /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-09-17_gemini.md
  nvda         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nvda/fundamental_analysis_2026-09-17_gemini.md
  orcl         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/orcl/fundamental_analysis_2026-09-17_gemini.md
  pltr         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pltr/fundamental_analysis_2026-09-17_gemini.md
  skhy         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/skhy/fundamental_analysis_2026-09-17_gemini.md
  sofi         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/sofi/fundamental_analysis_2026-09-17_gemini.md
  tsm          fail   /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/tsm/fundamental_analysis_2026-09-17_gemini.md
  vst          fail   /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/vst/fundamental_analysis_2026-09-17_gemini.md
  wdc          fail   /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/wdc/fundamental_analysis_2026-09-17_gemini.md
  goog         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/goog/technical_analysis_2026-09-18_gemini.md
  grab         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/grab/technical_analysis_2026-09-17_gemini.md
  nbis         fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/nbis/technical_analysis_2026-09-17_gemini.md

CSV written → qa/llm_review_2026-09-18.csv (83 row(s))
```
