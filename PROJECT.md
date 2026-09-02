# Project: FraudGuard Phase 4

## Architecture
FraudGuard Phase 4 provides the serverless explainability and event-driven automation layer:
1. **S3 & EventBridge**: Batch transform outputs CSV results into `s3://{BUCKET}/inference-output/`. S3 event notification emits `Object Created` event to EventBridge. EventBridge rule `s3_inference_output_rule` matches prefix `"inference-output/"` and triggers Lambda.
2. **Lambda Explainability Layer**: `lambda/handler.py` parses the EventBridge event, fetches and streams `results.csv` from S3.
3. **Bedrock Claude 3 Haiku Integration**: For fraud-positive rows (`fraud_score > 0.9`), `lambda/bedrock_client.py` constructs a structured prompt using human-readable features (`TransactionAmt`, `hour_of_day`, `P_emaildomain_bucket`, `card4`, `card6`, `ProductCD`) and invokes `anthropic.claude-3-haiku-20240307-v1:0` via AWS Bedrock Runtime Messages API. Clean transactions (`fraud_score <= 0.9`) are skipped with zero Bedrock / DynamoDB calls (cost rule).
4. **DynamoDB Persistence**: Explanations and transaction metadata are saved to DynamoDB with partition key `TransactionID` (String), `txn_id` (String), `fraud_score` (Decimal), `explanation` (String), and ISO-8601 UTC `timestamp` (String).
5. **Terraform Infrastructure**: Modular IaC in `infra/terraform/modules/lambda/` and updated root `main.tf`, `modules/eventbridge/`, `outputs.tf`, `env_file.tf`, with anti-circular `aws_lambda_permission` in root `main.tf`.
6. **Workflow Scripts**: `scripts/upload_data.ps1`, `scripts/deploy_lambda.ps1`, and `scripts/run_dashboard.ps1` (running live ops console on `http://localhost:8080`).
7. **Test Fixtures & Mock Test Suite**: `tests/fixtures/sample_fraud_event.json`, `tests/fixtures/sample_results.csv` (5 rows, 2 fraud-positive > 0.9, 3 clean < 0.5), and `tests/test_handler.py` unit testing with mock AWS clients.
8. **Visual Assets & Reports**: Official AWS Architecture GIF (`docs/img/AWS-services-fraud-guard.gif`), Live Web Console Screenshot (`docs/img/web.png`), and [Production Gap Audit](docs/PRODUCTION_GAP_AUDIT.md).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F1 | Lambda Bedrock Client | `lambda/bedrock_client.py` calling Bedrock Claude 3 Haiku Messages API with human-readable transaction features | M1 | Survey (R1) |
| F2 | Lambda Event Handler | `lambda/handler.py` parsing EventBridge S3 events, streaming CSV, threshold filter >0.9, Decimal DynamoDB writes | M1 | Survey (R1) |
| F3 | Lambda Requirements | `lambda/requirements.txt` with runtime/dev dependencies (boto3, pandas, pytest) | M1 | Survey (R1) |
| F4 | Lambda Terraform Module | `infra/terraform/modules/lambda/` (`main.tf`, `variables.tf`, `outputs.tf`) with Python 3.12, 256MB, 300s timeout, 14-day CloudWatch log group | M2 | Survey (R2) |
| F5 | Root Terraform & EventBridge Wiring | Root `main.tf` module call + `aws_lambda_permission`, `modules/eventbridge/` second rule + target, `outputs.tf`, `env_file.tf` | M2 | Survey (R3) |
| F6 | IAM Role S3 Read Addition | `infra/terraform/modules/iam/main.tf` grant `s3:GetObject` on S3 bucket to Lambda execution role | M2 | Survey (R2/R3) |
| F7 | S3 Data Upload Script | `scripts/upload_data.ps1` with `.env` guard, validation, and `aws s3 cp` | M3 | Survey (R4) |
| F8 | Lambda Packaging & Deploy Script | `scripts/deploy_lambda.ps1` with zip packaging (excluding pycache/requirements), S3 upload, update-function-code + first-run fallback | M3 | Survey (R4) |
| F9 | EventBridge S3 Event Fixture | `tests/fixtures/sample_fraud_event.json` with AWS EventBridge Object Created schema | M4 | Survey (R5) |
| F10 | Batch Transform Results CSV Fixture | `tests/fixtures/sample_results.csv` with 5 rows (2 fraud >0.9, 3 clean <0.5) and 64-feature subset | M4 | Survey (R5) |
| F11 | Offline Unit Test Suite | `tests/test_handler.py` testing Bedrock call counts (=2), DynamoDB writes (=2), Decimal types, zero clean calls, and threshold overrides | M4 | Survey (R5) |
| F12 | Full Verification & Gate Pass | Passing `terraform validate`, `pytest tests/test_handler.py -v`, script execution & package generation | M5 | Acceptance Criteria |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Lambda Application Code | `lambda/bedrock_client.py`, `lambda/handler.py`, `lambda/requirements.txt` (F1, F2, F3) | none | DONE |
| M2 | Terraform Infrastructure | `infra/terraform/modules/lambda/`, `modules/eventbridge/`, `modules/iam/`, `main.tf`, `variables.tf`, `outputs.tf`, `env_file.tf` (F4, F5, F6) | none | DONE |
| M3 | Workflow PowerShell Scripts | `scripts/upload_data.ps1`, `scripts/deploy_lambda.ps1` (F7, F8) | M1 | DONE |
| M4 | Test Fixtures & Unit Tests | `tests/fixtures/sample_fraud_event.json`, `tests/fixtures/sample_results.csv`, `tests/test_handler.py` (F9, F10, F11) | M1 | DONE |
| M5 | Final Integration & Gate Audit | Complete test verification, terraform validate, package zip generation, and forensic audit (F12) | M1, M2, M3, M4 | DONE |

## Interface Contracts

### Lambda Handler ↔ EventBridge S3 Event
- Input format: EventBridge Detail object:
  ```json
  {
    "detail": {
      "bucket": { "name": "bucket-name" },
      "object": { "key": "inference-output/results.csv" }
    }
  }
  ```
  Fallback format: S3 Direct Notification `event["Records"][0]["s3"]["bucket"]["name"]` & `["object"]["key"]`.

### Lambda Handler ↔ Bedrock Client
- Signature: `explain(txn_id: str, fraud_score: float, features: dict) -> str`
- Prompt human-readable features: `TransactionAmt`, `hour_of_day`, `ProductCD`, `card4`, `card6`, `P_emaildomain_bucket`.
- Model ID: `anthropic.claude-3-haiku-20240307-v1:0` via Anthropic Messages API (`anthropic_version: "bedrock-2023-05-31"`).
- Return: Plain-English explanation string.

### Lambda Handler ↔ DynamoDB Table
- Partition Key: `TransactionID` (String) matching `txn_id`.
- Attributes:
  - `TransactionID`: String
  - `txn_id`: String
  - `fraud_score`: Decimal (e.g. `Decimal("0.9421")`)
  - `explanation`: String
  - `timestamp`: ISO-8601 UTC String (`YYYY-MM-DDTHH:MM:SSZ`)

### Terraform EventBridge ↔ Root `main.tf` ↔ Lambda Module
- `module.eventbridge.inference_trigger_rule_arn` exported and consumed by `aws_lambda_permission.allow_eventbridge` in root `main.tf`.
- `module.lambda.function_arn` consumed by `module.eventbridge.lambda_function_arn`.
- `module.lambda.function_name` consumed by root `main.tf` permission and `env_file.tf`.

## Code Layout
```
FraudGuard/
├── lambda/
│   ├── handler.py
│   ├── bedrock_client.py
│   ├── requirements.txt
│   └── lambda_package.zip  (generated by deploy script)
├── infra/terraform/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── env_file.tf
│   └── modules/
│       ├── eventbridge/
│       │   ├── main.tf
│       │   ├── variables.tf
│       │   └── outputs.tf
│       ├── lambda/
│       │   ├── main.tf
│       │   ├── variables.tf
│       │   └── outputs.tf
│       ├── iam/
│       │   └── main.tf
│       └── dynamodb/
├── scripts/
│   ├── run_pipeline.ps1
│   ├── run_pipeline.sh
│   ├── upload_data.ps1
│   └── deploy_lambda.ps1
├── tests/
│   ├── fixtures/
│   │   ├── sample_fraud_event.json
│   │   └── sample_results.csv
│   └── test_handler.py
└── ml/
    └── model_artifacts/
        └── feature_list.txt
```
