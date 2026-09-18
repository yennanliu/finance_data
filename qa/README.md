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
Mean score       : 2.46 / 5

Verdict breakdown:
  pass              36
  warn               6
  fail              75

Mean score by dimension:
  data_integrity   2.72
  completeness     3.08
  depth            2.62
  consistency      2.84
  language         3.70

Failed review (75):
  0050         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/0050/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處捏造數據，例如對於營收成長率的預測缺乏實質依據。
  2330.tw      fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/2330.tw/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處捏造數據，例如對於營收和毛利率的數字缺乏來源脈絡。
  amd          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amd/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現的數據如 'TTM 營收 $41.31B (YoY +50.1%)' 需有來源脈絡，否則無法確認其真實性。
  amzn         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amzn/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處捏造數據，例如對於營收和利潤率的數字缺乏來源脈絡。
  avav         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avav/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處未填值的佔位符，如 'N/A' 和 'TBD'。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現的數據如TTM營收$89.10B（YoY +85.5%）缺乏來源脈絡。
  goog         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/goog/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現的數據如營收 YoY 成長率與其他數字未提供明確來源，缺乏數據誠信。
  grab         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/grab/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處捏造數據，例如營收年增率和利潤率的數字無法查證。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處數據不一致，例如不同章節對於營收的描述存在矛盾。
  ktos         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處數據捏造與不合理的數字，例如營業利益率為負且無法合理解釋。
  meta         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/meta/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現的數據如TTM營收228.25B的增長率與其他數據不一致，存在自我矛盾。
  mrvl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mrvl/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處數據未標明來源，缺乏數據誠信。
  msft         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/msft/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處未填值的佔位符，如「$XXX」、「N/A」等。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處捏造數據，例如 TTM 營收達 $90.27B（YoY +345.7%）不符合實際情況。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現的數據如營收增長率454%未提供來源，缺乏數據誠信。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處捏造數據，例如無法驗證的財務數字和來源。
  nvda         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nvda/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處數據捏造，例如營收成長率和利潤率的數字不合理。
  onds         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/onds/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處捏造數據，例如營收增長率 1235.4% 明顯不合理。
  orcl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/orcl/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處數據捏造與不合理的數字，例如營收成長率與利潤率的數據不一致。
  pl           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pl/fundamental_analysis_2026-09-17_gemini.md
      → 報告中出現多處未標明來源的具體數字，如營收增長率和毛利率等，缺乏數據誠信。

CSV written → qa/llm_review_2026-09-18.csv (81 row(s))
```
