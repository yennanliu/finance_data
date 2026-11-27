# Report Quality Audit

Two stages, in order. Stage 1 is deterministic and free; stage 2 asks
an LLM to judge what regex cannot see.

## Stage 1 — rule-based scan (`scripts/check_report_quality.py`)

| Field | Value |
|-------|-------|
| Last run | 2026-11-27 |
| Bad reports, last 2 days | 12  (11.0%) |
| Bad reports, all scanned | 12 |
| CSV | [bad_reports_2026-11-27.csv](bad_reports_2026-11-27.csv) |
| Full summary | [summary_2026-11-27.txt](summary_2026-11-27.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================

Recent — last 2 UTC days (2026-11-26, 2026-11-27)
Total scanned : 109
Bad reports   : 12  (11.0%)

Issue breakdown:
  DCF_GAP                 11  the computed DCF value is more than 50% away from the price: a reading to review, not an arithmetic error
  DERIVATION               1  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)

------------------------------------------------------------

All scanned reports
Total scanned : 2046
Bad reports   : 12  (0.6%)

Issue breakdown:
  DCF_GAP                 11  the computed DCF value is more than 50% away from the price: a reading to review, not an arithmetic error
  DERIVATION               1  a step of a $$ … $$ or $ … $ equation chain does not recompute (a = b that is false)

Top 10 tickers by bad-report count:
  skhy            2 / 31   bad
  amd             1 / 47   bad
  amzn            1 / 56   bad
  avgo            1 / 66   bad
  grab            1 / 59   bad
  ktos            1 / 54   bad
  mrvl            1 / 28   bad
  pltr            1 / 55   bad
  sndk            1 / 13   bad
  tsla            1 / 47   bad

CSV written → qa/bad_reports_2026-11-27.csv
```

## Stage 2 — LLM review (`scripts/review_report_quality.py`)

Grades data integrity, completeness, depth, internal consistency and
language on a 1-5 scale over a rolling 2-day window (report-gen crons
run 17:00-03:00 UTC, so one cycle spans two date stamps). The judge
is never the provider that wrote the report (OpenAI grades
Gemini-generated reports, Gemini grades OpenAI-generated ones), and
is given the close each report was built on and stage 1's findings.

| Field | Value |
|-------|-------|
| CSV | [llm_review_2026-11-27.csv](llm_review_2026-11-27.csv) |
| Full summary | [llm_review_2026-11-27.txt](llm_review_2026-11-27.txt) |

```

============================================================
Reports reviewed : 189
Mean score       : 3.96 / 5

Verdict breakdown (189 grounded):
  pass             105
  warn              59
  fail              25

Mean score by dimension:
  data_integrity   3.98
  completeness     4.50
  depth            3.98
  consistency      4.05
  language         4.57

Failed review (25):
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-11-26_openai.md
      → 數據存在極為荒謬的捏造：報告宣稱 MU 的 TTM 營收達 $133.19B 且營業利益率達 74.6%（GAAP 營業利益 $99.34B），與記憶體產業實際規模與獲利水準嚴重脫節。
  mu           fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/mu/fundamental_analysis_2026-11-27_openai.md
      → 記憶體製造商 MU 的 TTM 毛利率達 80.7%、營業利益率達 74.6%（最新季度達 80.7%），嚴重背離半導體記憶體硬體製造業的合理利潤水準。
  skhy         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/skhy/fundamental_analysis_2026-11-26_openai.md
      → 第 3.5 節稱「2026 年第二季達 KRW 93.82T」，然而第 3.2 節列示該季營收僅為「KRW 79.32T」，單季淨利顯著大於單季營收，數據嚴重矛盾荒謬。
  sndk         fundamental_analysis         /home/runner/work/finance_data/finance_data/ai_gen_report/fundamental/sndk/fundamental_analysis_2026-11-26_openai.md
      → 第 3.3 節與 11.5 節列出記憶體製造商「TTM 毛利率 80.0%」與「最新季度營業利益率 79.6%」，屬於明顯背離產業常理的異常數據。
  2330.tw      market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/2330.tw/market_news_2026-11-27_gemini.md
      → 新聞總覽將「Intel Guidance Shock Sends Taiwan Stocks Plunging 812 Points at Open」列為 2026-11-01；該日為星期日，台股休市，所述開盤重挫事件日
  3008.tw      market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/3008.tw/market_news_2026-11-26_gemini.md
      → 報告將台股單週下跌「6.2%」稱為「創下自 1991 年以來的最大單週跌幅」，此歷史紀錄說法高度可疑，足以動搖核心市場敘事。
  6643.tw      market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/6643.tw/market_news_2026-11-26_gemini.md
      → 報告稱「矽智財族群雖然毛利率高達 100%」，將整個族群毛利率概括為 100%，屬明顯不合理的數字陳述。
  ant          market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/ant/market_news_2026-11-27_gemini.md
      → 報告稱「最新收盤價為 82.79 美元」並多次描述 2026-11-26 收盤；但 2026-11-26 是美國感恩節，NASDAQ 當日休市，相關收盤價與交易日敘述不成立。
  meta         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/meta/market_news_2026-11-26_gemini.md
      → 報告把 Class C 股份計畫描述為支應 AI 資本支出的「籌資緩衝」及不稀釋投票權的融資管道，混淆股權激勵安排與公司籌資，並據此推導融資風險。
  mrvl         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/mrvl/market_news_2026-11-27_gemini.md
      → 報告多處稱市場預期營收為「3.15 億美元」，相對於同段所述 EPS 1.10 美元及 Marvell 的公司規模極不合理，疑將十億誤寫為億，屬重大數據錯誤。
  nu           market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/nu/market_news_2026-11-27_gemini.md
      → 報告多處稱「12 美元」為 NU 的「IPO 價格」或「IPO 基準線」；Nu Holdings 的 IPO 發行價為每股 9 美元，將 12 美元描述為 IPO 價格屬重大數據錯誤。
  nvda         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/nvda/market_news_2026-11-26_gemini.md
      → 報告將「黃仁勳重新回任執行長」及「重返執行長職位僅一天後」當作核心事實，但沒有交代他曾離任；這項重大人事事件高度可疑，足以使主要分析建立在錯誤前提上。
  orcl         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/orcl/market_news_2026-11-26_gemini.md
      → 報告稱 Larry Ellison「單日蒸發 10.9 億美元」，但來源索引標題寫的是「lost $10.9 billion」；中文金額少了一個數量級。
  qqq          market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/qqq/market_news_2026-11-27_gemini.md
      → 報告稱「若於 2000 年頂部投入 200 萬美元在 QQQ 本金將會耗盡」，但未提取款或其他會使本金耗盡的條件，將歷史回撤表述成本金歸零，屬重大數據誤導。
  rklb         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/rklb/market_news_2026-11-27_gemini.md
      → 報告將「第 101 次 Electron 發射任務」延伸描述為「破百次的成功發射」，混淆任務總數與成功發射累計數；Rocket Lab 過往曾有發射失敗，這會誇大其成功紀錄。
  skhy         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/skhy/market_news_2026-11-27_gemini.md
      → 公司概覽稱 SK hynix「成立於 1949 年」，與公司實際成立年份不符。
  sndk         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/sndk/market_news_2026-11-27_gemini.md
      → 報告將「價格底限」連結到「至少 80% 的毛利率」，並在多處當作獲利保障；對 NAND 儲存業者而言此數字極不合理，且合約價格底限本身不能保證特定毛利率。
  soxx         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/soxx/market_news_2026-11-26_gemini.md
      → 報告稱「截至 2026 年 11 月 26 日……SOXX 收在 127.98 美元」，但 2026 年 11 月 26 日是美國感恩節，市場休市，該日不會有收盤價；且同段稱「感恩節前夕」也與日期不符。
  soxx         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/soxx/market_news_2026-11-27_gemini.md
      → 報告列出 SOXX 收盤價 127.98，卻引用行使價 390.000 的 SOXX 賣權作為近期市場資料，兩者價位差距極大，顯示選擇權資料可能與標的價格不匹配。
  spcx         market_news                  /home/runner/work/finance_data/finance_data/ai_gen_report/market_news/spcx/market_news_2026-11-26_gemini.md
      → 報告將「FCC 正式批准 SpaceX 部署最多 100 萬顆」及「SPCX 135 美元 IPO 發行價」等重大事件與數字當作確定事實，存在重大捏造或失實風險。

CSV written → qa/llm_review_2026-11-27.csv (84 row(s))
```
