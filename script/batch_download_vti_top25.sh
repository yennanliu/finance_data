#!/bin/bash
# Batch download 10-K reports for VTI Top 25 companies

echo "=========================================="
echo "Batch 10-K Downloader - VTI Top 25"
echo "=========================================="
echo ""

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Array of company slugs from the data file
declare -a COMPANIES=(
    "nvidia-corporation"
    "apple-inc"
    "microsoft-corporation"
    "amazoncom-inc"
    "broadcom-inc"
    "google-inc"
    "meta-platforms-inc"
    "tesla-inc"
    "berkshire-hathaway"
    "jpmorgan-chase-co"
    "eli-lilly-co"
    "visa-inc"
    "exxon-mobil-corporation"
    "netflix-inc"
    "johnson-johnson"
    "mastercard-incorporated"
    "walmart-inc"
    "oracle-corporation"
    "palantir-technologies-inc"
    "advanced-micro-devices-inc"
    "costco-wholesale-corporation"
    "abbvie-inc"
    "the-home-depot-inc"
    "procter-gamble-co"
)

declare -a SYMBOLS=(
    "NVDA"
    "AAPL"
    "MSFT"
    "AMZN"
    "AVGO"
    "GOOGL"
    "META"
    "TSLA"
    "BRK.B"
    "JPM"
    "LLY"
    "V"
    "XOM"
    "NFLX"
    "JNJ"
    "MA"
    "WMT"
    "ORCL"
    "PLTR"
    "AMD"
    "COST"
    "ABBV"
    "HD"
    "PG"
)

# Total count
TOTAL=${#COMPANIES[@]}
SUCCESS=0
FAILED=0

# Log file
LOG_FILE="$PROJECT_DIR/batch_download_$(date +%Y%m%d_%H%M%S).log"
echo "Log file: $LOG_FILE"
echo ""

# Loop through each company
for i in "${!COMPANIES[@]}"; do
    COMPANY="${COMPANIES[$i]}"
    SYMBOL="${SYMBOLS[$i]}"
    INDEX=$((i + 1))

    echo "=========================================="
    echo "[$INDEX/$TOTAL] Processing: $SYMBOL - $COMPANY"
    echo "=========================================="

    # Run the download script with uv
    uv run "$SCRIPT_DIR/download_10k_pdf.py" "$COMPANY" 2>&1
    EXIT_CODE=$?

    # Check exit status
    if [ $EXIT_CODE -eq 0 ]; then
        SUCCESS=$((SUCCESS + 1))
        echo "✓ Completed: $SYMBOL" | tee -a "$LOG_FILE"
    else
        FAILED=$((FAILED + 1))
        echo "✗ Failed: $SYMBOL" | tee -a "$LOG_FILE"
    fi

    echo "" | tee -a "$LOG_FILE"

    # Add a small delay between companies to be respectful
    if [ $INDEX -lt $TOTAL ]; then
        echo "Waiting 3 seconds before next company..." | tee -a "$LOG_FILE"
        sleep 3
    fi
done

# Final summary
echo "=========================================="
echo "BATCH DOWNLOAD COMPLETE"
echo "=========================================="
echo "Total companies: $TOTAL"
echo "Successful: $SUCCESS"
echo "Failed: $FAILED"
echo "Log file: $LOG_FILE"
echo "=========================================="
