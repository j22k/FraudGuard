# FraudGuard — AI Assistant Context

## Overview
Production-style AWS fraud detection pipeline combining SageMaker MLOps, XGBoost batch scoring, Amazon Bedrock (Claude 3 Haiku) natural language explainability, and DynamoDB persistence, fully provisioned with modular Terraform.

## Technology Stack
- **Machine Learning:** XGBoost Classifier, SageMaker Pipelines (Preprocess → Train → Evaluate → Register)
- **Batch Inference:** SageMaker Batch Transform (`ml.m5.xlarge`) with ephemeral teardown
- **Generative AI:** Amazon Bedrock (Claude 3 Haiku) via Anthropic Messages API (invoked on `score > 0.90` only)
- **Compute & Routing:** AWS Lambda (Python 3.12), Amazon EventBridge (prefix-filtered rules)
- **Data & Persistence:** Amazon S3 (AES-256), Amazon DynamoDB (`PAY_PER_REQUEST`)
- **Infrastructure as Code:** Terraform (`s3`, `iam`, `dynamodb`, `eventbridge`, `lambda`, `sagemaker`)
- **Operations Console:** Local triage server (`dashboard/server.py` on port 8080) and web UI

## Architectural Principles
1. **Cost Control:** Bedrock is called exclusively on high-risk fraud cases (>0.90); clean transactions (98.5%+) bypass LLM and database writes ($0.00 spend).
2. **Ephemeral Compute:** Batch transform instances spin up on demand and terminate immediately post-inference.
3. **Decoupled Serverless:** EventBridge decouples S3 storage from the SageMaker DAG and downstream Lambda explainability.
4. **Least-Privilege Security:** Separate IAM roles with minimal scoped permissions for SageMaker, EventBridge, and Lambda.