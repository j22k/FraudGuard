# FraudGuard — Technical Architecture & Interface Contracts

This document outlines the system architecture, component contracts, IAM least-privilege matrix, and data schemas for FraudGuard.

![FraudGuard AWS Architecture](img/AWS-services-fraud-guard.gif)

---

## 1. System Topology & Component Map

| Component | Technology | Role |
|---|---|---|
| **Raw Data Ingestion** | Amazon S3 | Ingestion destination for transaction datasets (`raw/` prefix). Emits events to EventBridge. |
| **MLOps Pipeline DAG** | Amazon SageMaker Pipelines | Automated preprocessing, XGBoost training, evaluation, and conditional model registration. |
| **Model Registry** | SageMaker Model Registry | Versioned model artifact repository (`fraudguard-model-group`) with approval gating. |
| **Batch Inference** | SageMaker Batch Transform | High-throughput offline batch scoring on ephemeral `ml.m5.xlarge` instances. |
| **Event Routing** | Amazon EventBridge | Decoupled event routing filtering on S3 prefixes (`raw/` and `inference-output/`). |
| **Explainability Handler** | AWS Lambda (Python 3.12) | Streams scored CSV, filters high-risk records (`fraud_score > 0.90`), formats features, calls Bedrock. |
| **Generative AI** | Amazon Bedrock (Claude 3 Haiku) | Generates structured plain-English root-cause explanations for fraud operations teams. |
| **Persistence Store** | Amazon DynamoDB | On-demand table storing flagged transaction IDs, fraud scores, LLM explanations, and UTC timestamps. |
| **Operations Console** | Local Web UI / Server | Real-time triage console with search, filtering, and forensic dossier inspection. |
| **Infrastructure as Code** | Terraform (v1.5+) | Modular cloud provisioning with zero manual console dependencies. |

---

## 2. Interface Contracts

### 2.1 EventBridge ──► SageMaker Pipeline Trigger
* **Event Pattern:** S3 `ObjectCreated` event on `s3://{bucket}/raw/*.csv`
* **Target:** `arn:aws:sagemaker:us-east-1:{account}:pipeline/fraudguard-pipeline`
* **Execution Role:** `fraudguard-eventbridge-sagemaker-role-dev`
* **Parameter Passed:** `RawDataS3Uri = "s3://{bucket}/raw/train_transaction.csv"`

### 2.2 EventBridge ──► Lambda Explainability Trigger
* **Event Pattern:** S3 `ObjectCreated` event on `s3://{bucket}/inference-output/*.csv`
* **Target:** `arn:aws:lambda:us-east-1:{account}:function:fraudguard-explainability-dev`
* **Permission:** `aws_lambda_permission.allow_eventbridge`

### 2.3 Lambda ──► Amazon Bedrock (Claude 3 Haiku)
* **API:** Amazon Bedrock Runtime Messages API (`invoke_model`)
* **Model ID:** `anthropic.claude-3-haiku-20240307-v1:0` (with Claude 3.5 Haiku fallback candidates)
* **Prompt Schema:** Ingests 6 structured feature groups:
  1. Basic Transaction Metrics (Amount, Hour UTC, Product Category, Card Network)
  2. Identity & Match Verification (Email Domain Risk, Address Match M6, Match Profile M4)
  3. Velocity & Behavioral Signals (Transaction Frequency `card1_addr1_count`, Days since prior `D2`, Account activity `D15`, Distance `dist1`)
  4. Anomaly Risk Flags (Vesta Anomaly Scores `V45-V258`, Missing Field Flags)
* **Output:** 3–4 sentence plain-English narrative with immediate operational recommendations.

### 2.4 Lambda ──► DynamoDB Persistence Schema
* **Table Name:** `fraudguard-flagged-transactions-dev`
* **Billing Mode:** `PAY_PER_REQUEST` (On-Demand)
* **Partition Key:** `TransactionID` (String)
* **Attributes:**
  ```json
  {
    "TransactionID": "3492498",
    "txn_id": "3492498",
    "fraud_score": 0.9595,
    "explanation": "Transaction 3492498 was flagged with critical fraud score 0.96. Key risk indicators include high-value transaction executed during off-peak hours...",
    "timestamp": "2026-08-30T10:49:52.101537+00:00"
  }
  ```

---

## 3. IAM Least-Privilege Policy Matrix

```
┌──────────────────────────────────────┬─────────────────────────────────────────────────────────────┐
│ IAM Role                             │ Scoped Permissions                                         │
├──────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
│ SageMaker Execution Role             │ • s3:GetObject, s3:PutObject on project bucket only         │
│                                      │ • sagemaker:Create*Job, sagemaker:Describe*Job              │
│                                      │ • sagemaker:CreateModelPackage, UpdateModelPackage          │
│                                      │ • logs:CreateLogGroup, logs:PutLogEvents                    │
├──────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
│ EventBridge SageMaker Trigger Role   │ • sagemaker:StartPipelineExecution on pipeline ARN only     │
├──────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
│ Lambda Execution Role                │ • s3:GetObject on inference-output/*                        │
│                                      │ • bedrock:InvokeModel on anthropic.claude-3-haiku-*         │
│                                      │ • dynamodb:PutItem on fraudguard-flagged-transactions-*     │
│                                      │ • logs:CreateLogStream, logs:PutLogEvents                   │
└──────────────────────────────────────┴─────────────────────────────────────────────────────────────┘
```

---

## 4. Terraform Infrastructure Modules Layout

```
infra/terraform/
├── main.tf                  # Root orchestrator & cross-module permissions
├── variables.tf             # Project name, environment, AWS region definitions
├── outputs.tf               # Exports ARNs & bucket IDs
├── env_file.tf              # Auto-generates root .env configuration
└── modules/
    ├── s3/                  # S3 Bucket with AES-256 encryption & EventBridge notifications
    ├── iam/                 # Least-privilege roles for SageMaker, EventBridge, and Lambda
    ├── dynamodb/            # On-demand DynamoDB table for fraud alerts
    ├── eventbridge/         # S3 event matching rules & pipeline/Lambda targets
    ├── lambda/              # Python 3.12 Lambda function & CloudWatch log group
    └── sagemaker/           # SageMaker Model Package Group & registry configuration
```
