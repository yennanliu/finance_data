---
series: Mock FDE RKK Interview
title: 系列總覽 — Google Cloud Forward Deployed Engineer (GenAI) 模擬面試
lang: zh-Hant
status: index
---

# 🧭 Mock FDE RKK Interview 系列總覽

> 模擬 **Google Cloud — Forward Deployed Engineer, Generative AI** 的 **RKK 面試**。
> 目標職缺 JD：[Forward Deployed Engineer, Generative AI, Google Cloud](https://www.google.com/about/careers/applications/jobs/results/114214983025205958-forward-deployed-engineer-generative-ai-google-cloud)

---

## 🎯 這個系列在練什麼？

RKK（Role-Knowledge / Architecture Reasoning）面試 **不考背書**，考的是：

1. **Discovery**：資訊不足時，你會先問什麼？
2. **End-to-End Design**：你能不能畫出一個能上線的架構？
3. **Deep Dive**：面試官往下追問時，你的設計撐不撐得住？
4. **Tradeoff**：你能不能 **主動量化** 成本／延遲／品質／風險？

> **FDE 與一般 AI Engineer 最大的差別**：
> 不是只用 Prompt 解決問題，而是會往 **Infrastructure Boundary（基礎設施邊界）** 思考，
> 並且 **每一個設計都主動說出**：為什麼選它、不選什麼、成本多少、延遲多少、風險是什麼、如何量化驗證。

---

## 📊 RKK 評分維度

| 維度 | 權重 | 白話說明 |
| :--- | :---: | :--- |
| Discovery & Clarification | 20% | 有沒有先問清楚需求，而不是急著設計 |
| System Design | 25% | End-to-End 架構是否合理、能否上線 |
| GenAI Depth | 25% | RAG / Agent / Routing 的細節深度 |
| Security & Reliability | 15% | 信任邊界、權限分離、容錯 |
| Tradeoff Analysis | 15% | 是否 **主動量化** 取捨 |

**Level 對照（Google 內部 leveling 概念）：**

- **L4**：方向正確、能設計出可運作系統。
- **L4+**：開始往基礎設施邊界思考，會講安全術語。
- **L5**：**主動量化 Tradeoff**，把問題從「ML 問題」升維成「Cost / Production Engineering 問題」。

---

## 🗺️ 系列路線圖（對應 JD 五大類別）

| 集數 | 主題 | 對應 JD 考點 | 狀態 |
| :---: | :--- | :--- | :---: |
| **EP01** | 銀行 GenAI Agent Platform — Discovery × 安全邊界 | 類別五 Discovery、類別二 Prompt Injection / Indirect Injection / Dual-Model / Sandbox / CMEK | ✅ |
| **EP02** | Semantic Model Routing — Cost Engineering | 類別四 Semantic Model Routing、LLM-as-a-Judge | ✅ |
| **EP03** | Context & Memory — 對抗 Token 通膨 | 類別一 Context Management、Tiered Memory、類別四 Context Caching | ✅ |
| **EP04** | RAG 進階 — Hybrid Search × Re-ranking × RAG Triad | 類別一 Hybrid Search / Re-ranking、類別四 RAG Triad | ✅ |
| **EP05** | 超大規模化 — Async / Backpressure / Idempotency / Fan-out / Blue-Green Indexing | 類別三 全部 | ✅ |
| **EP06** | State Machine & Deterministic Graph — 控制 Agent 反思迴圈 | 類別一 State Machine、LangGraph / ADK | ✅ |
| **EP07** | Production 排錯 — Top-Down Structured Troubleshooting | 類別五 排錯方法論、類別四 TTFT / Context Caching | ✅ |

> 每一集都是獨立可讀，但建議照順序，因為後面的情境會沿用前面的銀行客戶。

---

## 🧩 每一集的固定結構

1. **🎬 情境 (Scenario)** — 故意給資訊不足的真實案例
2. **🎯 本集 RKK 考點地圖** — 對應 JD 的哪些題目
3. **❓ 題目 (Question)**
4. **🪤 一般候選人怎麼答（陷阱）**
5. **✅ 期待回答（L5 範本）**
6. **🔍 Deep Dive 追問** — 面試官會往哪裡鑽
7. **🎯 面試官在看什麼（Signals）**
8. **🗣️ 加分金句（Killer Phrases）**
9. **📋 RKK Feedback & 評級**
10. **🔮 下集預告**

---

> ⚠️ 本系列為面試練習用模擬內容，技術細節以教學清晰為主，實際生產設計請以官方文件與你的合規團隊為準。
