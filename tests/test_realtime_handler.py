"""Unit tests for FraudGuard Real-Time Lambda Handler.

Runs completely offline without AWS credentials by mocking boto3
sagemaker-runtime, bedrock-runtime, and dynamodb interfaces.
"""

import io
import json
import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest

LAMBDA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lambda"))
if LAMBDA_DIR not in sys.path:
    sys.path.insert(0, LAMBDA_DIR)

import realtime_handler


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Ensure deterministic offline environment."""
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("DYNAMODB_TABLE", "fraudguard-flagged-transactions-dev")
    monkeypatch.setenv("SAGEMAKER_ENDPOINT_NAME", "fraudguard-realtime-endpoint")
    monkeypatch.setenv("FRAUD_SCORE_THRESHOLD", "0.90")


def test_realtime_options_cors():
    """Verify CORS preflight OPTIONS request."""
    event = {"httpMethod": "OPTIONS"}
    resp = realtime_handler.lambda_handler(event)
    assert resp["statusCode"] == 200
    assert resp["headers"]["Access-Control-Allow-Origin"] == "*"


def test_realtime_high_risk_triggers_bedrock():
    """Verify a high-risk transaction (>0.90) invokes Bedrock and saves to DynamoDB."""
    payload = {
        "txn_id": "TXN-TEST-9999",
        "TransactionAmt": 2850.00,
        "fraud_score": 0.9621,
        "ProductCD": "W",
        "card4": "visa",
        "card6": "credit",
        "P_emaildomain": "protonmail.com",
        "hour_of_day": 3.0,
    }
    event = {
        "httpMethod": "POST",
        "body": json.dumps(payload),
    }

    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    with patch("realtime_handler.explain") as mock_explain, \
         patch("boto3.resource", return_value=mock_dynamodb):
        
        mock_explain.return_value = "High risk transaction: Abnormally large amount at 03:00 UTC."
        
        resp = realtime_handler.lambda_handler(event)

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["txn_id"] == "TXN-TEST-9999"
        assert body["fraud_score"] == 0.9621
        assert body["decision"] == "DECLINE"
        assert "latency_ms" in body
        assert body["latency_ms"]["ml_inference"] >= 0
        assert body["source"] == "realtime"

        # Verify Bedrock was invoked
        mock_explain.assert_called_once()

        # Verify DynamoDB put_item was called with source: realtime
        mock_table.put_item.assert_called_once()
        saved_item = mock_table.put_item.call_args[1]["Item"]
        assert saved_item["TransactionID"] == "TXN-TEST-9999"
        assert saved_item["source"] == "realtime"
        assert saved_item["fraud_score"] == Decimal("0.9621")


def test_realtime_clean_skips_bedrock():
    """Verify a clean transaction (<=0.90) skips Bedrock invocation to protect costs."""
    payload = {
        "txn_id": "TXN-TEST-CLEAN",
        "TransactionAmt": 25.00,
        "fraud_score": 0.1250,
        "card4": "visa",
        "card6": "debit",
        "hour_of_day": 14.0,
    }
    event = {
        "httpMethod": "POST",
        "body": json.dumps(payload),
    }

    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    with patch("realtime_handler.explain") as mock_explain, \
         patch("boto3.resource", return_value=mock_dynamodb):
        
        resp = realtime_handler.lambda_handler(event)

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["decision"] == "APPROVE"
        assert body["fraud_score"] == 0.1250

        # Bedrock should NOT be called on clean traffic
        mock_explain.assert_not_called()


def test_realtime_invalid_json():
    """Verify handler responds with 400 Bad Request on malformed JSON payload."""
    event = {
        "httpMethod": "POST",
        "body": "{invalid-json",
    }
    resp = realtime_handler.lambda_handler(event)
    assert resp["statusCode"] == 400
