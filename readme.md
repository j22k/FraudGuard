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

🚧 Active build. Currently in infra scaffolding + dataset selection phase.

- [x] Architecture finalized
- [x] Terraform module structure scaffolded
- [ ] Dataset + feature list locked
- [ ] Local XGBoost training + eval
- [ ] SageMaker Pipeline port
- [ ] Lambda + Bedrock Haiku standalone test
- [ ] EventBridge wiring
- [ ] End-to-end test (synthetic txn → full pipeline)
- [ ] Cost report + LinkedIn writeup

## Setup

> Infra not yet provisioned — placeholder until Terraform modules are complete.

```bash
# local dev
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# infra (once ready)
cd infra/terraform
terraform init
terraform plan
```

## Why This Project

Most public fraud-detection repos stop at a notebook with an AUC score. FraudGuard is built to answer the questions an interviewer actually asks: What happens at 1M transactions/day? What's your idle-cost story? Why Terraform over CloudFormation? Why batch over real-time? Every component here exists because of a specific tradeoff, documented and defensible.

## License

MIT