#!/usr/bin/env bash
# Uploads raw dataset to S3 using configuration from .env
# Usage: bash scripts/upload_data.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: .env file not found at $ENV_FILE" >&2
    echo "Run 'terraform apply' in infra/terraform/ first — it auto-generates .env." >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

RAW_DATA="$PROJECT_ROOT/data/raw/train_transaction.csv"
if [ ! -f "$RAW_DATA" ]; then
    echo "ERROR: Raw data file not found at $RAW_DATA" >&2
    exit 1
fi

DEST_S3="s3://${FRAUDGUARD_S3_BUCKET}/raw/train_transaction.csv"
echo "Uploading raw transaction dataset to S3..."
echo "  Source:      $RAW_DATA"
echo "  Destination: $DEST_S3"

aws s3 cp "$RAW_DATA" "$DEST_S3"

echo "Upload complete. EventBridge will trigger the SageMaker pipeline automatically."
