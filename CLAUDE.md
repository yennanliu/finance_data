# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -e ".[dev]"

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_llm.py -v

# NOTE: .python-version pins 3.9 (often not installed locally). The suite is
# verified under Python 3.13 — if `pytest` can't find an interpreter, run it
# explicitly, e.g. `python3.13 -m pytest tests/ -v`. Tests are fully offline
# (network/SDK/selenium boundaries are mocked); no API keys required.

# Generate analysis locally
python scripts/generate_analysis.py AAPL --analysis-type fundamental-analysis --provider claude
python scripts/generate_analysis.py MSFT --analysis-type technical-analysis --provider openai

# Build and preview docs site
python3 scripts/build_docs.py && mkdocs serve

# Trigger GitHub Actions workflow via CLI
gh workflow run daily_analysis.yml -f ticker=MSFT -f analysis_type=technical-analysis

# Trigger analysis via Makefile (fires GitHub Actions workflows)
make analyze TICKERS="NVDA TSLA" TYPES="fundamental-analysis,technical-analysis"
make analyze-mag7
make deep-dive TICKERS="NVDA"
```

## Architecture

The codebase generates AI-powered investment research reports and publishes them via MkDocs to GitHub Pages. Full architecture is in `docs/ARCHITECTURE.md`.

### Core flow
```
scripts/generate_analysis.py
  → scripts/analysis/utils/data_fetch.py   (yfinance + web scrapers → OHLCV, financials)
  → scripts/analysis/context/__init__.py   (assembles data into LLM-ready context, 12 branches)
  → scripts/analysis/prompts/*.txt          (prompt templates, one per analysis type)
  → scripts/analysis/utils/llm.py          (Claude or OpenAI API call)
  → ai_gen_report/fundamental/<ticker>/<type>_<date>.md   (fundamental-analysis)
  → ai_gen_report/technical/<ticker>/<type>_<date>.md     (technical-analysis, + chart PNGs)
  → ai_gen_report/stock/<ticker>/<type>_<date>.md         (all other analysis types)
```

`scripts/build_docs.py` then mirrors `ai_gen_report/` into `docs/` and `docs/zh/` so MkDocs can serve them.

### Key files
- `scripts/analysis/config/__init__.py` — `ANALYSIS_TYPES` dict (12 types), model/token defaults
- `scripts/analysis/config/providers.py` — per-provider defaults (Claude: 8k tokens, OpenAI: 16k) plus `FALLBACK_CHAIN` + `resolve_chain()`: the ordered provider pool the generators try (currently gemini → openai; edit the list to add levels)
- `scripts/analysis/utils/llm.py` — `run_with_fallback()` runs an ordered `(provider, model)` chain, returning the first success; context is fetched once and reused across fallback attempts
- `scripts/analysis/context/__init__.py` — 12-branch context assembler; touch when adding analysis types (`utils/context.py` is a back-compat shim re-exporting it)
- `scripts/analysis/utils/llm.py` — `call_llm()` dispatcher; handles rate-limit retries and refusal overrides
- `scripts/analysis/data/prices.py` — the committed OHLCV store (`data/prices/<key>.csv`); pure-stdlib read path
- `scripts/analysis/data/price_analytics.py` — pure-stdlib statistics derived from the store (returns, drawdown, rolling volatility, return histogram, monthly grid, series averages); with `fundamental_analytics.py` it powers the **Market Data** section (`docs/data/`). All chart maths lives here, never in JS — see `docs/PRICE_STORE_DESIGN.md` §12
- `scripts/.ticker_schedule.json` — data-driven ticker list for daily CI jobs
- `.github/workflows/daily_analysis.yml` — 61 cron slots/day (36 fundamental + 25 technical), one ticker per slot
- `.github/actions/` — shared composite actions used by the workflows: `commit-and-push` (stage/commit/rebase-retry/push), `python-env` (setup-python + pip install), `build-site` (MkDocs install/generate/stamp/build). Change CI behaviour here rather than in each workflow

### Adding a new analysis type
1. Add entry to `ANALYSIS_TYPES` in `scripts/analysis/config/__init__.py`, including its `prompt_file` (the template's basename — `PROMPT_MAP` is derived from this field, so there is no second map to edit)
2. Create prompt at `scripts/analysis/prompts/<prompt_file>.txt` (placeholders: `{ticker}`, `{financial_context}`, `{today}`)
3. Add context-building branch in `scripts/analysis/context/__init__.py`
4. Test: `python scripts/generate_analysis.py AAPL --analysis-type <type>`

### Adding a new ticker to daily schedule
1. Edit `scripts/.ticker_schedule.json` (drives the price store's ticker universe)
2. Add a `cron:` entry **and** a matching `case` arm in `.github/workflows/daily_analysis.yml` — a scheduled run only knows its cron string, so the arm is what maps it to a ticker. Same for `daily_market_news.yml`
3. `pytest tests/test_workflows.py` — fails if a cron has no arm (or an arm no cron), or if two crons resolve to the same ticker+analysis type; an unmapped cron also fails the run itself rather than silently publishing a duplicate TSLA report

## Report output
- Reports written as Markdown to `ai_gen_report/fundamental/<ticker>/`, `ai_gen_report/technical/<ticker>/`, or `ai_gen_report/stock/<ticker>/` depending on analysis type (see Core flow above)
- `build_docs.py` merges all three per ticker and copies them into `docs/reports/<ticker>/` and `docs/zh/reports/<ticker>/`
- `build_docs.py` also publishes `data/prices/` **and** `data/fundamentals/` together as `docs/data/` (**Market Data**) — an overview table plus one tabbed page per ticker: Overview (candles, returns, TTM figures) · Price (drawdown, volatility, return distribution, monthly heatmap) · Financials (statements, margins, returns on capital) · Valuation (P/E, P/S, P/B, EV multiples, P/E bands) · Data & glossary (both CSVs, JSON payloads, term definitions)
- Every chart card carries a one-line explainer, captioned x/y axes and — for the valuation multiples and rolling volatility — a dashed line at the series' own historical average (`price_analytics.series_average`, computed in Python, never in JS)
- The pre-merge URLs `docs/prices/<ticker>/` and `docs/fundamentals/<ticker>/` still exist as redirect stubs (`build_legacy_redirects()`), hidden from the nav via `.pages` `hide: true`
- `docs/` is auto-generated — edit source files in `ai_gen_report/` and `scripts/`, not in `docs/`
- `scripts/maintain_ai_gen_report.py` handles re-splitting (`reorg`) and pruning old dated reports (`prune --before YYYY-MM-DD`)

## Bilingual site (EN + `zh/`)
The site is **one** MkDocs build: `docs/` is English and `docs/zh/` is Traditional Chinese, so `theme.language` is `en` everywhere and nothing about the ZH tree is automatic.
- All UI copy lives in `LANG_TEXT` in `scripts/build_docs.py` (`t(lang, key)`); both halves must carry every key. Chart labels rendered by JS are localised separately in `docs/javascripts/price-charts.js` and `kline-chart.js`, which detect `/zh/` from the URL
- `build_nav_pages()` lists `- zh` on the **EN** root `.pages`. Without it awesome-pages drops `docs/zh/` from the nav entirely (a `nav:` with no `...` is exhaustive) and every ZH page silently renders the *English* tab row, linking back into the English tree
- Three theme overrides in `docs/overrides/partials/` make navigation language-aware, and are written against the `mkdocs-material==9.5.*` pin in `.github/actions/build-site/action.yml`:
  - `tabs.html` / `nav.html` — on a ZH page, render the `zh` subtree as the tab row and sidebar, so both trees render identically. The subtree is found by URL prefix, not by title, so renaming it in `LANG_TEXT` cannot break the lookup
  - `alternate.html` — maps the language switcher to *the same page* in the other tree instead of the site root. The ZH tree mirrors **index pages only** (dated report/news leaves are English-only), so the mapping is applied to `page.is_index` pages and falls back to the configured root link otherwise — a wrong guess here 404s
- The ZH tree therefore needs no separate deploy; `build_docs.py` writes both and `mkdocs build --strict` ships them together

## QA audit
`.github/workflows/qa_report_quality.yml` runs nightly at 02:00 UTC in **two stages**:

1. **Rule-based (free, deterministic, pure-stdlib)** — `check_report_quality.py` → `qa/bad_reports_<date>.csv` + `qa/summary_<date>.txt`, then `check_mermaid.py`. Detection logic lives in `scripts/analysis/validate/__init__.py`. This is the primary gate; it catches mechanical failures (empty, refusal, truncated, placeholders, bad Mermaid)
2. **LLM review (OpenAI, costs tokens)** — `review_report_quality.py` → `qa/llm_review_<date>.csv` + `.txt`. Grades what regex cannot see: fabricated numbers, shallow analysis, conclusion-vs-evidence contradictions, simplified-Chinese leakage. Scores 5 dimensions 1–5 and returns `pass`/`warn`/`fail`

Then `prune_qa.py --keep 10` trims `qa/` to the 10 most recent run dates (it prunes *any* dated file, so new artifact types need no change there), and the workflow regenerates `qa/README.md` and commits.

Notes on stage 2:
- **Reviewer models are deliberately separate from the generation chain.** `REVIEWER_MODELS` in `review_report_quality.py`, not `resolve_chain()` — otherwise changing the generator's OpenAI model would silently re-point the auditor. One entry per provider (a `--cross-provider` switch must not hand Gemini an OpenAI model id), each a cheap model because cost is driven by *input* volume, not the ~300-token verdict. `--model` applies only to `--provider`
- **Rolling 2-day window** (`--days 2`), not "today": report-gen crons run 17:00–03:00 UTC, so one generation cycle straddles midnight and lands under two date stamps. A 1-day window silently skips the 17:00–23:00 batch (the majority of output)
- **Non-blocking** — exits 0 even on `fail` verdicts, so a bad night still commits an audit trail. `--fail-on-fail` opts into exit 1
- Per-report provider errors and unparseable responses become `ERROR` / `PARSE_ERROR` rows rather than aborting the run
- `refusal_retry=False` is mandatory: the refusal-override prefix in `analysis/utils/llm.py` instructs the model to *write a report*, which would turn the grader into a generator
- `--cross-provider` never lets a provider grade a report it generated (`parse_file` reads the generating provider from frontmatter). If no other provider has a key it exits 1 up front rather than silently self-grading
- **Stage 2 never sits on stage 1's critical path.** `openai` is installed *after* stage 1 runs, and the install / key check / review steps are all gated and `continue-on-error` — a missing secret or PyPI hiccup annotates the run but still commits the stage-1 audit
- **The report under review is untrusted input.** It is model output built partly from scraped news/RSS text, so an attacker-controlled headline can reach the judge. `REVIEWER_SYSTEM_MESSAGE` instructs the grader to ignore instructions inside `<report_data>`; the delimiters alone are not the boundary
- **The model's verdict is reconciled against its own scores** (`_enforce_verdict`), only ever downgraded. A `pass` alongside `data_integrity=1` would otherwise be filtered out of the problem CSV and never trip `--fail-on-fail`
- Malformed JSON *shapes* (a list under `dimensions`, a number under `issues`) raise `ValueError` → `PARSE_ERROR` row. `review_one`'s handler is deliberately broad: no single bad response may abort a 100-report batch
- Skippable/tunable from the GitHub UI via the `llm_review`, `llm_review_model`, `llm_review_days` and `llm_review_limit` dispatch inputs. A blank input adds no flag, so scheduled runs keep the script defaults. `llm_review_limit` exists for cheap model comparisons: selection is sorted, so the same cap over the same `--days` grades the same reports under two different `llm_review_model` values
- **stdout is this script's data channel, not a log channel.** The workflow tees stdout into the committed `qa/llm_review_<date>.txt`, but `analysis/utils/logging_utils.py` attaches its handler to *stdout* — so the first live run buried the summary under ~400 lines of per-call INFO noise and grew `qa/README.md` by 432 lines. `route_library_logs_to_stderr()` moves `analysis.*` handlers to stderr at the start of `main()`. Fixed locally rather than in the shared logger, because every other CLI wants its logs on stdout as ordinary CI output
- **The judge is reproducible, but ~a third of its verdicts are boilerplate.** Two live `gpt-4o-mini` runs over the same 117 reports agreed closely — 34/12/71 then 36/6/75 pass/warn/fail, with per-dimension means within 0.04 — so the scores are stable, not noisy. The problem is their content: ~25 rows per run score **1 on all five dimensions** and carry near-identical template prose across unrelated tickers, only ~6 of which quote any figure. At least one is checkably false (msft flagged for `$XXX`/`N/A` placeholders that appear **nowhere** in its 79 KB). The other ~56 rows are grounded — 29 quote figures that do exist, and `mu`'s `$90.27B` TTM revenue is a genuine fabrication (actual ≈ $37B) that stage 1 passed clean. So the aggregate fail rate is not actionable, but the grounded subset is exactly what this stage is for
- **`grounded` column / `verdict_is_grounded()`** implements that split: a `warn`/`fail` whose dimensions are *all* 1 **and** whose issues quote no figure traceable to the report is marked ungrounded. Such rows stay in the CSV for auditability but are excluded from the headline verdict counts and cannot trip `--fail-on-fail`. `pass` verdicts need no evidence, and an all-1s row that does cite a real figure is kept
- A larger model has **not** been compared yet; `llm_review_limit` makes that cheap. On current evidence the boilerplate looks more like a prompt/scoring-rubric problem than raw model capability
- Stage 2 also covers `ai_gen_report/market_news/`, which stage 1 currently does not (see `DEFAULT_ROOTS` in each)
- Prompt/rubric: `scripts/analysis/prompts/qa_review.txt` (escape literal JSON braces as `{{` `}}` — the template is `.format()`ed)
- **The rubric names three things that are explicitly NOT defects**, each traced to a wrong verdict in the third live run. Don't reintroduce them:
  1. **Missing source citations.** Reports are generated from a financial-data context that never appears in the report body, so they structurally cannot cite figures inline. 38 of that run's 54 grounded fails complained about this — an unsatisfiable criterion the original rubric asked for verbatim (「具體數字是否有來源脈絡」). `data_integrity` now judges whether a *number is credible*, not whether a citation is present
  2. **The report's own derived valuations.** 加權合理價值 / DCF 內在價值 / 目標價 / MOS are sourced to the report's own model, usually with assumptions shown in its DCF chapter — `amd`'s 「加權合理價值 $619.64」 is derived in its Ch.8, yet was failed as 來源不明. Criticise the *assumptions* instead
  3. **Self-flagged data anomalies.** `soxq` was failed for a 31.0% dividend yield that its own report had already identified as distorted and restated at 1.15%. That is good practice and now scores up, not down
- The rubric also states the evidence rule that `verdict_is_grounded()` enforces (low scores need a traceable quote), so a verdict is never quarantined for breaking a rule it was not given
