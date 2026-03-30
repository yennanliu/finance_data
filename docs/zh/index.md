---
title: 財經資料研究中心
description: AI 驅動的投資研究、SEC 文件與基本面分析
---

# 財經資料研究中心

<div class="grid cards" markdown>

-   :material-chart-line:{ .lg .middle } **分析報告**

    ---
    美股的 AI 生成基本面與內部交易報告
    提供繁體中文及豐富的視覺化圖表。

    [:octicons-arrow-right-24: 瀏覽報告](reports/index.md)

-   :material-file-document-multiple:{ .lg .middle } **SEC 文件**

    ---
    30+ 家主要公司的 10-K 年度報告，包括 Apple、NVDA、
    Microsoft、Tesla、Palantir 等。

    [:octicons-arrow-right-24: 瀏覽文件](sec/10k.md)

-   :material-robot:{ .lg .middle } **AI 研究筆記**

    ---
    使用 NotebookLM 創建的深度研究筆記，涵蓋
    自主系統、國防科技和成長股。

    [:octicons-arrow-right-24: 瀏覽筆記](notebooks/index.md)

-   :material-script-text:{ .lg .middle } **下載腳本**

    ---
    Python 工具，用於直接從 EDGAR 批量下載 SEC 文件
    具有速率限制和 CIK 查詢功能。

    [:octicons-arrow-right-24: 查看腳本](scripts.md)

</div>

---

## 精選報告

| 公司 | 類型 | 語言 | 日期 |
|---------|------|----------|------|
| [Ondas Inc. (ONDS)](reports/onds/index.md) | 基本面分析 | 繁體中文 | 2026-02 |
| [Microsoft (MSFT)](reports/msft/index.md) | 內部交易 | 繁體中文 | 2026-02 |
| [Palantir (PLTR)](reports/pltr/index.md) | 綜合分析 | English | 2026-02 |

---

## 覆蓋範圍

=== "分析報告"
    | 代號 | 公司 | 可用報告 |
    |--------|---------|------------------|
    | ONDS | Ondas Inc. | 基本面、視覺化 |
    | MSFT | Microsoft Corp. | 內部交易 |
    | PLTR | Palantir Technologies | 綜合 |

=== "10-K 文件"
    | 代號 | 公司 | 可用年份 |
    |--------|---------|----------------|
    | AAPL | Apple Inc. | 2015–2024 |
    | MSFT | Microsoft Corp. | 多個 |
    | NVDA | NVIDIA Corporation | 多個 |
    | TSLA | Tesla Inc. | 多個 |
    | META | Meta Platforms | 多個 |
    | AMZN | Amazon.com Inc. | 多個 |
    | PLTR | Palantir Technologies | 多個 |
    | ONDS | Ondas Holdings | 多個 |
    | RKLB | Rocket Lab | 多個 |
    | KTOS | Kratos Defense | 多個 |

=== "AI 研究筆記"
    | 代號 | 公司 | 主題 |
    |--------|---------|-------|
    | ONDS | Ondas Inc. | 自主防禦系統 |
    | RKLB | Rocket Lab | 太空發射業務 |
    | AVAV | AeroVironment | 國防無人機 |
    | RCAT | Red Cat Holdings | 戰術無人機系統 |
    | TSLA | Tesla Inc. | 實體 AI |
    | NEE | NextEra Energy | 清潔能源 |
    | AMZN | Amazon | AWS AI 策略 |

---

## 關於本專案

此存儲庫提供用於下載、儲存和分析美股資料的工具和研究：

- **`ai_gen_report/stock/`** — AI 生成的投資分析報告（Markdown + HTML）
- **`ai_gen_report/market_news/`** — AI 生成的每日市場新聞分析
- **`notebook_llm/`** — 使用 Google NotebookLM 創建的深度研究文件
- **`10-k/`** — 30+ 家公司的年度 SEC 文件（PDF）
- **`10-q/`** — 季度 SEC 文件
- **`13-f/`** — 機構持股文件
- **`scripts/`** — 用於 SEC EDGAR 批量下載的 Python 自動化工具
- **`investor_day/`** — 投資者日簡報資料

!!! note "資料來源"
    SEC 文件來自 [SEC EDGAR](https://www.sec.gov/cgi-bin/browse-edgar) 和
    [annualreports.com](https://www.annualreports.com/)。分析由 Claude AI 生成。

!!! warning "免責聲明"
    所有分析僅供教育和研究目的。
    本網站上的任何內容均不構成投資建議。
