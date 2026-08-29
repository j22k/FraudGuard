#!/usr/bin/env bash
# Runs SageMaker Batch Transform using the latest approved model
# Usage: bash scripts/run_batch_transform.sh s3://bucket/processed/test/ [--wait]

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <input-s3-uri> [--wait]"
    echo "Example: $0 s3://my-bucket/processed/test/ --wait"
    exit 1
fi

INPUT_S3="$1"
WAIT_FLAG="${2:-}"

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

echo "Loaded environment from .env"
echo "  AWS_REGION:             $AWS_REGION"
echo "  SAGEMAKER_ROLE_ARN:     $SAGEMAKER_ROLE_ARN"
echo "  FRAUDGUARD_S3_BUCKET:   $FRAUDGUARD_S3_BUCKET"
echo ""

cd "$PROJECT_ROOT"
if [ "$WAIT_FLAG" == "--wait" ]; then
    python "$PROJECT_ROOT/ml/batch_transform.py" --input-s3 "$INPUT_S3" --wait
else
    python "$PROJECT_ROOT/ml/batch_transform.py" --input-s3 "$INPUT_S3"
fi
