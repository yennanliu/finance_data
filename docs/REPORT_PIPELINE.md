# Report Pipeline

How one report is produced, and the safeguards that keep its figures honest. For
the package layout, see [`ARCHITECTURE.md`](ARCHITECTURE.md). For the nightly
audit that checks the output, see [`QA_AUDIT.md`](QA_AUDIT.md).

```
generate_analysis.py  →  analysis.pipeline.run_analysis()
  fetch      analysis.data.sources.fetch_data()        yfinance + Finviz / StockAnalysis / Roic.ai
  assemble   analysis.context.build_context()          one branch per analysis type
             + context/fundamental_facts.py            VERIFIED FIGURES (fundamental only)
  generate   analysis.llm.run_with_fallback()          gemini → openai
  recheck    pipeline.recheck_valuation()              §8.8 arithmetic (fundamental only)
  publish    analysis.publish                          front matter + dated file
```

---

## LLM layer

Code: `scripts/analysis/utils/llm.py`, re-exported as `analysis.llm`.

- **Fallback chain.** `FALLBACK_CHAIN` in `config/providers.py` (currently
  `["gemini", "openai"]`) is resolved by `resolve_chain()` into ordered
  `(provider, model)` attempts. `run_with_fallback()` returns the first success.
  The context is fetched once and reused across attempts. `--provider` moves a
  provider to the front of the chain.
- **Rate limits** are retried with exponential backoff (30 s base, 5 attempts).
- **Refusals.** A short reply matching a refusal pattern is retried up to 5 times
  with an override prefix and rising temperature. A model that still refuses
  raises `RefusalError`. That error is not terminal, so the chain falls through
  to the next provider. Returning the refusal as a report is what published
  MRVL's one-line 2026-10-22 report.
- **Sampling.** Reports are sampled at `REPORT_TEMPERATURE` (0.3, in
  `config/__init__.py`).
- **Token budget.** The budget sent is `--max-tokens` (default `DEFAULT_TOKENS` =
  32000), or `defaults.max_tokens` in `.ticker_schedule.json` in CI. A full
  fundamental report (11 chapters, Ch.8 DCF arithmetic) needs ~32k output tokens.
  `run_openai` clamps to the model's own ceiling (`OPENAI_MAX_TOKENS`; gpt-4o is
  16,384, so the OpenAI fallback truncates full-length reports). `run_gemini`
  clamps to 65,536 and retries at that ceiling on truncation.
  `PROVIDER_DEFAULTS[*].default_tokens` documents what each model can emit; only
  `default_model` is read by code.

---

## Fundamental reports

### VERIFIED FIGURES block

The model copies figures reliably and derives them badly. So the figures that
need deriving are computed in Python and handed to the model as a block it is
told to quote (rule 19 in `prompts/fundamental.txt`).

- Builder: `context/fundamental_facts.py` (pure). Inputs:
  `data/report_inputs.py`. Assumptions and peer sets: `config/valuation.py`.
- Contents:
  - TTM figures from the SEC fundamentals store, refreshed live from companyfacts
  - TTM-vs-prior-TTM growth, kept apart from latest-quarter growth
  - FCF = OCF − capex
  - CAPM / WACC inputs
  - Multiples vs their own 5-year history
  - Peer multiples

### yfinance field labelling

yfinance `info` fields are labelled with their period in the shared context:

- `revenueGrowth`, `earningsGrowth`, `earningsQuarterlyGrowth` and
  `operatingMargins` are the **latest quarter**, never TTM.
- Yahoo's `freeCashflow` is its "levered FCF" and is not passed on.
- Ratios that mix quote and statement currencies (ADRs such as TSM and SKHY) are
  withheld.
- `fetch_data` asks Yahoo for `prices.to_yf_symbol(ticker)`. A bare `0050`
  returns 404.

### §8.8 recheck and write-back

After generation, `pipeline.recheck_valuation()` recomputes §8.8's weighted fair
value from the report's own `value × weight` terms (`validate/arithmetic.py`) and
appends a 「程式複算」 block.

- **Corrected.** On a mismatch whose weights sum to 100%, `arithmetic.correct()`
  writes the sum back: the stated total wherever it is printed, plus MOS /
  upside near their labels or beside the fair value, matched by value at the
  printed precision. On a line that itself names MOS / upside or shows the fair
  value, a decimal percent one unit off also matches (MRVL 2026-10-27 printed
  −30.0% for −29.94%), and the "fair value − price" difference (−$70.00) is
  rewritten too. Front matter records `arithmetic_check: corrected`. The
  model's figure is kept in `weighted_fair_value_stated` and in a one-line notice
  under the title. The notice also warns when the new MOS crosses a rule-20
  rating band.
- **Why write back.** The earlier notice-only approach left 22 of 35 reports on
  2026-10-23 opening with a banner saying their headline value was wrong.
- **Not corrected** when the stated total equals one of the terms (TSLA, INTC
  and NVDA printed one method's value as the total, and a global replace would
  rewrite that term) or when the weights don't sum to 100%. Those keep the
  「應為」 notice. Other derivation steps are left to `derivation.fix()`
  (below).
- **Older reports.** `scripts/recheck_fundamental_reports.py` gives a report
  written before this recheck existed what the pipeline would give it today:
  `recheck_valuation` (correct, product line, annotation, front matter) for one
  with no recheck or only a 「應為」 notice, then `derivation.fix` for all. It
  rewrites a file only when the body changes and is idempotent. A report whose
  §8.8 already adds up gets no recap block. Run on 2026-10-30, it corrected 300
  reports and flagged 36 more it could not correct (stage-1 `ARITHMETIC` went
  from 376 to 86). 31 corrections move MOS into another rule-20 band; their
  notice says so, and their rating text is left as the model wrote it.
- **Backfill 2026-10-30.** The 35 reports already marked `corrected` that still
  carried a stale MOS, upside or difference were re-run through `correct()`.
  Only decimal-percent and dollar changes were kept; whole percents and the
  「程式複算」 notice lines were left as written.

- **Product line.** `arithmetic.fix_products()` then rewrites §8.8's
  `= $a + $b + … = $S` line so each product is its term's `value × weight`.
  It runs only once the total is right (`ok` or `corrected`), and only on a run
  of exactly one amount per term, each within 25% of its product, followed by
  its own `= $S` that the rewritten products, as printed, add up to. Otherwise a product the model got wrong keeps adding
  up to the old total.

### Equation chains (every report type)

`validate/derivation.py` evaluates every `=` / `≈` link of each `$$ … $$` and
inline `$ … $` span. Inline maths is told apart from prose prices by
`INLINE_MATH`: no space inside either `$`, at least one TeX command, and no digit
after the closing `$`.
RKLB 2026-10-28 printed `$28.825 + … + $5.108 = $59.323 ≈ $58.90` and
`\frac{$58.90 − $58.60}{$58.90} = \frac{+$0.72}{$58.90} = +0.5%`. Both ends of
each chain were right and the middle was invented. `run_analysis` calls
`derivation.fix()` on every report. It changes one number only: the single new
number in a middle step whose two neighbours agree, re-solved so the step holds
($59.323 → $58.903, $0.72 → $0.30). Front matter records `derivation_fixed: N`.
Any other broken link is left as written for stage-1 QA (`DERIVATION`). The
prompt (rule 18) says every `=` must hold and `≈` is only for rounding.

---

## Technical reports

Code: `data/sources.complete_bars`, `data/technicals.py`.

- **Only complete bars.** For a while after the close, Yahoo publishes the new
  session's bar with volume but NaN prices. That once gave eight reports a
  `$nan` close and no levels. Trailing NaN-close bars and an in-progress session
  are dropped. A newer official close from the quote is appended
  (`close_source: quote` in front matter).
- **No bars, no report.** `pipeline.require_price_history` aborts a technical run
  that has no bars or price, rather than let the model invent one (0050 was
  affected all through October).
- **Indicators.** RSI and ATR use Wilder smoothing. Weekly rows are labelled by
  their last trading day, never a future Sunday.
- **Candlestick claims.** The context carries the last 10 daily and 8 weekly OHLC
  bars. The prompt allows candlestick claims about those bars only.
- **Levels.** The computed R1–S3 are written to front matter as `levels`, which
  stage-1 QA compares with Ch.4.

---

## Front matter (provenance)

Every report records how it was made, so QA can check it later:

| Field | Meaning |
|-------|---------|
| `price`, `price_date` | The close the model was given, and its session date |
| `close_source` | `quote` when the last close came from the quote, not a bar |
| `levels` | Computed R1–S3 (technical) |
| `arithmetic_check`, `weighted_fair_value_stated` | §8.8 recheck result (fundamental) |
| `derivation_fixed` | Numbers `derivation.fix()` re-solved in a `$$ … $$` or inline `$ … $` equation chain |
| `data_sources_ok`, `data_sources_failed` | Which fetchers succeeded |
| `prompt_sha256`, `temperature`, `max_tokens` | Reproducibility |

---

## Market news

Code: `scripts/generate_market_news.py`.

- **Sources:** Yahoo (`sources.yahoo_news()`), four keyword RSS feeds and
  Perplexity Discover. Results are merged and de-duplicated by title. Every
  source fails soft to `[]`.
- **Perplexity** (`perplexity.ai/discover`) is behind Cloudflare and has no feed.
  It is read without a key through Google News `site:perplexity.ai when:7d`,
  keeping only titles that name the ticker (case-sensitive) or the company's
  short name. The raw search is mostly other companies' articles and quote pages.
