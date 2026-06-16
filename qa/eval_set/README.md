# Eval Set — labelled samples for retrieval precision/recall (P3)

Each JSON file is one labelled report sample consumed by
`scripts/eval/retrieval.py` (via `run_eval.py --eval-set qa/eval_set`).

Filename convention: `<TICKER>_<DATE>.json`

## Schema

```json
{
  "ticker": "AAPL",
  "date": "2026-06-16",
  "analysis_type": "market-news",

  "retrieved_docs": [
    {"id": "n1", "title": "...", "publisher": "Bing News", "summary": "..."}
  ],

  "relevance_labels": { "n1": 1, "n2": 0 },

  "gold_events": ["Q3 earnings beat", "new product launch"],

  "report_md": "optional — paste report body so recall can match gold events"
}
```

- **`relevance_labels`** → drives **precision** (relevant retrieved / total retrieved).
  Label `1` = relevant to analysing the ticker, `0` = noise (same-name company,
  quote-listing page, stale, off-topic). Can be bootstrapped by the
  `context_relevance` judge, then human-corrected.
- **`gold_events`** → drives **recall** (gold events covered / total gold events).
  The events that *should* have been surfaced that day. Hardest to build; start
  with a handful of tier-1 tickers for one week.

`retrieved_docs` can be copied straight from a report's `.context.json` sidecar
(`retrieved_docs` field), so you only need to add the labels.

See `qa/RAG_EVALUATION.md` for the full methodology.
