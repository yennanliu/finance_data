---
type: Dataset
title: SEC filings
description: >-
  Original SEC filings (10-K, 10-Q, 13-F, 6-K) downloaded from EDGAR for 30+
  companies, used as source material for analysis.
resource: https://yennanliu.github.io/finance_data/sec/
tags: [sec, edgar, 10-k, 10-q, 13-f, 6-k, filings]
timestamp: 2026-07-24T00:00:00Z
---

# SEC filings

Filings downloaded from SEC EDGAR and organized by form type and company. They
back the fundamental and financial-report analyses.

## Layout

```
10-k/<company>/   annual reports
10-q/<company>/   quarterly reports
13-f/<company>/   institutional holdings
6-k/<company>/    foreign-issuer reports
```

Published indices:
`https://yennanliu.github.io/finance_data/sec/` (10k / 10q / 13f / 6k pages).
The published site links to filing indices; large PDFs are not mirrored.

## Fields

- **company** — issuer name / ticker
- **form type** — 10-K, 10-Q, 13-F, or 6-K
- **filing date** — as reported on EDGAR

Downloaders live in `scripts/` (SEC EDGAR fetchers).

Related: [analysis-reports.md](analysis-reports.md)
