#!/bin/bash
# Batch download recent 5-year 10-K reports for VTI Top 25 (via SEC EDGAR)

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# US domestic filers → 10-K
declare -a US_TICKERS=(
    "NVDA" "AAPL" "MSFT" "AMZN" "AVGO"
    "GOOGL" "META" "TSLA" "BRK.B" "ORCL"
    "PLTR" "AMD"
)

# Foreign private issuers → 20-F (equivalent of 10-K)
declare -a FOREIGN_TICKERS=("TSM")

TOTAL=$(( ${#US_TICKERS[@]} + ${#FOREIGN_TICKERS[@]} ))
SUCCESS=0
FAILED=0
INDEX=0

echo "Batch 10-K Downloader — VTI Top 25 (SEC EDGAR, last 5 years)"
echo "=============================================================="

for TICKER in "${US_TICKERS[@]}"; do
    INDEX=$((INDEX + 1))
    echo ""
    echo "[$INDEX/$TOTAL] $TICKER"
    uv run "$SCRIPT_DIR/download_10k_edgar.py" "$TICKER" && SUCCESS=$((SUCCESS + 1)) || FAILED=$((FAILED + 1))
    [ $INDEX -lt $TOTAL ] && sleep 1
done

for TICKER in "${FOREIGN_TICKERS[@]}"; do
    INDEX=$((INDEX + 1))
    echo ""
    echo "[$INDEX/$TOTAL] $TICKER (foreign filer → 20-F)"
    uv run "$SCRIPT_DIR/download_10k_edgar.py" "$TICKER" --form 20-F && SUCCESS=$((SUCCESS + 1)) || FAILED=$((FAILED + 1))
done

echo ""
echo "=============================================================="
echo "Complete: $SUCCESS/$TOTAL succeeded, $FAILED failed"
