#!/usr/bin/env python3
"""
FraudGuard — SageMaker Evaluation Entrypoint
Evaluates the trained XGBoost model on the test dataset.
"""

import json
import os
import tarfile
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import average_precision_score, roc_auc_score, precision_recall_curve

DROP_COLS = ['TransactionID', 'TransactionDT', 'isFraud']
TARGET_COL = 'isFraud'


def eval_set_metrics(model, X, y):
    y_pred_proba = model.predict_proba(X)[:, 1]

    aucpr = float(average_precision_score(y, y_pred_proba))
    auc_roc = float(roc_auc_score(y, y_pred_proba))

    precisions, recalls, thresholds = precision_recall_curve(y, y_pred_proba)
    pr_at_thresholds = {}
    for t in [0.3, 0.5, 0.7, 0.9]:
        idx = int(np.argmin(np.abs(thresholds - t)))
        pr_at_thresholds[str(t)] = {
            'precision': float(precisions[idx]),
            'recall': float(recalls[idx]),
        }

    return {
        'aucpr': aucpr,
        'auc_roc': auc_roc,
        'precision_recall_at_thresholds': pr_at_thresholds,
    }


if __name__ == '__main__':
    model_path = '/opt/ml/processing/model/model.tar.gz'
    test_path = '/opt/ml/processing/test/test.csv'
    output_dir = '/opt/ml/processing/evaluation'
    os.makedirs(output_dir, exist_ok=True)

    # Extract model
    print(f"Extracting model from {model_path}...")
    with tarfile.open(model_path, 'r:gz') as tar:
        tar.extractall('/tmp/model')

    model = xgb.XGBClassifier()
    model.load_model('/tmp/model/xgb_fraud_v1.json')
    print("Model loaded successfully.")

    # Load test data
    print(f"Loading test data from {test_path}...")
    test = pd.read_csv(test_path)
    X_test = test.drop(columns=DROP_COLS)
    y_test = test[TARGET_COL]

    # Evaluate
    print("Evaluating on test split...")
    results = {
        'test': eval_set_metrics(model, X_test, y_test)
    }

    print(f"Test AUC-PR:  {results['test']['aucpr']:.4f}")
    print(f"Test AUC-ROC: {results['test']['auc_roc']:.4f}")

    eval_filepath = os.path.join(output_dir, 'eval_results.json')
    with open(eval_filepath, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Evaluation complete. Results saved to {eval_filepath}")
