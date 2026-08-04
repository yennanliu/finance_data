# Project Architecture

## Overview

**finance_data** is an automated US stock analysis system that generates investment research reports with AI-powered insights and interactive technical charts.

```
Entry Points (scripts/)
    ↓
generate_analysis.py
    ↓ (dispatches)
    +→ analysis/ (package)
        ├── config/
        │   ├── __init__.py (ANALYSIS_TYPES, TODAY, model defaults)
        │   └── providers.py (provider-specific defaults)
        ├── utils/
        │   ├── llm.py (Claude/OpenAI API wrappers)
        │   ├── data_fetch.py (yfinance, Finviz, interactive charts)
        │   ├── context.py (analysis context assembly)
        │   ├── formatting.py (formatting utilities)
        │   └── logging_utils.py (logging setup)
        └── prompts/ (analysis type templates)
```

## Key Components

### Config
- **`config/__init__.py`** — `ANALYSIS_TYPES` dict (12 types), `DEFAULT_MODEL`, `DEFAULT_TOKENS`, `TODAY`
- **`config/providers.py`** — Per-provider defaults (Claude / Gemini: 32k tokens; OpenAI: 16k, the gpt-4o ceiling). Documentation of what each paired model can emit — the budget actually sent is `--max-tokens` (default `DEFAULT_TOKENS` = 32000) or, in CI, `.ticker_schedule.json`.

### Data Fetching (`utils/data_fetch.py`)
- `fetch_data(ticker)` — fetches OHLCV history + financials (yfinance, Finviz, StockAnalysis)
- `compute_technicals(hist)` — ASCII technical indicators (MA, RSI, MACD, etc.)

### Price store (`data/prices.py`)
- `data/prices/<ticker>.csv` — committed 10-year OHLCV store, the single source of
  truth for every chart on the site. Maintained by `scripts/update_prices.py`;
  chart payloads are derived from it by `build_docs.py` at build time and are not
  committed. Reports themselves carry no chart markup. See
  [`PRICE_STORE_DESIGN.md`](PRICE_STORE_DESIGN.md).

### LLM (`utils/llm.py`)
- `call_claude(...)` — Claude API with rate-limit retries + refusal-override
- `call_openai(...)` — OpenAI API with model-specific token caps + rate-limit retries
- `call_llm(..., provider, ...)` — dispatcher function

### Context Assembly (`utils/context.py`)
- `build_context(data, analysis_type)` — assembles data blocks for the chosen analysis type (12 branches)

### Entry Points

#### `generate_analysis.py`
```bash
python scripts/generate_analysis.py TICKER [--analysis-type TYPE] [--provider claude|openai] [--model ID] [--max-tokens N]
```
Generates AI-analyzed investment report with interactive candlestick chart.

#### `generate_market_news.py`
```bash
python scripts/generate_market_news.py TICKER [--provider claude|openai]
```
Generates market news summary (reuses `analysis/utils/llm.py`).

## Analysis Types (12 total)

| Type | Use Case |
|------|----------|
| `fundamental-analysis` | Deep financials: P/E, debt, ROE, growth + DCF intrinsic value (assumption reasoning chain + step-by-step arithmetic + audit checklist) |
| `technical-analysis` | Charts, MA, RSI, MACD, support/resistance |
| `stock-eval` | Comprehensive: fundamental + valuation |
| `stock-valuation` | DCF, EV/EBITDA, target price |
| `economics-analysis` | Macro environment impact |
| `sector-analysis` | Industry trends + peers |
| `portfolio-review` | Holdings performance + allocation |
| `earnings-call-analysis` | Sentiment + key themes from transcripts |
| `insider-trading` | Form 4 filings & smart money moves |
| `institutional-ownership` | 13F filings & smart money tracking |
| `financial-report-analyst` | 8-phase SEC filing audit |
| `report-generator` | Flexible HTML report builder |

## Provider Configuration

```python
# scripts/analysis/config/providers.py
PROVIDER_DEFAULTS = {
    "claude": {"default_model": "claude-sonnet-4-6", "default_tokens": 32000},
    "openai": {"default_model": "gpt-4o", "default_tokens": 16000},   # gpt-4o ceiling
    "gemini": {"default_model": "gemini-3.6-flash", "default_tokens": 32000},
}
```

Only `default_model` is read by code (`resolve_chain`); `default_tokens` documents
what each paired model can actually emit. The budget sent to the API comes from
`--max-tokens` (default `DEFAULT_TOKENS` = 32000) or `.ticker_schedule.json` in CI.
A full-length fundamental report (7000-10000 字, 11 chapters, Ch.8 DCF arithmetic)
needs ~32k output tokens to finish in one shot. `max_tokens` is a ceiling, not a
spend, so a generous value costs nothing on shorter reports. Two clamps apply:
`run_openai` caps at the model's own limit (gpt-4o: 16,384, so the OpenAI fallback
truncates full-length reports — use a gpt-5.6-* model to avoid that), and
`run_gemini` caps at 65,536 while auto-retrying at that ceiling on truncation.

## CI/CD: Daily Analysis Workflow

**File:** `.github/workflows/daily_analysis.yml`

**Schedule:** 21 tickers × 2 analysis types (fundamental + technical) = 42 daily jobs

**Ticker List:** `scripts/.ticker_schedule.json` (data-driven)

**Provider:** OpenAI (gpt-4o) by default

---

## How to Add a New Analysis Type

1. **Add to `ANALYSIS_TYPES`** in `scripts/analysis/config/__init__.py`:
   ```python
   "my-analysis": {
       "filename_prefix": "my_analysis",
       "label": "My Custom Analysis",
       "ext": ".md",
   }
   ```

2. **Create prompt template** at `scripts/analysis/prompts/my_analysis.txt` with placeholders:
   ```
   {ticker}
   {financial_context}
   {today}
   ```

3. **Add context builder** in `scripts/analysis/utils/context.py`:
   ```python
   elif analysis_type == "my-analysis":
       # Assemble relevant data blocks
       context = f"Financial data:\n{data.get('...', '')}"
       return context
   ```

4. **Test:**
   ```bash
   python scripts/generate_analysis.py AAPL --analysis-type my-analysis
   ```

---

## How to Add a New Ticker to Daily Schedule

1. **Edit** `scripts/.ticker_schedule.json`:
   ```json
   {
     "fundamental": [..., "NEWTICKER"],
     "technical": [..., "NEWTICKER"]
   }
   ```

2. **Add cron entries** to `.github/workflows/daily_analysis.yml`:
   ```yaml
   - cron: "0 21 * * *"  # 21:00 UTC → fundamental
   - cron: "10 23 * * *"  # 23:10 UTC → technical
   ```

3. **Commit & push** — workflow reads schedule.json at runtime

---

## Testing

**Run unit tests:**
```bash
pytest tests/ -v
```

**Test a single analysis locally:**
```bash
python scripts/generate_analysis.py MSFT --analysis-type technical-analysis
```

**Trigger CI manually:**
```bash
gh workflow run daily_analysis.yml -f ticker=MSFT -f analysis_type=technical-analysis
```

---

## Error Handling & Logging

- **Exceptions:** `AnalysisError`, `LLMError`, `DataFetchError` defined in `analysis/exceptions.py`
- **Logging:** Structured logging via `setup_logger()` in `analysis/utils/logging_utils.py`
- **Top-level:** `main()` in entry points catches exceptions and exits(1) on failure

---

## Performance Notes

- **Chart generation:** Plotly HTML embed (~47KB per report) — no external files
- **API calls:** Rate-limit retries with exponential backoff (30s base, up to 240s)
- **Refusal handling:** Up to 5 retry attempts with escalating temperature (0.7 → 1.0 → 1.2)
- **Data fetch:** Yfinance + 3 web scrapers (Finviz, StockAnalysis, ROIC.ai) — ~5-10s per ticker

---

## Files & Permissions

- `scripts/` — Runnable entry points
- `scripts/analysis/` — Package library
- `tests/` — pytest unit tests
- `.github/workflows/` — CI/CD automation
- `pyproject.toml` — Dependency declarations
