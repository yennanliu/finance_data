# Project Architecture

**finance_data** generates Traditional-Chinese investment research reports with
LLMs, checks them, and publishes them with MkDocs to GitHub Pages, together with
committed price and fundamentals datasets.

Related docs:

| Doc | Covers |
|-----|--------|
| [`REPORT_PIPELINE.md`](REPORT_PIPELINE.md) | How a report is produced and the safeguards on its figures |
| [`SITE_BUILD.md`](SITE_BUILD.md) | `build_docs.py`, page anatomy, styling, release, bilingual site |
| [`QA_AUDIT.md`](QA_AUDIT.md) | The nightly two-stage report audit |
| [`RUNBOOK.md`](RUNBOOK.md) | Re-running failed crons, provider failures |
| [`PRICE_STORE_DESIGN.md`](PRICE_STORE_DESIGN.md) | The OHLCV store and Market Data section |
| [`FUNDAMENTALS_STORE_EVAL.md`](FUNDAMENTALS_STORE_EVAL.md) | The SEC fundamentals store |

---

## System overview

```
            ┌──────────────── GitHub Actions (cron) ────────────────┐
            │                                                       │
 yfinance ─▶│ update_kline_data   → data/prices/<ticker>.csv        │
 SEC XBRL ─▶│ update_fundamentals → data/fundamentals/<ticker>.csv  │
            │                                                       │
 scrapers ─▶│ daily_analysis      → ai_gen_report/{fundamental,     │
 RSS/news ─▶│ daily_market_news       technical,stock,market_news}/ │
            │                                                       │
            │ qa_report_quality   → qa/                             │
            │ deploy (04:00 UTC)  → build_docs.py → mkdocs → Pages  │
            └───────────────────────────────────────────────────────┘
```

---

## Package layout (`scripts/analysis/`)

The library is layered: data → context → llm → pipeline → publish. Entry-point
scripts in `scripts/` are thin CLIs over it.

```
scripts/analysis/
├── config/
│   ├── __init__.py        ANALYSIS_TYPES (12), DEFAULT_MODEL, DEFAULT_TOKENS, REPORT_TEMPERATURE, TODAY
│   ├── providers.py       PROVIDER_DEFAULTS, FALLBACK_CHAIN, resolve_chain()
│   └── valuation.py       valuation assumptions and peer sets
├── data/                  network + stores + pure analytics
│   ├── sources.py         fetch_data(): yfinance + Finviz / StockAnalysis / Roic.ai; complete_bars()
│   ├── technicals.py      indicators (Wilder RSI/ATR), weekly bars, R1–S3 levels
│   ├── prices.py          committed OHLCV store (data/prices/), pure stdlib read path
│   ├── fundamentals.py    committed SEC quarterly store (data/fundamentals/)
│   ├── report_inputs.py   inputs for the VERIFIED FIGURES block
│   ├── price_analytics.py         returns, drawdown, volatility, histograms, averages
│   ├── fundamental_analytics.py   TTM, margins, multiples, split adjustment
│   └── intrinsic_value.py         DCF, reverse DCF, sensitivity, WACC build-up
├── context/
│   ├── __init__.py        build_context(): one branch per analysis type
│   └── fundamental_facts.py   VERIFIED FIGURES block (pure)
├── llm/__init__.py        public LLM API (re-exports utils/llm.py)
├── prompts/*.txt          one template per analysis type, plus system and QA prompts
├── pipeline.py            run_analysis(): fetch → assemble → generate → recheck → publish
├── publish.py             dedup_path(), frontmatter()
├── validate/              report checks used by QA stage 1 and the pipeline
│   ├── __init__.py        ISSUE_TYPES, parse_file, content_findings
│   ├── arithmetic.py      §8.8 / MOS recheck and write-back
│   ├── technical.py       NaN, price, level and R/R checks
│   └── market_data.py     front-matter price vs the price store
├── utils/
│   ├── llm.py             run_claude / run_openai / run_gemini, call_llm, run_with_fallback
│   ├── mermaid.py         Mermaid sanitising
│   ├── formatting.py, logging_utils.py
│   └── context.py, data_fetch.py   back-compat shims
└── exceptions.py          AnalysisError, LLMError, RefusalError, DataFetchError, ConfigError
```

### Entry points (`scripts/`)

| Script | Purpose |
|--------|---------|
| `generate_analysis.py` | One report: `TICKER [--analysis-type T] [--provider claude\|openai\|gemini] [--model ID] [--max-tokens N] [--output-dir D]` |
| `generate_market_news.py` | Daily news digest for one ticker (same provider flags) |
| `generate_stock_watchlist.py` | Pre-market fundamental watchlist |
| `build_docs.py` | Generates `docs/` (EN + ZH) from reports and stores |
| `update_prices.py`, `update_fundamentals.py` | Refresh the committed stores |
| `check_report_quality.py`, `check_mermaid.py`, `review_report_quality.py`, `prune_qa.py` | QA audit |
| `download_10k_edgar.py`, `download_10q_edgar.py`, `download_10k_pdf.py`, `download_grab_6k*.py` | SEC filing downloaders |
| `maintain_ai_gen_report.py` | `reorg` / `prune --before YYYY-MM-DD` |
| `release_version.py`, `mkdocs_release_hook.py`, `mkdocs_minify_hook.py` | Release and build hooks |
| `rerun_failed_cron.sh`, `trigger_analysis.sh` | Ops helpers (see `RUNBOOK.md`, `Makefile`) |

---

## Analysis types

Defined in `ANALYSIS_TYPES`. Each entry's `prompt_file` names its template in
`prompts/`. Output goes to `ai_gen_report/fundamental/` (fundamental),
`ai_gen_report/technical/` (technical) or `ai_gen_report/stock/` (everything
else), under `<ticker>/<filename_prefix>_<date>_<provider>.md` (e.g.
`technical_analysis_2026-10-24_gemini.md`).

| Type | Use case |
|------|----------|
| `fundamental-analysis` | Financials, growth, DCF + weighted fair value (11 chapters) |
| `technical-analysis` | Trend, MA, RSI, MACD, support/resistance, trade plan |
| `stock-eval` | Fundamental + valuation overview |
| `stock-valuation` | DCF, EV/EBITDA, target price |
| `economics-analysis` | Macro environment impact |
| `sector-analysis` | Industry trends and peers |
| `portfolio-review` | Holdings performance and allocation |
| `earnings-call-analysis` | Sentiment and key themes from transcripts |
| `insider-trading` | Form 4 activity |
| `institutional-ownership` | 13F holdings changes |
| `financial-report-analyst` | SEC filing audit |
| `report-generator` | Interactive HTML report |

### Adding an analysis type

1. Add an entry to `ANALYSIS_TYPES` in `config/__init__.py`, including its
   `prompt_file`. `PROMPT_MAP` is derived from that field, so there is no second
   map to edit.
2. Create `prompts/<prompt_file>.txt` (placeholders: `{ticker}`,
   `{financial_context}`, `{today}`).
3. Add a context branch in `context/__init__.py`.
4. Add the type to the `lenses` / `fams` COPY entries in
   `docs/overrides/home.html` (the landing page's analysis wheel).
5. Test: `uv run python scripts/generate_analysis.py AAPL --analysis-type <type>`.

---

## Providers

```python
# scripts/analysis/config/providers.py
PROVIDER_DEFAULTS = {
    "claude": {"default_model": "claude-sonnet-4-6", "default_tokens": 32000},
    "openai": {"default_model": "gpt-4o",            "default_tokens": 16000},  # gpt-4o ceiling
    "gemini": {"default_model": "gemini-3.8-flash",  "default_tokens": 32000},
}
FALLBACK_CHAIN = ["gemini", "openai"]
```

CI reads its provider, model and token budget from `defaults` in
`scripts/.ticker_schedule.json`. See [`REPORT_PIPELINE.md`](REPORT_PIPELINE.md#llm-layer)
for retries, refusals and token clamps.

---

## CI/CD

| Workflow | Schedule (UTC) | What it does |
|----------|----------------|--------------|
| `daily_analysis.yml` | 61 slots, 17:00–03:00 | One ticker × type per slot: 36 fundamental + 25 technical |
| `daily_market_news.yml` | 38 slots, 17:00–23:10 | One news digest per ticker |
| `daily_stock_watchlist.yml` | 22:00 | Pre-market watchlist |
| `qa_report_quality.yml` | 02:00 | Two-stage QA audit → `qa/` |
| `cleanup_refusals.yml` | 02:00 | Removes refusal posts |
| `update_fundamentals.yml` | Sun 03:00 | Refreshes `data/fundamentals/` from SEC companyfacts |
| `update_kline_data.yml` | 03:30 | Refreshes `data/prices/` |
| `deploy.yml` | 04:00, plus pushes that touch site config/assets | `build_docs.py` + `mkdocs build --strict` → GitHub Pages |
| `daily_progress.yml` | 00:40 | Daily progress summary |
| `prune_old_reports.yml` | 04:30 on the 1st | Deletes reports older than 90 days |
| `download_10k.yml`, `download_10q.yml` | 1st of the month | SEC filings |
| `scraper_smoke.yml` | Mon 06:00 | Live check of the web scrapers |
| `advanced_analysis.yml` | manual | Earnings-call, insider, 13F and HTML reports |
| `release.yml` | manual | Version bump, GitHub Release, deploy |
| `sample_build.yml` | manual | Small smoke build of the site |
| `tests.yml` | push / PR | pytest on Python 3.11 and 3.13 (`uv sync --locked`) |

Shared steps live in composite actions under `.github/actions/`:
`commit-and-push` (stage, commit, rebase-retry, push), `python-env`
(setup-python + `uv pip install`; no workflow uses pip directly) and
`build-site` (MkDocs install, generate, stamp, build). Change CI behaviour there
rather than in each workflow.

### Adding a ticker to the daily schedule

1. Add it to `scripts/.ticker_schedule.json`. This list also drives the price
   store's ticker universe.
2. Add a `cron:` entry **and** a matching `case` arm in
   `.github/workflows/daily_analysis.yml`. A scheduled run only knows its cron
   string, so the arm is what maps it to a ticker. Do the same in
   `daily_market_news.yml`.
3. Run `uv run pytest tests/test_workflows.py`. It fails if a cron has no arm (or
   an arm has no cron), or if two crons resolve to the same ticker and type. An
   unmapped cron also fails the run itself rather than publishing a duplicate
   report.

---

## Testing

```bash
uv sync --extra dev
uv run pytest tests/ -v
```

Tests are fully offline. Network, SDK and Selenium boundaries are mocked, so no
API keys are needed. After changing dependencies in `pyproject.toml`, run
`uv lock` and commit `uv.lock`: `tests.yml` installs with `--locked` and fails on
a stale lockfile.
