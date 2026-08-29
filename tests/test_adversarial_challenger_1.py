"""Adversarial stress-test suite executed by Challenger 1 (Lambda & Data Stream).

This suite tests edge cases, boundary conditions, URL encoding, categorical extraction,
Decimal precision, zero-call cost rules, and failure modes in lambda/handler.py and lambda/bedrock_client.py.
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

import handler
import bedrock_client


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("DYNAMODB_TABLE", "fraudguard-flagged-transactions-dev")
    monkeypatch.setenv("FRAUD_SCORE_THRESHOLD", "0.9")


def _create_mock_environment(csv_content: str):
    """Helper to mock S3, Bedrock, and DynamoDB for a given CSV string."""
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {
        "Body": io.BytesIO(csv_content.encode("utf-8"))
    }

    mock_bedrock = MagicMock()
    bedrock_response = {
        "content": [{"type": "text", "text": "Mocked explanation for flagged transaction."}]
    }
    mock_bedrock.invoke_model.return_value = {
        "body": io.BytesIO(json.dumps(bedrock_response).encode("utf-8"))
    }

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

    return {
        "s3": mock_s3,
        "bedrock": mock_bedrock,
        "dynamodb": mock_dynamodb,
        "table": mock_table,
        "client_side_effect": client_side_effect,
        "resource_side_effect": resource_side_effect,
    }


# ==============================================================================
# DIMENSION 1: Score Boundary Conditions & Threshold Logic
# ==============================================================================
class TestScoreBoundaries:
    """Stress-test score boundaries around threshold 0.9."""

    @pytest.mark.parametrize(
        "score_str,should_trigger",
        [
            ("0.9", False),           # Exact boundary: 0.9 <= 0.9 MUST be skipped
            ("0.90", False),          # Exact boundary formatted
            ("0.90000000", False),    # Exact boundary float
            ("0.89999999", False),    # Just below threshold
            ("0.90000001", True),     # Just above threshold MUST trigger
            ("0.900001", True),       # Above threshold
            ("0.95", True),           # Well above threshold
            ("1.0", True),            # Maximum valid probability
            ("1.0000", True),         # Maximum valid probability
            ("0.0", False),           # Minimum probability
            ("0.0000", False),        # Minimum probability
            ("-0.0001", False),       # Negative score
            ("-1.0", False),          # Negative score
            ("-99.0", False),         # Extreme negative
            ("1.5", True),            # Over 1.0 (anomalous score)
        ],
    )
    def test_score_boundary_conditions(self, score_str, should_trigger):
        csv_data = f"TransactionID,fraud_score,TransactionAmt,hour_of_day\ntxn_test,{score_str},100.0,12\n"
        env = _create_mock_environment(csv_data)

        with patch("boto3.client", side_effect=env["client_side_effect"]), \
             patch("boto3.resource", side_effect=env["resource_side_effect"]):
            event = {
                "detail": {
                    "bucket": {"name": "test-bucket"},
                    "object": {"key": "inference-output/test_boundary.csv"},
                }
            }
            res = handler.handler(event, None)

            assert res["statusCode"] == 200
            assert res["records_processed"] == 1
            if should_trigger:
                assert res["fraud_detected"] == 1
                assert res["explanations_generated"] == 1
                assert env["bedrock"].invoke_model.call_count == 1
                assert env["table"].put_item.call_count == 1
            else:
                assert res["fraud_detected"] == 0
                assert res["explanations_generated"] == 0
                assert env["bedrock"].invoke_model.call_count == 0
                assert env["table"].put_item.call_count == 0

    @pytest.mark.parametrize(
        "invalid_score",
        ["", "   ", "nan", "NaN", "None", "null", "N/A", "undefined", "abc", "0.9.9", "inf", "-inf"],
    )
    def test_invalid_and_missing_scores_handled_gracefully(self, invalid_score):
        """Ensure invalid score strings do not raise unhandled exceptions and are skipped."""
        csv_data = f"TransactionID,fraud_score,TransactionAmt\ntxn_bad,{invalid_score},50.0\n"
        env = _create_mock_environment(csv_data)

        with patch("boto3.client", side_effect=env["client_side_effect"]), \
             patch("boto3.resource", side_effect=env["resource_side_effect"]):
            event = {
                "detail": {
                    "bucket": {"name": "test-bucket"},
                    "object": {"key": "inference-output/test_invalid.csv"},
                }
            }
            res = handler.handler(event, None)

            assert res["statusCode"] == 200
            assert res["records_processed"] == 1
            # Note: inf is a float that is > 0.9, but strings like 'abc' or 'nan' shouldn't crash
            if invalid_score.lower() == "inf":
                # float("inf") > 0.9 in Python
                assert res["fraud_detected"] == 1
            else:
                assert res["fraud_detected"] == 0
                assert env["bedrock"].invoke_model.call_count == 0
                assert env["table"].put_item.call_count == 0

    def test_environment_threshold_parsing_edge_cases(self, monkeypatch):
        """Test invalid FRAUD_SCORE_THRESHOLD fallback to 0.9."""
        monkeypatch.setenv("FRAUD_SCORE_THRESHOLD", "invalid_threshold_str")
        csv_data = "TransactionID,fraud_score\ntxn1,0.91\ntxn2,0.89\n"
        env = _create_mock_environment(csv_data)

        with patch("boto3.client", side_effect=env["client_side_effect"]), \
             patch("boto3.resource", side_effect=env["resource_side_effect"]):
            event = {
                "detail": {
                    "bucket": {"name": "test-bucket"},
                    "object": {"key": "inference-output/test_env.csv"},
                }
            }
            res = handler.handler(event, None)
            assert res["statusCode"] == 200
            # Defaulted to 0.9, so 0.91 triggers, 0.89 skipped
            assert res["fraud_detected"] == 1
            assert res["explanations_generated"] == 1


# ==============================================================================
# DIMENSION 2: S3 URL-Encoded Keys Handling
# ==============================================================================
class TestS3UrlEncoding:
    """Stress-test URL-encoded S3 keys containing spaces, pluses, and special characters."""

    @pytest.mark.parametrize(
        "raw_event_key,expected_s3_key",
        [
            ("inference-output/results+batch+1.csv", "inference-output/results batch 1.csv"),
            ("inference-output/results%20batch%201.csv", "inference-output/results batch 1.csv"),
            ("inference-output/run%2B2026/results.csv", "inference-output/run+2026/results.csv"),
            ("inference-output/batch%2Fsubfolder/results%20file.csv", "inference-output/batch/subfolder/results file.csv"),
            ("inference-output/special%40folder/test+results.csv", "inference-output/special@folder/test results.csv"),
        ],
    )
    def test_eventbridge_url_unquoting(self, raw_event_key, expected_s3_key):
        csv_data = "TransactionID,fraud_score\n3000001,0.95\n"
        env = _create_mock_environment(csv_data)

        with patch("boto3.client", side_effect=env["client_side_effect"]), \
             patch("boto3.resource", side_effect=env["resource_side_effect"]):
            event = {
                "detail": {
                    "bucket": {"name": "test-bucket"},
                    "object": {"key": raw_event_key},
                }
            }
            res = handler.handler(event, None)

            assert res["statusCode"] == 200
            # Check that S3 get_object received the unquoted key
            env["s3"].get_object.assert_called_once_with(
                Bucket="test-bucket",
                Key=expected_s3_key,
            )
            assert res["fraud_detected"] == 1

    def test_direct_s3_notification_url_unquoting(self):
        csv_data = "TransactionID,fraud_score\n3000001,0.95\n"
        env = _create_mock_environment(csv_data)

        with patch("boto3.client", side_effect=env["client_side_effect"]), \
             patch("boto3.resource", side_effect=env["resource_side_effect"]):
            event = {
                "Records": [
                    {
                        "s3": {
                            "bucket": {"name": "test-bucket"},
                            "object": {"key": "inference-output/results+file%20v2.csv"},
                        }
                    }
                ]
            }
            res = handler.handler(event, None)

            assert res["statusCode"] == 200
            env["s3"].get_object.assert_called_once_with(
                Bucket="test-bucket",
                Key="inference-output/results file v2.csv",
            )


# ==============================================================================
# DIMENSION 3: Categorical Features & One-Hot vs Raw Representations
# ==============================================================================
class TestFeatureExtraction:
    """Stress-test categorical extraction across one-hot, raw, missing, and malformed features."""

    def test_raw_categorical_features(self):
        """Direct raw column names should be extracted cleanly."""
        features = {
            "TransactionAmt": "250.75",
            "hour_of_day": "14",
            "ProductCD": "W",
            "card4": "visa",
            "card6": "credit",
            "P_emaildomain_bucket": "high_risk",
        }
        formatted = bedrock_client._format_feature_values(features)
        assert formatted["TransactionAmt"] == "$250.75"
        assert formatted["hour_of_day"] == "14:00 UTC"
        assert formatted["ProductCD"] == "W"
        assert formatted["card4"] == "visa"
        assert formatted["card6"] == "credit"
        assert formatted["P_emaildomain_bucket"] == "high_risk"

    def test_one_hot_encoded_features(self):
        """One-hot encoded flags (from 64-feature list) should be mapped back to categories."""
        features = {
            "TransactionAmt": 1500.0,
            "hour_of_day": 3.0,
            "ProductCD_C": 0,
            "ProductCD_H": 0,
            "ProductCD_R": 0,
            "ProductCD_S": 0,
            "ProductCD_W": 1.0,
            "card4_american express": 0,
            "card4_discover": 0,
            "card4_mastercard": 0,
            "card4_visa": 1,
            "card6_credit": 1.0,
            "card6_debit": 0,
            "P_emaildomain_bucket_high_risk": 1,
            "P_emaildomain_bucket_low_risk": 0,
        }
        formatted = bedrock_client._format_feature_values(features)
        assert formatted["TransactionAmt"] == "$1,500.00"
        assert formatted["hour_of_day"] == "03:00 UTC"
        assert formatted["ProductCD"] == "W"
        assert formatted["card4"] == "visa"
        assert formatted["card6"] == "credit"
        assert formatted["P_emaildomain_bucket"] == "high_risk"

    def test_boolean_and_string_one_hot_flags(self):
        """String/boolean variants in one-hot columns should be handled."""
        features = {
            "ProductCD_R": "1",
            "card4_mastercard": "True",
            "card6_charge card": "true",
            "P_emaildomain_bucket_mid_risk": "1.0",
        }
        formatted = bedrock_client._format_feature_values(features)
        assert formatted["ProductCD"] == "R"
        assert formatted["card4"] == "mastercard"
        assert formatted["card6"] == "charge card"
        assert formatted["P_emaildomain_bucket"] == "mid_risk"

    def test_missing_and_nan_features_fallback(self):
        """Missing or NaN features must fall back gracefully to Unknown."""
        features = {
            "TransactionAmt": "nan",
            "hour_of_day": "None",
            "ProductCD": "",
            "card4": "NaN",
            "card6": None,
            # P_emaildomain_bucket omitted completely
        }
        formatted = bedrock_client._format_feature_values(features)
        assert formatted["TransactionAmt"] == "Unknown"
        assert formatted["hour_of_day"] == "Unknown"
        assert formatted["ProductCD"] == "Unknown"
        assert formatted["card4"] == "Unknown"
        assert formatted["card6"] == "Unknown"
        assert formatted["P_emaildomain_bucket"] == "Unknown"

    def test_malformed_numeric_features(self):
        """Malformed amounts or hours shouldn't raise unhandled exceptions."""
        features = {
            "TransactionAmt": "not_a_number",
            "hour_of_day": "midnight",
        }
        formatted = bedrock_client._format_feature_values(features)
        assert formatted["TransactionAmt"] == "$not_a_number"
        assert formatted["hour_of_day"] == "midnight"

    def test_prompt_construction_with_features(self):
        """Verify prompt contains formatted features."""
        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.return_value = {
            "body": io.BytesIO(b'{"content":[{"type":"text","text":"Explanation"}]}')
        }

        bedrock_client.explain(
            txn_id="TX_999",
            fraud_score=0.9750,
            features={
                "TransactionAmt": "3200.50",
                "hour_of_day": "4",
                "ProductCD_W": 1,
                "card4_visa": 1,
                "card6_debit": 1,
                "P_emaildomain_bucket_high_risk": 1,
            },
            client=mock_bedrock,
        )

        call_args = mock_bedrock.invoke_model.call_args.kwargs
        payload = json.loads(call_args["body"])
        prompt = payload["messages"][0]["content"]

        assert "Transaction ID: TX_999" in prompt
        assert "Fraud Probability Score: 0.9750" in prompt
        assert "$3,200.50" in prompt
        assert "04:00 UTC" in prompt
        assert "Product Category: W" in prompt
        assert "Card Network: visa" in prompt
        assert "Card Type: debit" in prompt
        assert "Email Domain Risk: high_risk" in prompt


# ==============================================================================
# DIMENSION 4: Decimal Precision Integrity in DynamoDB
# ==============================================================================
class TestDecimalPrecisionIntegrity:
    """Stress-test Decimal precision and type verification in DynamoDB writes."""

    @pytest.mark.parametrize(
        "raw_score_str,expected_decimal",
        [
            ("0.9421", Decimal("0.9421")),
            ("0.90000001", Decimal("0.90000001")),
            ("0.999999", Decimal("0.999999")),
            ("1.0", Decimal("1.0")),
            ("0.9123456789", Decimal("0.9123456789")),
        ],
    )
    def test_decimal_conversion_accuracy(self, raw_score_str, expected_decimal):
        """Verify that Decimal conversion does not produce IEEE-754 float precision artifacts."""
        csv_data = f"TransactionID,fraud_score,TransactionAmt\nTXN_DEC,{raw_score_str},100\n"
        env = _create_mock_environment(csv_data)

        with patch("boto3.client", side_effect=env["client_side_effect"]), \
             patch("boto3.resource", side_effect=env["resource_side_effect"]):
            event = {
                "detail": {
                    "bucket": {"name": "test-bucket"},
                    "object": {"key": "inference-output/test_decimal.csv"},
                }
            }
            handler.handler(event, None)

            put_call = env["table"].put_item.call_args
            assert put_call is not None
            item = put_call.kwargs["Item"]

            # Must be Decimal instance
            assert isinstance(item["fraud_score"], Decimal)
            assert item["fraud_score"] == expected_decimal
            # Verify string representation has no binary artifact like '0.94210000000000002629'
            assert str(item["fraud_score"]) == str(expected_decimal)

    def test_dynamodb_schema_strictness(self):
        """Ensure all DynamoDB item fields strictly match expected string/Decimal types."""
        csv_data = "TransactionID,fraud_score,TransactionAmt\n3000001,0.95,100\n"
        env = _create_mock_environment(csv_data)

        with patch("boto3.client", side_effect=env["client_side_effect"]), \
             patch("boto3.resource", side_effect=env["resource_side_effect"]):
            event = {
                "detail": {
                    "bucket": {"name": "test-bucket"},
                    "object": {"key": "inference-output/test_schema.csv"},
                }
            }
            handler.handler(event, None)

            item = env["table"].put_item.call_args.kwargs["Item"]
            assert set(item.keys()) == {"TransactionID", "txn_id", "fraud_score", "explanation", "timestamp"}
            assert isinstance(item["TransactionID"], str)
            assert isinstance(item["txn_id"], str)
            assert isinstance(item["fraud_score"], Decimal)
            assert isinstance(item["explanation"], str)
            assert isinstance(item["timestamp"], str)
            assert item["timestamp"].endswith("+00:00") or item["timestamp"].endswith("Z")


# ==============================================================================
# DIMENSION 5: 100% Clean Batch Zero-Call Guarantee
# ==============================================================================
class TestCleanBatchZeroCallGuarantee:
    """Verify zero Bedrock / DynamoDB calls when batch is 100% clean."""

    def test_mixed_clean_batch_zero_calls(self):
        """Batch containing 0.0, 0.5, 0.8999, 0.9000 (boundary), negative, and empty score."""
        clean_rows_csv = (
            "TransactionID,fraud_score,TransactionAmt,hour_of_day\n"
            "C1,0.0,10.0,1\n"
            "C2,0.1234,25.0,2\n"
            "C3,0.5000,50.0,3\n"
            "C4,0.8999,75.0,4\n"
            "C5,0.9000,100.0,5\n"      # Exactly 0.9000
            "C6,-0.100,15.0,6\n"
            "C7,,20.0,7\n"             # Empty score
            "C8,invalid,30.0,8\n"      # Invalid score
        )
        env = _create_mock_environment(clean_rows_csv)

        with patch("boto3.client", side_effect=env["client_side_effect"]), \
             patch("boto3.resource", side_effect=env["resource_side_effect"]):
            event = {
                "detail": {
                    "bucket": {"name": "test-bucket"},
                    "object": {"key": "inference-output/all_clean.csv"},
                }
            }
            res = handler.handler(event, None)

            assert res["statusCode"] == 200
            assert res["records_processed"] == 8
            assert res["fraud_detected"] == 0
            assert res["explanations_generated"] == 0

            # Absolute zero cost rule: No Bedrock calls, No DynamoDB calls
            assert env["bedrock"].invoke_model.call_count == 0
            assert env["table"].put_item.call_count == 0


# ==============================================================================
# ADDITIONAL STRESS CASES: Large batch, S3 error handling, Bedrock error propagation
# ==============================================================================
class TestResilienceAndScale:
    """Test handler behavior on large datasets, empty files, and error conditions."""

    def test_large_batch_processing(self):
        """Process 500 rows with 50 fraud rows (>0.9) and 450 clean rows."""
        lines = ["TransactionID,fraud_score,TransactionAmt,hour_of_day"]
        expected_fraud = 0
        for i in range(1, 501):
            if i % 10 == 0:
                score = 0.91 + (i % 8) * 0.01
                expected_fraud += 1
            else:
                score = (i % 9) * 0.1  # 0.0 to 0.8
            lines.append(f"TX_{i},{score:.4f},{i*10.5:.2f},{i%24}")

        csv_content = "\n".join(lines) + "\n"
        env = _create_mock_environment(csv_content)

        with patch("boto3.client", side_effect=env["client_side_effect"]), \
             patch("boto3.resource", side_effect=env["resource_side_effect"]):
            event = {
                "detail": {
                    "bucket": {"name": "test-bucket"},
                    "object": {"key": "inference-output/large_batch.csv"},
                }
            }
            res = handler.handler(event, None)

            assert res["statusCode"] == 200
            assert res["records_processed"] == 500
            assert res["fraud_detected"] == expected_fraud
            assert res["explanations_generated"] == expected_fraud
            assert env["bedrock"].invoke_model.call_count == expected_fraud
            assert env["table"].put_item.call_count == expected_fraud

    def test_empty_csv_header_only(self):
        """CSV with only headers should process 0 records gracefully."""
        csv_content = "TransactionID,fraud_score,TransactionAmt\n"
        env = _create_mock_environment(csv_content)

        with patch("boto3.client", side_effect=env["client_side_effect"]), \
             patch("boto3.resource", side_effect=env["resource_side_effect"]):
            event = {
                "detail": {
                    "bucket": {"name": "test-bucket"},
                    "object": {"key": "inference-output/empty.csv"},
                }
            }
            res = handler.handler(event, None)

            assert res["statusCode"] == 200
            assert res["records_processed"] == 0
            assert res["fraud_detected"] == 0
            assert env["bedrock"].invoke_model.call_count == 0
            assert env["table"].put_item.call_count == 0

    def test_invalid_event_structure_returns_400(self):
        """Completely invalid event structure should return 400 error."""
        invalid_event = {"something_unexpected": True}
        res = handler.handler(invalid_event, None)
        assert res["statusCode"] == 400
        assert res["records_processed"] == 0
        assert res["fraud_detected"] == 0
