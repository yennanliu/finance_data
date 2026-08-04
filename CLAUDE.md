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
  → scripts/analysis/utils/context.py      (assembles data into LLM-ready context, 12 branches)
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
- `scripts/analysis/utils/context.py` — 12-branch context assembler; touch when adding analysis types
- `scripts/analysis/utils/llm.py` — `call_llm()` dispatcher; handles rate-limit retries and refusal overrides
- `scripts/.ticker_schedule.json` — data-driven ticker list for daily CI jobs
- `.github/workflows/daily_analysis.yml` — cron that fires 42 jobs/day (21 tickers × 2 types)

### Adding a new analysis type
1. Add entry to `ANALYSIS_TYPES` in `scripts/analysis/config/__init__.py`
2. Create prompt at `scripts/analysis/prompts/<type>.txt` (placeholders: `{ticker}`, `{financial_context}`, `{today}`)
3. Add context-building branch in `scripts/analysis/utils/context.py`
4. Test: `python scripts/generate_analysis.py AAPL --analysis-type <type>`

### Adding a new ticker to daily schedule
1. Edit `scripts/.ticker_schedule.json`
2. Add cron entries in `.github/workflows/daily_analysis.yml`

## Report output
- Reports written as Markdown to `ai_gen_report/fundamental/<ticker>/`, `ai_gen_report/technical/<ticker>/`, or `ai_gen_report/stock/<ticker>/` depending on analysis type (see Core flow above)
- `build_docs.py` merges all three per ticker and copies them into `docs/reports/<ticker>/` and `docs/zh/reports/<ticker>/`
- `docs/` is auto-generated — edit source files in `ai_gen_report/` and `scripts/`, not in `docs/`
- `scripts/maintain_ai_gen_report.py` handles re-splitting (`reorg`) and pruning old dated reports (`prune --before YYYY-MM-DD`)

## QA audit
- `.github/workflows/qa_report_quality.yml` runs nightly at 02:00 UTC: `check_report_quality.py` → `qa/bad_reports_<date>.csv` + `qa/summary_<date>.txt`, then `check_mermaid.py`, then regenerates `qa/README.md`
- `scripts/prune_qa.py --keep 10` keeps only the 10 most recent run dates in `qa/`; the workflow runs it before committing
