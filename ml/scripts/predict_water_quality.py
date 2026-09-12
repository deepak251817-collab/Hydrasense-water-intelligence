"""Predict Water Quality using Random Forest Classifier (Phase 5C-2).

Loads the trained Random Forest model (ml/models/random_forest_classifier.joblib)
and generates predictions and class probabilities for the test dataset
(or an arbitrary input dataset).

Saves outputs to ml/data/processed/random_forest_predictions.csv with schema:
- pH
- tds
- turbidity
- temperature
- actual_label
- predicted_label
- probability_safe
- probability_unsafe
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import joblib
import numpy as np
import pandas as pd

from ml.preprocessing.prepare_supervised import (
    STANDARDIZED_FEATURE_COLUMNS,
    STANDARDIZED_TARGET_COLUMN,
    SupervisedPreprocessor,
)

DEFAULT_MODEL_PATH = PROJECT_ROOT / "ml" / "models" / "random_forest_classifier.joblib"
DEFAULT_INPUT_PATH = PROJECT_ROOT / "ml" / "data" / "processed" / "supervised_test.csv"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "ml" / "data" / "processed" / "random_forest_predictions.csv"


def predict_water_quality(
    input_path: Path = DEFAULT_INPUT_PATH,
    model_path: Path = DEFAULT_MODEL_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> pd.DataFrame:
    """Generate water quality predictions and probability distributions."""
    print("=" * 70)
    print("HYDRASENSE PHASE 5C-2: PREDICT WATER QUALITY")
    print("=" * 70)
    print(f"Input Dataset:  {input_path}")
    print(f"Model File:     {model_path}")
    print(f"Output Path:    {output_path}")

    if not model_path.exists():
        raise FileNotFoundError(f"Model artifact not found at '{model_path}'. Run training first.")
    if not input_path.exists():
        raise FileNotFoundError(f"Input data not found at '{input_path}'.")

    # 1. Load Data and Model
    df = pd.read_csv(input_path)
    model = joblib.load(model_path)
    print(f"\n1. Loaded input data: {len(df):,} rows.")

    # 2. Extract Features (exclude target if present)
    feature_input = df.drop(columns=[STANDARDIZED_TARGET_COLUMN]) if STANDARDIZED_TARGET_COLUMN in df.columns else df
    # Use the training-fitted schema (fitted ONLY on training data during training) - identity pass-through.
    preprocessor = SupervisedPreprocessor(feature_cols=list(STANDARDIZED_FEATURE_COLUMNS))
    preprocessor.fit(pd.DataFrame(columns=list(STANDARDIZED_FEATURE_COLUMNS)))
    X = preprocessor.transform(feature_input)

    # 3. Predict Classes & Probabilities
    y_pred = model.predict(X)
    y_prob = model.predict_proba(X)

    classes = list(model.classes_)
    safe_idx = classes.index("Safe")
    unsafe_idx = classes.index("Unsafe")

    prob_safe = y_prob[:, safe_idx]
    prob_unsafe = y_prob[:, unsafe_idx]

    # 4. Validate Probabilities
    assert np.all(prob_safe >= 0.0) and np.all(prob_safe <= 1.0), "prob_safe outside [0, 1]"
    assert np.all(prob_unsafe >= 0.0) and np.all(prob_unsafe <= 1.0), "prob_unsafe outside [0, 1]"
    assert np.allclose(prob_safe + prob_unsafe, 1.0), "Probabilities do not sum to 1.0"
    print("2. Probabilities validated: strictly numeric and bounded within [0, 1].")

    # 5. Build Output DataFrame
    out_df = pd.DataFrame()
    for col in STANDARDIZED_FEATURE_COLUMNS:
        out_df[col] = df[col]

    if STANDARDIZED_TARGET_COLUMN in df.columns:
        out_df["actual_label"] = df[STANDARDIZED_TARGET_COLUMN]
    else:
        out_df["actual_label"] = "Unknown"

    out_df["predicted_label"] = y_pred
    out_df["probability_safe"] = np.round(prob_safe, 4)
    out_df["probability_unsafe"] = np.round(prob_unsafe, 4)

    # 6. Save Predictions CSV
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(output_path, index=False)
    print(f"3. Saved {len(out_df):,} predictions to: {output_path}")

    # Summary of predictions
    pred_summary = out_df["predicted_label"].value_counts().to_dict()
    print("\n4. Prediction Summary:")
    for label, count in pred_summary.items():
        pct = (count / len(out_df)) * 100.0
        print(f"   - {label:<10}: {count:>6,} ({pct:5.2f}%)")

    print("=" * 70)
    print("SUCCESS: Prediction generation complete.")
    print("=" * 70)

    return out_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate water quality predictions.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH, help="Path to input CSV.")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH, help="Path to model joblib.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Path for predictions CSV.")
    args = parser.parse_args()

    predict_water_quality(
        input_path=args.input,
        model_path=args.model,
        output_path=args.output,
    )
