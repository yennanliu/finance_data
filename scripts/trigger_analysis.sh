#!/usr/bin/env bash
# Usage:
#   ./scripts/trigger_analysis.sh TICKER [TICKER ...] [--types TYPE,TYPE]
#
# Examples:
#   ./scripts/trigger_analysis.sh IEF AGG VEA
#   ./scripts/trigger_analysis.sh AAPL --types fundamental-analysis
#   ./scripts/trigger_analysis.sh NVDA TSLA --types fundamental-analysis,technical-analysis

set -euo pipefail

GH="${GH_BIN:-gh}"
REPO="${GH_REPO:-yennanliu/finance_data}"
WORKFLOW="Daily Stock Analysis"
DEFAULT_TYPES="fundamental-analysis,technical-analysis"

# ── Parse args ────────────────────────────────────────────────────────────────
TICKERS=()
TYPES="$DEFAULT_TYPES"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --types)
      TYPES="$2"
      shift 2
      ;;
    --repo)
      REPO="$2"
      shift 2
      ;;
    -*)
      echo "Unknown flag: $1" >&2
      exit 1
      ;;
    *)
      TICKERS+=("$1")
      shift
      ;;
  esac
done

if [[ ${#TICKERS[@]} -eq 0 ]]; then
  echo "Usage: $0 TICKER [TICKER ...] [--types TYPE,TYPE] [--repo owner/repo]"
  echo ""
  echo "Available analysis types:"
  echo "  fundamental-analysis  technical-analysis  stock-eval"
  echo "  economics-analysis    portfolio-review     sector-analysis"
  exit 1
fi

# Split TYPES by comma into array
IFS=',' read -ra TYPE_LIST <<< "$TYPES"

# ── Trigger runs ──────────────────────────────────────────────────────────────
TOTAL=$(( ${#TICKERS[@]} * ${#TYPE_LIST[@]} ))
echo "Triggering ${TOTAL} workflow run(s) on [${REPO}]"
echo "  Tickers : ${TICKERS[*]}"
echo "  Types   : ${TYPE_LIST[*]}"
echo ""

SUCCESS=0
FAIL=0

for TICKER in "${TICKERS[@]}"; do
  for ATYPE in "${TYPE_LIST[@]}"; do
    printf "  %-8s %-30s ... " "$TICKER" "$ATYPE"
    if URL=$("$GH" workflow run "$WORKFLOW" --repo "$REPO" \
               --field ticker="$TICKER" \
               --field analysis_type="$ATYPE" 2>&1); then
      echo "OK  $URL"
      (( SUCCESS++ )) || true
    else
      echo "FAIL: $URL"
      (( FAIL++ )) || true
    fi
  done
done

echo ""
echo "Done: ${SUCCESS} triggered, ${FAIL} failed."
[[ $FAIL -eq 0 ]]
