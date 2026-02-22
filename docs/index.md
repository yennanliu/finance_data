---
title: Finance Data Research Hub
description: AI-driven investment research, SEC filings, and fundamental analysis
---

# Finance Data Research Hub

<div class="grid cards" markdown>

-   :material-chart-line:{ .lg .middle } **Analysis Reports**

    ---
    AI-generated fundamental & insider trading reports for US equities
    in Traditional Chinese with rich visualizations.

    [:octicons-arrow-right-24: Browse Reports](reports/index.md)

-   :material-file-document-multiple:{ .lg .middle } **SEC Filings**

    ---
    10-K annual reports for 30+ major companies including Apple, NVDA,
    Microsoft, Tesla, Palantir and more.

    [:octicons-arrow-right-24: Browse Filings](sec/10k.md)

-   :material-robot:{ .lg .middle } **AI Notebooks**

    ---
    Deep-dive research notebooks created with NotebookLM covering
    autonomous systems, defense tech, and growth equities.

    [:octicons-arrow-right-24: Browse Notebooks](notebooks/index.md)

-   :material-script-text:{ .lg .middle } **Download Scripts**

    ---
    Python tools for batch-downloading SEC filings directly from
    EDGAR with rate-limiting and CIK lookup.

    [:octicons-arrow-right-24: View Scripts](scripts.md)

</div>

---

## Featured Reports

| Company | Type | Language | Date |
|---------|------|----------|------|
| [Ondas Inc. (ONDS)](reports/onds/index.md) | Fundamental Analysis | 繁體中文 | 2026-02 |
| [Microsoft (MSFT)](reports/msft/index.md) | Insider Trading | 繁體中文 | 2026-02 |
| [Palantir (PLTR)](reports/pltr/index.md) | Comprehensive Analysis | English | 2026-02 |

---

## Coverage Universe

=== "Analysis Reports"
    | Ticker | Company | Reports Available |
    |--------|---------|------------------|
    | ONDS | Ondas Inc. | Fundamental, Visual |
    | MSFT | Microsoft Corp. | Insider Trading |
    | PLTR | Palantir Technologies | Comprehensive |

=== "10-K Filings"
    | Ticker | Company | Years Available |
    |--------|---------|----------------|
    | AAPL | Apple Inc. | 2015–2024 |
    | MSFT | Microsoft Corp. | Multiple |
    | NVDA | NVIDIA Corporation | Multiple |
    | TSLA | Tesla Inc. | Multiple |
    | META | Meta Platforms | Multiple |
    | AMZN | Amazon.com Inc. | Multiple |
    | PLTR | Palantir Technologies | Multiple |
    | ONDS | Ondas Holdings | Multiple |
    | RKLB | Rocket Lab | Multiple |
    | KTOS | Kratos Defense | Multiple |

=== "AI Notebooks"
    | Ticker | Company | Topic |
    |--------|---------|-------|
    | ONDS | Ondas Inc. | Autonomous Defense Systems |
    | RKLB | Rocket Lab | Space Launch Business |
    | AVAV | AeroVironment | Defense Drones |
    | RCAT | Red Cat Holdings | Tactical UAS |
    | TSLA | Tesla Inc. | Physical AI |
    | NEE | NextEra Energy | Clean Energy |
    | AMZN | Amazon | AWS AI Strategy |

---

## About This Project

This repository provides tools and research for downloading, storing, and analysing US equity data:

- **`claude_code/`** — AI-generated investment analysis reports (Markdown + HTML)
- **`notebook_llm/`** — Deep research documents created with Google NotebookLM
- **`10-k/`** — Annual SEC filings (PDF) for 30+ companies
- **`10-q/`** — Quarterly SEC filings
- **`13-f/`** — Institutional holdings filings
- **`script/`** — Python automation tools for SEC EDGAR batch downloads
- **`investor_day/`** — Investor day presentation materials

!!! note "Data Sources"
    SEC filings sourced from [SEC EDGAR](https://www.sec.gov/cgi-bin/browse-edgar) and
    [annualreports.com](https://www.annualreports.com/). Analysis generated with Claude AI.

!!! warning "Disclaimer"
    All analysis is for educational and research purposes only.
    Nothing on this site constitutes investment advice.
