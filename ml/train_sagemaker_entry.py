"""
FraudGuard — SageMaker Training Entrypoint
Wrapper around train.py that adapts I/O to SageMaker container paths.
"""

import argparse
import os
import json
import pandas as pd
import numpy as np
import xgboost as xgb

# Import utility functions from train.py which is in the same directory (ml/)
from train import split_xy, eval_set_metrics, compute_scale_pos_weight

def train_model(X_train, y_train, X_val, y_val, scale_pos_weight, args):
    model = xgb.XGBClassifier(
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        learning_rate=args.learning_rate,
        subsample=args.subsample,
        colsample_bytree=args.colsample_bytree,
        scale_pos_weight=scale_pos_weight,
        eval_metric='aucpr',
        early_stopping_rounds=args.early_stopping_rounds,
        random_state=42,
        n_jobs=-1,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=50,
    )

    return model

if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    # SageMaker hyperparameters are passed as command-line arguments
    parser.add_argument('--n_estimators', type=int, default=1200)
    parser.add_argument('--max_depth', type=int, default=6)
    parser.add_argument('--learning_rate', type=float, default=0.05)
    parser.add_argument('--subsample', type=float, default=0.8)
    parser.add_argument('--colsample_bytree', type=float, default=0.8)
    parser.add_argument('--early_stopping_rounds', type=int, default=30)

    # SageMaker environment variables
    parser.add_argument('--model_dir', type=str, default=os.environ.get('SM_MODEL_DIR', '/opt/ml/model'))
    parser.add_argument('--train_dir', type=str, default=os.environ.get('SM_CHANNEL_TRAIN', '/opt/ml/input/data/train'))
    parser.add_argument('--val_dir', type=str, default=os.environ.get('SM_CHANNEL_VALIDATION', '/opt/ml/input/data/validation'))
    parser.add_argument('--test_dir', type=str, default=os.environ.get('SM_CHANNEL_TEST', '/opt/ml/input/data/test'))
    parser.add_argument('--output_data_dir', type=str, default=os.environ.get('SM_OUTPUT_DATA_DIR', '/opt/ml/output/data'))

    args, _ = parser.parse_known_args()

    # Load data from SageMaker input channels
    print("Loading data...")
    train = pd.read_csv(os.path.join(args.train_dir, 'train.csv'))
    val = pd.read_csv(os.path.join(args.val_dir, 'val.csv'))
    test = pd.read_csv(os.path.join(args.test_dir, 'test.csv'))

    # Split X and y
    X_train, y_train = split_xy(train)
    X_val, y_val = split_xy(val)
    X_test, y_test = split_xy(test)

    # Compute class weights
    scale_pos_weight = compute_scale_pos_weight(y_train)
    print(f"scale_pos_weight: {scale_pos_weight:.2f}")

    # Train model
    print("Training model...")
    model = train_model(X_train, y_train, X_val, y_val, scale_pos_weight, args)

    # Evaluate model
    print("Evaluating model...")
    results = {
        'val': eval_set_metrics(model, X_val, y_val),
        'test': eval_set_metrics(model, X_test, y_test),
    }

    for split_name in ['val', 'test']:
        m = results[split_name]
        print(f"\n{split_name.upper()} AUC-PR:  {m['aucpr']:.4f}")
        print(f"{split_name.upper()} AUC-ROC: {m['auc_roc']:.4f}")

    # Save evaluation results to evaluation output path for ConditionStep / PropertyFile
    eval_dir = os.path.join(args.output_data_dir, 'evaluation')
    os.makedirs(eval_dir, exist_ok=True)
    eval_filepath = os.path.join(eval_dir, 'eval_results.json')
    
    with open(eval_filepath, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Saved evaluation results to {eval_filepath}")

    # Save model artifacts and feature list to SM_MODEL_DIR
    model_filepath = os.path.join(args.model_dir, 'xgb_fraud_v1.json')
    model.save_model(model_filepath)
    print(f"Model saved to {model_filepath}")

    feature_filepath = os.path.join(args.model_dir, 'feature_list.txt')
    with open(feature_filepath, 'w') as f:
        f.write('\n'.join(X_train.columns.tolist()))
    print(f"Feature list saved to {feature_filepath}")
