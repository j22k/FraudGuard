"""
FraudGuard — local XGBoost training + eval
Run: python ml/train.py
"""

import os
import json
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score

DROP_COLS = ['TransactionID', 'TransactionDT', 'isFraud']
TARGET_COL = 'isFraud'

MODEL_OUT = 'ml/model_artifacts/xgb_fraud_v1.json'
FEATURE_LIST_OUT = 'ml/model_artifacts/feature_list.txt'
EVAL_RESULTS_OUT = 'ml/model_artifacts/eval_results.json'


def load_data():
    train = pd.read_csv('data/processed/train.csv')
    val = pd.read_csv('data/processed/val.csv')
    test = pd.read_csv('data/processed/test.csv')
    return train, val, test


def split_xy(df: pd.DataFrame):
    X = df.drop(columns=DROP_COLS)
    y = df[TARGET_COL]
    return X, y


def compute_scale_pos_weight(y: pd.Series) -> float:
    neg = (y == 0).sum()
    pos = (y == 1).sum()
    return neg / pos


def train_model(X_train, y_train, X_val, y_val, scale_pos_weight):
    model = xgb.XGBClassifier(
        n_estimators=1200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos_weight,
        eval_metric='aucpr',
        early_stopping_rounds=30,
        random_state=42,
        n_jobs=-1,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=50,
    )

    return model


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


def evaluate_and_save(model, X_val, y_val, X_test, y_test):
    os.makedirs('ml/model_artifacts', exist_ok=True)

    results = {
        'val': eval_set_metrics(model, X_val, y_val),
        'test': eval_set_metrics(model, X_test, y_test),
    }

    for split_name in ['val', 'test']:
        m = results[split_name]
        print(f"\n{split_name.upper()} AUC-PR:  {m['aucpr']:.4f}")
        print(f"{split_name.upper()} AUC-ROC: {m['auc_roc']:.4f}")
        for t, pr in m['precision_recall_at_thresholds'].items():
            print(f"  threshold={t}: precision={pr['precision']:.3f}, recall={pr['recall']:.3f}")

    with open(EVAL_RESULTS_OUT, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nEval results saved: {EVAL_RESULTS_OUT}")

    return results


def feature_importance(model, X_train):
    importances = pd.Series(model.feature_importances_, index=X_train.columns)
    importances = importances.sort_values(ascending=False)
    print("\nTop 15 feature importances:")
    print(importances.head(15))
    return importances


def save_artifacts(model, feature_cols):
    os.makedirs('ml/model_artifacts', exist_ok=True)

    model.save_model(MODEL_OUT)

    with open(FEATURE_LIST_OUT, 'w') as f:
        f.write('\n'.join(feature_cols))

    print(f"Model saved: {MODEL_OUT}")
    print(f"Feature list saved: {FEATURE_LIST_OUT}")


def run():
    train, val, test = load_data()

    X_train, y_train = split_xy(train)
    X_val, y_val = split_xy(val)
    X_test, y_test = split_xy(test)

    scale_pos_weight = compute_scale_pos_weight(y_train)
    print(f"scale_pos_weight: {scale_pos_weight:.2f}")

    model = train_model(X_train, y_train, X_val, y_val, scale_pos_weight)

    evaluate_and_save(model, X_val, y_val, X_test, y_test)
    feature_importance(model, X_train)

    save_artifacts(model, X_train.columns.tolist())


if __name__ == '__main__':
    run()