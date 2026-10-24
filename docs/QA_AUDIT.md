# QA Audit

`.github/workflows/qa_report_quality.yml` audits recently generated reports every
night at **02:00 UTC**, after the report-generation crons (17:00–03:00 UTC) have
mostly finished. It has two stages, and the second never blocks the first.

| Stage | Script | Cost | Output |
|-------|--------|------|--------|
| 1. Rule-based | `scripts/check_report_quality.py`, `scripts/check_mermaid.py` | free, deterministic, pure stdlib | `qa/bad_reports_<date>.csv`, `qa/summary_<date>.txt` |
| 2. LLM review | `scripts/review_report_quality.py` | OpenAI tokens | `qa/llm_review_<date>.csv`, `qa/llm_review_<date>.txt` |

After both stages, `scripts/prune_qa.py --keep 10` keeps only the 10 most recent
run dates in `qa/`. It prunes *any* dated file, so a new artifact type needs no
change there. The workflow then regenerates `qa/README.md` and commits.

---

## Stage 1: rule-based checks

Detection logic lives in `scripts/analysis/validate/` (`__init__.py`,
`arithmetic.py`, `technical.py`, `market_data.py`). This is the primary gate.

Every issue code and its one-line description is in `ISSUE_TYPES`
(`validate/__init__.py`) and is printed beside its count. Type-specific checks are
`content_findings()` functions that return `(code, note)` pairs. Add a new check
there, not inline in `parse_file`.

### Issue codes

| Applies to | Code | Fires when |
|------------|------|------------|
| All | `EMPTY`, `NO_FRONTMATTER`, `REFUSAL`, `TOO_SHORT`, `CUTOFF`, `HTML_LEAK`, `MERMAID`, `DUPLICATE`, `READ_ERROR` | Mechanical failures |
| All | `PLACEHOLDER` | An unfilled template placeholder, including the prompts' example figures copied verbatim (`$XXX`, `第 XX 百分位`) |
| Fundamental | `MISSING_SECTIONS` | Any of `## 1.`–`## 11.` is absent |
| Fundamental | `ARITHMETIC` | The §8.8 total differs from Σ of its terms by more than 0.5%, **or** the §1.0 MOS / DCF premium differs by more than 1pp from what the report's own fair value, DCF value and price give (`arithmetic.valuation_mismatches`) |
| Fundamental | `PRICE_MISMATCH` | The quoted 現價 differs from the front-matter `price` |
| Technical | `NAN_VALUE` | A `$nan` / `nan%` leaked from an empty data bar |
| Technical | `PRICE_MISMATCH` | The headline price differs from the front-matter `price` by more than 0.5% |
| Technical | `LEVEL_MISMATCH` | A Ch.4 R1–S3 differs from the front-matter `levels` entry with the same label |
| Technical | `RR_MISMATCH` | The stated R/R matches neither T1 nor T2 computed from its own entry and stop. A range entry may use its midpoint or either end |
| Any report with provenance | `STORE_MISMATCH` | Front-matter `price` ≠ the `data/prices/` close on `price_date`, with later splits undone. Silent when the store has no bar for that date yet |
| Any report with provenance | `STALE_PRICE` | A store session is dated strictly between `price_date` and the report date, so a newer close existed |

### Summary layout

The summary leads with a **last-2-UTC-days slice** (`--recent-days`) before the
all-corpus counts, and `qa/README.md` shows both. The corpus total is dominated
by reports written before a fix landed, so the recent slice is the number to
watch.

`FILENAME_RE` accepts the duplicate suffix on either side of the provider. Before
that fix, `_2026-10-23_gemini-2.md` was read as type `unknown` and skipped every
check (34 such files existed).

Stage 1 does not cover `ai_gen_report/market_news/`. Stage 2 does (see
`DEFAULT_ROOTS` in each script).

---

## Stage 2: LLM review

Stage 2 grades what regex cannot see: fabricated numbers, shallow analysis,
conclusions that contradict the evidence, and simplified-Chinese leakage. It
scores five dimensions from 1 to 5 and returns `pass`, `warn` or `fail`.

The prompt and rubric live in `scripts/analysis/prompts/qa_review.txt`. The
template is `.format()`ed, so escape literal JSON braces as `{{` `}}`.

### Who grades what

- The judge is deliberately **not** the generator. The generator defaults to
  Gemini, and the workflow passes `--provider openai --cross-provider`. Reports
  that fell back to OpenAI are graded by Gemini. Without `GEMINI_API_KEY` the
  workflow drops `--cross-provider` with a warning.
  `test_the_default_reviewer_is_not_the_default_generator` pins this.
- `--cross-provider` never lets a provider grade a report it generated.
  `parse_file` reads the generating provider from front matter. If no other
  provider has a key, the script exits 1 up front rather than grading its own
  reports.
- Reviewer models are set in `REVIEWER_MODELS` in `review_report_quality.py`,
  **not** in `resolve_chain()`. Otherwise changing the generator's OpenAI model
  would silently change the auditor too. There is one entry per provider, so a
  `--cross-provider` switch never hands Gemini an OpenAI model id. Each is a
  cheap model, because cost is driven by input volume, not the ~300-token
  verdict. `--model` applies only to `--provider`.

### Inputs to the judge

- The prompt carries a trusted `{pipeline_record}` block outside `<report_data>`,
  built by `pipeline_record()`: the close the report was given, failed data
  sources and the stage-1 findings.
- The rubric tells the judge **not** to list or score stage-1 findings. In the
  first live run the judge was told to let them lower its scores. It passed 0 of
  133 reports and spent 20 issues restating §8.8 corrections.
- **The report under review is untrusted input.** It is model output built partly
  from scraped news and RSS text, so an attacker-controlled headline can reach
  the judge. `REVIEWER_SYSTEM_MESSAGE` tells the grader to ignore instructions
  inside `<report_data>`. The delimiters alone are not the boundary.
- `refusal_retry=False` is mandatory. The refusal-override prefix in
  `analysis/utils/llm.py` tells the model to *write a report*, which would turn
  the grader into a generator.

### What the rubric says is NOT a defect

Each of these was traced to a wrong verdict in the third live run. Don't
reintroduce them.

1. **Missing source citations.** Reports are generated from a financial-data
   context that never appears in the report body, so they cannot cite figures
   inline. 38 of that run's 54 grounded fails complained about this, an
   unsatisfiable criterion the original rubric asked for verbatim
   (「具體數字是否有來源脈絡」). `data_integrity` now judges whether a *number is
   credible*, not whether a citation is present.
2. **The report's own derived valuations.** 加權合理價值 / DCF 內在價值 / 目標價 /
   MOS come from the report's own model, usually with the assumptions shown in
   its DCF chapter. `amd`'s 「加權合理價值 $619.64」 is derived in its Ch.8, yet was
   failed as 來源不明. Criticise the *assumptions* instead.
3. **Self-flagged data anomalies.** `soxq` was failed for a 31.0% dividend yield
   that its own report had already identified as distorted and restated at
   1.15%. That is good practice and now scores up, not down.

The rubric also states the evidence rule that `verdict_is_grounded()` enforces
(a low score needs a traceable quote), so no verdict is quarantined for breaking
a rule it was not given.

### Verdict handling

- **Verdicts are reconciled against their own scores** (`_enforce_verdict`) and
  only ever downgraded. Otherwise a `pass` alongside `data_integrity=1` would be
  filtered out of the problem CSV and never trip `--fail-on-fail`.
- **`grounded` column / `verdict_is_grounded()`**: a `warn`/`fail` whose
  dimensions are *all* 1 **and** whose issues quote no figure traceable to the
  report is marked ungrounded. Such rows stay in the CSV for auditability but are
  excluded from the headline verdict counts and cannot trip `--fail-on-fail`.
  `pass` verdicts need no evidence, and an all-1s row that cites a real figure is
  kept.
- Malformed JSON *shapes* (a list under `dimensions`, a number under `issues`)
  raise `ValueError` and become a `PARSE_ERROR` row. Provider errors become
  `ERROR` rows. `review_one`'s handler is deliberately broad: no single bad
  response may abort a 100-report batch.

### How the workflow runs it

- **Rolling 2-day window** (`--days 2`), not "today". Report-gen crons run
  17:00–03:00 UTC, so one generation cycle straddles midnight and lands under two
  date stamps. A 1-day window silently skips the 17:00–23:00 batch, which is most
  of the output.
- **Non-blocking.** The script exits 0 even on `fail` verdicts, so a bad night
  still commits an audit trail. `--fail-on-fail` opts into exit 1.
- **Never on stage 1's critical path.** `openai` is installed *after* stage 1
  runs, and the install, key check and review steps are all gated and
  `continue-on-error`. A missing secret or PyPI hiccup annotates the run but
  still commits the stage-1 audit.
- **Tunable from the GitHub UI** via the `llm_review`, `llm_review_model`,
  `llm_review_days` and `llm_review_limit` dispatch inputs. A blank input adds no
  flag, so scheduled runs keep the script defaults. `llm_review_limit` exists for
  cheap model comparisons: selection is sorted, so the same cap over the same
  `--days` grades the same reports under two different models.
- **stdout is this script's data channel, not a log channel.** The workflow tees
  stdout into the committed `qa/llm_review_<date>.txt`, but
  `analysis/utils/logging_utils.py` attaches its handler to stdout. The first
  live run buried the summary under ~400 lines of per-call INFO logs and grew
  `qa/README.md` by 432 lines. `route_library_logs_to_stderr()` moves the
  `analysis.*` handlers to stderr at the start of `main()`. This is fixed locally
  rather than in the shared logger, because every other CLI wants its logs on
  stdout as ordinary CI output.

### How far to trust the scores

The judge is reproducible, but about a third of its verdicts are boilerplate.

- Two live `gpt-4o-mini` runs over the same 117 reports agreed closely: 34/12/71,
  then 36/6/75 pass/warn/fail, with per-dimension means within 0.04. The scores
  are stable, not noisy.
- About 25 rows per run score **1 on all five dimensions** and carry
  near-identical template prose across unrelated tickers. Only about 6 of them
  quote any figure. At least one is checkably false: msft was flagged for
  `$XXX`/`N/A` placeholders that appear nowhere in its 79 KB.
- The other ~56 rows are grounded. 29 quote figures that do exist, and `mu`'s
  `$90.27B` TTM revenue was a genuine fabrication (actual ≈ $37B) that stage 1
  passed clean.

So the aggregate fail rate is not actionable, but the grounded subset is exactly
what this stage is for. A larger reviewer model has **not** been compared yet;
`llm_review_limit` makes that cheap. On current evidence the boilerplate looks
more like a prompt or rubric problem than a model-capability one.
