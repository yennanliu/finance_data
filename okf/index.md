---
type: Knowledge Bundle
title: Finance Data Research Hub
description: >-
  AI-driven US-equity investment research — fundamental & technical analysis,
  SEC filings, insider/institutional tracking, and daily market news, published
  in Traditional Chinese.
resource: https://yennanliu.github.io/finance_data/
tags: [finance, us-equities, investment-research, sec-filings, ai-generated]
timestamp: 2026-07-24T00:00:00Z
---

# Finance Data Research Hub — Knowledge Bundle

This is an [Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf)
bundle: a vendor-neutral, plain-markdown description of the knowledge this
project produces, meant to be read and navigated by AI agents.

The project generates AI-powered investment research reports for US equities and
publishes them as a static site via MkDocs → GitHub Pages. All human-facing
reports are written in **Traditional Chinese**.

## What lives here

Follow the links to explore the bundle. Each linked file carries YAML
frontmatter (`type`, `description`, `resource`, `tags`, `timestamp`) plus a
markdown body.

### Datasets — [datasets/index.md](datasets/index.md)
- [Analysis reports](datasets/analysis-reports.md) — 12 AI-generated report types per ticker
- [SEC filings](datasets/sec-filings.md) — 10-K, 10-Q, 13-F, 6-K for 30+ companies
- [Market news](datasets/market-news.md) — daily AI-curated news per ticker
- [K-line / OHLCV data](datasets/kline-data.md) — per-ticker price series for charts

### References — [references/index.md](references/index.md)
- [Analysis types](references/analysis-types.md) — the 12 report types and what each covers
- [Coverage](references/coverage.md) — the tickers tracked daily

## How the data is produced

```
scripts/generate_analysis.py
  → data_fetch (yfinance + web scrapers → OHLCV, financials)
  → context   (assembles LLM-ready context)
  → prompts/*.txt
  → llm       (Claude / OpenAI / Gemini, with provider fallback)
  → ai_gen_report/{fundamental,technical,stock}/<ticker>/<type>_<date>.md
scripts/build_docs.py  → mirrors reports into docs/ (EN) and docs/zh/ for MkDocs
```

Source and change history: [log.md](log.md) · Repository:
<https://github.com/yennanliu/finance_data>
