---
series: Mock FDE RKK Interview
episode: 3
title: EP03 — Context & Memory：對抗 Token 瀑布通膨
lang: zh-Hant
covers:
  - 類別一：Context Management（上下文管理與修剪）
  - 類別一：Memory Architecture & Tiered Storage（階層式記憶體）
  - 類別四：Hardware-Level Context Caching
---

# 🎙️ EP03 — Context & Memory：對抗 Token 瀑布通膨

> **本集主軸**：對話越長、工具回傳越大，Context Window 就被撐爆，成本與延遲一起惡化。
> 考點不是「記得多」，而是「**該記什麼、該丟什麼、記在哪一層**」。

---

## 🎬 情境 (Scenario)

沿用銀行 Agent。客服 Agent 上線後出現：

- 多輪對話到第 20 輪，**Token 數呈瀑布式通膨**，每一輪都把全部歷史塞回去
- Agent 呼叫 Core Banking API，回傳一包 **3 萬 token 的 JSON**，直接吃光 context
- 跨 session 完全沒記憶，老客戶每次都要重講背景

請設計 Agent 的 **上下文管理** 與 **記憶體架構**。

---

## 🎯 本集 RKK 考點地圖

| JD 考點 | 出現形式 |
| :--- | :--- |
| Context Management / Truncate / Compact | Q1、Q2 |
| Tiered Memory（Session / Vector DB / Semantic） | Q3 |
| Hardware-Level Context Caching | Q4 |

**評分維度：** GenAI Depth 25% ｜ System Design 25% ｜ Tradeoff 15%

---

## ❓ Q1 — 對話拉長導致 Token 通膨，怎麼處理？

### 🪤 一般候選人怎麼答
「設一個 max history，超過就砍掉最舊的。」—— 太粗暴，會砍掉重要事實（如客戶身分、限制條件）。

### ✅ 期待回答

把上下文拆成 **不可壓縮（pinned）** 與 **可壓縮（compactable）** 兩部分：

| 區段 | 策略 |
| :--- | :--- |
| System Prompt / Policy / 工具 Schema | **Pinned**，永遠保留（且應快取，見 Q4） |
| 早期對話 | **Compact**：用 LLM 摘要成 running summary |
| 近期 N 輪 | **保留原文**（Sliding Window） |

> 關鍵：**Compact（語義壓縮）≠ Truncate（直接截斷）**。
> Truncate 丟資訊；Compact 用摘要保留語義、壓掉 token。Production 通常是「Sliding Window（近期原文）+ Rolling Summary（早期摘要）」混合。

### 🎯 面試官在看什麼
- ✅ 知不知道「不是所有 token 等價」—— 有些必須 pin。
- ✅ 能不能區分 truncate vs compact。

---

## ❓ Q2 — 工具回傳一包 3 萬 token 的 JSON，怎麼辦？

### ✅ 期待回答

> **「不要把工具的原始輸出直接餵回 LLM。」**

- **Schema 化裁剪**：只取 Agent 任務需要的欄位（projection），其餘丟棄。
- **Summarize-then-inject**：先用便宜模型/規則把 JSON 壓成結構化摘要，再進 context。
- **Reference / Offload**：把大物件存到外部（如物件儲存 / 暫存表），context 裡只放 **引用 ID + 摘要**，需要細節時再按需取回。

**Deep Dive：「為什麼不直接調大 context window 就好？」**
> 「因為 (1) 成本隨 input token 線性上升；(2) 長 context 有 **lost-in-the-middle** 的品質衰退；(3) 延遲（TTFT）變差。調大視窗是治標。」

### 🎯 面試官在看什麼
- ✅ 是否把「工具輸出」視為需要工程化處理的資料，而非直接塞。
- ✅ 知不知道長 context 的副作用（成本 / lost-in-the-middle / 延遲）。

---

## ❓ Q3 — 設計階層式記憶體（Tiered Memory）

### ✅ 期待回答

| 層級 | 載體 | 存什麼 | 生命週期 |
| :--- | :--- | :--- | :--- |
| **短期記憶** Session Cache | Redis / Memorystore | 當前對話狀態、近期輪次 | 分鐘～小時，TTL 過期 |
| **語義記憶** Semantic Summary | 結構化摘要欄位 | 「這個客戶偏好 / 限制 / 已解決問題」 | 跨 session 持久 |
| **長期記憶** Vector DB 歷史歸檔 | Vertex AI Vector Search | 歷史對話 embedding，可語義檢索 | 長期 |

**切換邏輯：** session 結束 → 把關鍵事實 **萃取成 semantic summary 落地** → 原始逐字稿 embedding 後歸檔到 Vector DB。下次同一客戶進來，先載入 semantic summary（便宜、準），需要更早細節時才去 Vector DB 撈。

**Deep Dive：「Vector DB 記憶會不會撈回不相關的舊事？」**
> 「會 —— 所以要 (1) 加 metadata filter（user_id / 時效）；(2) 對記憶檢索結果做 relevance gating，低於門檻不注入；(3) semantic summary 優先於 raw retrieval。」

### 🎯 面試官在看什麼
- ✅ 三層各自的 **載體、內容、生命週期** 是否清楚。
- ✅ 持久化與切換時機（session 結束萃取）。

---

## ❓ Q4 — Hardware-Level Context Caching

### ✅ 期待回答

System Prompt + 工具 Schema 又大又每次都一樣 → 啟用 **Vertex AI Context Caching**，把這段固定前綴的 KV 快取住，後續請求不必重算。

- **省什麼**：重複前綴的 input token 成本 + TTFT。
- **驅逐策略（Eviction）**：要平衡 —— 快取有 **最低計費 / TTL**，太短會 **冷啟動** 重算，太長會付閒置費。應依流量熱度設 TTL，對高頻 prefix 才開快取。

### 🎯 面試官在看什麼
- ✅ 知道 context caching 是針對 **固定大前綴**（system prompt / schema）。
- ✅ 能講出 **eviction 的取捨**（冷啟動 vs 最低計費懲罰）。

---

## 🗣️ 加分金句

1. *"Not all tokens are equal — pin the system prompt and policy, compact the rest."*
2. *"Compact is semantic compression; truncate just drops information."*
3. *"Never feed raw tool output back — project, summarize, or offload by reference."*
4. *"A bigger context window is treating the symptom: cost, lost-in-the-middle, and TTFT all get worse."*
5. *"Cache the fixed prefix with Context Caching, and tune eviction against cold-start vs minimum-billing."*

---

## 📋 RKK Feedback & 評級

| 表現 | Level |
| :--- | :---: |
| 只會 max-history truncate | L3 / L4 |
| Pinned + sliding window + rolling summary，工具輸出工程化 | **L4+** |
| 三層記憶 + 持久化切換 + context caching 取捨 + 主動講長 context 副作用 | **L5** |

---

## 🔮 下集預告 — EP04：RAG 進階（Hybrid Search × Re-ranking × RAG Triad）

> 為什麼 Vector Search 撈出的 Top 50 不準？Dense vs Sparse 怎麼融合？幻覺怎麼用 Groundedness 抓出來？

---

> ⚠️ 本系列為面試練習用模擬內容，技術細節以教學清晰為主，實際生產設計請以官方文件與你的合規團隊為準。
