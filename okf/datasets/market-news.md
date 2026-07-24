---
type: Dataset
title: Daily market news
description: Daily AI-curated market-news summaries, one file per ticker per day.
resource: https://yennanliu.github.io/finance_data/market_news/
tags: [market-news, daily, ai-generated]
timestamp: 2026-07-24T00:00:00Z
---

# Daily market news

AI-curated market-news summaries generated on a daily cron, one Markdown file
per ticker per day.

## Layout

```
ai_gen_report/market_news/<ticker>/market_news_<date>_<provider>.md
```

Published: `https://yennanliu.github.io/finance_data/market_news/<ticker>/`

## Fields

- **ticker** — the equity symbol
- **date** — generation date
- **provider** — the LLM provider that produced the summary

Related: [analysis-reports.md](analysis-reports.md)
