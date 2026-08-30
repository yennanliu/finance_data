# Daily Cycle Collector

How generated content gets from ~100 scheduled jobs into the repository as a
single commit per day.

## Why

Every generator job used to commit and push its own output. That produced
~100 commits a day and a permanent push race:

- 36 of 38 `daily_market_news` runs share a cron minute with a
  `daily_analysis` run.
- `0 2 * * *` was a three-way collision (`daily_analysis` MU fundamental,
  `qa_report_quality`, `cleanup_refusals`).
- `daily_analysis` retried a rejected push five times and then **exited 0**,
  so an exhausted retry silently dropped the report.

Generators now upload their output as a workflow artifact and never touch the
branch. `collect_daily.yml` is the only workflow that writes generated content.

## The cycle

The generation window does not line up with a calendar day:

| Window (UTC)  | Producer                              |
| ------------- | ------------------------------------- |
| 17:00 – 23:10 | `daily_market_news` (38 crons)        |
| 17:00 – 21:00 | `daily_analysis` fundamental (25)     |
| 21:30 – 01:30 | `daily_analysis` technical (25)       |
| 02:00 – 03:40 | `daily_analysis` fundamental (11)     |
| 22:00         | `daily_stock_watchlist`               |
| 03:30         | `update_kline_data`                   |

A run at 22:00 and a run at 02:00 belong to the **same** batch. So a cycle is
named for the UTC date on which it *started*: anything at or after 17:00 UTC
belongs to that day's cycle, anything earlier to the previous day's.

That rule lives in `scripts/cycle.py` and is the single source of truth. Every
generator calls it to name its artifact, and the collector calls it to build
the prefix it collects. Get it wrong and a cycle either splits across two
commits or swallows the next one — `tests/test_cycle.py` pins the boundary.

## Flow

```
generators (17:00 → 03:40)          collect_daily.yml (03:50)      deploy.yml (05:00)
  generate report                     download every artifact
  stage only THIS run's files         named cycle-<date>-*
  upload-artifact                 →   unpack over the checkout      →  build + publish
  (no commit, contents: read)         run QA audit
                                      build progress summary
                                      ONE commit, one push
```

Artifact names are `cycle-<date>-<source>-<parts...>`, e.g.
`cycle-2026-08-30-analysis-NVDA-technical`, `cycle-2026-08-30-news-AMD`,
`cycle-2026-08-30-prices`.

## Why artifacts rather than a shared branch

A per-day branch that every job pushed to would have moved the push race, not
removed it — 100 jobs would still contend, just on a different ref. With
artifacts only one job ever pushes, so the race is gone rather than relocated.

It also *reduces* blast radius. Previously a failed push lost that report
permanently. Now artifacts are retained for 7 days, so a failed collector is
re-runnable:

```
gh workflow run collect_daily.yml -f cycle_date=2026-08-30
```

## Ordering constraints

Two workflows had to move into the collector because they read content that is
no longer on the branch when they used to run:

- **`qa_report_quality.yml`** audits the reports on disk. At its old 02:00 slot
  it would now grade the *previous* cycle.
- **`daily_progress.yml`** derived its summary from
  `git log --since="12 hours ago"`, which only worked while each report was its
  own commit. It now builds from the collector's exact file list
  (`scripts/build_progress.py`).

Both are kept in the repo as `workflow_dispatch`-only for manual runs.

`deploy.yml` moved from 04:00 to 05:00: it must run after the *collector*, not
merely after the last generator. At 04:00 it had a 10-minute margin, and a slow
or retried collect would have published a day-old site.

## Safety

Artifacts carry repo-relative paths and are unpacked over a real checkout, so
`scripts/collect_cycle.py` guards extraction twice:

1. Entries that escape the destination (absolute paths, `..`) are rejected.
2. Entries outside `ALLOWED_ROOTS` (`ai_gen_report`, `data`, `ws`, `progress`)
   are skipped — an artifact cannot rewrite a workflow or a script.

A generator that starts writing somewhere new must be added to `ALLOWED_ROOTS`
deliberately.

Other properties worth knowing:

- **Re-runs**: if a ticker is re-run, two artifacts share a name. The newest
  wins (`select_for_cycle`).
- **Partial failure**: one corrupt or undownloadable artifact is logged and
  skipped; the rest of the cycle still commits. The collector fails only if
  *every* artifact fails.
- **Empty cycle**: collecting nothing is not an error. The workflow logs a
  warning and makes no commit.

## Adding a generator

1. Stage only what the run produced (copy the `Stage generated files` step).
2. Upload with a `cycle-${{ steps.cycle.outputs.date }}-<source>-...` name.
3. Set `permissions: contents: read` — it must not push.
4. If it writes outside the existing content roots, add the root to
   `ALLOWED_ROOTS` in `scripts/collect_cycle.py`.
