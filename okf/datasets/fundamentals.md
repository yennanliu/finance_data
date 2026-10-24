---
type: Dataset
title: Quarterly fundamentals
description: Per-ticker quarterly financial statements from SEC XBRL companyfacts (CSV), powering the site's Financials, Valuation and Intrinsic value views.
resource: https://yennanliu.github.io/finance_data/data/
tags: [fundamentals, financial-statements, sec, xbrl, csv]
timestamp: 2026-10-24T00:00:00Z
---

# Quarterly fundamentals

Up to ten years of *reported* quarterly financial statements per ticker, sourced
from SEC's XBRL `companyfacts` API and refreshed weekly. A newly fetched period
always replaces the stored one, so restatements simply overwrite earlier
figures. Only companies that file 10-Q/10-K have a file; Taiwan-listed symbols,
foreign filers (such as TSM, GRAB, NU) and ETFs do not.

## Layout

```text
data/fundamentals/<ticker>.csv
```

Refreshed by `.github/workflows/update_fundamentals.yml`
(`scripts/update_fundamentals.py`). Design notes:
`docs/FUNDAMENTALS_STORE_EVAL.md`.

## Fields

One row per reported quarter, oldest first. Key columns:

- **period_end**, **fy**, **fp**, **form**, **filed** — period end date, fiscal
  year, fiscal period (`Q1`–`Q4`), source form and filing date
- **revenue**, **gross_profit**, **operating_income**, **net_income**,
  **pretax_income**, **income_tax**, **interest_expense** — income statement, in
  reporting currency
- **eps_basic**, **eps_diluted**, **shares_diluted** — as reported (not
  split-adjusted; the site adjusts per-share figures on read)
- **ocf**, **capex**, **sbc**, **dividends_paid**, **buybacks**, **dep_amort** —
  cash flow
- **cash_and_equiv**, **total_assets**, **total_equity**, **total_liabilities**,
  **long_term_debt**, … — balance sheet

Empty cells mean the company did not report that concept for the period.

Related: [kline-data.md](kline-data.md) (valuation multiples combine both series)
· [analysis-reports.md](analysis-reports.md) (fundamental reports quote TTM
figures derived from this store)
