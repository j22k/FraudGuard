# FraudGuard ML — Project Context

## What this is
Production-grade AWS fraud detection pipeline. Portfolio + LinkedIn piece. Not toy code.

## Stack
- XGBoost binary classifier, SageMaker Pipelines (train/eval/register)
- Batch transform inference (NOT real-time endpoint) — cost control
- Bedrock Claude Haiku — explainability, fraud-positive txns ONLY
- EventBridge — fires on fraud-positive inference event
- Lambda (Python 3.12) — receives event, calls Bedrock, writes DynamoDB
- DynamoDB — txn_id, fraud_score, explanation, features, timestamp
- S3 — raw data, processed splits, model artifacts, batch output
- Terraform — IaC, modular

## Terraform structure
Root module → calls 6 child modules: s3, dynamodb, iam, lambda, eventbridge, sagemaker.
- SageMaker pipeline itself = Python SDK, NOT Terraform. TF only manages Model Package Group + IAM roles.
- `aws_lambda_permission` for EventBridge → lives in root `main.tf`, NOT lambda module. Avoids circular dep.
- Destroy-target pattern: kill SageMaker resources post-training to avoid idle cost.

## Cost rules (non-negotiable)
- Haiku called ONLY on fraud=positive. Never on clean txns.
- No real-time SageMaker endpoints. Batch transform only.
- Selective `terraform destroy -target=` for expensive resources.

## Response rules for Claude Code / Claude in this repo
- Caveman/ultra-terse. Code-first. No prose padding.
- No unsolicited boilerplate, no placeholders unless infra genuinely not provisioned.
- Don't re-explain stack — assume context above is known.
- No unsolicited suggestions unless asked.
- Full working code when asked, not stubs.

## Status (update as you go)
See `/todo` — currently: Terraform scaffold + data sourcing phase. Feature list unfinalized. Haiku prompt unfinalized. No AWS resources provisioned yet.