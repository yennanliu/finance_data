# Report Quality Audit

| Field | Value |
|-------|-------|
| Last run | 2026-08-02 |
| Bad reports found | 33 |
| CSV | [bad_reports_2026-08-02.csv](bad_reports_2026-08-02.csv) |
| Full summary | [summary_2026-08-02.txt](summary_2026-08-02.txt) |
| Retention | 10 most recent runs (older files pruned by `scripts/prune_qa.py`) |

## Latest Summary

```

============================================================
Total scanned : 3009
Bad reports   : 33  (1.1%)

Issue breakdown:
  TOO_SHORT               26
  CUTOFF                   9
  REFUSAL                  1
  HTML_LEAK                1
  MERMAID                  1

Top 10 tickers by bad-report count:
  goog            4 / 111  bad
  meta            4 / 112  bad
  avgo            3 / 98   bad
  orcl            3 / 115  bad
  pltr            3 / 113  bad
  ktos            2 / 112  bad
  msft            2 / 113  bad
  nbis            2 / 94   bad
  pl              2 / 114  bad
  0050            1 / 119  bad

CSV written → qa/bad_reports_2026-08-02.csv
```
