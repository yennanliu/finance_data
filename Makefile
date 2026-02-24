## ── Variables ────────────────────────────────────────────────────────────────
GH        ?= $(shell which gh || echo /opt/homebrew/bin/gh)
GH_REPO   ?= yennanliu/finance_data
TICKERS   ?= AAPL
TYPES     ?= fundamental-analysis,technical-analysis
DELAY     ?= 20   # seconds between workflow dispatches (avoids concurrent rate limits)
TRIGGER   := GH_BIN="$(GH)" GH_REPO="$(GH_REPO)" TRIGGER_DELAY="$(DELAY)" bash scripts/trigger_analysis.sh

## ── Help ─────────────────────────────────────────────────────────────────────
.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'

## ── Analysis shortcuts ───────────────────────────────────────────────────────
.PHONY: analyze
analyze: ## Trigger workflows — e.g. make analyze TICKERS="IEF AGG VEA"
	$(TRIGGER) $(TICKERS) --types $(TYPES)

.PHONY: analyze-bonds
analyze-bonds: ## IEF AGG TLT — bond ETF suite
	$(TRIGGER) IEF AGG TLT --types $(TYPES)

.PHONY: analyze-intl
analyze-intl: ## VEA VWO EEM — international equity ETFs
	$(TRIGGER) VEA VWO EEM --types $(TYPES)

.PHONY: analyze-mag7
analyze-mag7: ## AAPL MSFT NVDA META AMZN GOOG TSLA
	$(TRIGGER) AAPL MSFT NVDA META AMZN GOOG TSLA --types $(TYPES)

.PHONY: analyze-watchlist
analyze-watchlist: ## Full personal watchlist
	$(TRIGGER) IEF AGG VEA NVDA TSLA PLTR RKLB ONDS AVAV KTOS --types $(TYPES)

## ── Advanced analysis shortcuts ──────────────────────────────────────────────
.PHONY: insider
insider: ## Insider trading analysis — e.g. make insider TICKERS="TSLA NVDA"
	$(TRIGGER) $(TICKERS) --types insider-trading

.PHONY: institutional
institutional: ## Institutional ownership — e.g. make institutional TICKERS="MSFT META"
	$(TRIGGER) $(TICKERS) --types institutional-ownership

.PHONY: earnings-call
earnings-call: ## Earnings call analysis — e.g. make earnings-call TICKERS="AAPL NVDA"
	$(TRIGGER) $(TICKERS) --types earnings-call-analysis

.PHONY: html-report
html-report: ## Generate interactive HTML report — e.g. make html-report TICKERS="AAPL"
	$(TRIGGER) $(TICKERS) --types report-generator

.PHONY: deep-dive
deep-dive: ## All 4 new analysis types for a single stock — e.g. make deep-dive TICKERS="NVDA"
	$(TRIGGER) $(TICKERS) --types earnings-call-analysis,insider-trading,institutional-ownership,report-generator
