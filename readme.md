# FraudGuard

Production-style AWS fraud detection pipeline — XGBoost inference, LLM-based explainability, and event-driven serverless routing, fully provisioned via Terraform.

Built as a portfolio project to demonstrate cost-conscious, interview-defensible ML infra decisions — not a toy notebook demo.

## Architecture

```
Transaction Input
      ↓
SageMaker Pipeline (preprocess → train → evaluate → register)
      ↓
XGBoost Batch Transform (fraud probability → binary label via threshold)
      ↓
EventBridge Rule (fires only on fraud-positive inference)
      ↓
Lambda (receives flagged txn payload)
      ↓
Bedrock — Claude Haiku (plain-English fraud explanation)
      ↓
DynamoDB (txn_id, fraud_score, explanation, timestamp)
```

Clean transactions exit after the XGBoost step. No LLM call, no downstream cost.

## Key Design Decisions

| Decision | Why |
|---|---|
| LLM called only on fraud-positives | Bedrock cost stays near-zero at scale — most traffic is clean |
| Batch transform, not real-time endpoint | No idle inference costs; endpoint destroyed after each job |
| Terraform destroy-target pattern | SageMaker resources torn down post-training, not left running |
| EventBridge over polling | Decouples inference from explanation/storage; async by design |
| Least-privilege IAM | Each Lambda/SageMaker role scoped to only its required actions |

Every decision above is intentional and was chosen over a simpler/costlier alternative — documented here for interview discussion.

## Stack

- **ML:** XGBoost, SageMaker Pipelines, batch transform inference
- **LLM:** Amazon Bedrock (Claude Haiku) — fraud-positive explainability only
- **Infra:** Terraform (modular: `s3`, `sagemaker`, `lambda`, `dynamodb`, `eventbridge`, `iam`)
- **Compute/Routing:** AWS Lambda, EventBridge
- **Storage:** S3 (artifacts/data), DynamoDB (results)
- **Language:** Python

## Repo Structure

```
fraudguard/
├── ml/              # feature engineering, training, evaluation scripts
├── lambda/          # explainability handler (Bedrock Haiku call)
├── infra/terraform/ # modular IaC — s3, sagemaker, lambda, dynamodb, eventbridge, iam
├── tests/           # unit + integration tests
├── scripts/         # pipeline submission, local run helpers
├── docs/            # architecture notes, cost analysis, blog drafts
└── data/            # local dataset (gitignored / DVC-tracked)
```

## Status

- [x] Architecture finalized
- [x] Terraform modular infrastructure deployed (S3, IAM, DynamoDB, Model Registry, EventBridge, Lambda)
- [x] Dataset & feature engineering schema locked (64 features)
- [x] Local XGBoost training & baseline validation (Test AUC-PR: 0.4208, ROC-AUC: 0.8754)
- [x] SageMaker Pipeline workflow (ProcessingStep → TrainingStep → Evaluate → ConditionStep → RegisterModel)
- [x] Lambda & Bedrock Claude 3.5 Haiku explainability handler (`lambda/handler.py`, `lambda/bedrock_client.py`)
- [x] EventBridge rule for inference output triggering Lambda
- [x] Unit test suite for explainability handler with mocked AWS clients (`tests/test_handler.py`)
- [x] End-to-end live batch run & validation (`88,581` inferences, `1,271` fraud cases detected, DynamoDB populated)
- [x] Cost defense report & portfolio writeup

---

## Complete End-to-End Execution Guide

### 1. Local Environment Setup
```bash
python -m venv .venv
source .venv/bin/activate         # Linux / macOS
# or: .venv\Scripts\Activate.ps1   # Windows PowerShell

pip install -r requirements.txt
```

### 2. Pre-package Lambda & Deploy Infrastructure
Before initial `terraform apply`, package the Lambda archive, then apply the infrastructure:
```powershell
# Windows PowerShell
Compress-Archive -Path lambda\handler.py, lambda\bedrock_client.py -DestinationPath lambda\lambda_package.zip -Force

cd infra/terraform
terraform init
terraform apply
cd ../..
```

*(This provisions all AWS resources and auto-generates the root `.env` file containing resource ARNs and bucket IDs).*

### 3. Run Unit Tests Locally
```bash
python -m pytest tests/test_handler.py -v
```

### 4. Upload Data & Run SageMaker Pipeline
Upload raw data to S3 (EventBridge will auto-trigger the training pipeline, or you can run the pipeline directly):
```powershell
# Upload raw data
.\scripts\upload_data.ps1        # or: bash scripts/upload_data.sh

# Run pipeline directly
.\scripts\run_pipeline.ps1       # or: bash scripts/run_pipeline.sh
```

### 5. Approve Model & Run Batch Transform
1. Once the training pipeline completes, go to **AWS Console $\rightarrow$ SageMaker $\rightarrow$ Model Registry $\rightarrow$ `fraudguard-model-group`**.
2. Select the new model version $\rightarrow$ **Update approval status** $\rightarrow$ Set to **`Approved`**.
3. Run the batch transform job (auto-discovers latest preprocessed dataset from S3):
```powershell
.\scripts\run_batch_transform.ps1 -Wait
```

### 6. Verify Results in DynamoDB
When batch transform finishes, scored predictions land in `s3://$bucket/inference-output/`:
1. EventBridge triggers `fraudguard-explainability-dev`.
2. Lambda filters high-risk transactions (`fraud_score > 0.9`).
3. Amazon Bedrock (Claude 3 Haiku) generates plain-English fraud risk summaries.
4. Results are stored in DynamoDB table `fraudguard-flagged-transactions-dev`.

---

## Scripts Reference

| Script (PowerShell) | Script (Bash) | Purpose |
|---|---|---|
| `scripts/upload_data.ps1` | `scripts/upload_data.sh` | Uploads local raw dataset to S3 bucket configured in `.env`. |
| `scripts/run_pipeline.ps1` | `scripts/run_pipeline.sh` | Submits and starts the SageMaker training pipeline DAG. |
| `scripts/run_batch_transform.ps1` | `scripts/run_batch_transform.sh` | Fetches the latest approved model from Model Registry and runs batch inference. |
| `scripts/deploy_lambda.ps1` | `scripts/deploy_lambda.sh` | Packages and updates the Lambda function code without re-running Terraform. |

## Why This Project

Most public fraud-detection repos stop at a notebook with an AUC score. FraudGuard is built to answer the questions an interviewer actually asks: What happens at 1M transactions/day? What's your idle-cost story? Why Terraform over CloudFormation? Why batch over real-time? Every component here exists because of a specific tradeoff, documented and defensible.

## License

MIT