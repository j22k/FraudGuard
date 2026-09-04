"""
FraudGuard — Deploy Real-Time / Serverless SageMaker Endpoint
Deploys the approved model from the SageMaker Model Registry
(or local model artifacts) as a live Real-Time or Serverless Endpoint.

Usage:
  python ml/deploy_realtime.py --serverless
  python ml/deploy_realtime.py --instance-type ml.m5.large
"""

import argparse
import logging
import os
import sys
import boto3
import sagemaker
from sagemaker.model import ModelPackage
from sagemaker.serverless import ServerlessInferenceConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

REGION = os.environ.get("AWS_REGION", "us-east-1")
ROLE_ARN = os.environ.get("SAGEMAKER_ROLE_ARN")
BUCKET = os.environ.get("FRAUDGUARD_S3_BUCKET")
MODEL_PACKAGE_GROUP = os.environ.get("FRAUDGUARD_MODEL_PACKAGE_GROUP", "fraudguard-model-group")
DEFAULT_ENDPOINT_NAME = os.environ.get("FRAUDGUARD_ENDPOINT_NAME", "fraudguard-realtime-endpoint")


def get_latest_approved_model_package(sm_client: boto3.client, group_name: str) -> str:
    """Return the ARN of the most recently approved model package in the group."""
    response = sm_client.list_model_packages(
        ModelPackageGroupName=group_name,
        ModelApprovalStatus="Approved",
        SortBy="CreationTime",
        SortOrder="Descending",
        MaxResults=1,
    )
    packages = response.get("ModelPackageSummaryList", [])
    if not packages:
        raise RuntimeError(
            f"No approved models found in group '{group_name}'.\n"
            f"Approve a model package in SageMaker Model Registry before deploying."
        )
    arn = packages[0]["ModelPackageArn"]
    logger.info(f"Found approved model package: {arn}")
    return arn


def deploy_endpoint(
    endpoint_name: str = DEFAULT_ENDPOINT_NAME,
    serverless: bool = True,
    instance_type: str = "ml.m5.large",
    initial_instance_count: int = 1,
):
    """Deploy the real-time endpoint."""
    if not ROLE_ARN:
        logger.error("SAGEMAKER_ROLE_ARN environment variable is required.")
        sys.exit(1)

    sm_client = boto3.client("sagemaker", region_name=REGION)
    sm_session = sagemaker.Session(boto_session=boto3.Session(region_name=REGION))

    model_package_arn = get_latest_approved_model_package(sm_client, MODEL_PACKAGE_GROUP)

    model = ModelPackage(
        role=ROLE_ARN,
        model_package_arn=model_package_arn,
        sagemaker_session=sm_session,
    )

    if serverless:
        logger.info(f"Deploying Serverless Endpoint: {endpoint_name} (2048 MB memory, max concurrency 10)...")
        serverless_config = ServerlessInferenceConfig(
            memory_size_in_mb=2048,
            max_concurrency=10,
        )
        predictor = model.deploy(
            endpoint_name=endpoint_name,
            serverless_inference_config=serverless_config,
        )
    else:
        logger.info(f"Deploying Provisioned Endpoint: {endpoint_name} ({instance_type} x {initial_instance_count})...")
        predictor = model.deploy(
            initial_instance_count=initial_instance_count,
            instance_type=instance_type,
            endpoint_name=endpoint_name,
        )

    logger.info(f"Successfully deployed endpoint: {predictor.endpoint_name}")
    return predictor.endpoint_name


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy FraudGuard SageMaker Real-Time Endpoint")
    parser.add_argument("--endpoint-name", default=DEFAULT_ENDPOINT_NAME, help="Name of the endpoint")
    parser.add_argument("--serverless", action="store_true", default=True, help="Deploy as Serverless endpoint")
    parser.add_argument("--provisioned", dest="serverless", action="store_false", help="Deploy as Provisioned endpoint")
    parser.add_argument("--instance-type", default="ml.m5.large", help="Instance type for provisioned endpoint")
    parser.add_argument("--instance-count", type=int, default=1, help="Instance count for provisioned endpoint")

    args = parser.parse_args()
    deploy_endpoint(
        endpoint_name=args.endpoint_name,
        serverless=args.serverless,
        instance_type=args.instance_type,
        initial_instance_count=args.instance_count,
    )
