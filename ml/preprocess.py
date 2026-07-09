"""
FraudGuard — preprocessing
Locked feature list (27 features) → clean train/val/test splits, time-based.
"""

import pandas as pd
import numpy as np


NUMERIC_COLS = [
    'TransactionAmt', 'card1', 'card2', 'card3', 'card5', 'addr1', 'dist1',
    'D2', 'D8', 'D10', 'D15',
    'V257', 'V244', 'V201', 'V189', 'V45', 'V158', 'V228', 'V258'
]

CATEGORICAL_COLS = ['ProductCD', 'card4', 'card6', 'M4', 'M6']
TARGET_COL = 'isFraud'
ID_COL = 'TransactionID'
TIME_COL = 'TransactionDT'
RAW_EMAIL_COL = 'P_emaildomain'

# raw columns actually needed from CSV — everything else skipped at read time
RAW_COLS = [ID_COL, TARGET_COL, TIME_COL, RAW_EMAIL_COL] + NUMERIC_COLS + CATEGORICAL_COLS

EMAIL_BUCKET_MAP = {
    'protonmail.com': 'high_risk', 'mail.com': 'high_risk', 'outlook.es': 'high_risk',
    'aim.com': 'high_risk', 'outlook.com': 'high_risk',
    'hotmail.es': 'mid_risk', 'live.com.mx': 'mid_risk', 'hotmail.com': 'mid_risk',
}
DEFAULT_BUCKET = 'low_risk'


def bucket_email(domain: str) -> str:
    if pd.isna(domain):
        return 'missing'
    return EMAIL_BUCKET_MAP.get(domain, DEFAULT_BUCKET)


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df['hour_of_day'] = (df[TIME_COL] // 3600) % 24
    df['card1_addr1_count'] = df.groupby(['card1', 'addr1'], dropna=False)['card1'].transform('count')
    df['P_emaildomain_bucket'] = df[RAW_EMAIL_COL].apply(bucket_email)
    df.drop(columns=[RAW_EMAIL_COL], inplace=True)
    return df


def handle_missing(df: pd.DataFrame) -> pd.DataFrame:
    for col in NUMERIC_COLS:
        if df[col].isnull().any():
            df[f'{col}_isnull'] = df[col].isnull().astype(int)
            df[col] = df[col].fillna(df[col].median())

    for col in CATEGORICAL_COLS:
        df[col] = df[col].fillna('missing')

    return df


def encode_categoricals(df: pd.DataFrame) -> pd.DataFrame:
    cat_cols = CATEGORICAL_COLS + ['P_emaildomain_bucket']
    return pd.get_dummies(df, columns=cat_cols, dummy_na=False)


def time_based_split(df: pd.DataFrame, train_frac=0.7, val_frac=0.15):
    df = df.sort_values(TIME_COL).reset_index(drop=True)
    n = len(df)
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))

    train = df.iloc[:train_end]
    val = df.iloc[train_end:val_end]
    test = df.iloc[val_end:]

    return train, val, test


def run_pipeline(raw_path: str):
    # only read needed cols — avoids loading 394-col / 1.7GB frame
    df = pd.read_csv(raw_path, usecols=RAW_COLS)

    df = engineer_features(df)
    df = handle_missing(df)
    df = encode_categoricals(df)

    train, val, test = time_based_split(df)

    print(f"Train: {len(train)} ({train[TARGET_COL].mean():.4f} fraud rate)")
    print(f"Val:   {len(val)} ({val[TARGET_COL].mean():.4f} fraud rate)")
    print(f"Test:  {len(test)} ({test[TARGET_COL].mean():.4f} fraud rate)")

    return train, val, test


if __name__ == '__main__':
    train, val, test = run_pipeline('data/raw/train_transaction.csv')

    train.to_csv('data/processed/train.csv', index=False)
    val.to_csv('data/processed/val.csv', index=False)
    test.to_csv('data/processed/test.csv', index=False)