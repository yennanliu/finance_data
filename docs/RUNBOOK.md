# Operations Runbook

Operational procedures for the daily analysis pipeline.

---

## Re-running failed daily cron jobs

The daily workflows fire ~40+ scheduled jobs/day:

| Workflow | File | Jobs |
|----------|------|------|
| Daily Stock Analysis | `.github/workflows/daily_analysis.yml` | 1 per ticker × {fundamental, technical} |
| Daily Market News | `.github/workflows/daily_market_news.yml` | 1 per ticker |

Each cron slot maps to a specific ticker (and analysis type) via a `case
"$SCHEDULE" in …` block inside the workflow. When a batch of these fail, use the
helper below to re-run exactly the failed ones.

### TL;DR

```bash
# Preview what failed in the last day (no dispatches):
./scripts/rerun_failed_cron.sh --dry-run

# Re-run them, one at a time, waiting for each to finish:
./scripts/rerun_failed_cron.sh --wait
```

### ⚠️ Do NOT use `gh run rerun` to backfill after a fix

`gh run rerun <id>` replays a run **at its original commit SHA**. If the failures
were caused by a bug or config that has since been fixed on `main` (e.g. an
unavailable model, an expired setting), the rerun re-executes the **old broken
code** and fails again with the identical error.

To pick up the current `main`, you must dispatch a **fresh** run
(`gh workflow run …` / `workflow_dispatch`). That is exactly what
`scripts/rerun_failed_cron.sh` does — it *re-dispatches*, it does not *rerun*.

### How the helper works

1. Lists failed `schedule`-event runs for each daily workflow within a time window.
2. Extracts each run's cron expression from its run title.
3. Decodes cron → ticker (+ analysis type) by reading the `case`-map **inside the
   workflow YAML**, so the mapping never drifts out of sync with the schedule.
4. Re-dispatches one fresh `workflow_dispatch` run per unique failed job.

```
./scripts/rerun_failed_cron.sh [--since DAYS] [--workflow FILE]
                               [--wait] [--dry-run] [--delay N] [--repo o/r]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--since DAYS` | `1` | Look back this many days for failures |
| `--workflow FILE` | both | Limit to one workflow, e.g. `daily_analysis.yml` |
| `--wait` | off | Wait for each re-dispatched run to finish before the next (sequential) |
| `--dry-run` | off | Print what would be dispatched; dispatch nothing |
| `--delay N` | `20` | Seconds between dispatches when **not** using `--wait` |
| `--repo o/r` | `yennanliu/finance_data` | Target repository |

### Manual fallback (single job)

```bash
gh workflow run daily_analysis.yml   -f ticker=NVDA -f analysis_type=technical-analysis
gh workflow run daily_market_news.yml -f ticker=NVDA
```

---

## Provider fallback chain & common failure modes

Report generation runs an ordered provider chain (see
`scripts/analysis/config/providers.py` → `FALLBACK_CHAIN` / `resolve_chain()`),
currently **gemini → openai**. The first provider to succeed wins; context is
fetched once and reused across attempts (`scripts/analysis/utils/llm.py` →
`run_with_fallback()`).

Two failures seen in production, both **account-level** (a rerun will not fix them —
fix the account/config, then re-dispatch with the helper above):

| Symptom in logs | Cause | Fix |
|-----------------|-------|-----|
| `google.genai … 429 RESOURCE_EXHAUSTED … monthly spending cap` | Gemini (primary) billing cap hit | Raise/reset cap in AI Studio billing, or reorder the chain |
| `openai … 403 … does not have access to model '<model>'` | OpenAI fallback pointed at a model the project can't use | Set an accessible model as the OpenAI default in `providers.py` (e.g. `gpt-4o`) |

> When the primary provider is exhausted (e.g. Gemini spend cap), **every** daily
> run burns a failed primary attempt before falling back. If that state persists,
> reorder `FALLBACK_CHAIN` so a healthy provider is first.
