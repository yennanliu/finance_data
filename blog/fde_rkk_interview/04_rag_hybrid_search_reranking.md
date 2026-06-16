---
series: Mock FDE RKK Interview
episode: 4
title: EP04 — RAG 進階：Hybrid Search × Re-ranking × RAG Triad
lang: zh-Hant
covers:
  - 類別一：Hybrid Search & Fusion Algorithms（RRF）
  - 類別一：Re-ranking Mechanics（Cross-Encoder）
  - 類別四：RAG Triad Metrics Tracking
---

# 🎙️ EP04 — RAG 進階：Hybrid Search × Re-ranking × RAG Triad

> **本集主軸**：PoC 的 RAG「回答品質不錯」，但上線後 **幻覺仍在**。
> 考點是檢索品質的兩段式提升（**召回 → 精排**）與 **如何量化抓幻覺**。

---

## 🎬 情境 (Scenario)

銀行知識庫 RAG 上線後：

- 員工問「**信用卡爭議款最新處理 SLA 是幾天？**」，Agent 答錯（引用到舊政策）
- 向量檢索撈出 Top 50，但正確段落排在第 37 名
- 專有名詞 / 產品代號（如 `AML-2024-R3`）用純語義搜尋常常 miss
- 沒有任何指標能說明「幻覺率」到底多少

請設計檢索與評估管線。

---

## 🎯 本集 RKK 考點地圖

| JD 考點 | 出現形式 |
| :--- | :--- |
| Hybrid Search & RRF | Q1 |
| Re-ranking / Cross-Encoder | Q2 |
| RAG Triad（Context Relevance / Groundedness / Answer Relevance） | Q3 |

**評分維度：** GenAI Depth 25% ｜ Tradeoff 15% ｜ System Design 25%

---

## ❓ Q1 — 純向量搜尋會 miss 專有名詞，怎麼辦？（Hybrid Search）

### ✅ 期待回答

| | Dense（向量） | Sparse（BM25 / SPLADE） |
| :--- | :--- | :--- |
| 擅長 | 語義近似、換句話說 | **精確關鍵字 / 代號 / 罕見詞** |
| 弱點 | 對 `AML-2024-R3` 這種代號失效 | 不懂同義 / 語義 |

> 解法：**兩路都跑，再用 RRF（Reciprocal Rank Fusion）融合排名。**

**為什麼用 RRF 而不是加權分數相加？**
> 「因為 dense 的 cosine 分數和 BM25 分數 **量綱不同、不可直接相加**。RRF 只看 **排名（rank）** 不看原始分數：`score = Σ 1/(k + rank_i)`，天然解決量綱問題，且實作簡單、無需調權重。」

可在單一引擎（如 BigQuery Search）或中台做融合。

### 🎯 面試官在看什麼
- ✅ 講得出 dense / sparse 的 **trade-off**，而不只是「我加個 BM25」。
- ✅ 知道 **RRF 用排名、規避量綱問題**。

---

## ❓ Q2 — Top 50 撈回來了但正確答案排第 37，怎麼辦？（Re-ranking）

### ✅ 期待回答

> 第一段檢索（Bi-Encoder / 向量）是 **為了快、為了召回**，所以撈 Top 50；但它 query 和 doc 分開編碼，精度有限。

第二段用 **Cross-Encoder（Vertex AI Ranking API）** 精排：query 與每個候選 **一起進模型**做相關性打分，把 Top 50 精煉成 **Top 5**。

```
Query → [Bi-Encoder 向量檢索] → Top 50（快、廣）
      → [Cross-Encoder 重排]  → Top 5（準、貴）→ 送進 LLM
```

**為什麼這樣降幻覺？**
> 「LLM 幻覺很大一部分來自 **context 裡塞了不相關段落**。Top 5 精準上下文 → groundedness 提升 → 幻覺下降。同時 token 變少 → 成本與延遲也降。」

**Deep Dive：「為什麼不直接全部用 Cross-Encoder？」**
> 「Cross-Encoder 要對每個候選做一次 forward pass，**O(n) 且貴**，無法掃全庫。所以是『Bi-Encoder 召回 → Cross-Encoder 精排』的兩段式，兼顧速度與精度。」

### 🎯 面試官在看什麼
- ✅ 理解 **Bi-Encoder（召回） vs Cross-Encoder（精排）** 的計算成本差異。
- ✅ 把 re-ranking 連到 **降幻覺 + 降 token 成本**。

---

## ❓ Q3 — 怎麼量化「幻覺率」？（RAG Triad）

### ✅ 期待回答

用可觀測性工具（**OpenTelemetry / Cloud Monitoring**）動態追蹤三元組：

| 指標 | 問的問題 | 抓什麼 |
| :--- | :--- | :--- |
| **Context Relevance** | 撈回來的內容跟問題相關嗎？ | 檢索品質（retriever 好不好） |
| **Groundedness** | 答案有沒有 **忠於** 撈回的內容？ | **抓幻覺的核心** |
| **Answer Relevance** | 答案有沒有真的回答問題？ | 生成品質 |

> 三個一起看才能定位問題：
> - Context Relevance 低 → 修 **retriever**（Hybrid / Re-rank）
> - Context 高但 Groundedness 低 → 模型在 **編造** → 修 prompt / 加 citation 約束
> - 前兩者高但 Answer Relevance 低 → 模型答非所問 → 修生成

**Deep Dive：「線上 3M 請求，每筆都評估嗎？」**
> 「不。用 **分層隨機抽樣 + LLM-as-a-Judge** 評估，控成本（呼應 EP02 Q4）。」

### 🎯 面試官在看什麼
- ✅ 能不能用 RAG Triad **三軸定位** 問題出在 retriever 還是 generator。
- ✅ 知道 Groundedness 是抓幻覺的核心指標。

---

## 🗣️ 加分金句

1. *"Dense and sparse scores aren't on the same scale — that's why we fuse by rank with RRF, not by adding scores."*
2. *"Bi-encoder for recall, cross-encoder for precision — Top 50 down to Top 5."*
3. *"Most hallucination comes from irrelevant context — better re-ranking lowers it and cuts tokens at the same time."*
4. *"Groundedness is the core hallucination metric in the RAG triad."*
5. *"Low context relevance → fix the retriever; high context but low groundedness → the model is fabricating."*

---

## 📋 RKK Feedback & 評級

| 表現 | Level |
| :--- | :---: |
| 只會「加 BM25 / 換 embedding model」 | L4 |
| Hybrid + RRF + Cross-Encoder 兩段式，講得出成本 | **L4+** |
| 用 RAG Triad 三軸定位、連到抽樣評估與成本 | **L5** |

---

## 🔮 下集預告 — EP05：超大規模化（Async / Backpressure / Idempotency / Fan-out）

> 黑五大促 15 倍爆量、GKE 節點被搶佔猝死、Agent 同時併發呼叫十幾個 API —— 系統怎麼不倒？

---

> ⚠️ 本系列為面試練習用模擬內容，技術細節以教學清晰為主，實際生產設計請以官方文件與你的合規團隊為準。
