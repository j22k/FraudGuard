#!/usr/bin/env bash
# Loads .env from project root and runs the SageMaker pipeline.
# Usage: bash scripts/run_pipeline.sh (from project root)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: .env file not found at $ENV_FILE" >&2
    echo "" >&2
    echo "Run 'terraform apply' in infra/terraform/ first — it auto-generates .env." >&2
    exit 1
fi

# Export all non-comment, non-blank lines
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

echo "Loaded environment from .env"
echo "  AWS_REGION            = $AWS_REGION"
echo "  SAGEMAKER_ROLE_ARN    = $SAGEMAKER_ROLE_ARN"
echo "  FRAUDGUARD_S3_BUCKET  = $FRAUDGUARD_S3_BUCKET"
echo ""

python "$PROJECT_ROOT/ml/sagemaker_pipeline.py"
