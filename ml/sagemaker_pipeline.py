"""
FraudGuard — SageMaker Pipeline
Wraps preprocess.py + train.py + eval logic into SageMaker-native steps.
Run: python ml/sagemaker_pipeline.py  (submits pipeline and starts execution)
"""

import os
import sagemaker
from sagemaker.workflow.pipeline import Pipeline
from sagemaker.workflow.steps import ProcessingStep, TrainingStep
from sagemaker.workflow.condition_step import ConditionStep
from sagemaker.workflow.conditions import ConditionGreaterThanOrEqualTo
from sagemaker.workflow.functions import JsonGet
from sagemaker.workflow.parameters import ParameterString, ParameterFloat
from sagemaker.workflow.properties import PropertyFile
from sagemaker.sklearn.processing import SKLearnProcessor
from sagemaker.processing import ProcessingInput, ProcessingOutput
from sagemaker.xgboost.estimator import XGBoost
from sagemaker.inputs import TrainingInput
from sagemaker.workflow.step_collections import RegisterModel
from sagemaker.model_metrics import ModelMetrics, MetricsSource

# ---- Config — pull from env/terraform output, NOT hardcoded ----
REGION = os.environ.get('AWS_REGION', 'us-east-1')
ROLE_ARN = os.environ['SAGEMAKER_ROLE_ARN']         # from terraform output, no default — fail loud if missing
BUCKET = os.environ['FRAUDGUARD_S3_BUCKET']          # from terraform output
PIPELINE_NAME = 'fraudguard-pipeline'
MODEL_PACKAGE_GROUP = 'fraudguard-model-group'

sagemaker_session = sagemaker.Session(default_bucket=BUCKET)

# ---- Pipeline parameters (overridable at execution time, not code change) ----
raw_data_s3 = ParameterString(name='RawDataS3Uri', default_value=f's3://{BUCKET}/raw/train_transaction.csv')
min_aucpr_threshold = ParameterFloat(name='MinAUCPR', default_value=0.35)

# =====================================================================
# STEP 1 — Processing (wraps preprocess.py)
# =====================================================================
sklearn_processor = SKLearnProcessor(
    framework_version='1.2-1',
    role=ROLE_ARN,
    instance_type='ml.m5.xlarge',
    instance_count=1,
    base_job_name='fraudguard-preprocess',
    sagemaker_session=sagemaker_session,
)

processing_step = ProcessingStep(
    name='PreprocessFraudData',
    processor=sklearn_processor,
    code='ml/preprocess_sagemaker_entry.py',
    inputs=[
        ProcessingInput(source=raw_data_s3, destination='/opt/ml/processing/input'),
    ],
    outputs=[
        ProcessingOutput(output_name='train', source='/opt/ml/processing/train'),
        ProcessingOutput(output_name='val', source='/opt/ml/processing/val'),
        ProcessingOutput(output_name='test', source='/opt/ml/processing/test'),
    ],
)

# =====================================================================
# STEP 2 — Training (wraps train.py)
# =====================================================================
xgb_estimator = XGBoost(
    entry_point='train_sagemaker_entry.py',
    source_dir='ml/',
    framework_version='1.7-1',
    role=ROLE_ARN,
    instance_type='ml.m5.xlarge',
    instance_count=1,
    base_job_name='fraudguard-train',
    sagemaker_session=sagemaker_session,
    hyperparameters={
        'n_estimators': 1200,
        'max_depth': 6,
        'learning_rate': 0.05,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'early_stopping_rounds': 30,
    },
)

training_step = TrainingStep(
    name='TrainFraudModel',
    estimator=xgb_estimator,
    inputs={
        'train': TrainingInput(
            s3_data=processing_step.properties.ProcessingOutputConfig.Outputs['train'].S3Output.S3Uri,
            content_type='text/csv',
        ),
        'validation': TrainingInput(
            s3_data=processing_step.properties.ProcessingOutputConfig.Outputs['val'].S3Output.S3Uri,
            content_type='text/csv',
        ),
        'test': TrainingInput(
            s3_data=processing_step.properties.ProcessingOutputConfig.Outputs['test'].S3Output.S3Uri,
            content_type='text/csv',
        ),
    },
)

# =====================================================================
# STEP 3 — Evaluation (Evaluates model on test set)
# =====================================================================
eval_results_file = PropertyFile(
    name="eval_results",
    output_name="evaluation",
    path="eval_results.json",
)

evaluation_step = ProcessingStep(
    name='EvaluateFraudModel',
    processor=sklearn_processor,
    code='ml/eval_sagemaker_entry.py',
    inputs=[
        ProcessingInput(
            source=training_step.properties.ModelArtifacts.S3ModelArtifacts,
            destination='/opt/ml/processing/model',
        ),
        ProcessingInput(
            source=processing_step.properties.ProcessingOutputConfig.Outputs['test'].S3Output.S3Uri,
            destination='/opt/ml/processing/test',
        ),
    ],
    outputs=[
        ProcessingOutput(output_name='evaluation', source='/opt/ml/processing/evaluation'),
    ],
    property_files=[eval_results_file],
)

# =====================================================================
# STEP 4 — Register Model (gated on eval metric)
# =====================================================================
model_metrics = ModelMetrics(
    model_statistics=MetricsSource(
        s3_uri=evaluation_step.properties.ProcessingOutputConfig.Outputs['evaluation'].S3Output.S3Uri,
        content_type='application/json',
    )
)

register_step = RegisterModel(
    name='RegisterFraudModel',
    estimator=xgb_estimator,
    model_data=training_step.properties.ModelArtifacts.S3ModelArtifacts,
    content_types=['text/csv'],
    response_types=['text/csv'],
    inference_instances=['ml.m5.large'],
    transform_instances=['ml.m5.large'],
    model_package_group_name=MODEL_PACKAGE_GROUP,
    approval_status='PendingManualApproval',  # human gate before prod use
    model_metrics=model_metrics,
)

# ---- Condition: only register if test AUC-PR clears threshold ----
condition_step = ConditionStep(
    name='CheckAUCPRThreshold',
    conditions=[
        ConditionGreaterThanOrEqualTo(
            left=JsonGet(
                step_name=evaluation_step.name,
                property_file=eval_results_file,
                json_path='test.aucpr',
            ),
            right=min_aucpr_threshold,
        )
    ],
    if_steps=[register_step],
    else_steps=[],
)

# =====================================================================
# Assemble pipeline
# =====================================================================
pipeline = Pipeline(
    name=PIPELINE_NAME,
    parameters=[raw_data_s3, min_aucpr_threshold],
    steps=[processing_step, training_step, evaluation_step, condition_step],
    sagemaker_session=sagemaker_session,
)

if __name__ == '__main__':
    print(f"Upserting pipeline '{PIPELINE_NAME}' to SageMaker...")
    pipeline.upsert(role_arn=ROLE_ARN)
    print(f"Pipeline '{PIPELINE_NAME}' registered successfully.")

    print("Starting pipeline execution...")
    execution = pipeline.start()
    print(f"Pipeline execution started!")
    print(f"Execution ARN: {execution.arn}")
    print("You can now monitor this execution in the SageMaker Console.")
