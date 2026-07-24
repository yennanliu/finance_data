---
type: Reference
title: Analysis types
description: The 12 AI-generated analysis types produced for each ticker.
resource: https://yennanliu.github.io/finance_data/reports/
tags: [analysis-types, taxonomy]
timestamp: 2026-07-24T00:00:00Z
---

# Analysis types

Twelve report types are defined in `scripts/analysis/config/__init__.py`
(`ANALYSIS_TYPES`). Labels are the Traditional-Chinese headings used in reports.

| Key | Label (zh-TW) | Output |
|-----|---------------|--------|
| `fundamental-analysis` | 基本面深度分析 | `.md` |
| `technical-analysis` | 技術分析 | `.md` + charts |
| `stock-eval` | 綜合股票評估 | `.md` |
| `stock-valuation` | 多方法估值分析 | `.md` |
| `financial-report-analyst` | 財報深度解析 | `.md` |
| `earnings-call-analysis` | 財報電話會議分析 | `.md` |
| `insider-trading` | 內部人交易分析 | `.md` |
| `institutional-ownership` | 機構持股分析 | `.md` |
| `sector-analysis` | 產業板塊分析 | `.md` |
| `economics-analysis` | 總體經濟分析 | `.md` |
| `portfolio-review` | 投資組合回顧 | `.md` |
| `report-generator` | 綜合HTML投資報告 | `.html` |

Reports feed the [analysis-reports dataset](../datasets/analysis-reports.md).
