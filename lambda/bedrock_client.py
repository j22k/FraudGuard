"""FraudGuard Bedrock Explainability Client.

This module constructs structured prompts using key transaction features and invokes
Anthropic Claude 3 Haiku via Amazon Bedrock Runtime to generate plain-English
fraud risk explanations.
"""

import json
import logging
import os
from typing import Any, Dict, Optional
import boto3

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"
ANTHROPIC_VERSION = "bedrock-2023-05-31"


def _extract_categorical_feature(features: Dict[str, Any], prefix: str, default: str = "unknown") -> str:
    """Extract a categorical feature value from raw key or one-hot encoded flags.

    Args:
        features: Dictionary containing transaction features.
        prefix: The base feature name (e.g. 'card4', 'card6', 'ProductCD', 'P_emaildomain_bucket').
        default: Fallback value if feature is not present.

    Returns:
        String representation of the categorical value.
    """
    # Check if direct raw feature key is present and not empty
    if prefix in features and features[prefix] is not None:
        raw_val = str(features[prefix]).strip()
        if raw_val and raw_val.lower() != "nan" and raw_val.lower() != "none":
            return raw_val

    # Check for one-hot encoded flags (e.g., 'card4_visa': 1, 'ProductCD_W': 1.0)
    prefix_pattern = f"{prefix}_"
    for key, value in features.items():
        if key.startswith(prefix_pattern):
            try:
                # Handle numeric 1, 1.0, or string '1', '1.0'
                if float(value) == 1.0:
                    category = key[len(prefix_pattern):].strip()
                    return category
            except (ValueError, TypeError):
                # Handle boolean True or string 'true'
                if str(value).strip().lower() in ("true", "1"):
                    category = key[len(prefix_pattern):].strip()
                    return category

    return default


def _format_feature_values(features: Dict[str, Any]) -> Dict[str, str]:
    """Extract and format human-readable transaction features for prompt construction.

    Args:
        features: Dictionary of raw and/or encoded transaction features.

    Returns:
        Dictionary of formatted feature strings.
    """
    # 1. Transaction Amount
    amt_val = features.get("TransactionAmt")
    if amt_val is not None and str(amt_val).strip() not in ("", "nan", "None"):
        try:
            amt_str = f"${float(amt_val):,.2f}"
        except (ValueError, TypeError):
            amt_str = f"${amt_val}"
    else:
        amt_str = "Unknown"

    # 2. Hour of Day
    hour_val = features.get("hour_of_day")
    if hour_val is not None and str(hour_val).strip() not in ("", "nan", "None"):
        try:
            hour_int = int(float(hour_val))
            hour_str = f"{hour_int:02d}:00 UTC"
        except (ValueError, TypeError):
            hour_str = str(hour_val)
    else:
        hour_str = "Unknown"

    # 3. Categoricals (ProductCD, card4, card6, P_emaildomain_bucket, M4, M6)
    product_cd = _extract_categorical_feature(features, "ProductCD", default="Unknown")
    card4 = _extract_categorical_feature(features, "card4", default="Unknown")
    card6 = _extract_categorical_feature(features, "card6", default="Unknown")
    email_risk = _extract_categorical_feature(features, "P_emaildomain_bucket", default="Unknown")
    m4_val = _extract_categorical_feature(features, "M4", default="Unknown")
    m6_val = _extract_categorical_feature(features, "M6", default="Unknown")

    if m6_val.upper() == "F":
        m6_str = "Failed / Mismatch (M6=F)"
    elif m6_val.upper() == "T":
        m6_str = "Passed / Matched (M6=T)"
    else:
        m6_str = m6_val

    # 4. Velocity Signal: card1_addr1_count
    velocity_val = features.get("card1_addr1_count")
    if velocity_val is not None and str(velocity_val).strip() not in ("", "nan", "None"):
        try:
            v_int = int(float(velocity_val))
            velocity_str = f"{v_int} transactions for card/address combo"
        except (ValueError, TypeError):
            velocity_str = str(velocity_val)
    else:
        velocity_str = "Unknown"

    # 5. Behavioral Time Deltas & Location (D2, D8, D10, D15, dist1)
    def _format_num_field(key: str, suffix: str = "") -> str:
        val = features.get(key)
        if val is not None and str(val).strip() not in ("", "nan", "None"):
            try:
                num = float(val)
                return f"{num:g}{suffix}"
            except (ValueError, TypeError):
                return f"{val}{suffix}"
        return "Not specified"

    d2_str = _format_num_field("D2", " days")
    d8_str = _format_num_field("D8", " days")
    d10_str = _format_num_field("D10", " days")
    d15_str = _format_num_field("D15", " days")
    dist1_str = _format_num_field("dist1", " miles")

    # 6. High-Variance Vesta Fraud Anomaly Flags (V45, V158, V189, V201, V228, V244, V257, V258)
    v_flags = []
    for v_key in ["V45", "V158", "V189", "V201", "V228", "V244", "V257", "V258"]:
        v_val = features.get(v_key)
        if v_val is not None and str(v_val).strip() not in ("", "nan", "None"):
            try:
                num = float(v_val)
                if num != 0:
                    v_flags.append(f"{v_key}={num:g}")
            except (ValueError, TypeError):
                v_flags.append(f"{v_key}={v_val}")
    v_flags_str = ", ".join(v_flags) if v_flags else "None / Baseline"

    # 7. Missing value indicators summary
    missing_flags = []
    for null_key in ["dist1_isnull", "addr1_isnull", "D2_isnull", "D10_isnull", "D15_isnull", "V258_isnull"]:
        val = features.get(null_key)
        if val is not None:
            if str(val).strip().lower() in ("true", "1", "1.0"):
                missing_flags.append(null_key.replace("_isnull", ""))
    missing_str = ", ".join(missing_flags) + " missing" if missing_flags else "All key fields present"

    return {
        "TransactionAmt": amt_str,
        "hour_of_day": hour_str,
        "ProductCD": product_cd,
        "card4": card4,
        "card6": card6,
        "P_emaildomain_bucket": email_risk,
        "M4": m4_val,
        "M6": m6_str,
        "card1_addr1_count": velocity_str,
        "D2": d2_str,
        "D8": d8_str,
        "D10": d10_str,
        "D15": d15_str,
        "dist1": dist1_str,
        "v_flags": v_flags_str,
        "missing_fields": missing_str,
    }


def explain(
    txn_id: str,
    fraud_score: float,
    features: Dict[str, Any],
    client: Optional[Any] = None,
    region_name: Optional[str] = None,
) -> str:
    """Generate a plain-English fraud risk explanation for a flagged transaction.

    Args:
        txn_id: The transaction ID.
        fraud_score: ML model fraud probability score (0.0 to 1.0).
        features: Dictionary containing transaction features (raw or one-hot).
        client: Optional boto3 bedrock-runtime client instance (useful for mocking).
        region_name: Optional AWS region override.

    Returns:
        Plain-English explanation generated by Claude 3 Haiku.
    """
    formatted_features = _format_feature_values(features)

    prompt = (
        f"Transaction ID: {txn_id}\n"
        f"Fraud Probability Score: {fraud_score:.4f} (Threshold: > 0.90)\n\n"
        f"TRANSACTION RISK ATTRIBUTES:\n"
        f"1. Basic Transaction Metrics:\n"
        f"   - Amount: {formatted_features['TransactionAmt']}\n"
        f"   - Hour of Day (UTC): {formatted_features['hour_of_day']}\n"
        f"   - Product Category: {formatted_features['ProductCD']}\n"
        f"   - Card Network: {formatted_features['card4']}\n"
        f"   - Card Type: {formatted_features['card6']}\n\n"
        f"2. Identity & Match Verification:\n"
        f"   - Email Domain Risk: {formatted_features['P_emaildomain_bucket']}\n"
        f"   - Address Match (M6): {formatted_features['M6']}\n"
        f"   - Match Rule Profile (M4): {formatted_features['M4']}\n\n"
        f"3. Velocity & Behavioral Signals:\n"
        f"   - Transaction Frequency: {formatted_features['card1_addr1_count']}\n"
        f"   - Days Since Prior Transaction (D2): {formatted_features['D2']}\n"
        f"   - Days Since Account Activity (D15): {formatted_features['D15']}\n"
        f"   - Location Distance (dist1): {formatted_features['dist1']}\n\n"
        f"4. Anomaly Risk Flags:\n"
        f"   - Vesta Anomaly Scores: {formatted_features['v_flags']}\n"
        f"   - Missing Field Flags: {formatted_features['missing_fields']}\n\n"
        f"Please generate a structured, plain-English fraud risk explanation (3-4 sentences) for the operations team. "
        f"State the primary risk drivers and recommend an immediate operational action."
    )

    system_prompt = (
        "You are FraudGuard, an automated financial fraud detection analyst. "
        "Provide a concise, clear 3-4 sentence risk analysis of why a transaction was flagged "
        "as high risk based on its features across Basic Metrics, Identity Match, Velocity, "
        "Behavioral Deltas, and Anomaly Risk Flags. State primary risk drivers and recommend "
        "an immediate operational action. Be objective, precise, and professional."
    )

    payload = {
        "anthropic_version": ANTHROPIC_VERSION,
        "max_tokens": 300,
        "temperature": 0.2,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }

    if client is None:
        region = region_name or os.environ.get("AWS_REGION", "us-east-1")
        client = boto3.client("bedrock-runtime", region_name=region)

    candidate_models = [
        MODEL_ID,
        "us.anthropic.claude-3-5-haiku-20241022-v1:0",
        "anthropic.claude-3-5-haiku-20241022-v1:0",
    ]

    for model_id in candidate_models:
        try:
            logger.info("Invoking Bedrock model %s for transaction %s (score: %.4f)", model_id, txn_id, fraud_score)
            response = client.invoke_model(
                modelId=model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(payload),
            )
            raw_body = response["body"].read()
            if isinstance(raw_body, bytes):
                response_body = json.loads(raw_body.decode("utf-8"))
            else:
                response_body = json.loads(raw_body)

            content_blocks = response_body.get("content", [])
            if content_blocks and isinstance(content_blocks, list):
                explanation = content_blocks[0].get("text", "").strip()
            else:
                explanation = str(response_body)

            logger.info("Successfully generated explanation for transaction %s using %s", txn_id, model_id)
            return explanation
        except Exception as e:
            logger.warning("Bedrock invocation with model %s failed: %s", model_id, str(e))
            continue

    # Fallback explanation if Bedrock model access is restricted
    amt_str = str(formatted_features.get('TransactionAmt', '$0.00'))
    hour_str = f"{formatted_features.get('hour_of_day', 'N/A')}"
    domain_str = formatted_features.get('P_emaildomain_bucket', 'unknown')
    card_str = f"{formatted_features.get('card4', 'card')} {formatted_features.get('card6', '')}".strip()
    m6_str = formatted_features.get('M6', 'unknown')
    velocity_str = formatted_features.get('card1_addr1_count', 'unknown')

    fallback_explanation = (
        f"Transaction {txn_id} was flagged with critical fraud score {fraud_score:.2f}. "
        f"Key risk indicators include high-value transaction of {amt_str} executed during "
        f"off-peak hours ({hour_str}) on a {card_str} with {domain_str} email risk profile, "
        f"address match status '{m6_str}', and velocity indicator '{velocity_str}'."
    )
    logger.info("Generated heuristic explanation for transaction %s: %s", txn_id, fallback_explanation)
    return fallback_explanation

