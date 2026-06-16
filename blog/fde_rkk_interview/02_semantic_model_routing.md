---
series: Mock FDE RKK Interview
episode: 2
title: EP02 — Semantic Model Routing × Cost Engineering
lang: zh-Hant
covers:
  - 類別四：Semantic Model Routing
  - 類別四：LLM-as-a-Judge at Scale
---

# 🎙️ EP02 — Semantic Model Routing × Cost Engineering

> **本集主軸**：幫客戶砍掉 50% 成本的殺手鐧。
> 但真正的考點是 —— 你能不能把它從「**ML 分類問題**」升維成「**Cost Engineering / Production Optimization 問題**」。這正是 L4 與 L5 的分水嶺。

---

## 🎬 情境 (Scenario)

沿用 EP01 的銀行客戶。現在規模上來了：

- 每天 **3M requests/day**
- 目前 **所有 Query → Gemini 2.5 Pro**
- 每月成本 **$300K+**

**要求：** 成本降 **50%** ｜ 品質下降 **< 5%** ｜ **P95 latency < 3 秒**

請設計：Routing Architecture、Confidence Estimation、Fallback Strategy、Online Evaluation、如何證明 ROI。

---

## 🎯 本集 RKK 考點地圖

| JD 考點 | 在本集出現的形式 |
| :--- | :--- |
| Semantic Model Routing | 整集主軸 |
| Confidence / Entropy-based Routing | Q2 Runtime Confidence |
| LLM-as-a-Judge at Scale | Q4 Online Evaluation |
| Tradeoff Quantification | Q5 ROI |

**評分維度（本集重點）：** GenAI Depth 25% ｜ **Tradeoff Analysis 15%（本集最關鍵）** ｜ System Design 25%

---

## 🪤 最大的陷阱：把 Routing 當成 Simple vs Complex

大部分候選人會這樣分：

```
Request → Classifier → Simple → Small Model
                     → Complex → Gemini Pro
```

方向對，但面試官會立刻反問：「**什麼叫 Simple？**」

- 「今天 PTO 有幾天？」→ 簡單
- 「比較去年跟今年 AML policy 差異，並產生 email」→ 複雜
- 「幫我查詢客戶資料」→ ???

> 第三個 **不是 complexity 問題，而是 Tool Use 問題**。
> 所以 production router 不該分 Simple / Complex，而要 **按任務型態（Intent）** 分。

---

## ❓ Q1 — Routing Architecture

### ✅ 期待回答（L5 範本）

> 「在設計 router 之前，我會先看 **流量分布**，因為 semantic routing 只有在『大比例請求是低複雜度』時才划算。」

然後按 **Intent** 而非複雜度路由：

```
                ┌─ FAQ            → Gemma（地端自託管 / 便宜）
                │
Intent Router ──┼─ RAG            → Gemini Flash
                │
                ├─ Tool Calling   → Gemini Pro
                │
                ├─ Multi-step Agent → Gemini Pro
                │
                └─ Long Context   → Gemini Pro
```

> 這才是真正的 **Cost Optimization** —— 不同任務型態對模型能力的需求天差地別。

**Deep Dive：「你說的 confidence > 80%，這 80% 哪來的？」**
> 「不能拍腦袋。應該用 **offline evaluation + online A/B test** 經驗推導：掃 threshold 0.6 / 0.7 / 0.8 / 0.9，分別量 Cost、Latency、Answer Quality，找出 **Pareto Frontier**。」

### 🎯 面試官在看什麼
- ✅ 是否先問流量分布（顧問思維）。
- ✅ 是否用 Intent 而非 Simple/Complex。
- ✅ threshold 是否 **經驗推導** 而非硬編碼。

---

## ❓ Q2 — Confidence Estimation（這是最容易失分的地方）

### 🪤 一般候選人怎麼答

回 Precision / Recall / F1 —— **那是訓練分類模型的指標**，不是面試官問的。

### ✅ 期待回答（Runtime Confidence）

面試官問的是：使用者剛送進 `What is PTO policy?`，**router 在當下怎麼知道自己有 87% 把握？**

**方法 1：Router Logit（信心分數）**
```
FAQ 0.93 ｜ Agent 0.04 ｜ Reasoning 0.03  →  Confidence = 0.93
```

**方法 2：Entropy（Google 很愛考）**
```
FAQ 0.33 ｜ Agent 0.33 ｜ Reasoning 0.34  →  高熵 = 不確定 → 直接升級 Gemini Pro
```

> 這就是題目裡的 **Entropy-based Routing**：分布越平均（熵越高），代表 router 越沒把握，就用置信度熵值決定要不要 escalate。

### 🎯 面試官在看什麼
- ✅ 能不能區分 **訓練期指標（P/R/F1）** vs **推論期 runtime confidence（logit / entropy）**。
- ✅ 知不知道 entropy 是 production 常用的 escalation 訊號。

---

## ❓ Q3 — Fallback Strategy

### ✅ 期待回答（三級路由，不要一步到 Pro）

```
❌  Router Fail → Pro（一次跳到最貴）

✅  Gemma → (low confidence) → Gemini Flash → (still low) → Gemini Pro
    便宜    →                  中等          →             貴
```

> 逐級升級，每一級都先嘗試「夠用且更便宜」的模型，**還能再省很多錢**。

### 🎯 面試官在看什麼
- ✅ 是否設計 **cheap → medium → expensive 的漸進式 fallback**，而不是非黑即白。

---

## ❓ Q4 — Online Evaluation

### 🪤 一般候選人怎麼答

又回到 Precision / Recall / F1（同 Q2 的坑）。

### ✅ 期待回答（Production 線上指標）

| 指標 | 意義 |
| :--- | :--- |
| **Routing Accuracy** | 實際是否選到正確的模型 |
| **Escalation Rate** | 多少流量被升級到 Pro（太高表示 router 沒用） |
| **Cost per Request** | 平均成本（核心 KPI） |
| **P95 Latency** | 尾端延遲 |
| **User Satisfaction** | 👍/👎 thumb up/down |
| **LLM-as-a-Judge Score** | Groundedness / Answer Relevance |

**Deep Dive：LLM-as-a-Judge 怎麼控成本與消偏見？**
> 「用 **分層隨機抽樣（Stratified Sampling）** 抽樣評估控成本；用 **CoT + 打亂上下文順序** 消除裁判的 **Position Bias（位置偏見）**。」

### 🎯 面試官在看什麼
- ✅ 是否知道線上評估看的是 **業務 KPI（cost / escalation / latency / 滿意度）**，不是模型訓練指標。

---

## ❓ Q5 — 如何證明 ROI（本集最關鍵：主動量化）

### ✅ 期待回答（用數字說話）

| | 改造前 | 改造後 |
| :--- | :--- | :--- |
| 流量分配 | 100% Gemini Pro | 70% Gemma / 20% Flash / 10% Pro |
| 月成本 | **$300K** | **$120K** |
| 節省 | — | **60%** |
| 品質 | 100% | **97% retained** |

> 「原本 3M req/day 全打 Pro = $300K/月；routing 後 70/20/10 分配 ≈ $120K/月，**省 60%**，品質 **保留 97%**（掉 < 5% 達標）。」

**比較三組數據證明價值：**
1. **成本**（avg / median / total，前 vs 後）→ 證明省錢與 router 有效性
2. **處理時間** → 證明輕模型降低延遲
3. **品質分數**（前 vs 後）→ 證明品質僅小幅下降，但換來大幅省錢

### 🎯 面試官在看什麼
- ✅ **是否主動把 Tradeoff 量化成數字**（這是從 L4 跨到 L5 的唯一門檻）。
- ✅ 是否把它當 **Cost Engineering** 而非 ML 練習。

---

## 🗣️ 本集加分金句（Killer Phrases）

1. *"Before designing the router, I'd first understand the traffic distribution — semantic routing only pays off when a large percentage of requests are low-complexity."*
2. *"The real router is not Simple vs Complex, it's Intent-based: FAQ / RAG / Agent / Reasoning."*
3. *"I'd derive the threshold empirically via offline eval and online A/B testing, then pick the Pareto frontier."*
4. *"High entropy means the router is uncertain — escalate to Pro."*
5. *"70% Gemma, 20% Flash, 10% Pro → $300K to $120K, 60% savings, 97% quality retained."*

---

## 📋 RKK Feedback & 評級

| 表現 | Level |
| :--- | :---: |
| 只把它當 ML 分類問題（Simple/Complex + P/R/F1） | **L4 / L4+** |
| 用 Intent routing + entropy + 三級 fallback | **L4+** |
| **主動量化 ROI（$300K→$120K、60%、97%）+ Pareto threshold** | **L5** |

> **本集的唯一升級鑰匙：把每個設計都接上「成本多少、延遲多少、品質掉多少、如何驗證」。**

---

## 🔮 下集預告 — EP03：Context & Memory，對抗 Token 通膨

> 對話越拉越長，Token 瀑布式通膨，工具回傳的巨大 JSON 把 Context Window 撐爆。
> 你會怎麼設計 **Truncate / Compact** 與 **階層式記憶（Session Cache / Vector DB / Semantic Summary）**？

---

> ⚠️ 本系列為面試練習用模擬內容，技術細節以教學清晰為主，實際生產設計請以官方文件與你的合規團隊為準。
