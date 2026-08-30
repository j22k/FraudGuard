"""
FraudGuard — SageMaker Batch Transform
Fetches the latest approved model from the Model Registry and runs a batch
transform job against preprocessed transaction data.

Prerequisites:
  1. SageMaker pipeline has run and a model is in the registry with status 'Approved'.
     (Pipeline registers with 'PendingManualApproval' — you must approve it first
      in the SageMaker console: Model Registry → fraudguard-model-group → Approve)
  2. Input S3 path contains preprocessed CSV data (64 features, no target column,
     no TransactionID/TransactionDT). This is the format the processing step produces.

Run:
  python ml/batch_transform.py --input-s3 s3://YOUR_BUCKET/path/to/preprocessed/

Output lands at:
  s3://FRAUDGUARD_S3_BUCKET/inference-output/
  → EventBridge fires on this prefix → Lambda → Bedrock → DynamoDB
"""

import io
import os
import argparse
import pandas as pd
import boto3
import sagemaker
from sagemaker.model import ModelPackage
from datetime import datetime

# ---- Config — same pattern as sagemaker_pipeline.py ----
REGION              = os.environ.get('AWS_REGION', 'us-east-1')
ROLE_ARN            = os.environ['SAGEMAKER_ROLE_ARN']
BUCKET              = os.environ['FRAUDGUARD_S3_BUCKET']
MODEL_PACKAGE_GROUP = os.environ.get('FRAUDGUARD_MODEL_PACKAGE_GROUP', 'fraudguard-model-group')

OUTPUT_PATH         = f's3://{BUCKET}/inference-output/'
INSTANCE_TYPE       = 'ml.m5.large'


def get_latest_approved_model_package(sm_client: boto3.client, group_name: str) -> str:
    """Return the ARN of the most recently approved model package in the group."""
    response = sm_client.list_model_packages(
        ModelPackageGroupName=group_name,
        ModelApprovalStatus='Approved',
        SortBy='CreationTime',
        SortOrder='Descending',
        MaxResults=1,
    )
    packages = response.get('ModelPackageSummaryList', [])
    if not packages:
        raise RuntimeError(
            f"No approved models found in group '{group_name}'.\n"
            f"  -> Run the SageMaker pipeline first: python ml/sagemaker_pipeline.py\n"
            f"  -> Then approve the model in the SageMaker console:\n"
            f"     Model Registry -> {group_name} -> (select version) -> Update approval status -> Approved"
        )
    arn = packages[0]['ModelPackageArn']
    created = packages[0]['CreationTime'].strftime('%Y-%m-%d %H:%M UTC')
    print(f"  Found: {arn}")
    print(f"  Created: {created}")
    return arn


def get_latest_test_s3_uri(s3_client: boto3.client, bucket: str) -> str:
    """Find the latest PreprocessFraudData test output in S3."""
    paginator = s3_client.get_paginator('list_objects_v2')
    test_objects = []
    for page in paginator.paginate(Bucket=bucket, Prefix='fraudguard-pipeline/'):
        for obj in page.get('Contents', []):
            if obj['Key'].endswith('PreprocessFraudData/output/test/test.csv'):
                test_objects.append(obj)
    if not test_objects:
        raise RuntimeError(
            f"No preprocessed test data found in bucket '{bucket}'.\n"
            f"Please run the SageMaker pipeline first or provide --input-s3."
        )
    test_objects.sort(key=lambda x: x['LastModified'], reverse=True)
    latest_key = test_objects[0]['Key']
    s3_uri = f"s3://{bucket}/{latest_key}"
    return s3_uri


def prepare_inference_dataset(s3_client: boto3.client, bucket: str, raw_input_s3: str) -> str:
    """Download preprocessed test split, strip target/metadata columns, and save headerless inference payload."""
    print(f"\n3. Preparing clean inference dataset from {raw_input_s3}...")
    path_without_s3 = raw_input_s3.replace("s3://", "")
    src_bucket, src_key = path_without_s3.split("/", 1)

    response = s3_client.get_object(Bucket=src_bucket, Key=src_key)
    df = pd.read_csv(io.BytesIO(response['Body'].read()))

    # Drop target and timestamp columns if present
    for col in ['TransactionDT', 'isFraud']:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Put TransactionID as column 0
    if 'TransactionID' in df.columns:
        cols = ['TransactionID'] + [c for c in df.columns if c != 'TransactionID']
        df = df[cols]

    out_key = 'inference-input/test_features_for_inference.csv'
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False, header=False)

    s3_client.put_object(
        Bucket=bucket,
        Key=out_key,
        Body=csv_buffer.getvalue().encode('utf-8')
    )
    dest_uri = f"s3://{bucket}/{out_key}"
    print(f"   Payload ready: {len(df)} rows, {df.shape[1]-1} features (+ TransactionID)")
    print(f"   Uploaded to:   {dest_uri}")
    return dest_uri


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Run SageMaker batch transform for FraudGuard inference.'
    )
    parser.add_argument(
        '--input-s3',
        type=str,
        required=False,
        default=None,
        help=(
            'S3 URI of preprocessed input data. If omitted, automatically discovers '
            'the latest test.csv output from the SageMaker pipeline in your bucket.'
        ),
    )
    parser.add_argument(
        '--wait',
        action='store_true',
        default=False,
        help='Block terminal until the transform job completes (default: async).',
    )
    args = parser.parse_args()

    boto_session   = boto3.Session(region_name=REGION)
    sm_client      = boto_session.client('sagemaker')
    s3_client      = boto_session.client('s3')
    sm_session     = sagemaker.Session(boto_session=boto_session, default_bucket=BUCKET)
    job_name       = f"fraudguard-transform-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    if args.input_s3 and args.input_s3.startswith("s3://"):
        raw_test_s3_uri = args.input_s3
    else:
        raw_test_s3_uri = get_latest_test_s3_uri(s3_client, BUCKET)

    print(f"\n{'='*60}")
    print(f"FraudGuard Batch Transform")
    print(f"{'='*60}")
    print(f"\n1. Fetching latest approved model from '{MODEL_PACKAGE_GROUP}'...")
    model_package_arn = get_latest_approved_model_package(sm_client, MODEL_PACKAGE_GROUP)

    print(f"\n2. Creating SageMaker Model from package...")
    model = ModelPackage(
        role=ROLE_ARN,
        model_package_arn=model_package_arn,
        sagemaker_session=sm_session,
    )

    clean_inference_s3 = prepare_inference_dataset(s3_client, BUCKET, raw_test_s3_uri)

    print(f"\n4. Configuring transform job...")
    transformer = model.transformer(
        instance_count=1,
        instance_type=INSTANCE_TYPE,
        output_path=OUTPUT_PATH,
        assemble_with='Line',   # one prediction per line
        accept='text/csv',
    )

    print(f"\n5. Submitting batch transform job: {job_name}")
    print(f"   Input  -> {clean_inference_s3}")
    print(f"   Output -> {OUTPUT_PATH}")
    print(f"   Instance: {INSTANCE_TYPE}")

    transformer.transform(
        data=clean_inference_s3,
        content_type='text/csv',
        split_type='Line',      # process one row at a time
        input_filter="$[1:]",   # pass only the 64 feature columns (drop TransactionID at col 0)
        join_source="Input",    # attach TransactionID and input features to output prediction
        job_name=job_name,
        wait=args.wait,
    )

    print(f"\n{'='*60}")
    if args.wait:
        print(f"Transform job complete.")
    else:
        print(f"Transform job submitted (running async).")
        print(f"Monitor: AWS Console -> SageMaker -> Batch transform jobs -> {job_name}")
    print(f"\nWhen job finishes:")
    print(f"  -> Output lands at {OUTPUT_PATH}")
    print(f"  -> EventBridge fires on inference-output/ prefix")
    print(f"  -> Lambda reads results, calls Bedrock for fraud_score > 0.9 rows")
    print(f"  -> Results written to DynamoDB table: {os.environ.get('FRAUDGUARD_DYNAMODB_TABLE', 'fraudguard-flagged-transactions-dev')}")
    print(f"{'='*60}\n")
