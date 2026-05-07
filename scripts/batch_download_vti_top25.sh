#!/bin/bash
# Batch download recent 5-year 10-K reports for VTI Top 25 companies

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

declare -a SLUGS=(
    "nvidia-corporation"
    "apple-inc"
    "microsoft-corporation"
    "amazoncom-inc"
    "broadcom-inc"
    "google-inc"
    "meta-platforms-inc"
    "tesla-inc"
    "berkshire-hathaway"
    "oracle-corporation"
    "palantir-technologies-inc"
    "advanced-micro-devices-inc"
    "taiwan-semiconductor-manufacturing"
)

declare -a SYMBOLS=(
    "NVDA" "AAPL" "MSFT" "AMZN" "AVGO"
    "GOOGL" "META" "TSLA" "BRK.B" "ORCL"
    "PLTR" "AMD" "TSM"
)

TOTAL=${#SLUGS[@]}
SUCCESS=0
FAILED=0

echo "Batch 10-K Downloader — VTI Top 25 (last 5 years)"
echo "=================================================="

for i in "${!SLUGS[@]}"; do
    INDEX=$((i + 1))
    echo ""
    echo "[$INDEX/$TOTAL] ${SYMBOLS[$i]}"

    uv run "$SCRIPT_DIR/download_10k_pdf.py" "${SLUGS[$i]}"

    if [ $? -eq 0 ]; then
        SUCCESS=$((SUCCESS + 1))
    else
        FAILED=$((FAILED + 1))
        echo "  ✗ Failed: ${SYMBOLS[$i]}"
    fi

    [ $INDEX -lt $TOTAL ] && sleep 3
done

echo ""
echo "=================================================="
echo "Complete: $SUCCESS/$TOTAL succeeded, $FAILED failed"
