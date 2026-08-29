"""Unit tests for FraudGuard Lambda alert handler and Bedrock explainability client.

These tests run completely offline without AWS credentials by using unittest.mock
to patch boto3 client and resource interfaces.
"""

import io
import json
import os
import sys
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

# Add lambda/ directory to sys.path so lambda modules can be imported directly
LAMBDA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lambda"))
if LAMBDA_DIR not in sys.path:
    sys.path.insert(0, LAMBDA_DIR)

FIXTURES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "fixtures"))


@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    """Set deterministic environment variables for offline test execution."""
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("DYNAMODB_TABLE", "fraudguard-flagged-transactions-dev")
    monkeypatch.setenv("FRAUD_SCORE_THRESHOLD", "0.9")


@pytest.fixture
def sample_event():
    """Load realistic EventBridge S3 Object Created event payload."""
    event_path = os.path.join(FIXTURES_DIR, "sample_fraud_event.json")
    with open(event_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def sample_csv_bytes():
    """Load 5-row sample results CSV fixture."""
    csv_path = os.path.join(FIXTURES_DIR, "sample_results.csv")
    with open(csv_path, "rb") as f:
        return f.read()


@pytest.fixture
def mock_aws_services(sample_csv_bytes):
    """Set up mocked S3, Bedrock Runtime, and DynamoDB services."""
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {
        "Body": io.BytesIO(sample_csv_bytes)
    }

    mock_bedrock = MagicMock()
    bedrock_response_payload = {
        "content": [
            {
                "type": "text",
                "text": "Flagged transaction: high risk transaction amount and anomalous time of day.",
            }
        ]
    }

    def mock_invoke_model(*args, **kwargs):
        return {
            "body": io.BytesIO(json.dumps(bedrock_response_payload).encode("utf-8"))
        }

    mock_bedrock.invoke_model.side_effect = mock_invoke_model

    mock_dynamodb = MagicMock()
    mock_table = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    def client_side_effect(service_name, *args, **kwargs):
        if service_name == "s3":
            return mock_s3
        elif service_name == "bedrock-runtime":
            return mock_bedrock
        return MagicMock()

    def resource_side_effect(service_name, *args, **kwargs):
        if service_name == "dynamodb":
            return mock_dynamodb
        return MagicMock()

    with patch("boto3.client", side_effect=client_side_effect) as patch_client, \
         patch("boto3.resource", side_effect=resource_side_effect) as patch_resource:
        yield {
            "s3": mock_s3,
            "bedrock": mock_bedrock,
            "dynamodb": mock_dynamodb,
            "table": mock_table,
            "patch_client": patch_client,
            "patch_resource": patch_resource,
        }


class TestLambdaHandler:
    """Test suite for Lambda handler event processing, filtering, and DynamoDB persistence."""

    def test_handler_end_to_end(self, mock_aws_services, sample_event):
        """End-to-end test feeding sample_fraud_event.json and sample_results.csv.

        Asserts:
        - Bedrock invoke_model called EXACTLY 2 times (for rows with fraud_score > 0.9)
        - DynamoDB put_item called EXACTLY 2 times (for rows with fraud_score > 0.9)
        - Zero Bedrock or DynamoDB calls for the 3 clean rows (fraud_score < 0.5)
        """
        import handler

        response = handler.handler(sample_event, None)

        assert response["statusCode"] == 200
        assert response["records_processed"] == 5
        assert response["fraud_detected"] == 2
        assert response["explanations_generated"] == 2

        # 1. S3 get_object verification
        mock_aws_services["s3"].get_object.assert_called_once_with(
            Bucket="fraudguard-test-bucket",
            Key="inference-output/results.csv",
        )

        # 2. Bedrock invoke_model verification (EXACTLY 2 calls for fraud rows)
        assert mock_aws_services["bedrock"].invoke_model.call_count == 2

        # 3. DynamoDB put_item verification (EXACTLY 2 calls)
        assert mock_aws_services["table"].put_item.call_count == 2

        # Verify the transactions flagged correspond to the 2 fraud rows (>0.9)
        put_calls = mock_aws_services["table"].put_item.call_args_list
        written_txn_ids = [call.kwargs["Item"]["TransactionID"] for call in put_calls]
        assert "3000001" in written_txn_ids
        assert "3000002" in written_txn_ids
        assert "3000003" not in written_txn_ids
        assert "3000004" not in written_txn_ids
        assert "3000005" not in written_txn_ids

    def test_dynamodb_item_schema(self, mock_aws_services, sample_event):
        """Verify the exact schema, types, and constraints of items written to DynamoDB.

        Asserts:
        - Contains TransactionID, txn_id, fraud_score, explanation, timestamp
        - fraud_score is an instance of decimal.Decimal
        - timestamp is a valid ISO-8601 UTC string
        """
        import handler

        handler.handler(sample_event, None)

        put_calls = mock_aws_services["table"].put_item.call_args_list
        assert len(put_calls) == 2

        for call in put_calls:
            item = call.kwargs["Item"]

            # Required schema keys
            assert "TransactionID" in item
            assert "txn_id" in item
            assert "fraud_score" in item
            assert "explanation" in item
            assert "timestamp" in item

            # Type checks
            assert isinstance(item["TransactionID"], str)
            assert isinstance(item["txn_id"], str)
            assert item["TransactionID"] == item["txn_id"]
            assert len(item["TransactionID"]) > 0

            # Decimal type check (critical: native float is not allowed in DynamoDB)
            assert isinstance(item["fraud_score"], Decimal)
            assert item["fraud_score"] > Decimal("0.90")

            # Explanation check
            assert isinstance(item["explanation"], str)
            assert len(item["explanation"]) > 0

            # Timestamp check: valid ISO-8601 format
            assert isinstance(item["timestamp"], str)
            parsed_dt = datetime.fromisoformat(item["timestamp"])
            assert parsed_dt is not None

    def test_threshold_override(self, mock_aws_services, sample_event, monkeypatch):
        """Verify FRAUD_SCORE_THRESHOLD override behavior.

        With FRAUD_SCORE_THRESHOLD=0.95:
        - Row 1 (score 0.9421) is skipped (0.9421 <= 0.95)
        - Row 2 (score 0.9850) is processed (0.9850 > 0.95)
        - Rows 3, 4, 5 (< 0.5) are skipped
        - Results in EXACTLY 1 Bedrock call and 1 DynamoDB write
        """
        monkeypatch.setenv("FRAUD_SCORE_THRESHOLD", "0.95")
        import handler

        response = handler.handler(sample_event, None)

        assert response["statusCode"] == 200
        assert response["records_processed"] == 5
        assert response["fraud_detected"] == 1
        assert response["explanations_generated"] == 1

        assert mock_aws_services["bedrock"].invoke_model.call_count == 1
        assert mock_aws_services["table"].put_item.call_count == 1

        written_item = mock_aws_services["table"].put_item.call_args.kwargs["Item"]
        assert written_item["TransactionID"] == "3000002"
        assert written_item["fraud_score"] == Decimal("0.985") or written_item["fraud_score"] == Decimal("0.9850")

    def test_all_clean_rows_zero_calls(self, monkeypatch):
        """Verify that a results CSV with only clean rows makes 0 Bedrock and 0 DynamoDB calls."""
        import handler

        clean_csv = (
            "TransactionID,fraud_score,TransactionAmt,hour_of_day\n"
            "4000001,0.0210,15.50,10\n"
            "4000002,0.1145,55.00,12\n"
            "4000003,0.3420,80.00,16\n"
        )

        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {"Body": io.BytesIO(clean_csv.encode("utf-8"))}

        mock_bedrock = MagicMock()
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        def client_side_effect(service_name, *args, **kwargs):
            if service_name == "s3":
                return mock_s3
            elif service_name == "bedrock-runtime":
                return mock_bedrock
            return MagicMock()

        def resource_side_effect(service_name, *args, **kwargs):
            if service_name == "dynamodb":
                return mock_dynamodb
            return MagicMock()

        with patch("boto3.client", side_effect=client_side_effect), \
             patch("boto3.resource", side_effect=resource_side_effect):
            event = {
                "detail": {
                    "bucket": {"name": "fraudguard-test-bucket"},
                    "object": {"key": "inference-output/clean_results.csv"},
                }
            }
            response = handler.handler(event, None)

            assert response["statusCode"] == 200
            assert response["records_processed"] == 3
            assert response["fraud_detected"] == 0
            assert response["explanations_generated"] == 0

            # Asserts zero Bedrock calls and zero DynamoDB writes
            assert mock_bedrock.invoke_model.call_count == 0
            assert mock_table.put_item.call_count == 0

    def test_non_inference_event_skipped(self):
        """Verify that S3 objects not matching 'inference-output/*.csv' are skipped safely."""
        import handler

        with patch("boto3.client") as mock_client, patch("boto3.resource") as mock_resource:
            event = {
                "detail": {
                    "bucket": {"name": "fraudguard-test-bucket"},
                    "object": {"key": "raw/train_transaction.csv"},
                }
            }
            response = handler.handler(event, None)

            assert response["statusCode"] == 200
            assert response["records_processed"] == 0
            assert response["fraud_detected"] == 0
            assert response["explanations_generated"] == 0
            mock_client.return_value.get_object.assert_not_called()
            mock_resource.return_value.Table.assert_not_called()

    def test_direct_s3_notification_fallback(self, mock_aws_services):
        """Verify handler supports fallback standard S3 notification event format (Records list)."""
        import handler

        s3_record_event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "fraudguard-test-bucket"},
                        "object": {"key": "inference-output/results.csv"},
                    }
                }
            ]
        }

        response = handler.handler(s3_record_event, None)

        assert response["statusCode"] == 200
        assert response["records_processed"] == 5
        assert response["fraud_detected"] == 2
        assert response["explanations_generated"] == 2
        assert mock_aws_services["bedrock"].invoke_model.call_count == 2
        assert mock_aws_services["table"].put_item.call_count == 2


class TestBedrockClient:
    """Test suite for Bedrock Claude 3 Haiku explainability client."""

    @patch("boto3.client")
    def test_bedrock_client_explain(self, mock_boto_client):
        """Direct unit test for explain() asserting prompt content and message format.

        Asserts:
        - Model ID is 'anthropic.claude-3-haiku-20240307-v1:0'
        - Content type and accept headers are 'application/json'
        - Payload contains 'anthropic_version': 'bedrock-2023-05-31'
        - Prompt includes transaction ID, fraud probability, and human-readable feature values
        - Returns the stripped explanation string from Claude
        """
        from bedrock_client import explain

        mock_bedrock = MagicMock()
        mock_boto_client.return_value = mock_bedrock

        claude_response = {
            "content": [
                {
                    "type": "text",
                    "text": "Transaction 3000001 was flagged due to an unusually high amount ($950.00) at 03:00 UTC with high-risk email domain.",
                }
            ]
        }
        mock_bedrock.invoke_model.return_value = {
            "body": io.BytesIO(json.dumps(claude_response).encode("utf-8"))
        }

        features = {
            "TransactionAmt": 950.00,
            "hour_of_day": 3,
            "ProductCD_W": 1,
            "card4_visa": 1,
            "card6_debit": 0,
            "P_emaildomain_bucket_high_risk": 1,
        }

        result = explain(
            txn_id="3000001",
            fraud_score=0.9421,
            features=features,
            client=mock_bedrock,
        )

        assert "Transaction 3000001 was flagged" in result
        mock_bedrock.invoke_model.assert_called_once()

        call_kwargs = mock_bedrock.invoke_model.call_args.kwargs
        assert call_kwargs["modelId"] == "anthropic.claude-3-haiku-20240307-v1:0"
        assert call_kwargs["contentType"] == "application/json"
        assert call_kwargs["accept"] == "application/json"

        # Inspect request body payload
        payload = json.loads(call_kwargs["body"])
        assert payload["anthropic_version"] == "bedrock-2023-05-31"
        assert "system" in payload
        assert "FraudGuard" in payload["system"]
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["role"] == "user"

        user_content = payload["messages"][0]["content"]
        assert "3000001" in user_content
        assert "0.9421" in user_content
        assert "$950.00" in user_content
        assert "03:00 UTC" in user_content
