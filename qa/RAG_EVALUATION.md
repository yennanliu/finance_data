# 📐 RAG Evaluation — 如何衡量我們系統的檢索增強生成品質

> 本文說明 **grounding / relevance / precision / recall** 四類指標的定義、彼此關係，以及 **如何在本專案的 pipeline 中實作**。
>
> 適用對象：`scripts/generate_analysis.py`（財務數據 → 報告）與 `scripts/generate_market_news.py`（新聞 → 報告）這兩條生成線。

---

## ✅ 實作狀態（已落地）

本文的方法論已實作於 **`scripts/eval/`**，並把 context 留存接進兩條生成線：

| 元件 | 檔案 | 對應階段 |
| :--- | :--- | :--- |
| Context 留存（sidecar） | `scripts/eval/context_store.py` + 兩個 generator 已接線 | **P0** |
| LLM-as-judge（groundedness / context & answer relevance） | `scripts/eval/judges.py` + `scripts/eval/prompts/` | **P1 / P2** |
| 檢索指標（precision / recall / F1） | `scripts/eval/retrieval.py` | **P3** |
| 抽樣評估 CLI + 趨勢輸出 | `scripts/eval/run_eval.py` → `qa/eval_*.csv` | **P4** |
| Eval set 範本 | `qa/eval_set/` | **P3** |
| 單元測試 | `tests/test_eval.py`（12 passed，無需 API） | — |

### 快速上手

```bash
# 0) 之後每次生成報告會自動寫出 <report>.context.json sidecar（可用 --no-context-sidecar 關閉）
python scripts/generate_market_news.py PLTR --provider gemini

# 1) 不打 API：只看「有多少報告已留存 context」(P0 覆蓋率)
python3 scripts/eval/run_eval.py --root ai_gen_report/market_news --no-llm --summary

# 2) 抽 10% 樣本、用 gpt-4o 當裁判，算 groundedness / relevance，輸出 CSV
python3 scripts/eval/run_eval.py --root ai_gen_report/market_news \
    --since 2026-06 --sample 0.1 --judge-provider openai --judge-model gpt-4o \
    --csv qa/eval_2026-06-16.csv --summary

# 3) 檢索 precision/recall（需 qa/eval_set/*.json 標註）
python3 scripts/eval/run_eval.py --eval-set qa/eval_set --no-llm --summary
```

> 設計重點：sidecar 寫入 **絕不會中斷報告生成**（全程 try/except 降級為警告）；
> sidecar 預設 **不入 git**（`.gitignore` 已加 `*.context.json`），因 CI 每天 42 份會膨脹 repo —— eval 在 **同一次 run** 內讀取即可；要做跨日趨勢再改設定。
> 裁判預設用 **與生成不同的模型**（降低自我偏袒，見 §2.3）。

---

## 0. 先認清：我們的「RAG」長什麼樣？

本系統不是教科書式的「Vector DB → top-k chunks → LLM」，而是 **兩個檢索面（retrieval surface）**：

| 檢索面 | 來源 | 程式位置 | 特性 |
| :--- | :--- | :--- | :--- |
| **A. 結構化財務數據** | yfinance（價格、估值、財報） | `utils/data_fetch.py` → `utils/context.py` | 欄位固定、幾乎一定相關；風險在 **數值正確性 / 新鮮度** |
| **B. 非結構化新聞** | Google/Bing/Yahoo/Seeking Alpha RSS + yfinance news | `generate_market_news.py::fetch_news()` | 關鍵字搜尋、會撈到 **不相關 / 過期 / 跑題** 的新聞；**precision/recall/relevance 真正的戰場** |

**生成端**：兩者組成 context → `utils/llm.py::call_llm()` → Markdown 報告。

> 👉 因此評估要 **分面對待**：
> - 對 **B（新聞檢索）** 套用完整的 retrieval 指標（precision / recall / context relevance）。
> - 對 **A（財務數據）** 重點在 **groundedness（報告數字 = context 數字？）** 與 **freshness**。
> - 對 **最終報告** 一律套用 **groundedness + answer relevance**。

---

## 1. 四個核心指標：定義與直覺

### 1.1 Grounding / Groundedness（忠實度）— 抓幻覺的核心
> **報告裡每一個事實宣稱，是否都能在我們餵給 LLM 的 context 裡找到根據？**

- 例：報告寫「P/E 為 32.5」，但 context 的 `trailingPE` 是 28.1 → **not grounded（幻覺）**。
- 例：報告寫「公司剛宣布裁員」，但 14 則新聞裡沒有任何一則提到 → **not grounded**。
- 這是 **金融報告最致命的指標** —— 編造數字會直接誤導投資判斷。

### 1.2 Relevance（相關度）— 分兩種，別混淆

| 種類 | 問的問題 | 對應檢索面 |
| :--- | :--- | :--- |
| **Context Relevance** | 撈回來的新聞/數據，跟這支股票的分析任務相關嗎？ | 衡量 **retriever**（RSS 關鍵字搜尋好不好） |
| **Answer Relevance** | 最終報告有沒有真的回答「這支股票該關注什麼」？還是答非所問、灌水？ | 衡量 **generator** |

### 1.3 Precision（精確率）— 撈回來的，有多少是該要的？
> **Precision = 相關文件數 / 檢索回來的文件總數**

- 我們的痛點：RSS 用 `{ticker}+stock` 關鍵字搜尋，常撈到 **同名公司、過期新聞、純列表頁**（看 EP04 的 RAG 概念）。
- Precision 低 = context 被雜訊稀釋 → 推升幻覺、浪費 token。

### 1.4 Recall（召回率）— 該撈的，撈到了多少？
> **Recall = 撈到的相關文件數 / 應該存在的相關文件總數**

- 我們的痛點：只有 4 個 RSS feed + yfinance，重大新聞可能 **整個漏掉**。
- Recall 低 = 報告 **遺漏關鍵事件**（如漏掉財報暴雷）。

### 1.5 一張圖看懂關係

```
        ┌─────────── 檢索品質（Retriever）───────────┐   ┌─── 生成品質（Generator）───┐
新聞/數據源 ──fetch──> 撈回的 context ──餵入──> LLM ──> 報告
              │              │                              │
        Recall│        Precision                     Groundedness（忠於 context？）
       (沒漏?) │     Context Relevance                Answer Relevance（有回答?）
              └──────────────┴──────────────────────────────┘
```

- **Precision/Recall 互相拉扯**：撈越多新聞 → recall ↑ 但 precision 常 ↓。要找平衡點。
- **先修 retriever 再修 generator**：context relevance 低時，再強的模型也救不了 → groundedness 一定差。

---

## 2. 怎麼算？（方法論）

### 2.1 需要一份「評估集」（Eval Set）
沒有 ground truth 就只能算 groundedness/relevance（LLM 自評），算不了 precision/recall。建議建立：

```
qa/eval_set/
  AAPL_2026-06-16.json     # 人工或半自動標註
  NVDA_2026-06-16.json
```

每筆樣本：
```json
{
  "ticker": "AAPL",
  "date": "2026-06-16",
  "analysis_type": "market-news",
  "retrieved_docs": [               // fetch_news() 實際撈回的
    {"id": "n1", "title": "...", "publisher": "Bing News", "url": "...", "published": "2026-06-15"},
    ...
  ],
  "relevance_labels": {             // precision 用：每篇相關嗎？(人工或 LLM 標)
    "n1": 1, "n2": 0, "n3": 1
  },
  "gold_events": [                  // recall 用：當天「應該」被涵蓋的重大事件
    "Q3 earnings beat", "new iPhone launch"
  ]
}
```

> 💡 **務實做法**：Precision 的 relevance_labels 可用 **LLM-as-a-judge 自動標**（再抽樣人工校正）；Recall 的 `gold_events` 較難，初期可只對 **少量 tier-1 tickers** 人工建一週。

### 2.2 各指標的計算方式

| 指標 | 怎麼算 | 需要 ground truth？ |
| :--- | :--- | :--- |
| **Groundedness** | 把報告拆成 atomic claims，逐條問 judge：「這條能否由 context 支持？」→ 支持數 / 總數 | ❌（只需 context + 報告） |
| **Context Relevance** | 對每篇撈回的新聞問 judge：「跟分析此股相關嗎 0/1」→ 平均 | ❌ |
| **Answer Relevance** | judge 對「報告是否切題、有無灌水」打分 1–5 | ❌ |
| **Precision** | Σ(relevant retrieved) / Σ(retrieved) | ✅ relevance_labels |
| **Recall** | Σ(gold_events 被報告/context 命中) / Σ(gold_events) | ✅ gold_events |

> Precision/Recall 也可合成 **F1 = 2·P·R/(P+R)**，但金融場景通常 **Recall 更重要**（漏掉重大利空 > 多撈幾則雜訊）。

### 2.3 LLM-as-a-Judge：控成本與消偏見（對齊 EP02/EP04）
- **抽樣**：不要每天 2,700+ 份全評。用 **分層隨機抽樣**（按 ticker tier × analysis_type）抽 5–10%。
- **位置偏見**：判 groundedness 時 **打亂 claim 順序**；用 **CoT**（先列證據再下判斷）。
- **judge 模型**：用與生成 **不同的模型**（如生成用 gemini-flash，judge 用 claude / gpt-4o）降低自我偏袒。

---

## 3. 在本系統怎麼實作（具體落地）

### 3.1 新增評估模組
```
scripts/eval/
  __init__.py
  judges.py        # LLM-as-judge：groundedness / context_relevance / answer_relevance
  retrieval.py     # precision / recall / F1（吃 eval_set）
  run_eval.py      # CLI：跑一批報告 → 輸出指標 + CSV
  prompts/
    groundedness.txt
    context_relevance.txt
    answer_relevance.txt
```

### 3.2 關鍵：在生成時「留存 context」
目前報告只存最終 Markdown，**沒留下當時餵進去的 context**，事後無法算 groundedness。**第一步要先補這個**：

- 在 `generate_analysis.py` / `generate_market_news.py` 產出報告時，把組好的 `financial_context`（或 news block + 來源清單）一起寫到旁路檔，例如：
  ```
  ai_gen_report/.../market_news_2026-06-16_gemini.md
  ai_gen_report/.../market_news_2026-06-16_gemini.context.json   ← 新增
  ```
- 內容含：`retrieved_docs`（fetch_news 回傳）、`financial_snapshot`、`prompt_hash`、`model`。
- 這樣 groundedness/precision 才有「對照組」。

> 注意：市場新聞報告 **已經有來源索引**（檔尾「📌 新聞來源索引」+ frontmatter `provider`），可先用它當粗略 retrieved_docs，但結構化的 `.context.json` 更可靠。

### 3.3 Judge 實作（`scripts/eval/judges.py`）
> ⚠️ 注意：`analysis.utils.llm.call_llm` 的簽章 **綁死了分析用的 prompt 模板**（`call_llm(ticker, context, analysis_type, …)`），不能拿來做通用對話。
> 因此 judges **自帶一個 raw-completion 函式 `judge_complete()`**（沿用 `generate_market_news.py` 的三家 provider 呼叫法），不重用 `call_llm`。

```python
def groundedness(report_md, context_text, *, provider="openai", model=None):
    """把報告拆成 atomic claims，逐條判斷是否被 context 支持。"""
    prompt = _load_prompt("groundedness.txt").format(
        context=context_text, report=report_md, max_claims=40)
    raw = judge_complete(prompt, provider, model, max_tokens=3500)  # raw 對話，非 call_llm
    claims = extract_json(raw).get("claims", [])   # 容錯：剝 ```json``` 圍欄、抓首個 {/[
    supported = sum(1 for c in claims if c.get("supported"))
    return {
        "groundedness": supported / max(len(claims), 1),
        "n_unsupported": len(claims) - supported,
        "unsupported_claims": [c for c in claims if not c.get("supported")],  # ← 抓幻覺
    }
```

`groundedness.txt` prompt 重點：
- 要求 judge **只能用 context 判斷**，context 沒有的就算 unsupported；
- 輸出 **結構化 JSON**（claim / supported / evidence span）；
- 數字類 claim 要 **逐位比對**（金融數字最常出錯）。

### 3.4 Retrieval 指標（`scripts/eval/retrieval.py`）
```python
def precision_recall(sample: dict) -> dict:
    retrieved = sample["retrieved_docs"]
    labels    = sample["relevance_labels"]            # {doc_id: 0/1}
    rel_retrieved = sum(labels.get(d["id"], 0) for d in retrieved)
    precision = rel_retrieved / max(len(retrieved), 1)

    gold = sample.get("gold_events", [])
    hit  = count_events_covered(gold, sample["report_md"])  # LLM 或關鍵字比對
    recall = hit / max(len(gold), 1) if gold else None
    return {"precision": precision, "recall": recall,
            "f1": f1(precision, recall) if recall is not None else None}
```

### 3.5 串進現有 QA 流程
`check_report_quality.py` 已經會掃 `ai_gen_report/` 找壞檔（refusal/cutoff/language）。**把語義評估接在它後面**：

```
check_report_quality.py   →  heuristic 壞檔（已有）
        +
scripts/eval/run_eval.py  →  抽樣算 groundedness/relevance/precision/recall（新增）
        ↓
qa/eval_2026-06-16.csv     +  qa/eval_summary_2026-06-16.txt   ← 比照現有 bad_reports 產出
```

`run_eval.py` CLI 仿照既有風格：
```bash
python3 scripts/eval/run_eval.py --since 2026-06 --sample 0.1 --judge-model claude-... \
        --csv qa/eval_2026-06-16.csv --summary
```

---

## 4. 該追蹤什麼 + 警戒線（建議起點）

| 指標 | 目標 | 紅線（觸發 review） | 失守時先修哪裡 |
| :--- | :--- | :--- | :--- |
| **Groundedness** | ≥ 0.95 | < 0.90 | prompt 加「只能依據提供的資料」、context 留存核對數字 |
| **Context Relevance** | ≥ 0.80 | < 0.65 | 改 RSS query、加日期過濾、加 re-rank（見下） |
| **Answer Relevance** | ≥ 4.2/5 | < 3.5 | prompt 結構、減少模板灌水 |
| **News Precision** | ≥ 0.70 | < 0.50 | 去重、過濾過期、過濾同名公司 |
| **News Recall** | ≥ 0.70 | < 0.50 | 增加 feed 來源、放寬關鍵字 |

> 把這些數字 **逐日寫進 `qa/`**，就能畫趨勢 —— 對齊 EP04 的「RAG Triad 動態追蹤」精神（OpenTelemetry / Cloud Monitoring 等同物，在我們這裡就是 CSV + 趨勢）。

---

## 5. 量到問題後，能怎麼改善 retriever？（對應 EP04）

若 **Context Relevance / Precision 偏低**，可在 `fetch_news()` 後加一層：
1. **日期過濾**：丟掉 N 天前的新聞（frontmatter 已有 `date`，可加 `--news-max-age-days`）。
2. **去重**：已做部分；可再用標題相似度去近重複。
3. **Re-ranking**：用 cross-encoder / 小模型對「ticker + title/snippet」打分，取 top-k（EP04 Q2）。
4. **Hybrid**：關鍵字（sparse）已有；可加 embedding（dense）對 snippet 做語義篩，RRF 融合（EP04 Q1）。

若 **Recall 偏低**：加 feed（如 Reuters、PR Newswire）、或用公司全名 + ticker 雙查詢。

---

## 6. 落地順序（Phased Rollout）

1. ✅ **P0 — 留存 context**：兩條生成線已自動輸出 `.context.json`（`context_store.py`）。
2. ✅ **P1 — Groundedness**：`judges.groundedness`，最高價值、不需 ground truth。抽樣跑，先抓數字幻覺。
3. ✅ **P2 — Context/Answer Relevance**：`judges.context_relevance` / `answer_relevance`，補上 retriever/generator 兩端視角。
4. ✅ **P3 — Precision/Recall**：`retrieval.py` + `qa/eval_set/` 範本（先建 tier-1 tickers 標註）。
5. ◑ **P4 — 趨勢化 + 警戒線**：`run_eval.py` 已能輸出 CSV + 紅線標記；**待辦**：排程每日寫 `qa/eval_*` 並接回 §5 的 retriever 改善。

> **剩下的非程式工作**：(a) 人工/半自動建 `qa/eval_set/*.json` 標註，讓 precision/recall 有 ground truth；
> (b) 把 `run_eval.py` 掛進 CI（接在 `check_report_quality.py` 之後）做每日趨勢。

---

## 附錄：名詞快速對照

| 中文 | English | 一句話 |
| :--- | :--- | :--- |
| 忠實度 | Groundedness / Faithfulness | 報告有沒有編造 context 沒有的東西 |
| 內容相關度 | Context Relevance | 撈回的資料跟任務相關嗎 |
| 回答相關度 | Answer Relevance | 報告有沒有切題回答 |
| 精確率 | Precision | 撈回的之中有多少該要 |
| 召回率 | Recall | 該撈的漏了沒 |
| RAG 三元組 | RAG Triad | Context Relevance + Groundedness + Answer Relevance |

> 延伸閱讀：`blog/fde_rkk_interview/04_rag_hybrid_search_reranking.md`（Hybrid Search / Re-ranking / RAG Triad 的面試級深度解析）。
