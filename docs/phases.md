# FraudGuard — Project Lifecycle & Phase Specifications

This document outlines the six architectural phases of the FraudGuard system.

---

## 🏗️ Phase Summary

| Phase | Title | Core Objective | Key Deliverables |
|---|---|---|---|
| **Phase 0** | **Data Engineering** | Sourcing & Feature Schema Locking | Ingested IEEE-CIS dataset into `data/raw/`. Locked 64-feature transformation schema. |
| **Phase 1** | **Machine Learning Baseline** | EDA & Local Model Validation | Imbalance handling (`scale_pos_weight`), local XGBoost training (`ml/train.py`), baseline AUC-PR: `0.4208`. |
| **Phase 2** | **MLOps Pipeline DAG** | SageMaker Containerization | 5-step DAG (`ml/sagemaker_pipeline.py`) with conditional gate on AUC-PR $\ge 0.35$ registering to Model Registry. |
| **Phase 3** | **Infrastructure as Code** | Terraform Provisioning | Modular Terraform provisioning S3, IAM, DynamoDB, EventBridge, SageMaker Model Group, and Lambda. |
| **Phase 4** | **Serverless Explainability** | Bedrock GenAI Integration | Lambda handler (`lambda/handler.py`) & Bedrock Claude 3 Haiku client (`lambda/bedrock_client.py`). |
| **Phase 5** | **Live Validation & UI** | Batch Inference & Ops Console | Batch transform execution (88K+ records), DynamoDB alerts, live triage dashboard (`http://localhost:8080`). |

---

## 🔄 Runtime State Machine

```
1. New Dataset Upload ──► S3 (raw/ prefix)
                            │
                            ▼
2. Trigger Pipeline   ──► EventBridge Rule ──► SageMaker Pipeline DAG
                            │
                            ▼
3. Batch Scoring      ──► SageMaker Batch Transform (ml.m5.xlarge)
                            │
                            ▼
4. Inference Output   ──► S3 (inference-output/ prefix)
                            │
                            ▼
5. Filter & Explain   ──► EventBridge ──► Lambda (Score > 0.90) ──► Bedrock Claude 3 Haiku
                            │
                            ▼
6. Alert Storage      ──► Amazon DynamoDB (fraudguard-flagged-transactions-dev)
                            │
                            ▼
7. Forensic Triage    ──► Local Ops Console (http://localhost:8080)
```