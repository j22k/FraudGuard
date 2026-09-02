# FraudGuard 🛡️
> **Cloud-Native Fraud Detection Pipeline with Automated MLOps & GenAI Explainability**

[![AWS](https://img.shields.io/badge/AWS-Cloud-orange?logo=amazon-aws)](https://aws.amazon.com/)
[![Terraform](https://img.shields.io/badge/IaC-Terraform_1.5+-844FBA?logo=terraform)](https://www.terraform.io/)
[![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)](https://www.python.org/)
[![SageMaker](https://img.shields.io/badge/MLOps-Amazon_SageMaker-232F3E?logo=amazon-aws)](https://aws.amazon.com/sagemaker/)
[![Bedrock](https://img.shields.io/badge/GenAI-Amazon_Bedrock_Claude_Haiku-teal)](https://aws.amazon.com/bedrock/)
[![DynamoDB](https://img.shields.io/badge/Database-Amazon_DynamoDB-4053D6?logo=amazon-dynamodb)](https://aws.amazon.com/dynamodb/)

FraudGuard is an event-driven, serverless machine learning operations (MLOps) pipeline designed for financial fraud detection. It couples gradient-boosted decision trees (XGBoost) on **Amazon SageMaker** with **Amazon Bedrock (Claude 3 Haiku)** to deliver real-time natural language fraud risk narratives to security analysts—while maintaining strict cost controls.

---

## 🏛️ System Architecture

![FraudGuard AWS Architecture](docs/img/AWS-services-fraud-guard.gif)

### Data & Execution Flow
```
1. Ingestion       ──► S3 Bucket (s3://{bucket}/raw/)
                         │ (ObjectCreated Notification)
                         ▼
2. MLOps DAG       ──► Amazon EventBridge ──► SageMaker Pipeline Execution
                         │ ├─ Preprocess (64-feature transformation & time-split)
                         │ ├─ Train (XGBoost with class imbalance weighting)
                         │ ├─ Evaluate (AUC-PR & ROC-AUC metric calculation)
                         │ └─ Quality Gate (AUC-PR >= 0.35) ──► Model Registry
                         ▼
3. Batch Scoring   ──► Ephemeral SageMaker Batch Transform (ml.m5.xlarge)
                         │ Outputs scored predictions to S3
                         ▼
4. Event Routing   ──► EventBridge Rule (inference-output/ prefix filter)
                         │ Invokes AWS Lambda Handler
                         ▼
5. Gated GenAI     ──► AWS Lambda (Threshold Filter: score > 0.90)
                         │ ├─ Clean Txns (<= 0.90): Zero Bedrock invocation ($0.00)
                         │ └─ Fraud Txns (> 0.90): Amazon Bedrock (Claude 3 Haiku)
                         ▼
6. Persistence     ──► Amazon DynamoDB (fraudguard-flagged-transactions-dev)
                         │ Stores: txn_id, fraud_score, Bedrock explanation, UTC timestamp
                         ▼
7. Security Node   ──► Live Forensic Operations Console (http://localhost:8080)
```

---

## 💡 Key Design Decisions & Cost Architecture

| Design Decision | Implementation | Production Rationale |
|---|---|---|
| **Gated LLM Invocations** | Bedrock Claude 3 Haiku is invoked **only** on fraud-positive transactions (`score > 0.90`). | Keeps GenAI API costs near zero at scale ($0 spend on 98.5%+ clean traffic). |
| **Ephemeral Batch Inference** | SageMaker Batch Transform over 24/7 Real-Time Endpoints. | Eliminates idle EC2 endpoint compute costs (~$150+/month); instances terminate immediately post-job. |
| **Event-Driven Decoupling** | Amazon EventBridge routes events from S3 to SageMaker and Lambda. | Eliminates polling loops and tightly couples services with native AWS retry semantics. |
| **Fully Modular IaC** | 100% codified via Terraform (`s3`, `iam`, `dynamodb`, `eventbridge`, `lambda`, `sagemaker`). | Guarantees deterministic cloud deployments and eliminates configuration drift. |
| **Least-Privilege Security** | Distinct IAM roles for SageMaker, EventBridge, and Lambda. | Zero cross-service credential sharing or wildcard permissions. |

---

## 🖥️ Live Forensic Operations Console

Inspect live flagged transactions, forensic dossiers, anomaly distributions, and Bedrock root-cause narratives:

![FraudGuard Live Ops Console](docs/img/web.png)

```powershell
# Launch local operations console
.\scripts\run_dashboard.ps1
```
*Accessible at `http://localhost:8080` (auto-syncs with live DynamoDB alerts).*

---

## 📁 Repository Structure

```
FraudGuard/
├── ml/                      # Machine Learning & SageMaker Pipeline DAG
│   ├── preprocess.py        # 64-feature transformation & time-based split
│   ├── train.py             # Local XGBoost training with scale_pos_weight
│   ├── sagemaker_pipeline.py# SageMaker DAG (Process -> Train -> Eval -> Register)
│   ├── batch_transform.py   # Batch transform runner against approved model
│   └── model_artifacts/     # Serialized model definitions & feature registry
├── lambda/                  # Serverless Explainability Layer
│   ├── handler.py           # EventBridge S3 parser & DynamoDB batch writer
│   └── bedrock_client.py    # Anthropic Messages API client for Claude 3 Haiku
├── infra/terraform/         # Modular Infrastructure as Code (IaC)
│   ├── main.tf              # Root module wiring & Lambda permissions
│   ├── modules/             # s3, iam, dynamodb, eventbridge, lambda, sagemaker
│   └── outputs.tf           # Auto-generates root .env configuration
├── dashboard/               # Security Forensic Node & Web UI
│   ├── server.py            # Local HTTP server streaming live DynamoDB items
│   └── web/                 # Frontend console (HTML5, Tailwind CSS, Lucide icons)
├── scripts/                 # Cross-platform execution automation (PowerShell / Bash)
│   ├── upload_data.ps1      # S3 dataset upload
│   ├── run_pipeline.ps1     # SageMaker pipeline trigger
│   ├── run_batch_transform.ps1 # Batch transform execution
│   ├── deploy_lambda.ps1    # Direct Lambda packaging & deployment
│   └── run_dashboard.ps1    # Local ops dashboard server
├── tests/                   # Test Automation
│   ├── test_handler.py      # Unit tests with mocked AWS services
│   └── test_adversarial_challenger_1.py # Adversarial & boundary condition test suite
└── docs/                    # Technical Documentation & Diagrams
    ├── PRODUCTION_GAP_AUDIT.md # Industrial benchmark & production audit
    ├── FraudGuard_Architecture_Diagram.pdf # PDF Architecture Blueprint
    └── FraudGuard_Architecture_Diagram.pptx # Slide Presentation Deck (16:9 Dark)
```

---

## 🚀 Quickstart Guide

### 0. Prerequisites & AWS Service Quotas
1. **AWS CLI & Terraform:** Configured with AWS credentials in `us-east-1` and Terraform `>= 1.5.0`.
2. **SageMaker Instance Service Quotas:**
   New AWS accounts default to `0` for SageMaker compute instances. Ensure quota is at least `1` in **AWS Console $\rightarrow$ Service Quotas $\rightarrow$ Amazon SageMaker** (in region `us-east-1`):
   * `ml.m5.xlarge for processing job usage`
   * `ml.m5.xlarge for training job usage`
   * `ml.m5.xlarge for transform job usage`
   *(Click "Request increase at account-level" if current value is `0`).*

### 1. Environment Setup
```powershell
# Clone repository and create Python virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows PowerShell (or source .venv/bin/activate on Linux/macOS)

# Install dependencies
pip install -r requirements.txt
```

### 2. Deploy Cloud Infrastructure
```powershell
# Package Lambda archive and provision AWS resources via Terraform
Compress-Archive -Path lambda\handler.py, lambda\bedrock_client.py -DestinationPath lambda\lambda_package.zip -Force

cd infra/terraform
terraform init
terraform apply -auto-approve
cd ../..
```
*(Terraform auto-generates the root `.env` containing your bucket names, role ARNs, and table IDs).*

### 3. Run Verification Tests
```powershell
python -m pytest tests/test_handler.py -v
```

### 4. Upload Data & Execute Pipeline
```powershell
# Upload dataset (triggers SageMaker DAG automatically via EventBridge)
.\scripts\upload_data.ps1

# Or trigger pipeline manually
.\scripts\run_pipeline.ps1
```

### 5. Run Batch Transform & Inspect Live Console
```powershell
# 1. Run batch inference against approved model version
.\scripts\run_batch_transform.ps1 -Wait

# 2. Launch operations dashboard
.\scripts\run_dashboard.ps1
```

---

## 📊 Evaluation & Validation Metrics

* **Dataset:** IEEE-CIS Fraud Detection Benchmark (590,540 raw transactions)
* **Features:** 64 engineered features (Aggregates, Interaction terms, Velocity counts, Email risk bucketing)
* **Model:** XGBoost Classifier with `scale_pos_weight=27.6`
* **Test Performance:**
  * **Test AUC-PR:** `0.4208` *(Gating Condition: `>= 0.35`)*
  * **Test ROC-AUC:** `0.8754`
  * **High-Risk Threshold (`> 0.90`):** Precision `69.5%`, Recall `28.8%`
* **Live Batch Validation:** 88,581 inferences scored $\rightarrow$ 1,271 fraud alerts flagged $\rightarrow$ Bedrock explanations persisted to DynamoDB.

---

## 📑 In-Depth Documentation

* 📄 [**Production Gap & Industrial Standard Audit**](docs/PRODUCTION_GAP_AUDIT.md) — Forensic code review, enterprise benchmark (vs. Stripe Radar / PayPal), and 10-step remediation roadmap.
* 📊 [**AWS Architecture Presentation Deck (.pptx)**](docs/FraudGuard_Architecture_Diagram.pptx) — 16:9 dark-mode presentation deck.
* 📄 [**AWS Architecture Blueprint (.pdf)**](docs/FraudGuard_Architecture_Diagram.pdf) — Architectural specification sheet.

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.