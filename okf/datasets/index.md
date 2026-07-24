---
type: Index
title: Datasets
description: The data collections published by the Finance Data Research Hub.
resource: https://yennanliu.github.io/finance_data/
tags: [datasets, index]
timestamp: 2026-07-24T00:00:00Z
---

# Datasets

| Dataset | Description | Source path |
|---------|-------------|-------------|
| [Analysis reports](analysis-reports.md) | 12 AI-generated report types per ticker | `ai_gen_report/{fundamental,technical,stock}/` |
| [SEC filings](sec-filings.md) | 10-K, 10-Q, 13-F, 6-K filings | `10-k/`, `10-q/`, `13-f/`, `6-k/` |
| [Market news](market-news.md) | Daily AI-curated market news per ticker | `ai_gen_report/market_news/` |
| [K-line / OHLCV](kline-data.md) | Per-ticker price series for charts | `ai_gen_report/kline/` |

See [../references/coverage.md](../references/coverage.md) for the list of
tracked tickers and [../references/analysis-types.md](../references/analysis-types.md)
for what each report type covers.
