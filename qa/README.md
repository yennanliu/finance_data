# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-10-25 |
| Bad reports, last 2 days | 5  (6.0%) |
| Bad reports, all scanned | 404 |
| CSV | [bad_reports_2026-10-25.csv](bad_reports_2026-10-25.csv) |
| Full summary | [summary_2026-10-25.txt](summary_2026-10-25.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-10-24, 2026-10-25)
Total scanned : 84
Bad reports   : 5  (6.0%)

Issue breakdown:
  ARITHMETIC               3  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
  DUPLICATE                2  same ticker+type+date with a -2 / -3 suffix
  PLACEHOLDER              1  unfilled template placeholder ({ticker}, [INSERT …, $XXX)

------------------------------------------------------------

All scanned reports
Total scanned : 1008
Bad reports   : 404  (40.1%)

Issue breakdown:
  ARITHMETIC             346  a derived valuation (§8.8 total, MOS, DCF premium) does not recompute from the report's own figures
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
  pl             19 / 33   bad
  grab           17 / 33   bad
  ktos           17 / 33   bad
  avav           16 / 33   bad
  avgo           16 / 34   bad
  onds           15 / 33   bad
  vst            15 / 34   bad
  amd            14 / 33   bad
  mrvl           14 / 16   bad
  rklb           14 / 33   bad

CSV written → qa/bad_reports_2026-10-25.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is OpenAI, never the provider that wrote the report (gemini), and is
given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-10-25.csv](llm_review_2026-10-25.csv) |
| Full summary | [llm_review_2026-10-25.txt](llm_review_2026-10-25.txt) |

```

============================================================
Reports reviewed : 131
Ungrounded       : 1  (all-ones scores citing nothing from the report — in the CSV, excluded below)
Mean score       : 2.48 / 5

Verdict breakdown (130 grounded):
  pass               2
  warn              70
  fail              58

Mean score by dimension:
  data_integrity   2.44
  completeness     3.35
  depth            2.54
  consistency      2.90
  language         3.94

Failed review (58):
  2330.tw      fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/2330.tw/fundamental_analysis_2026-10-24_gemini.md
      → 報告中出現的數據如營業利益率58.7%與56.1%相互矛盾。
  amzn         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/amzn/fundamental_analysis_2026-10-24_gemini.md
      → 報告中提到的TTM營收$775.68B與YoY增長15.8%不一致，因為這意味著去年營收應為$669.00B，但報告未提供該數據。
  avgo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/avgo/fundamental_analysis_2026-10-24_gemini.md
      → 報告中提到的 TTM 營收 $89.10B 與最新單季營收年增率 85.5% 之間存在矛盾，因為這樣的增長率無法合理推導出該基數。
  grab         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/grab/fundamental_analysis_2026-10-24_gemini.md
      → 報告中提到的加權合理價值 $3.78 與更正後的 $3.85 存在矛盾。
  intc         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/intc/fundamental_analysis_2026-10-24_gemini.md
      → 報告中提到的加權合理價值 $71.95 與後文計算的 $73.98 不一致。
  ktos         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/ktos/fundamental_analysis_2026-10-24_gemini.md
      → 報告中提到的加權合理價值 $37.30 與複算結果 $35.36 不一致。
  mrvl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mrvl/fundamental_analysis_2026-10-24_openai.md
      → 第 6.2 節出現未填值的佔位符「NOPAT = $XX.XB × (1-12.4%) ≈ $XX.XB」與「投入資本 = 股東權益 + 債務 - 現金 ≈ $XX.XB」。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-10-24_gemini.md
      → 報告中提到的營業利益率達 80.7% 與 74.6% 之間存在矛盾。
  nbis         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nbis/fundamental_analysis_2026-10-24_gemini.md
      → 報告中提到的加權合理價值 $184.82 與後續更正的 $193.01 之間存在矛盾。
  nu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/nu/fundamental_analysis_2026-10-24_gemini.md
      → 報告中提到的加權合理價值 $18.66 與更正後的 $18.78 之間存在矛盾。
  orcl         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/orcl/fundamental_analysis_2026-10-24_gemini.md
      → 報告中提到的加權合理價值 $157.17 與更正後的 $162.02 之間存在矛盾。
  pltr         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/pltr/fundamental_analysis_2026-10-24_gemini.md
      → 報告中提到的加權合理價值 $188.50 與後文計算的 $183.12 不一致。
  robo         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/robo/fundamental_analysis_2026-10-24_gemini.md
      → 報告中提到的 P/B Ratio 為 246.86x，這個數字顯然不合理，應該是數據誠信問題。
  skhy         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/skhy/fundamental_analysis_2026-10-24_gemini.md
      → 報告中提到的 TTM 營收 189.17T KRW 與最新季營收年增 256.8% 的數據不合理，顯示出數據誠信問題。
  sofi         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/sofi/fundamental_analysis_2026-10-24_gemini.md
      → 報告中提到的 TTM FCF 為 -$8.79B，這與 GAAP 獲利轉正的結論相矛盾。
  soxx         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/soxx/fundamental_analysis_2026-10-24_gemini.md
      → 報告中提到的加權合理價值 $545.22 與 DCF 基準每股內在價值 $553.84 存在矛盾。
  tsla         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/tsla/fundamental_analysis_2026-10-24_gemini.md
      → 報告中提到的加權合理價值 $157.06 與更正後的 $165.21 之間存在矛盾。
  tsm          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/tsm/fundamental_analysis_2026-10-24_gemini.md
      → 報告中提到的加權合理價值 $506.12 與後文的 $500.18 相矛盾。
  vti          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/vti/fundamental_analysis_2026-10-24_gemini.md
      → 報告中提到的加權合理價值 $423.90 與 DCF 基準每股內在價值 $421.50 之間的差異未解釋。
  wdc          fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/wdc/fundamental_analysis_2026-10-24_gemini.md
      → 報告中提到的加權合理價值 $445.00 與後續計算的 $454.70 不一致。

Ungrounded verdicts (1) — reviewer noise, not report defects:
  tsm          fail   /home/runner/work/finance_data/finance_data/ai_gen_report/technical/tsm/technical_analysis_2026-10-24_gemini.md

CSV written → qa/llm_review_2026-10-25.csv (129 row(s))
```
