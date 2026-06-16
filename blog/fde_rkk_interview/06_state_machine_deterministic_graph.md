---
series: Mock FDE RKK Interview
episode: 6
title: EP06 — State Machine & Deterministic Graph：收住 Agent 的反思迴圈
lang: zh-Hant
covers:
  - 類別一：State Machine & Deterministic Graph Workflows（LangGraph / Google ADK 2.0）
---

# 🎙️ EP06 — State Machine & Deterministic Graph：收住 Agent 的反思迴圈

> **本集主軸**：把控制權全丟給 LLM 的 Agent，看起來很聰明，但 production 會 **不收斂、不可預測、不可稽核**。
> 考點是：用 **確定性圖結構（DAG）** 把「**控制流**」從 LLM 手上拿回來，只讓 LLM 做「**判斷**」。

---

## 🎬 情境 (Scenario)

銀行用 ReAct-style Agent 處理「爭議款調查」流程，上線後：

- Agent 進入 **反思迴圈（Reflection Loop）** 不收斂，同一步反覆「我再想想」燒了 40 次 LLM call
- 流程不可預測：同樣的請求，有時呼叫 CRM，有時不呼叫
- 合規團隊問「這個決策走過哪些步驟？」—— **無法重現、無法稽核**

請重新設計 Agent 的控制流。

---

## 🎯 本集 RKK 考點地圖

| JD 考點 | 出現形式 |
| :--- | :--- |
| 為什麼不能把控制權全丟給 LLM | Q1 |
| DAG / State Machine 設計（LangGraph / ADK 2.0） | Q2 |
| Reflection Loop 收斂控制 | Q3 |

**評分維度：** System Design 25% ｜ GenAI Depth 25% ｜ Reliability 15%

---

## ❓ Q1 — 為什麼不能把控制權全丟給 LLM？

### ✅ 期待回答

> 「因為 LLM 是 **機率性** 的。讓它同時負責『**判斷**』和『**控制流程**』，會得到一個 **不可預測、不收斂、不可稽核** 的系統 —— 這在金融場景不可接受。」

要區分兩件事：

| | 誰負責 |
| :--- | :--- |
| **控制流（要走哪一步、迴圈幾次、何時停）** | **確定性的 Graph / State Machine** |
| **判斷（這段文字算不算爭議？該用哪個工具？）** | LLM（節點內） |

> 一句話：**LLM 決定「做什麼」，Graph 決定「流程怎麼走」。**（呼應 EP01：權限決策也不交給 LLM。）

### 🎯 面試官在看什麼
- ✅ 能不能把 **「判斷」與「控制流」分離**。
- ✅ 是否從可稽核 / 可重現的 production 角度論證。

---

## ❓ Q2 — 怎麼用 DAG / State Machine 設計？

### ✅ 期待回答（LangGraph / Google ADK 2.0）

把流程定義成 **有向圖**，節點是步驟、邊是 **明確的轉移條件**：

```
[接收爭議] → [分類 (LLM)] ──disputed──> [查 CRM] → [查 Core Banking] → [生成處理建議 (LLM)]
                          └─not disputed─> [回覆非爭議模板] → END
                                                                       │
                              [人工審核閘 (Human-in-the-loop)] <───────┘（金額 > 門檻時）
```

- **狀態（State）** 在節點間顯式傳遞（可序列化）→ 天然支援 EP05 的 **checkpoint / 斷點續傳**。
- **條件邊**由程式（或 LLM 的結構化輸出）決定，但 **轉移規則是確定的**。
- 高風險動作插入 **Human-in-the-loop 閘門**。

**Deep Dive：「LLM 還是要決定下一步，那不還是 LLM 控制？」**
> 「差別在於：LLM 只輸出一個 **受限的列舉值**（如 `route ∈ {disputed, not_disputed, need_more_info}`），Graph 根據這個列舉值走 **預先定義好** 的邊。LLM 不能發明新路徑、不能自己決定迴圈次數。」

### 🎯 面試官在看什麼
- ✅ 狀態顯式化、轉移條件明確、與 checkpoint 串起來。
- ✅ LLM 輸出被 **約束成列舉**，而非自由控制。

---

## ❓ Q3 — 反思迴圈不收斂、燒了 40 次 call，怎麼收住？

### ✅ 期待回答

確定性圖天生能限制迴圈：

- **硬上限（max iterations）**：reflection 迴圈設最大次數，到頂強制走「升級人工 / 回傳目前最佳結果」邊。
- **收斂判據**：每輪要有可量測的進展（如 critic 分數提升），連續 N 輪沒進步就停 —— 而不是讓 LLM 自己無限「我再想想」。
- **預算上限**：整條流程設 token / 成本 / 時間 budget，超過就降級（呼應 EP02 / EP05）。

**Deep Dive：「為什麼 ReAct 自由迴圈在 demo 沒事、production 出事？」**
> 「demo 輸入乾淨、樣本少；production 有對抗性 / 模糊輸入，會誘發模型反覆自我懷疑。沒有確定性護欄，迴圈次數和成本都不可控。」

### 🎯 面試官在看什麼
- ✅ 用 **圖結構 + 硬上限 + 收斂判據 + budget** 收斂迴圈。
- ✅ 理解 demo 與 production 的分布差異。

---

## 🗣️ 加分金句

1. *"The LLM decides what to do; the graph decides how the flow goes."*
2. *"Don't give the LLM control flow — it's probabilistic, so you get an unpredictable, non-converging, unauditable system."*
3. *"Constrain the LLM's output to an enum; the graph routes on predefined edges."*
4. *"Explicit serializable state is what makes checkpointing and replay possible."*
5. *"Bound the reflection loop with max iterations, a convergence criterion, and a budget."*

---

## 📋 RKK Feedback & 評級

| 表現 | Level |
| :--- | :---: |
| 只會堆 ReAct / 自由 agent | L3 / L4 |
| 用 LangGraph/ADK 定義 DAG、條件邊、max iterations | **L4+** |
| 判斷 vs 控制流分離 + 列舉約束 + checkpoint + budget + human-in-the-loop | **L5** |

---

## 🔮 下集預告 — EP07（系列收尾）：Production 排錯

> 客戶說「Agent 很慢 / 卡住了」，你只有一句模糊抱怨。
> 怎麼 **自上而下** 分層排查：前端接入層 → 中台狀態層 → 下游工具層 → 模型配額層（429）？並用 Cloud Trace 定位。

---

> ⚠️ 本系列為面試練習用模擬內容，技術細節以教學清晰為主，實際生產設計請以官方文件與你的合規團隊為準。
