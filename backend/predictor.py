import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score, precision_score,
    recall_score, f1_score, confusion_matrix
)
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings('ignore')


# ── Column config for Titanic-style datasets ──────────────────
# Day 9+: this will be auto-detected from the dataset
TARGET_COLUMN    = 'Survived'
FEATURE_COLUMNS  = ['Pclass', 'Sex', 'Age', 'Fare', 'SibSp', 'Parch']
CATEGORICAL_COLS = ['Sex']


def prepare_features(df: pd.DataFrame,
                     feature_cols: list,
                     categorical_cols: list) -> pd.DataFrame:
    """
    Encode categoricals + drop rows with nulls in feature/target cols.
    Returns a clean feature DataFrame ready for sklearn.
    """
    df = df.copy()

    # One-hot encode categorical columns
    for col in categorical_cols:
        if col in df.columns:
            dummies = pd.get_dummies(df[col], prefix=col, drop_first=True)
            df = pd.concat([df, dummies], axis=1)
            df = df.drop(columns=[col])

    # Update feature list to include encoded columns
    encoded_features = []
    for col in feature_cols:
        if col in categorical_cols:
            # Replace with encoded versions
            encoded_versions = [c for c in df.columns if c.startswith(f"{col}_")]
            encoded_features.extend(encoded_versions)
        else:
            if col in df.columns:
                encoded_features.append(col)

    return df, encoded_features


def train_model(df: pd.DataFrame) -> dict:
    """
    Full training pipeline:
      1. Validate target column exists
      2. Prepare + encode features
      3. Train/test split (80/20, random_state=42 for reproducibility)
      4. Scale features
      5. Fit LogisticRegression
      6. Evaluate: accuracy, precision, recall, F1
      7. Extract feature importances (coefficients)

    Returns a model bundle dict stored in the session.
    """
    # ── 1. Validate ───────────────────────────────────────────
    if TARGET_COLUMN not in df.columns:
        raise ValueError(
            f"Target column '{TARGET_COLUMN}' not found. "
            f"Available columns: {list(df.columns)}"
        )

    available_features = [c for c in FEATURE_COLUMNS if c in df.columns]
    if len(available_features) < 2:
        raise ValueError(
            f"Need at least 2 feature columns. "
            f"Found: {available_features}"
        )

    # ── 2. Prepare features ───────────────────────────────────
    df_prep, encoded_features = prepare_features(
        df, available_features, CATEGORICAL_COLS
    )

    # Drop rows where any feature or target is null
    cols_needed = encoded_features + [TARGET_COLUMN]
    df_clean = df_prep[cols_needed].dropna()

    if len(df_clean) < 50:
        raise ValueError(
            f"Not enough data after cleaning: {len(df_clean)} rows. Need at least 50."
        )

    X = df_clean[encoded_features]
    y = df_clean[TARGET_COLUMN]

    # ── 3. Train/test split ───────────────────────────────────
    # ALWAYS split before fitting — never train on test data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # ── 4. Scale features ─────────────────────────────────────
    # Logistic regression is sensitive to feature scale
    scaler  = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled  = scaler.transform(X_test)   # use train stats on test!

    # ── 5. Fit model ──────────────────────────────────────────
    model = LogisticRegression(
        max_iter=1000,
        random_state=42,
        class_weight='balanced'   # handles class imbalance
    )
    model.fit(X_train_scaled, y_train)

    # ── 6. Evaluate ───────────────────────────────────────────
    y_pred = model.predict(X_test_scaled)

    accuracy  = round(float(accuracy_score(y_test, y_pred))  * 100, 2)
    precision = round(float(precision_score(y_test, y_pred, zero_division=0)) * 100, 2)
    recall    = round(float(recall_score(y_test, y_pred, zero_division=0))    * 100, 2)
    f1        = round(float(f1_score(y_test, y_pred, zero_division=0))        * 100, 2)
    cm        = confusion_matrix(y_test, y_pred).tolist()

    # ── 7. Feature importance (coefficients) ──────────────────
    coefs = model.coef_[0]
    feature_importance = sorted(
        [
            {
                'feature':    feat,
                'coefficient': round(float(coef), 4),
                'direction':  'positive' if coef > 0 else 'negative',
                'abs_impact': round(abs(float(coef)), 4),
            }
            for feat, coef in zip(encoded_features, coefs)
        ],
        key=lambda x: x['abs_impact'],
        reverse=True
    )

    return {
        'model':             model,
        'scaler':            scaler,
        'encoded_features':  encoded_features,
        'target':            TARGET_COLUMN,
        'train_size':        len(X_train),
        'test_size':         len(X_test),
        'metrics': {
            'accuracy':  accuracy,
            'precision': precision,
            'recall':    recall,
            'f1':        f1,
        },
        'confusion_matrix':  cm,
        'feature_importance': feature_importance,
    }


def predict_single(model_bundle: dict, input_data: dict) -> dict:
    """
    Predict survival for a single passenger.
    input_data example:
      {"Pclass": 1, "Sex": "female", "Age": 29, "Fare": 100, "SibSp": 0, "Parch": 0}

    Returns prediction, probability, and top 3 influential features.
    """
    model    = model_bundle['model']
    scaler   = model_bundle['scaler']
    features = model_bundle['encoded_features']

    # Build input row
    row = pd.DataFrame([input_data])

    # Encode categoricals the same way as training
    for col in CATEGORICAL_COLS:
        if col in row.columns:
            dummies = pd.get_dummies(row[col], prefix=col, drop_first=True)
            row     = pd.concat([row, dummies], axis=1)
            row     = row.drop(columns=[col])

    # Align columns — add missing encoded cols as 0
    for feat in features:
        if feat not in row.columns:
            row[feat] = 0

    row_aligned = row[features].fillna(0)

    # Scale + predict
    row_scaled   = scaler.transform(row_aligned)
    prediction   = int(model.predict(row_scaled)[0])
    probabilities = model.predict_proba(row_scaled)[0]
    confidence   = round(float(probabilities[prediction]) * 100, 1)

    # Top 3 features that influenced this prediction
    importance = model_bundle['feature_importance'][:3]

    label = 'Survived ✓' if prediction == 1 else 'Did not survive ✗'

    return {
        'prediction':    prediction,
        'label':         label,
        'confidence':    confidence,
        'prob_survived': round(float(probabilities[1]) * 100, 1),
        'prob_not':      round(float(probabilities[0]) * 100, 1),
        'top_features':  importance,
    }


def model_summary_text(model_bundle: dict) -> list[str]:
    """Plain-English model summary for chat + activity feed."""
    m = model_bundle['metrics']
    fi = model_bundle['feature_importance']

    lines = [
        f"Logistic regression trained on {model_bundle['train_size']} rows, "
        f"tested on {model_bundle['test_size']} rows (80/20 split).",
        f"Accuracy: {m['accuracy']}% · Precision: {m['precision']}% · "
        f"Recall: {m['recall']}% · F1: {m['f1']}%.",
        f"Most influential feature: '{fi[0]['feature']}' "
        f"(coefficient: {fi[0]['coefficient']:+.4f}).",
    ]

    if fi[0]['direction'] == 'positive':
        lines.append(f"Higher '{fi[0]['feature']}' increases survival probability.")
    else:
        lines.append(f"Higher '{fi[0]['feature']}' decreases survival probability.")

    return lines