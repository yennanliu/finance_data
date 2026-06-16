---
series: Mock FDE RKK Interview
episode: 7
title: EP07 — Production 排錯：Top-Down Structured Troubleshooting（系列收尾）
lang: zh-Hant
covers:
  - 類別五：Top-Down Structured Troubleshooting
  - 類別四：TTFT & Tokens/sec Optimization
  - 類別四：Hardware-Level Context Caching
---

# 🎙️ EP07 — Production 排錯：Top-Down Structured Troubleshooting

> **本集主軸**：FDE 是「Forward Deployed」—— 客戶端真的會崩，你會被丟一句模糊的「**系統很慢 / Agent 卡住了**」。
> 考點是 **結構化排錯的紀律**：能不能把一句抱怨拆成清楚的分層，逐層用 telemetry 定位，而不是亂猜。

---

## 🎬 情境 (Scenario)

銀行打來：「你們的 Agent **今天下午開始很慢，有時候直接卡死**。」

你手上只有這句話。沒有 error code、沒有 repro、沒有時間範圍細節。請開始排查。

---

## 🎯 本集 RKK 考點地圖

| JD 考點 | 出現形式 |
| :--- | :--- |
| Top-Down Structured Troubleshooting | Q1、Q2 |
| TTFT & Tokens/sec 優化 | Q3 |
| Context Caching（冷啟動） | Q3 Deep Dive |

**評分維度：** Consulting & Troubleshooting（類別五）｜ Reliability 15% ｜ Tradeoff 15%

> 本集精神對應 Google 經典文化讀物《Life in App Engine Production》—— **先分層、再下鑽、用數據說話**。

---

## ❓ Q1 — 收到「很慢 / 卡死」，第一步做什麼？

### 🪤 一般候選人怎麼答
立刻猜「應該是模型太慢」就去調 prompt / 換模型 —— **沒有先界定問題就動手**，最大扣分。

### ✅ 期待回答（先 Clarify，再分層）

> 「在動任何東西之前，我先 **量化問題範圍**：」

- **何時開始**？對齊一個 **變更事件**（部署 / 流量尖峰 / 下游維護）。
- **「慢」是多慢**？P50 還是 P95 變差？是 **整體變慢** 還是 **長尾卡死**（兩者根因不同）。
- **影響範圍**：全部使用者，還是特定租戶 / 特定查詢型態？

然後 **自上而下分層**，把系統切成四層逐層排查：

```
① 前端接入層    （API Gateway / 連線池 / 負載平衡）
② 中台狀態層    （Pub/Sub 佇列堆積？Redis？Checkpointer？）
③ 下游工具 API 層（CRM / Core Banking 變慢或逾時？）
④ 模型配額層    （Gemini TPM 429？TTFT 變差？）
```

### 🎯 面試官在看什麼
- ✅ **先界定問題範圍**（P50 vs P95、整體 vs 長尾）再動手。
- ✅ 有清楚的 **分層心智模型**，不是隨機猜。

---

## ❓ Q2 — 怎麼逐層定位？用什麼工具？

### ✅ 期待回答（用 telemetry 下鑽）

> 「用 **分散式追蹤（Cloud Trace）** 拉一條慢請求的完整 span，看時間花在哪一層 —— 這是最快的定位法。」

| 層 | 看什麼指標 / 訊號 | 典型根因 |
| :--- | :--- | :--- |
| ① 前端 | 連線池使用率、佇列等待 | 同步阻塞 → 連線池耗盡（呼應 EP05 Q1） |
| ② 中台 | Pub/Sub backlog、Redis 延遲、checkpointer 寫入延遲 | 消費者跟不上 → 佇列堆積 |
| ③ 下游工具 | 各 API 的 P95、逾時率 | 某個地端 API 變慢 → 拖垮 fan-out（EP05 Q4） |
| ④ 模型 | TTFT、tokens/sec、**429 比率** | TPM 配額用盡或 context 膨脹 |

**Deep Dive：「Trace 顯示 80% 時間花在等一個下游 API，怎麼辦？」**
> 「短期：對它套 **hedged request + deadline + 局部降級**（EP05 Q4）；中期：和客戶確認該 API 的 SLA 與是否能加 read replica；同時把這層的 P95 設告警，避免再被動接電話。」

### 🎯 面試官在看什麼
- ✅ 直接用 **Cloud Trace span** 定位熱點，而非靠猜。
- ✅ 每一層都有 **對應的可觀測指標**。
- ✅ 排完能 **接回前面幾集的解法**（系統性思維）。

---

## ❓ Q3 — 如果定位到「模型這層 TTFT 太慢」，怎麼優化？

### ✅ 期待回答（TTFT & 吞吐量）

**TTFT（首字延遲）** 與 **Tokens/sec（吞吐）** 是影響體感最關鍵的兩個指標。手段：

| 手段 | 改善什麼 |
| :--- | :--- |
| **Streaming（SSE）** | 讓使用者更早看到首字，體感 TTFT 大幅下降 |
| **Quantization（量化）** | 自託管模型推理更快、更省（呼應 EP02 的 Gemma） |
| **Continuous Batching** | 提升 GPU 利用率與整體吞吐 |
| **PagedAttention** | 高效管理 KV cache，提升吞吐 |
| **縮短 input**｜prompt / context | input 越短 TTFT 越好（呼應 EP03 context 修剪） |

**Deep Dive：「TTFT 偶爾爆高，但平均很好，為什麼？」**
> 「很可能是 **Context Caching 冷啟動**：快取被驅逐後第一筆請求要重算大前綴的 KV，TTFT 就尖刺。對策是依流量熱度調 eviction TTL，對高頻 prefix 保溫（呼應 EP03 Q4）。」

### 🎯 面試官在看什麼
- ✅ 知道 TTFT vs throughput 是 **兩個不同問題**，手段不同。
- ✅ 能把 **冷啟動尖刺** 連到 context caching 的 eviction。

---

## 🗣️ 加分金句

1. *"Before I touch anything, I quantify the blast radius — P50 vs P95, all users vs one tenant."*
2. *"Overall-slow and tail-stall have different root causes."*
3. *"I'd pull a Cloud Trace span first and see which layer owns the latency, instead of guessing."*
4. *"Front-end / state / downstream-tool / model-quota — four layers, each with its own metric."*
5. *"Spiky TTFT with a good average usually means context-cache cold starts."*

---

## 📋 RKK Feedback & 評級

| 表現 | Level |
| :--- | :---: |
| 沒界定範圍就直接調 prompt / 換模型 | L3 |
| 有分層、會看 trace、知道 TTFT 手段 | **L4+** |
| 先量化範圍 → trace 下鑽 → 分層歸因 → 接回系統性解法 + 設告警 | **L5** |

---

## 🏁 系列總結 — 從 L4 到 L5 的那條線

走完七集，回頭看 FDE RKK 想要的訊號其實高度一致：

1. **先 Discovery，忍住不設計**（EP01）
2. **把決策權從 LLM 手上拿走** —— 權限給 policy engine、控制流給 graph（EP01 / EP06）
3. **安全放在架構層而非 prompt 層**（EP01：trust boundary、probabilistic vs deterministic）
4. **把問題升維成 Cost / Production Engineering，並主動量化 Tradeoff**（EP02 / 全系列）
5. **分散式容錯直覺**：idempotency、checkpoint、hedging、blue-green（EP05）
6. **結構化排錯**：先分層、用數據、不亂猜（EP07）

> **L4 → L5 的唯一那條線**：每講一個設計，都主動補上 ——
> **「為什麼選它 / 不選什麼 / 成本多少 / 延遲多少 / 風險是什麼 / 如何量化驗證。」**
>
> 這就是 Google Cloud FDE 與一般 AI Engineer 最明顯的差別。

---

> ⚠️ 本系列為面試練習用模擬內容，技術細節以教學清晰為主，實際生產設計請以官方文件與你的合規團隊為準。
