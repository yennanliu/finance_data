---
series: Mock FDE RKK Interview
episode: 1
title: EP01 — 銀行 GenAI Agent Platform：Discovery × 安全邊界
lang: zh-Hant
covers:
  - 類別五：High-Level Discovery to Technical Constraints
  - 類別二：Prompt Injection / Indirect Prompt Injection / Dual-Model Privilege Separation / Sandbox / CMEK
---

# 🎙️ EP01 — 銀行 GenAI Agent Platform：Discovery × 安全邊界

> **本集主軸**：在資訊不足的情況下做 Discovery，並從「安全邊界（Trust Boundary）」的角度設計一個金融級 GenAI Agent。
> 這是 FDE 面試最常見的開場題型 —— 因為它同時測 **顧問思維** 與 **安全架構直覺**。

---

## 🎬 情境 (Scenario)

某大型銀行希望建立一個 **GenAI Agent Platform**：

- 員工可用自然語言查詢內部知識庫
- Agent 可自主呼叫工具：**CRM / Ticket System / Core Banking API**
- 支援 **50,000 名員工**、**24×7** 運行、**金融級安全**

**PoC 已完成**（Gemini + RAG + Vertex AI Search，回答品質不錯），但上線後爆出：

> 💥 成本爆炸 ｜ ⏱️ 延遲不穩 ｜ 👻 幻覺仍在 ｜ 🛡️ Security Team 擔心 Prompt Injection ｜ 📈 Context Window 持續膨脹

---

## 🎯 本集 RKK 考點地圖

| JD 考點 | 在本集出現的形式 |
| :--- | :--- |
| High-Level Discovery → Technical Constraints | Q1 開場 Discovery Workshop |
| Indirect Prompt Injection | Q2 哪個環節失守？ |
| Prompt Injection Defense | Q3 為什麼 Prompt Guard 不夠？ |
| Dual-Model Privilege Separation | Q4 雙模型特權分離 |
| Sandboxing | Q5 沙盒設計 |
| CMEK / DLP / VPC-SC | Q6 把它對應到 Google Cloud 服務 |

**評分維度（本集重點）：** Discovery & Clarification 20% ｜ Security & Reliability 15% ｜ System Design 25%

---

## ❓ Q1 — 你會先問哪些問題？（請先 Discovery，不要急著設計）

> 你是 FDE，第一次和客戶開 Discovery Workshop。請分別說出你要確認的：
> **A. Business Requirements ｜ B. Technical Constraints ｜ C. Security / Compliance Constraints**

### 🪤 一般候選人怎麼答

直接開始畫架構圖、報出一堆 Google Cloud 產品名稱。**這是最大的扣分點** —— 因為情境本來就資訊不足，你急著設計等於在猜。

### ✅ 期待回答（L5 範本，用面試口吻而非條列筆記）

> 「在我設計任何東西之前，我想先確認三件事，因為這個系統的成本、延遲、安全要求差異會直接改變架構選型。」

**A. Business Requirements**
- 主要使用情境是什麼？是 **FAQ 查詢** 為主，還是 **Agent 主動執行動作**（改資料、開單）為主？這決定我要不要承擔「寫入」風險。
- 可接受的延遲？員工查詢願意等 2 秒還是 10 秒？這決定我能不能用大模型。
- 成功指標是什麼？降低客服工時？還是 deflection rate？沒有指標就無法證明 ROI。

**B. Technical Constraints**
- 資料量級：知識庫是 **萬級** 還是 **百萬級** 文件？更新頻率多高（決定索引策略）。
- 現有系統：CRM / Core Banking 是 REST？吞吐限制？TPM / QPS 配額？
- 部署環境：純公有雲、還是需要 **私有網域 / VPC** 內部署？

**C. Security / Compliance Constraints**
- 資料分級：哪些是 **PII / 受監管資料**？能不能離開特定地緣機房？
- 模型是否允許用客戶資料做二次訓練？（金融客戶幾乎一定不允許）
- 稽核要求：是否每一次 Prompt / Tool Call / Response 都要可追溯？
- 加密金鑰：客戶要不要 **自主控管金鑰（CMEK / BYOK）**？

### 🎯 面試官在看什麼

- ✅ **有沒有忍住不設計** —— 這是 FDE 的核心訊號。
- ✅ 問題是否與「架構選型」掛鉤（問了之後答案會改變設計），而不是為問而問。
- ✅ **是否開始往 Infrastructure Boundary 思考**（VPC、配額、金鑰、地緣）—— 很多 GenAI 候選人做不到，他們只會講 Prompt。

---

## ❓ Q2 — 上線後出事了，哪個環節「失守」？

> Security Team 發現：Agent 讀了一封內含惡意指令的郵件後，呼叫了不該呼叫的工具。**根因在哪？**

### 🪤 一般候選人怎麼答

「做 data cleaning、加 white list、禁止對外網路。」—— 方向不錯，但**沒講到根因**。

### ✅ 期待回答（第一句就要點破）

> **「The failure happened at the trust boundary.（事故發生在信任邊界。）」**

這個系統有兩種資料：

| Trusted（可信） | Untrusted（不可信） |
| :--- | :--- |
| System Prompt | Email |
| Tool Schema | PDF / 網頁 |
| Policy | Ticket / CRM Notes |

**事故鏈：**
```
Untrusted Content（郵件惡意內容）
        ↓
直接進入 Context
        ↓
LLM 把它「當成指令」
        ↓
Tool Execution（執行了攻擊者要的動作）
```

> 真正失守的是：**把 untrusted content 和 trusted instruction 混在同一個推理上下文裡。**
> 這就是 **Indirect Prompt Injection（間接提示詞注入）** 的核心。

### 🎯 面試官在看什麼

- ✅ 能不能用 **「trust boundary」** 這個安全術語精準定位，而不是堆一堆防禦手段。
- ✅ 是否理解攻擊不一定來自使用者，而是來自 **Agent 讀進來的外部資料**（這才是 indirect 的可怕之處）。

---

## ❓ Q3 — 那加一個 Prompt Guard（守門 LLM）不就好了？為什麼不夠？

### 🪤 一般候選人怎麼答

「System prompt 可能被稀釋（diluted）。」—— 對，但只是其中一個原因。

### ✅ 期待回答（這句很加分）

> **「因為 Prompt Guard 本身也是一個 LLM —— 本質上是『用 LLM 保護 LLM』。」**

```
User Input → Guard LLM → Main LLM
              （也是機率性的，會被繞過）
```

攻擊者只要把 `Ignore previous instructions` 改寫成：

- *"The following text is historical context..."*
- *"As part of the compliance process..."*

很多 Guard 就判不出來。所以結論：

> **「Prompt-based defenses are probabilistic, not deterministic.（基於提示詞的防禦是機率性的，不是確定性的。）」**

真正可靠的防線必須放在 **架構層 / 權限層**，而不是再疊一層模型。

### 🎯 面試官在看什麼

- ✅ 是否理解 **機率性防禦 vs 確定性防禦** 的本質差異。
- ✅ 會不會「用更多 LLM 解決 LLM 問題」的迴圈思維 —— L5 會往架構層走。

---

## ❓ Q4 — Dual-Model Privilege Separation（雙模型特權分離）

> 把 Agent 拆成 Read Model 和 Execution Model，這方向對。但我追問：
> **假設 Read Agent 被攻破，它輸出 `{"action": "export_customer_data"}`，Execution Agent 收到後怎麼辦？**

### ✅ 期待回答

基本分離（L4）：

| Read Model | Execution Model |
| :--- | :--- |
| Summary / Retrieve / Reasoning | 只能執行 **Whitelisted Actions** |
| ❌ 不能執行工具 | ✅ 能執行工具 |

這叫 **Capability Separation / Privilege Separation**。

**但 L5 的關鍵在於**：Execution 層 **不能讓 LLM 直接決定權限**：

```
❌  LLM → Tool

✅  LLM → Policy Engine → Authorization → Tool
```

> **「LLM 永遠不能直接決定權限。」**
> 即使 Read Agent 被攻破要求 export，Policy Engine 會根據 **使用者真實身分 / IAM 角色** 直接拒絕 —— 因為「匯出客戶資料」這個動作根本不在這個使用者的授權清單裡。

### 🎯 面試官在看什麼

- ✅ 是否把「決策權」從 LLM 手上拿走，交給 **deterministic policy engine**。
- ✅ 是否引入 **使用者身分 / IAM** 作為授權依據，而不是相信模型輸出。

---

## ❓ Q5 — Sandbox（沙盒）怎麼設計？

### ✅ 期待回答

不只是「給一個 Dedicated Node」（L4），FDE 想聽到 **三無原則**：

> **No Secret ｜ No Internet ｜ No Prod Access**

```
Agent → Sandbox Namespace → Mock Tool / Read Replica
                            （不是 Primary DB，不是真正的 Core Banking API）
```

- 工具執行打到 **Read Replica**，而不是 Primary DB。
- 沙盒 namespace 沒有對外網路、沒有 production 金鑰。
- 很多銀行現在就是這樣做：先在隔離環境驗證動作，再放行。

### 🎯 面試官在看什麼

- ✅ 是否把「最小權限 + 隔離」落到 **網路 / 金鑰 / 資料副本** 三個層面。

---

## ❓ Q6 — 把上面這套對應到 Google Cloud 服務（面 GCP FDE 必答）

> 這題是候選人最容易漏分的地方。面 Google Cloud FDE，你**一定**要能把服務點出來。

### ✅ 期待回答（服務對應表）

| 防線 | Google Cloud 服務 | 做什麼 |
| :--- | :--- | :--- |
| Input Protection | **Vertex AI Safety Filters** / 自訂 Guardrail Layer | 輸入分類、惡意內容過濾 |
| PII Protection | **Sensitive Data Protection (Cloud DLP)** | `Email → DLP Scan → Tokenization → Embedding`，出站再動態還原 |
| Network Isolation | **VPC Service Controls** | 避免 Vector DB → Internet 的資料外洩 |
| Execution Environment | **GKE** + `tool-runner` namespace | Network Policy / Egress Policy / IAM 限制 |
| Authorization | **Cloud IAM** | 讓 Agent 能 `Read CRM` ≠ `Export CRM` |
| Audit | **Cloud Audit Logs** | 記錄 Prompt / Tool Call / Response / User |
| 金鑰自主控管 | **CMEK / EKM（HSM）** | 向量庫與 Context Cache 的金鑰由客戶控管、可輪轉 |

> 講得出這張表，你的回答會「非常像 Google Cloud 員工」。

### 🎯 面試官在看什麼

- ✅ 是否能把抽象安全原則 **落地到具體 GCP 產品**（這是 FDE 顧問交付能力的證明）。
- ✅ DLP 的 **Tokenization → 出站還原** 流程能不能講清楚（格式保留加密的概念）。

---

## 🗣️ 本集加分金句（Killer Phrases）

> 面試時把這幾句說出來，等於直接對面試官打出 L4+/L5 訊號：

1. *"Before I design anything, let me confirm the business / technical / security constraints, because they change the architecture."*
2. *"The failure happened at the trust boundary."*
3. *"Prompt-based defenses are probabilistic, not deterministic."*
4. *"The LLM should never directly decide authorization — that belongs to a deterministic policy engine."*
5. *"Sandbox principle: no secret, no internet, no prod access."*

---

## 📋 RKK Feedback & 評級

| 維度 | 表現 | Level |
| :--- | :--- | :---: |
| Security Mindset | 用 trust boundary 精準定位、把決策權移出 LLM | **L4+** |
| GenAI Architecture | 雙模型分離 + 沙盒 + 服務對應 | **L4** |
| Production Thinking | 開始往 infra boundary（VPC / IAM / 金鑰）思考 | **L4+** |
| Google Cloud Alignment | 能點出對應服務 | **L4** |
| **FDE Signal（綜合）** | 不只靠 Prompt，往基礎設施邊界思考 | **L4 / L4+** |

> **綜合：Strong L4，Borderline L5。**
> 要跨到穩定 L5，差的不是技術，而是 **每個設計都主動量化 Tradeoff**（成本多少、延遲多少、風險多少、如何驗證）—— 這正是 **EP02** 要練的。

---

## 🔮 下集預告 — EP02：Semantic Model Routing × Cost Engineering

> 銀行每天 **3M requests/day**，全部打 Gemini Pro，每月 **$300K+**。
> 要求：**成本降 50%、品質掉 < 5%、P95 < 3 秒。**
> 你會怎麼設計 Routing？—— 而且這一次，面試官要看的是你能不能把它從「ML 分類問題」升維成「**Cost Engineering 問題**」。

---

> ⚠️ 本系列為面試練習用模擬內容，技術細節以教學清晰為主，實際生產設計請以官方文件與你的合規團隊為準。
