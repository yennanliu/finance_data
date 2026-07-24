---
type: Reference
title: Coverage
description: Tickers tracked by the daily analysis pipeline.
resource: https://yennanliu.github.io/finance_data/reports/
tags: [coverage, tickers, universe]
timestamp: 2026-07-24T00:00:00Z
---

# Coverage

The daily universe is defined in `scripts/.ticker_schedule.json`.

> **Scope note:** the hub is primarily US-equity research, but the universe
> also includes two Taiwan-listed symbols — `0050` (元大台灣50 ETF) and
> `2330.TW` (TSMC on the TWSE). Agents should not assume a US-only universe.

## Fundamental analysis (36 tickers)

`0050`, `2330.TW`, `TSLA`, `PL`, `GRAB`, `TSM`, `GOOG`, `AMZN`, `MSFT`, `SOFI`,
`PLTR`, `RKLB`, `ONDS`, `AVAV`, `KTOS`, `META`, `AMD`, `NVDA`, `NU`, `VST`,
`ORCL`, `INTC`, `SPCX`, `AVGO`, `NBIS`, `MU`, `SKHY`, `WDC`, `SNDK`, `MRVL`,
`SOXQ`, `SOXX`, `WQTM`, `VTI`, `QQQ`, `ROBO`

## Technical analysis (25 tickers)

`0050`, `2330.TW`, `TSLA`, `PL`, `GRAB`, `TSM`, `GOOG`, `AMZN`, `MSFT`, `SOFI`,
`PLTR`, `RKLB`, `ONDS`, `AVAV`, `KTOS`, `META`, `AMD`, `NVDA`, `NU`, `VST`,
`ORCL`, `INTC`, `SPCX`, `AVGO`, `NBIS`

The published per-ticker reports live at
`https://yennanliu.github.io/finance_data/reports/<ticker>/`.
