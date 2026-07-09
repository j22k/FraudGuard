## Start Here
Data first. No data → no model → nothing else matters. Everything downstream blocked on this.

## Phase Plan (sequential, don't skip)

**Phase 0 — Data**
- Find opensource fraud dataset (Kaggle: IEEE-CIS, or credit card fraud dataset — imbalanced, ~0.1-2% fraud rate typical)
- Download to `data/raw/`
- Decide feature set — freezes your Lambda payload shape + DynamoDB schema too, so lock this early

**Phase 1 — Local ML (notebook/VSCode, NOT SageMaker yet)**
- EDA in `notebooks/eda.ipynb` — class imbalance, feature distributions, nulls
- `ml/preprocess.py` — cleaning, encoding, train/test split logic (write as functions, reusable later in SageMaker processing step)
- Train XGBoost locally (`ml/train.py`), quick eval — prove the model works BEFORE touching AWS
- Why local first: SageMaker job cycles cost $ + time per iteration. Don't debug model logic on AWS clock.

**Phase 2 — Port to SageMaker Pipeline**
- `ml/sagemaker_pipeline.py` — wraps preprocess/train/eval into Pipeline steps (ProcessingStep, TrainingStep, ConditionStep for eval-gate, RegisterModel)
- This is where notebook code becomes reusable — same functions, just called by SageMaker's SDK instead of directly

**Phase 3 — Infra (Terraform)**
- `infra/terraform/modules/s3` + `dynamodb` first — passive, cheap, no compute cost sitting idle
- `iam` next — roles needed by everything else
- `lambda` + `eventbridge` — wire trigger path
- `sagemaker` module — mostly IAM role + Model Package Group refs; actual pipeline defn is Python SDK not TF

**Phase 4 — Lambda + Bedrock standalone test**
- Test `lambda/handler.py` + `bedrock_client.py` locally with a fake txn payload BEFORE wiring EventBridge
- Isolate: does Haiku call work / does DynamoDB write work — separately, then together

**Phase 5 — Wire it all + E2E test**
- EventBridge rule → Lambda → real flow
- Fake fraud txn → full pipeline → check DynamoDB row appears

**Phase 6 — Blog writeup**

## How SageMaker Notebook Fits In

You're not running one giant notebook on SageMaker. Two options, pick one:

1. **SageMaker Notebook Instance / Studio** — just a hosted Jupyter environment. You'd use it to *develop* `ml/preprocess.py` / `ml/train.py` interactively, same as local, except it has direct IAM access to S3/SageMaker APIs without local credential setup. Costs money while running — stop it when not using.
2. **No notebook on SageMaker at all** — develop 100% locally/Colab, and `ml/sagemaker_pipeline.py` (a plain `.py` script using `sagemaker` SDK) is what actually submits jobs to SageMaker. This is the leaner, more "production" pattern — matches your cost-discipline theme.

**Recommendation: option 2.** Fits your dual portfolio+blog goal better — "I didn't leave a notebook running, I wrote a pipeline script" is a stronger engineering story. Notebook only for throwaway EDA, never for the actual training/pipeline code.

## Workflow Runtime (steady state, post-build)
```
New txn → SageMaker batch transform job (scheduled or triggered)
  → XGBoost scores txn → fraud_score written to S3/event
  → if fraud_score > threshold: EventBridge rule matches → fires
  → Lambda triggered → builds prompt from txn features
  → Bedrock Haiku called → returns explanation
  → Lambda writes {txn_id, fraud_score, explanation, ts} → DynamoDB
  → clean txns: no Lambda/Haiku/DynamoDB write at all
```

## Functional Requirements
- FR1: Ingest transaction data, output fraud probability score (0-1) + binary label via threshold
- FR2: Retrain/re-register model via SageMaker Pipeline (repeatable, not manual)
- FR3: On fraud-positive only, generate plain-English explanation via Haiku
- FR4: Persist fraud result + explanation + txn_id + timestamp to DynamoDB
- FR5: Full pipeline triggerable end-to-end via new transaction event
- FR6: Infra fully provisionable/destroyable via Terraform (no manual console clicks)

## Non-Functional Requirements
- NFR1: **Cost** — no idle real-time endpoints; SageMaker resources destroyed post-job; Haiku invoked only on positives
- NFR2: **Reproducibility** — pipeline re-runnable from raw data → registered model with no manual steps
- NFR3: **Maintainability** — modular Terraform, single-purpose Python files, traceable structure
- NFR4: **Latency** — batch, not real-time SLA; explanation generation can be async, doesn't block score decision
- NFR5: **Security** — least-privilege IAM roles per module (Lambda role ≠ SageMaker role ≠ EventBridge role)
- NFR6: **Portfolio clarity** — code + blog must clearly demonstrate *why* each design choice was made (interview-defensible)

Next: lock feature list + dataset choice. That's the actual blocker right now per your `todo`. Want help picking a dataset?