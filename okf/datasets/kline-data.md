---
type: Dataset
title: K-line / OHLCV data
description: Per-ticker OHLCV price series (CSV) powering the site's charts.
resource: https://yennanliu.github.io/finance_data/
tags: [ohlcv, kline, price-data, csv, charts]
timestamp: 2026-08-04T00:00:00Z
---

# K-line / OHLCV data

Per-ticker Open/High/Low/Close/Volume series covering up to ten years, refreshed
by a scheduled job. This is the single source of truth for every chart on the
site; the chart payloads pages fetch are derived from it at docs-build time and
are not stored.

## Layout

```text
data/prices/<ticker>.csv
```

Refreshed by `.github/workflows/update_kline_data.yml`
(`scripts/update_prices.py`). Design notes: `docs/PRICE_STORE_DESIGN.md`.

## Fields

One row per trading day, oldest first:

- **date** — ISO `YYYY-MM-DD`
- **open**, **high**, **low**, **close** — as-reported prices (split-adjusted,
  not dividend-adjusted)
- **volume** — shares traded
- **div**, **split** — cash dividend / split ratio on that date; empty when
  there was no event

Related: [analysis-reports.md](analysis-reports.md) (technical analysis consumes this series)
