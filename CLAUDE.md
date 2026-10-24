# CLAUDE.md

Guidance for Claude Code in this repository. Detail lives in `docs/`, so read the
relevant doc before changing that area:

| Doc | Read before touching |
|-----|----------------------|
| `docs/ARCHITECTURE.md` | Package layout, analysis types, providers, CI workflows, adding a type or ticker |
| `docs/REPORT_PIPELINE.md` | `pipeline.py`, `context/`, `data/sources.py`, `data/technicals.py`, `validate/arithmetic.py`, LLM layer, market news |
| `docs/SITE_BUILD.md` | `build_docs.py`, `docs/overrides/`, stylesheets, JS, landing page, release, the ZH tree |
| `docs/QA_AUDIT.md` | `check_report_quality.py`, `review_report_quality.py`, `validate/`, `prompts/qa_review.txt` |
| `docs/PRICE_STORE_DESIGN.md` | `data/prices.py`, `price_analytics.py`, Market Data pages |
| `docs/RUNBOOK.md` | Re-running failed crons, provider outages |

## Commands

```bash
uv sync --extra dev                    # .venv from uv.lock (Python 3.11 per .python-version)
uv run pytest tests/ -v                # all tests; fully offline, no API keys
uv run pytest tests/test_llm.py -v     # one file

uv run python scripts/generate_analysis.py AAPL --analysis-type fundamental-analysis --provider gemini
uv run python scripts/generate_analysis.py MSFT --analysis-type technical-analysis --provider openai

# Docs site (MkDocs toolchain is not in uv.lock)
uv pip install "mkdocs-material==9.5.*" mkdocs-awesome-pages-plugin minify-html
uv run python scripts/build_docs.py && uv run mkdocs serve

gh workflow run daily_analysis.yml -f ticker=MSFT -f analysis_type=technical-analysis
make analyze TICKERS="NVDA TSLA" TYPES="fundamental-analysis,technical-analysis"
```

- Python >= 3.10 is required (`X | Y` annotations). CI runs 3.11 and 3.13.
- After editing dependencies in `pyproject.toml`, run `uv lock` and commit
  `uv.lock`. `tests.yml` installs with `--locked` and fails on a stale lockfile.

## Core flow

```
scripts/generate_analysis.py → analysis.pipeline.run_analysis()
  data/sources.py          fetch: yfinance + scrapers (complete bars only)
  context/__init__.py      assemble: one branch per type (+ fundamental_facts.py VERIFIED FIGURES)
  prompts/<type>.txt       template: {ticker} {financial_context} {today}
  utils/llm.py             generate: run_with_fallback over FALLBACK_CHAIN (gemini → openai)
  validate/arithmetic.py   recheck §8.8 and write the corrected sum back (fundamental)
  → ai_gen_report/{fundamental|technical|stock}/<ticker>/<prefix>_<date>_<provider>.md
scripts/build_docs.py      ai_gen_report/ + data/ → docs/ and docs/zh/ → mkdocs → GitHub Pages
```

All paths above are under `scripts/analysis/` unless shown otherwise.

## Rules that are easy to break

**Generation**
- Never return a refusal as a report. `call_llm` raises `RefusalError` after the
  last retry, so the chain falls through to the next provider.
- The model copies figures well and derives them badly. Compute derived numbers
  in Python (`fundamental_facts.py`) and have the prompt quote them.
- yfinance `revenueGrowth`, `earningsGrowth`, `earningsQuarterlyGrowth` and
  `operatingMargins` are **latest-quarter**, never TTM. Label them that way.
- Fetch Yahoo with `prices.to_yf_symbol(ticker)`. A bare `0050` returns 404.
- Technical runs abort without price bars (`require_price_history`). Never let
  the model invent a price.
- New report metadata goes in front matter. QA reads `price`, `price_date`,
  `levels` and `arithmetic_check` from there.

**Site**
- `docs/` is mostly generated (see `.gitignore`). Edit `ai_gen_report/`, `data/`
  and `scripts/`, not the output.
- Chart and statistics maths lives in Python (`price_analytics.py`,
  `fundamental_analytics.py`, `intrinsic_value.py`), never in JS.
- Raw-HTML hrefs must be written against the page's directory URL. MkDocs
  rewrites Markdown links, never raw ones.
- Every UI string goes in `LANG_TEXT` in `build_docs.py`, in **both** `en` and
  `zh`. The ZH tree mirrors index pages only, and the theme partials are written
  against the `mkdocs-material==9.5.*` pin.
- Colours are `--fp-*` tokens in `extra.css`. Report typography lives only in
  `report.css`. Material's root font-size is 20px.
- Never hardcode a release version in a template (`mkdocs_release_hook.py`
  injects it).

**QA**
- The reviewer must never be the generator. `REVIEWER_MODELS` is separate from
  `resolve_chain()`, and the reviewer runs with `refusal_retry=False`.
- The report under review is untrusted input (it contains scraped news).
- Stage 2 is non-blocking and must never sit on stage 1's critical path.
- Add a stage-1 check as a `content_findings()` pair plus an `ISSUE_TYPES`
  entry, not inline in `parse_file`.
- `qa_review.txt` is `.format()`ed, so escape JSON braces as `{{` `}}`.

**CI**
- Change shared CI behaviour in `.github/actions/` (`commit-and-push`,
  `python-env`, `build-site`), not in each workflow. No workflow uses pip
  directly.

## Common changes

**New analysis type:** add it to `ANALYSIS_TYPES` (with `prompt_file`), create
`prompts/<prompt_file>.txt`, add a branch in `context/__init__.py`, and add a
`lenses` / `fams` entry in `docs/overrides/home.html`.

**New daily ticker:** add it to `scripts/.ticker_schedule.json`, then add a
`cron:` **and** a matching `case` arm to `daily_analysis.yml` and
`daily_market_news.yml`. Then run `uv run pytest tests/test_workflows.py`.

**Release:** `gh workflow run release.yml -f bump=patch` (or `minor`, `major`,
`current`, or `-f version=X.Y.Z`; add `-f dry_run=true` to preview).
