"""
FraudGuard — SageMaker Real-Time Inference Entrypoint
Handles real-time model loading, request parsing, probability scoring,
and TreeSHAP feature attributions for production endpoints.
"""

import json
import logging
import os
import numpy as np
import pandas as pd
import xgboost as xgb

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

FEATURE_LIST_FILE = "feature_list.txt"


def _load_expected_features(model_dir: str):
    """Load the locked list of 64 expected feature names."""
    candidates = [
        os.path.join(model_dir, FEATURE_LIST_FILE),
        os.path.join(model_dir, "model_artifacts", FEATURE_LIST_FILE),
        os.path.join(os.path.dirname(__file__), "model_artifacts", FEATURE_LIST_FILE),
        os.path.join(os.getcwd(), "ml", "model_artifacts", FEATURE_LIST_FILE),
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                features = [line.strip() for line in f if line.strip()]
            logger.info(f"Loaded {len(features)} expected features from {path}")
            return features
    logger.warning("feature_list.txt not found in candidate paths; using empty fallback")
    return []


def model_fn(model_dir: str):
    """Load XGBoost model artifact from the model directory."""
    logger.info(f"Loading XGBoost model from model_dir: {model_dir}")
    
    candidates = [
        os.path.join(model_dir, "xgb_fraud_v1.json"),
        os.path.join(model_dir, "xgboost-model"),
        os.path.join(model_dir, "model_artifacts", "xgb_fraud_v1.json"),
        os.path.join(os.path.dirname(__file__), "model_artifacts", "xgb_fraud_v1.json"),
    ]
    
    booster = None
    for path in candidates:
        if os.path.exists(path):
            logger.info(f"Found model file at: {path}")
            booster = xgb.Booster()
            booster.load_model(path)
            break
            
    if booster is None:
        for root, _, files in os.walk(model_dir):
            for file in files:
                if file.endswith((".json", ".bin", "xgboost-model")):
                    p = os.path.join(root, file)
                    logger.info(f"Trying candidate model file: {p}")
                    try:
                        booster = xgb.Booster()
                        booster.load_model(p)
                        break
                    except Exception as e:
                        logger.warning(f"Failed to load {p}: {e}")
            if booster:
                break

    if booster is None:
        raise FileNotFoundError(f"Could not locate XGBoost model artifact in {model_dir}")

    expected_features = _load_expected_features(model_dir)
    defaults = _load_feature_defaults(model_dir)
    return {"booster": booster, "features": expected_features, "defaults": defaults}


def input_fn(request_body, request_content_type="application/json"):
    """Parse incoming request body into an aligned feature vector or DataFrame."""
    if request_content_type == "application/json":
        data = json.loads(request_body) if isinstance(request_body, (str, bytes)) else request_body
        return data
    elif request_content_type == "text/csv":
        s = request_body if isinstance(request_body, str) else request_body.decode("utf-8")
        lines = [line.strip().split(",") for line in s.strip().split("\n") if line.strip()]
        return lines
    else:
        raise ValueError(f"Unsupported content type: {request_content_type}")


EMAIL_BUCKET_MAP = {
    'protonmail.com': 'high_risk', 'mail.com': 'high_risk', 'outlook.es': 'high_risk',
    'aim.com': 'high_risk', 'outlook.com': 'high_risk',
    'hotmail.es': 'mid_risk', 'live.com.mx': 'mid_risk', 'hotmail.com': 'mid_risk',
}

DEFAULTS_FILE = "feature_defaults.json"


def _load_feature_defaults(model_dir: str):
    """Load default/median feature values for partial input payloads."""
    candidates = [
        os.path.join(model_dir, DEFAULTS_FILE),
        os.path.join(model_dir, "model_artifacts", DEFAULTS_FILE),
        os.path.join(os.path.dirname(__file__), "model_artifacts", DEFAULTS_FILE),
        os.path.join(os.getcwd(), "ml", "model_artifacts", DEFAULTS_FILE),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read {path}: {e}")
    return {}


def _align_features(data, expected_features, defaults=None):
    """Align raw or pre-encoded dict into the exact 64 feature vector."""
    if isinstance(data, list):
        arr = np.array(data, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        return arr

    if not isinstance(data, dict):
        raise ValueError("Input data must be a dictionary or list")

    if "features" in data and isinstance(data["features"], (dict, list)):
        return _align_features(data["features"], expected_features, defaults)

    defaults = defaults or {}
    data_copy = dict(data)

    # Automatically derive P_emaildomain_bucket if raw P_emaildomain is provided
    if "P_emaildomain" in data_copy and "P_emaildomain_bucket" not in data_copy:
        raw_email = str(data_copy["P_emaildomain"]).strip().lower()
        if raw_email:
            data_copy["P_emaildomain_bucket"] = EMAIL_BUCKET_MAP.get(raw_email, "low_risk")
        else:
            data_copy["P_emaildomain_bucket"] = "missing"

    row = []
    for feat in expected_features:
        if feat in data_copy:
            try:
                row.append(float(data_copy[feat]))
            except (ValueError, TypeError):
                row.append(float(defaults.get(feat, 0.0)))
        else:
            # Check if this feature is a one-hot column for a categorical field
            matched_onehot = False
            for raw_prefix in ["card4", "card6", "ProductCD", "M4", "M6", "P_emaildomain_bucket"]:
                if feat.startswith(f"{raw_prefix}_"):
                    suffix = feat[len(raw_prefix) + 1:]
                    if raw_prefix in data_copy:
                        raw_val = str(data_copy[raw_prefix]).lower()
                        if raw_val == suffix.lower():
                            row.append(1.0)
                        else:
                            row.append(0.0)
                        matched_onehot = True
                        break

            if not matched_onehot:
                # Use dataset median default if available, else fallback to 0.0
                row.append(float(defaults.get(feat, 0.0)))

    return np.array([row], dtype=np.float32)


def predict_fn(input_data, model_dict):
    """Run probability prediction and compute TreeSHAP feature attributions."""
    booster = model_dict["booster"]
    expected_features = model_dict.get("features", [])
    defaults = model_dict.get("defaults", {})

    X = _align_features(input_data, expected_features, defaults)
    
    feature_names = expected_features if (expected_features and len(expected_features) == X.shape[1]) else None
    dmatrix = xgb.DMatrix(X, feature_names=feature_names)
    
    raw_preds = booster.predict(dmatrix)
    fraud_score = float(raw_preds[0]) if len(raw_preds) > 0 else 0.0

    top_risk_factors = []
    try:
        contribs = booster.predict(dmatrix, pred_contribs=True)
        if len(contribs) > 0 and feature_names:
            feature_contribs = contribs[0][:-1]
            paired = []
            for i, name in enumerate(feature_names):
                if i < len(feature_contribs):
                    paired.append({
                        "feature": name,
                        "attribution": round(float(feature_contribs[i]), 4),
                        "input_value": float(X[0][i])
                    })
            paired.sort(key=lambda x: x["attribution"], reverse=True)
            top_risk_factors = paired[:5]
    except Exception as e:
        logger.debug(f"SHAP contribs computation skipped: {e}")

    return {
        "fraud_score": round(fraud_score, 4),
        "decision": "DECLINE" if fraud_score > 0.90 else ("REVIEW" if fraud_score > 0.50 else "APPROVE"),
        "top_risk_factors": top_risk_factors
    }


def output_fn(prediction, accept="application/json"):
    """Format the prediction response."""
    if accept == "application/json":
        return json.dumps(prediction), accept
    elif accept == "text/csv":
        return f"{prediction['fraud_score']},{prediction['decision']}\n", accept
    else:
        raise ValueError(f"Unsupported accept type: {accept}")
