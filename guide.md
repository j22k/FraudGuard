# FraudGuard — Complete Execution & Run Guide

Step-by-step guide to deploying infrastructure, training the ML model on AWS SageMaker, running batch inference, and generating AI-powered fraud risk explanations via Amazon Bedrock into DynamoDB.

---

## 📋 Prerequisites & One-Time Setup

1. **AWS CLI:** Installed and configured (`aws configure`) with credentials for your AWS account.
2. **Python:** Version 3.10+ (Python 3.12 recommended).
3. **Terraform:** Version `>= 1.5.0` installed.
4. **AWS Region:** Standardized on `us-east-1` (N. Virginia).
5. **AWS Service Quotas (SageMaker):**
   * Go to **AWS Console $\rightarrow$ Service Quotas $\rightarrow$ Amazon SageMaker** (in `us-east-1`).
   * Ensure `ml.m5.xlarge for processing job usage` and `ml.m5.xlarge for training job usage` have a quota of at least `1` or `2` (request increase if `0`).

---

## 🛠️ Step 1: Local Environment Setup

From your terminal in the project root:

```powershell
# 1. Create and activate Python virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # On Windows PowerShell
# source .venv/bin/activate    # On Linux / macOS

# 2. Install dependencies
pip install -r requirements.txt
```

---

## 📦 Step 2: Pre-package Lambda & Deploy Infrastructure (Terraform)

Terraform provisions all cloud resources (S3 bucket, DynamoDB table, IAM roles, EventBridge rules, SageMaker Model Group, and Lambda function) and auto-generates the root `.env` file.

```powershell
# 1. Create the initial Lambda package
Compress-Archive -Path lambda\handler.py, lambda\bedrock_client.py -DestinationPath lambda\lambda_package.zip -Force

# 2. Provision Infrastructure with Terraform
cd infra/terraform
terraform init -upgrade
terraform apply
cd ../..
```

> **Note:** `terraform apply` automatically generates a `.env` file in the project root containing your actual bucket names, table names, and IAM role ARNs.

---

## 🧪 Step 3: Run Local Unit Tests

Verify the explainability handler and Bedrock mock integration before running in the cloud:

```powershell
python -m pytest tests/test_handler.py -v
```

*(Expected output: 7 passed in under 1 second without requiring AWS calls).*

---

## 🚀 Step 4: Upload Training Data & Run SageMaker Pipeline

### Option A: Automatic Trigger via S3 Upload (EventBridge)
Uploading your dataset to the `raw/` S3 prefix automatically kicks off the SageMaker training pipeline:

```powershell
.\scripts\upload_data.ps1
```

### Option B: Trigger Pipeline Manually
You can also start or retrain the pipeline directly from your terminal:

```powershell
.\scripts\run_pipeline.ps1
```

### 🔍 Monitor in AWS Console:
1. Open **Amazon SageMaker $\rightarrow$ Pipelines**.
2. Click **`fraudguard-pipeline`** $\rightarrow$ Click the running execution.
3. Watch the 4 DAG steps complete:
   * **`PreprocessFraudData`** (Extracts 64 features, splits into train/val/test)
   * **`TrainFraudModel`** (Trains XGBoost with early stopping)
   * **`EvaluateFraudModel`** (Calculates AUC-PR and ROC-AUC)
   * **`CheckAUCPRThreshold` $\rightarrow$ `RegisterFraudModel`** (Gated on `AUC-PR >= 0.35`)

---

## ✅ Step 5: Approve Model in SageMaker Model Registry

Once the pipeline finishes successfully:

1. In AWS Console, go to **Amazon SageMaker $\rightarrow$ Model Registry**.
2. Click on **`fraudguard-model-group`**.
3. Select the latest model package version.
4. Click **Update approval status** $\rightarrow$ Change status from `PendingManualApproval` to **`Approved`** $\rightarrow$ Click **Update status**.

---

## ⚡ Step 6: Run Batch Transform (Inference)

Run batch inference using the approved model against preprocessed test transactions:

```powershell
# Automatically discovers the latest test dataset and runs batch transform
.\scripts\run_batch_transform.ps1 -Wait
```

*(Adding `-Wait` streams the job logs in your terminal until completed).*

---

## 🔎 Step 7: Verify EventBridge $\rightarrow$ Lambda $\rightarrow$ Bedrock $\rightarrow$ DynamoDB

When batch transform completes:
1. Scored CSV outputs land in `s3://$bucket/inference-output/`.
2. EventBridge rule `fraudguard-s3-inference-trigger-dev` automatically invokes the Lambda function `fraudguard-explainability-dev`.
3. Lambda filters for fraud-positive rows (`fraud_score > 0.9`).
4. Amazon Bedrock (Claude 3 Haiku) generates human-readable risk summaries.
5. Flagged transactions and AI explanations are written to DynamoDB.

### Check Results:
1. Open **Amazon DynamoDB $\rightarrow$ Tables $\rightarrow$ `fraudguard-flagged-transactions-dev`**.
2. Click **Explore table items**.
3. View the records containing `txn_id`, `fraud_score`, `explanation`, and `timestamp`.

---

## 🔄 Step 8: Updating Code & Fast Iteration

* **Updating Lambda logic:** To update `lambda/handler.py` or `lambda/bedrock_client.py` without touching Terraform:
  ```powershell
  .\scripts\deploy_lambda.ps1
  ```
* **Updating ML Pipeline:** Modify scripts in `ml/` and re-run:
  ```powershell
  .\scripts\run_pipeline.ps1
  ```

---

## 🧹 Step 9: Teardown / Clean Up (Destroy Infrastructure)

To tear down all provisioned cloud resources to prevent ongoing costs:

```powershell
cd infra/terraform
terraform destroy
cd ../..
```

*(Type `yes` when prompted. Note: Ensure you empty the S3 bucket if objects are retained before destruction).*

---

## 📚 Scripts Summary Table

| PowerShell Script | Bash Script (Linux/Mac) | Description |
|---|---|---|
| `.\scripts\upload_data.ps1` | `bash scripts/upload_data.sh` | Uploads local raw CSV to S3 `raw/` directory. |
| `.\scripts\run_pipeline.ps1` | `bash scripts/run_pipeline.sh` | Registers & runs SageMaker training pipeline. |
| `.\scripts\run_batch_transform.ps1` | `bash scripts/run_batch_transform.sh` | Runs batch transform on S3 test data. |
| `.\scripts\deploy_lambda.ps1` | `bash scripts/deploy_lambda.sh` | Packages & deploys Lambda updates directly. |
