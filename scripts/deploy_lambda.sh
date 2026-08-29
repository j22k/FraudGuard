#!/usr/bin/env bash
# Packages and updates the FraudGuard Lambda function code
# Usage: bash scripts/deploy_lambda.sh

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

FUNCTION_NAME="${LAMBDA_FUNCTION_NAME:-fraudguard-explainability-dev}"
LAMBDA_DIR="$PROJECT_ROOT/lambda"
ZIP_PATH="$LAMBDA_DIR/lambda_package.zip"

echo "Packaging Lambda code..."
rm -f "$ZIP_PATH"
(cd "$LAMBDA_DIR" && zip -r "$ZIP_PATH" handler.py bedrock_client.py)

echo "Uploading zip to S3..."
aws s3 cp "$ZIP_PATH" "s3://${FRAUDGUARD_S3_BUCKET}/lambda/lambda_package.zip"

echo "Updating Lambda function code ($FUNCTION_NAME)..."
aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --s3-bucket "$FRAUDGUARD_S3_BUCKET" \
    --s3-key "lambda/lambda_package.zip" \
    --region "${AWS_REGION:-us-east-1}"

echo "Lambda deployment complete."
