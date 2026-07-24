---
type: Dataset
title: K-line / OHLCV data
description: Per-ticker OHLCV price series (JSON) powering the site's charts.
resource: https://yennanliu.github.io/finance_data/
tags: [ohlcv, kline, price-data, json, charts]
timestamp: 2026-07-24T00:00:00Z
---

# K-line / OHLCV data

Per-ticker Open/High/Low/Close/Volume series, refreshed by a scheduled job and
used to render the site's hero k-line charts.

## Layout

```
ai_gen_report/kline/<ticker>.json
```

Refreshed by `.github/workflows/update_kline_data.yml`.

## Fields

Each record is a daily OHLCV point:

- **date**, **open**, **high**, **low**, **close**, **volume**

Related: [analysis-reports.md](analysis-reports.md) (technical analysis consumes this series)
