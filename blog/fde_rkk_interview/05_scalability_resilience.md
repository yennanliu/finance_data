---
series: Mock FDE RKK Interview
episode: 5
title: EP05 — 超大規模化與彈性架構
lang: zh-Hant
covers:
  - 類別三：Asynchronous Event-Driven Pipelines
  - 類別三：Backpressure & Dynamic Traffic Shaving
  - 類別三：Idempotency & State Recovery
  - 類別三：Speculative Tool Execution & Fan-Out Control
  - 類別三：Dynamic Data Drift & Blue-Green Indexing
---

# 🎙️ EP05 — 超大規模化與彈性架構

> **本集主軸**：PoC 在筆電上跑得很好，但金融級 24×7 + 爆量 + 節點隨機猝死，是完全不同的遊戲。
> 考點是 **分散式系統的容錯直覺**，這也是 GenAI 候選人最弱、最能拉開差距的一塊。

---

## 🎬 情境 (Scenario)

銀行 Agent 平台正式營運：

- 黑五 / 報稅季出現 **15 倍以上爆量**
- LLM 推理長耗時，**同步 HTTP 連線池被卡爆**
- GKE 節點因 OOM / 搶佔 **隨機重啟**，處理到一半的 Agent 任務消失
- Agent 一次要併發呼叫 **十幾個地端 API**，被最慢的那個拖死
- 知識庫高頻增刪，索引一更新就抖動

請設計可規模化、可恢復的架構。

---

## 🎯 本集 RKK 考點地圖

| JD 考點 | 出現形式 |
| :--- | :--- |
| Async Event-Driven Pipeline | Q1 |
| Backpressure & Traffic Shaving | Q2 |
| Idempotency & Exactly-Once Recovery | Q3 |
| Speculative Execution & Fan-Out | Q4 |
| Blue-Green / Lambda Indexing | Q5 |

**評分維度：** System Design 25% ｜ Security & Reliability 15% ｜ Tradeoff 15%

---

## ❓ Q1 — LLM 推理太久把後端連線池卡死，怎麼辦？

### ✅ 期待回答（同步轉非同步）

> 「不要讓使用者的同步 HTTP 請求 **一路阻塞等 LLM 跑完**。」

```
Client ──同步 HTTP──> API（立刻回 job_id / 202 Accepted）
                       │
                       └──發訊息──> Cloud Pub/Sub ──> Worker（GKE）跑 LLM
                                                         │
Client ──輪詢 / SSE / WebSocket──< 結果回推 <────────────┘
```

- 用 **Cloud Pub/Sub 解耦** 前端請求與長耗時推理。
- 前端拿到結果的方式：輪詢 job 狀態、或 SSE / WebSocket 串流。

### 🎯 面試官在看什麼
- ✅ 知道 **解耦同步請求與長任務**，避免連線池耗盡。

---

## ❓ Q2 — 黑五 15 倍爆量，怎麼削峰？（Backpressure）

### ✅ 期待回答

- **Pub/Sub Flow Control**：消費端依處理能力拉取，佇列當緩衝吸收尖峰，而不是把下游打爆。
- **多租戶 Fair-Share**：用 **Redis 令牌桶（token bucket）** 做限流，避免單一部門吃光配額。
- **優雅降級**：超載時，非關鍵任務降級（如關閉 re-ranking、改用便宜模型，呼應 EP02）。

**Deep Dive：「下游 Gemini 回 429（TPM 配額）怎麼辦？」**
> 「指數退避重試 + 佇列回壓；長期則靠 **Semantic Routing 分流** 降低對 Pro 的壓力，並向 Google 申請配額。」

### 🎯 面試官在看什麼
- ✅ 用 **佇列當 buffer** 吸收尖峰，而不是無腦水平擴容。
- ✅ 多租戶 fair-share 的概念。

---

## ❓ Q3 — GKE 節點猝死，半路的 Agent 任務怎麼救？（Idempotency）

### ✅ 期待回答（Exactly-Once 的真相）

> 「分散式環境做不到真正的 exactly-once delivery，但可以做到 **exactly-once effect** —— 靠 **冪等性 + checkpoint**。」

- **強一致性 Checkpointer**：Agent 每完成一步（尤其是工具呼叫）就把狀態寫入強一致儲存（如 Spanner / Firestore），節點重啟後從 checkpoint **斷點續傳**。
- **冪等鍵（Idempotency Key）**：每個工具呼叫帶唯一鍵，重放時若已執行過就跳過 —— 避免「重複轉帳」這種金融災難。

**Deep Dive：「為什麼工具呼叫一定要冪等？」**
> 「因為 retry 不可避免。沒有冪等鍵，retry = 重複執行副作用（重複開單、重複扣款）。」

### 🎯 面試官在看什麼
- ✅ 不會天真地說「用 exactly-once delivery」——而是 **idempotency + checkpoint** 達成 exactly-once effect。
- ✅ 意識到金融場景副作用重放的嚴重性。

---

## ❓ Q4 — Agent 併發呼叫十幾個 API，被最慢的拖死，怎麼辦？（Fan-Out）

### ✅ 期待回答

- **超時雙發（Speculative / Hedged Request）**：對高延遲尾端的呼叫，超過 P95 就 **再發一份**，誰先回用誰（前提：該呼叫冪等或唯讀）。
- **整體 deadline + 優雅降級**：設總超時，到點就用 **局部殘缺結果渲染**（"以下資訊暫時無法取得"），而不是讓使用者無限等。
- **並發上限 / Bulkhead**：限制同時 in-flight 呼叫數，隔離故障的下游。

### 🎯 面試官在看什麼
- ✅ Hedged request 的概念，且知道 **只有冪等/唯讀才能雙發**。
- ✅ **局部降級** 而非全有全無。

---

## ❓ Q5 — 知識庫高頻增刪，索引更新就抖動，怎麼辦？（Blue-Green Indexing）

### ✅ 期待回答（Lambda 雙緩衝）

| 索引 | 角色 |
| :--- | :--- |
| **Base Index（唯讀）** | 大、穩定、HNSW 圖結構健康 |
| **Delta Index（即時）** | 小、承接即時增刪 |

> 查詢時 **同時打 Base + Delta 再合併**；背景定期把 Delta 合進 Base 並重建，重建完用 **Blue-Green 無感切換**。
> 這樣兼顧 **即時更新**（Delta）與 **HNSW 圖健康度**（Base 不被頻繁增刪打亂）。

### 🎯 面試官在看什麼
- ✅ 知道頻繁增刪會 **破壞 HNSW 圖結構**，所以要 base/delta 分離。
- ✅ Blue-Green 切換做到對查詢無感。

---

## 🗣️ 加分金句

1. *"Decouple the synchronous request from long inference with Pub/Sub — return a job id immediately."*
2. *"The queue is the buffer that absorbs the spike; flow control gives multi-tenant fair-share."*
3. *"You can't get exactly-once delivery, but idempotency + checkpoint gives exactly-once effect."*
4. *"Hedge only idempotent calls; otherwise set a deadline and render partial results."*
5. *"Base index for HNSW health, delta index for freshness, blue-green to swap."*

---

## 📋 RKK Feedback & 評級

| 表現 | Level |
| :--- | :---: |
| 只說「加機器 / 水平擴容」 | L3 / L4 |
| Async + Pub/Sub + 限流 + 重試 | **L4+** |
| Idempotency key + checkpoint + hedged request + blue-green，且講得出金融副作用風險 | **L5** |

---

## 🔮 下集預告 — EP06：State Machine & Deterministic Graph

> 為什麼不能把控制權全丟給 LLM？反思迴圈（Reflection Loop）不收斂、無限自我懷疑燒錢，怎麼用 LangGraph / ADK 的 DAG 收住？

---

> ⚠️ 本系列為面試練習用模擬內容，技術細節以教學清晰為主，實際生產設計請以官方文件與你的合規團隊為準。
