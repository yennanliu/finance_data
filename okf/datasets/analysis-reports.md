---
type: Dataset
title: AI-generated analysis reports
description: >-
  Markdown investment-research reports, one file per (ticker, analysis type,
  date), generated daily by an LLM pipeline.
resource: https://yennanliu.github.io/finance_data/reports/
tags: [analysis, reports, ai-generated, markdown]
timestamp: 2026-07-24T00:00:00Z
---

# AI-generated analysis reports

The core dataset. Each report is a single dated Markdown file produced by
`scripts/generate_analysis.py` and mirrored into the published site.

## Layout

```
ai_gen_report/
├── fundamental/<ticker>/fundamental_analysis_<date>.md
├── technical/<ticker>/technical_analysis_<date>.md   (+ chart PNGs)
└── stock/<ticker>/<type>_<date>.md                   (all other types)
```

Published (per ticker, EN + ZH merged):
`https://yennanliu.github.io/finance_data/reports/<ticker>/`

## Fields

- **ticker** — the equity symbol (see [../references/coverage.md](../references/coverage.md))
- **analysis type** — one of 12 (see [../references/analysis-types.md](../references/analysis-types.md))
- **date** — ISO date the report was generated
- **language** — reports are authored in Traditional Chinese

## Provenance

Data is fetched via yfinance and web scrapers, assembled into an LLM context,
and written by a provider-fallback chain (Gemini → OpenAI → Claude). Reports are
AI-generated and are **not investment advice**.

Related: [sec-filings.md](sec-filings.md) · [market-news.md](market-news.md)
