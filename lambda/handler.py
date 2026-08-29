"""FraudGuard Lambda Event Handler.

This Lambda function processes SageMaker batch transform inference output CSV files
triggered via Amazon EventBridge S3 notifications. It evaluates transaction fraud scores,
generates plain-English risk explanations via Amazon Bedrock for high-risk transactions
(fraud_score > threshold), and persists flagged records into Amazon DynamoDB.
"""

import csv
from datetime import datetime, timezone
from decimal import Decimal
import io
import json
import logging
import os
from typing import Any, Dict, Optional, Tuple
from urllib.parse import unquote_plus
import boto3

try:
    from bedrock_client import explain
except ImportError:
    try:
        from .bedrock_client import explain
    except ImportError:
        import importlib
        bedrock_client = importlib.import_module("lambda.bedrock_client")
        explain = bedrock_client.explain

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


def _extract_s3_bucket_and_key(event: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Extract S3 bucket name and object key from EventBridge or S3 direct event.

    Args:
        event: AWS Lambda invocation event payload.

    Returns:
        Tuple of (bucket_name, object_key), or (None, None) if not found.
    """
    # 1. EventBridge S3 notification format: detail.bucket.name & detail.object.key
    detail = event.get("detail")
    if isinstance(detail, dict):
        bucket_info = detail.get("bucket", {})
        object_info = detail.get("object", {})
        bucket_name = bucket_info.get("name") if isinstance(bucket_info, dict) else None
        object_key = object_info.get("key") if isinstance(object_info, dict) else None

        if bucket_name and object_key:
            return bucket_name, unquote_plus(object_key)

    # 2. Direct S3 event notification format: Records[0].s3.bucket.name & Records[0].s3.object.key
    records = event.get("Records")
    if isinstance(records, list) and len(records) > 0:
        first_record = records[0]
        if isinstance(first_record, dict) and "s3" in first_record:
            s3_data = first_record["s3"]
            bucket_name = s3_data.get("bucket", {}).get("name")
            object_key = s3_data.get("object", {}).get("key")
            if bucket_name and object_key:
                return bucket_name, unquote_plus(object_key)

    return None, None


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda entry point for processing inference output events.

    Args:
        event: EventBridge or S3 event payload.
        context: Lambda context object.

    Returns:
        Structured dictionary response summarizing processing counts.
    """
    logger.info("Received event: %s", json.dumps(event))

    bucket_name, object_key = _extract_s3_bucket_and_key(event)

    if not bucket_name or not object_key:
        logger.error("Unable to extract S3 bucket and object key from event payload.")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid event structure: bucket or key not found"}),
            "records_processed": 0,
            "fraud_detected": 0,
            "explanations_generated": 0,
        }

    logger.info("Processing S3 object s3://%s/%s", bucket_name, object_key)

    # Ignore files not in inference-output/ prefix or not ending with .csv/.out
    if not object_key.startswith("inference-output/") or not (object_key.endswith(".csv") or object_key.endswith(".out")):
        logger.info("Skipping non-inference object key: %s", object_key)
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Skipped non-inference object",
                "bucket": bucket_name,
                "key": object_key,
            }),
            "records_processed": 0,
            "fraud_detected": 0,
            "explanations_generated": 0,
        }

    region = os.environ.get("AWS_REGION", "us-east-1")
    table_name = os.environ.get("DYNAMODB_TABLE", "fraudguard-flagged-transactions-dev")
    threshold_str = os.environ.get("FRAUD_SCORE_THRESHOLD", "0.9")

    try:
        threshold = float(threshold_str)
    except (ValueError, TypeError):
        logger.warning("Invalid FRAUD_SCORE_THRESHOLD '%s'; defaulting to 0.9", threshold_str)
        threshold = 0.9

    # Retrieve CSV from S3
    s3_client = boto3.client("s3", region_name=region)
    try:
        s3_response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        csv_bytes = s3_response["Body"].read()
        csv_content = csv_bytes.decode("utf-8")
    except Exception as e:
        logger.error("Failed to read S3 object s3://%s/%s: %s", bucket_name, object_key, str(e))
        raise

    # Initialize DynamoDB resource
    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)

    if not csv_content or not csv_content.strip():
        logger.warning("Empty CSV payload in s3://%s/%s", bucket_name, object_key)
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Empty file", "records_processed": 0}),
            "records_processed": 0,
            "fraud_detected": 0,
            "explanations_generated": 0,
        }

    # Feature column order matching 64-feature schema
    feature_names = [
        'TransactionAmt', 'card1', 'card2', 'card3', 'card5', 'addr1', 'dist1',
        'D2', 'D8', 'D10', 'D15', 'V45', 'V158', 'V189', 'V201', 'V228', 'V244',
        'V257', 'V258', 'hour_of_day', 'card1_addr1_count', 'card2_isnull',
        'card3_isnull', 'card5_isnull', 'addr1_isnull', 'dist1_isnull', 'D2_isnull',
        'D8_isnull', 'D10_isnull', 'D15_isnull', 'V257_isnull', 'V244_isnull',
        'V201_isnull', 'V189_isnull', 'V45_isnull', 'V158_isnull', 'V228_isnull',
        'V258_isnull', 'ProductCD_C', 'ProductCD_H', 'ProductCD_R', 'ProductCD_S',
        'ProductCD_W', 'card4_american express', 'card4_discover', 'card4_mastercard',
        'card4_missing', 'card4_visa', 'card6_charge card', 'card6_credit',
        'card6_debit', 'card6_debit or credit', 'card6_missing', 'M4_M0', 'M4_M1',
        'M4_M2', 'M4_missing', 'M6_F', 'M6_T', 'M6_missing',
        'P_emaildomain_bucket_high_risk', 'P_emaildomain_bucket_low_risk',
        'P_emaildomain_bucket_mid_risk', 'P_emaildomain_bucket_missing'
    ]

    MAX_EXPLANATIONS = int(os.environ.get("MAX_EXPLANATIONS", "50"))
    has_header = False

    # Read first line to detect header
    sample_first_line = csv_content[:1024].split("\n", 1)[0].lower()
    if "fraud_score" in sample_first_line or "transactionid" in sample_first_line:
        has_header = True

    processed_count = 0
    fraud_detected_count = 0
    explanations_generated_count = 0

    if has_header:
        reader = csv.DictReader(io.StringIO(csv_content))
        for row_idx, row in enumerate(reader, start=1):
            processed_count += 1
            raw_score = row.get("fraud_score")
            if raw_score is None or str(raw_score).strip() == "":
                continue
            try:
                fraud_score = float(raw_score)
            except (ValueError, TypeError):
                continue

            if fraud_score > threshold:
                fraud_detected_count += 1
                if explanations_generated_count < MAX_EXPLANATIONS:
                    txn_id = str(row.get("TransactionID") or row.get("txn_id") or f"txn_{processed_count}")
                    explanation = explain(txn_id=txn_id, fraud_score=fraud_score, features=row)
                    explanations_generated_count += 1
                    now_iso = datetime.now(timezone.utc).isoformat()
                    item = {
                        "TransactionID": str(txn_id),
                        "txn_id": str(txn_id),
                        "fraud_score": Decimal(str(round(fraud_score, 4))),
                        "explanation": str(explanation),
                        "timestamp": now_iso,
                    }
                    table.put_item(Item=item)
    else:
        reader = csv.reader(io.StringIO(csv_content))
        for row_idx, row in enumerate(reader, start=1):
            if not row:
                continue
            processed_count += 1
            try:
                fraud_score = float(row[-1].strip())
            except (ValueError, TypeError, IndexError):
                continue

            if fraud_score > threshold:
                fraud_detected_count += 1
                if explanations_generated_count < MAX_EXPLANATIONS:
                    txn_id = str(row[0].strip()) if len(row) > 1 else f"txn_{processed_count}"
                    features = {feature_names[i]: row[i+1] for i in range(min(len(feature_names), len(row)-2))}
                    features["TransactionID"] = txn_id
                    features["fraud_score"] = fraud_score

                    explanation = explain(txn_id=txn_id, fraud_score=fraud_score, features=features)
                    explanations_generated_count += 1
                    now_iso = datetime.now(timezone.utc).isoformat()
                    item = {
                        "TransactionID": str(txn_id),
                        "txn_id": str(txn_id),
                        "fraud_score": Decimal(str(round(fraud_score, 4))),
                        "explanation": str(explanation),
                        "timestamp": now_iso,
                    }
                    table.put_item(Item=item)

    logger.info(
        "Finished processing s3://%s/%s: %d processed, %d fraud detected, %d explanations generated",
        bucket_name,
        object_key,
        processed_count,
        fraud_detected_count,
        explanations_generated_count,
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Inference results processed successfully",
            "bucket": bucket_name,
            "key": object_key,
            "records_processed": processed_count,
            "fraud_detected": fraud_detected_count,
            "explanations_generated": explanations_generated_count,
        }),
        "records_processed": processed_count,
        "fraud_detected": fraud_detected_count,
        "explanations_generated": explanations_generated_count,
    }
