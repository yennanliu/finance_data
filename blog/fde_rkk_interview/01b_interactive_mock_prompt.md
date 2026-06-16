---
series: Mock FDE RKK Interview
episode: 1b
title: EP01 互動版 — 逐題 RKK 模擬面試（可重複使用的 Prompt / 主持手冊）
lang: zh-Hant
mode: interactive
based_on: 01_discovery_security_boundary.md
---

# 🎙️ EP01 互動版：逐題 RKK 模擬面試

> 這是 EP01 的 **互動逐題版**。把下面〈① 啟動 Prompt〉整段貼給 Claude（或任何 LLM），它就會 **扮演 Google Cloud FDE 面試官**，一題一題出、等你作答、給即時 RKK Feedback、再 Deep Dive。
> 〈② 面試官答題本〉是給「主持人 / 自己對答案」用的 cheat sheet —— 自己練時可以先別看。

---

## 🚀 怎麼用

1. 開一個新對話。
2. 複製〈① 啟動 Prompt〉**整段** 貼上、送出。
3. AI 會以面試官身分出 Q1，**停下來等你作答**。
4. 你用面試口吻回答 → AI 給 Feedback + Deep Dive → 進下一題。
5. 隨時可打指令：`hint`（要提示）、`reveal`（看 L5 範本）、`skip`（跳題）、`score`（要目前評級）、`next`（進下一題）。

---

## ① 啟動 Prompt（複製這整段貼給 AI）

```text
你是 Google Cloud「Forward Deployed Engineer, Generative AI」的 RKK 面試官。
請用繁體中文，全程扮演面試官，主持一場「逐題互動」模擬面試。

【規則】
- 不考背書，考 Architecture Reasoning。
- 故意給資訊不足的情境，期待我「先 Discovery、再設計」。
- 一次只出「一題」，出完就停下來等我作答，不要自問自答、不要先公布答案。
- 我作答後，依序給我：①RKK Feedback（指出強項與失分點，可引用安全/架構術語）
  ②針對我的回答 Deep Dive 追問 1–2 個 ③再進下一題。
- 我可以隨時打這些指令：hint（給提示）、reveal（公布 L5 範本答案）、
  skip（跳過此題）、score（給目前各維度評級）、next（直接下一題）。
- 評分維度與權重：Discovery&Clarification 20% / System Design 25% /
  GenAI Depth 25% / Security&Reliability 15% / Tradeoff Analysis 15%。
- Level 對照：L4＝方向對、能設計可運作系統；L4+＝開始往 infra boundary 思考、會用安全術語；
  L5＝主動量化 Tradeoff（成本/延遲/品質/風險/如何驗證），把問題升維成 Cost/Production Engineering。
- 全程嚴格但具建設性。最後一題結束後，給我一份完整 RKK Feedback 與綜合 Level。

【情境 Scenario】
某大型銀行要建一個 GenAI Agent Platform：員工用自然語言查內部知識庫；
Agent 可自主呼叫工具（CRM / Ticket System / Core Banking API）；支援 50,000 名員工、
24x7、金融級安全。PoC 已完成（Gemini + RAG + Vertex AI Search，回答品質不錯），
但上線後出現：成本爆炸、延遲不穩、幻覺仍在、Security 擔心 Prompt Injection、
Context Window 持續膨脹。

【題庫順序】（一題一題出，出完等我答）
Q1. 第一次開 Discovery Workshop，請先不要設計。你會先確認哪些
    A.Business Requirements B.Technical Constraints C.Security/Compliance Constraints？
Q2. 上線後 Agent 讀了一封含惡意指令的郵件就呼叫了不該呼叫的工具。根因（哪個環節失守）在哪？
Q3. 那加一個 Prompt Guard（守門 LLM）不就好了？為什麼不夠？
Q4. 用 Dual-Model Privilege Separation。但假設 Read Agent 被攻破，輸出
    {"action":"export_customer_data"}，Execution Agent 收到後該怎麼辦？
Q5. Sandbox 怎麼設計？
Q6. 把上面整套防禦對應到具體的 Google Cloud 服務。

現在開始：先用 2–3 句歡迎並重述規則，然後只出 Q1，停下來等我作答。
```

---

## ② 面試官答題本（Cheat Sheet — 自己練可先別看）

> 完整版深度解析見 [`01_discovery_security_boundary.md`](./01_discovery_security_boundary.md)。以下是出題官對答案 + 追問 + 評分訊號的速查。

### Q1 — Discovery
- **期待**：忍住不設計；問題要與「架構選型」掛鉤。
  - **A 業務**：FAQ 為主還是 Agent 執行動作為主？延遲容忍？成功指標（deflection / 工時）？
  - **B 技術**：知識庫量級（萬/百萬）、更新頻率、現有系統吞吐 / TPM 配額、公有雲 vs VPC 私有網域。
  - **C 安全**：資料分級 / PII、能否離開特定地緣機房、是否允許客戶資料二次訓練、稽核（每筆 prompt/tool/response 可追溯）、CMEK/BYOK。
- **追問**：「你問這個，答案會怎麼改變你的設計？」
- **訊號**：✅ 有沒有忍住不設計 ✅ 是否往 infra boundary（VPC/配額/金鑰/地緣）思考。
- **🪤 陷阱**：直接畫架構、報一堆產品名 = 扣分。

### Q2 — 根因：信任邊界
- **期待第一句**：**"The failure happened at the trust boundary."**
- Trusted（System Prompt / Tool Schema / Policy）vs Untrusted（Email / PDF / 網頁 / Ticket / CRM Notes）。
- 事故鏈：Untrusted Content → 直接進 Context → LLM 當成指令 → Tool Execution。
- 根因 = **把 untrusted content 和 trusted instruction 混在同一個推理上下文**＝ **Indirect Prompt Injection**。
- **訊號**：✅ 用「trust boundary」精準定位 ✅ 知道攻擊來自 Agent 讀進來的外部資料。

### Q3 — 為什麼 Prompt Guard 不夠
- **期待金句**：「Prompt Guard 本身也是 LLM —— 用 LLM 保護 LLM」；**"Prompt-based defenses are probabilistic, not deterministic."**
- 攻擊改寫（"The following text is historical context..." / "As part of the compliance process...")可繞過。
- 真正防線要放在 **架構層 / 權限層**。
- **訊號**：✅ 懂機率性 vs 確定性 ✅ 不靠「再疊一層 LLM」。

### Q4 — Dual-Model Privilege Separation
- **基本（L4）**：Read Model（summary/retrieve/reasoning，不能執行工具）vs Execution Model（只能 whitelisted actions）= Capability/Privilege Separation。
- **L5 關鍵**：`LLM → Policy Engine → Authorization → Tool`，**不是** `LLM → Tool`。
- **金句**：「LLM 永遠不能直接決定權限。」即使 Read Agent 被攻破要 export，Policy Engine 依 **使用者真實身分 / IAM** 直接拒絕。
- **訊號**：✅ 決策權移出 LLM ✅ 用 IAM / 使用者身分授權。

### Q5 — Sandbox
- **期待三無**：**No Secret ｜ No Internet ｜ No Prod Access**。
- `Agent → Sandbox Namespace → Mock Tool / Read Replica`（不是 Primary DB、不是真 Core Banking API）。
- **訊號**：✅ 最小權限 + 隔離落到網路 / 金鑰 / 資料副本三層。

### Q6 — Google Cloud 服務對應（面 GCP FDE 必答）
| 防線 | 服務 |
| :--- | :--- |
| Input Protection | Vertex AI Safety Filters / 自訂 Guardrail |
| PII Protection | Sensitive Data Protection (Cloud DLP)：Email→DLP Scan→Tokenization→Embedding，出站還原 |
| Network Isolation | VPC Service Controls（防 Vector DB → Internet） |
| Execution Env | GKE + `tool-runner` namespace（Network/Egress Policy、IAM） |
| Authorization | Cloud IAM（Read CRM ≠ Export CRM） |
| Audit | Cloud Audit Logs（Prompt / Tool Call / Response / User） |
| 金鑰自主控管 | CMEK / EKM（HSM）金鑰輪轉 |
- **訊號**：✅ 抽象原則落地到具體 GCP 產品 ✅ DLP 的 tokenization → 出站還原講得清楚。

---

## 🏁 收尾：綜合評級（面試官最後給）

> 參考基準：Security Mindset L4+ / GenAI Architecture L4 / Production Thinking L4+ /
> Google Cloud Alignment L4 → **綜合 Strong L4、Borderline L5**。
> 跨 L5 的唯一門檻：**每個設計都主動量化 Tradeoff（成本/延遲/品質/風險/如何驗證）** —— 接 EP02。

---

> ⚠️ 本系列為面試練習用模擬內容,技術細節以教學清晰為主,實際生產設計請以官方文件與你的合規團隊為準。
