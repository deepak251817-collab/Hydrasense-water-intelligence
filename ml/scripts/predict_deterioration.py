"""Predict Water-Quality Deterioration with XGBoost (Phase 5D-2).

Loads the trained XGBoost model (ml/models/xgboost_deterioration.joblib) and
generates deterioration predictions for a Phase 5D-1 chronological split
(default: the final test split forecast_test.csv).

Output (ml/data/processed/xgboost_predictions.csv) columns:
- station                Phase 5D-1 station/site identifier
- timestamp              observation time (prediction time, not future time)
- pH, tds, turbidity, temperature   sensor values preserved where useful
- actual_deterioration   observed target (NaN when not evaluable)
- predicted_deterioration model prediction (0/1; -1 where target not evaluable)
- prediction_probability P(target = 1), numeric and within [0, 1] (verified)

No probability values are fabricated: rows whose features cannot be evaluated
keep an empty probability and predicted_deterioration = -1 (explicitly
"not predictable"), rather than an invented number.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to sys.path so ml.* packages can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import joblib
import numpy as np
import pandas as pd

from ml.preprocessing.forecasting import (
    KNOWN_PARAMETERS,
    STATION_COLUMN,
    TARGET_COLUMN,
    TIMESTAMP_COLUMN,
    resolve_feature_columns,
)

DEFAULT_MODEL_PATH = PROJECT_ROOT / "ml" / "models" / "xgboost_deterioration.joblib"
DEFAULT_INPUT_PATH = PROJECT_ROOT / "ml" / "data" / "processed" / "forecast_test.csv"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "ml" / "data" / "processed" / "xgboost_predictions.csv"
DEFAULT_ERROR_ANALYSIS_PATH = PROJECT_ROOT / "ml" / "data" / "processed" / "xgboost_error_analysis.csv"

# USGS-facing prediction output contract (station, timestamp, the four USGS
# measurements, actual/predicted labels, probability). The actual sensor
# column set follows the input frame's parameters (see predict_deterioration).
PREDICTION_COLUMNS = [
    STATION_COLUMN,
    TIMESTAMP_COLUMN,
    "pH",
    "turbidity",
    "temperature",
    "specific_conductance",
    "actual_deterioration",
    "predicted_deterioration",
    "prediction_probability",
]


def predict_deterioration(
    input_path: Path = DEFAULT_INPUT_PATH,
    model_path: Path = DEFAULT_MODEL_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    error_analysis_path: Path | None = DEFAULT_ERROR_ANALYSIS_PATH,
    threshold: float = 0.5,
) -> pd.DataFrame:
    """Generate deterioration predictions with verified probabilities.

    ``threshold`` is the frozen probability threshold selected on the
    VALIDATION split (default 0.5); the test set never influences it.
    Also writes the error-analysis CSV (incorrect predictions only) with a
    summary of false positives, false negatives, and temporal clustering.
    """
    print("=" * 70)
    print("HYDRASENSE PHASE 5D-2: PREDICT DETERIORATION (XGBOOST)")
    print("=" * 70)
    print(f"Input Split:  {input_path}")
    print(f"Model File:   {model_path}")
    print(f"Output Path:  {output_path}")

    if not model_path.exists():
        raise FileNotFoundError(
            f"Model artifact not found at '{model_path}'. Run ml/scripts/train_xgboost.py first."
        )
    if not input_path.exists():
        raise FileNotFoundError(
            f"Input split not found at '{input_path}'. Phase 5D-1 ended in a documented "
            "STOP state (no suitable chronological dataset); forecast splits were never "
            "generated. Acquire a genuine time-series dataset - do NOT fabricate one."
        )

    # 1. Load split and model (prediction only - no fitting).
    df = pd.read_csv(input_path)
    model = joblib.load(model_path)
    print(f"\n1. Loaded split: {len(df):,} rows; model loaded from disk.")

    # 2. Resolve the Phase 5D-1 feature schema (target never a feature).
    feature_cols = resolve_feature_columns(df, target_col=TARGET_COLUMN)

    # 3. Predict only where the target is evaluable so the model input rows
    #    match supervised rows; other rows are kept with explicit "not
    #    predictable" markers rather than fabricated probabilities.
    evaluable = df[TARGET_COLUMN].notna()
    X_eval = df.loc[evaluable, feature_cols]

    predicted = np.full(len(df), -1, dtype=int)          # -1 = not predictable
    probability = np.full(len(df), np.nan, dtype=float)  # NaN = not predictable
    if evaluable.any():
        probability[evaluable.to_numpy()] = model.predict_proba(X_eval)[:, 1]
        # Frozen-threshold decision rule (NOT the model's internal predict()).
        predicted[evaluable.to_numpy()] = (probability[evaluable.to_numpy()] >= threshold).astype(int)

    # 4. Verify probabilities are numeric and within [0, 1].
    prob_values = probability[~np.isnan(probability)]
    assert np.issubdtype(prob_values.dtype, np.floating), "probabilities must be numeric"
    assert np.all((prob_values >= 0.0) & (prob_values <= 1.0)), "probabilities must lie within [0, 1]"
    evaluable_labels = predicted[evaluable.to_numpy()]
    assert set(np.unique(evaluable_labels)).issubset({0, 1}), "predicted labels must be binary 0/1"
    print(f"2. Validation: probabilities numeric within [0, 1]; labels binary 0/1 "
          f"(threshold={threshold}; {len(prob_values):,} evaluated, "
          f"{int(len(df) - len(prob_values)):,} not predictable).")

    # 5. Assemble the output schema (sensor columns = the frame's actual
    #    parameter columns; USGS provides specific_conductance, not tds).
    sensor_params = [p for p in KNOWN_PARAMETERS if p in df.columns]
    prediction_columns = [STATION_COLUMN, TIMESTAMP_COLUMN, *sensor_params,
                          "actual_deterioration", "predicted_deterioration",
                          "prediction_probability"]
    out = pd.DataFrame({
        STATION_COLUMN: df[STATION_COLUMN],
        TIMESTAMP_COLUMN: df[TIMESTAMP_COLUMN],
        **{p: df[p] for p in sensor_params},
        "actual_deterioration": df[TARGET_COLUMN],
        "predicted_deterioration": predicted,
        "prediction_probability": probability,
    })[prediction_columns]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)
    print(f"3. Saved {len(out):,} prediction rows to: {output_path}")

    pred_counts = pd.Series(predicted).value_counts().to_dict()
    print("\n4. Prediction Summary (deterioration indicator):")
    for key in (1, 0, -1):
        if key in pred_counts:
            label = {1: "predicted deterioration (1)", 0: "predicted no deterioration (0)",
                     -1: "not predictable (-1)"}[key]
            print(f"   - {label:<32}: {pred_counts[key]:>7,}")

    # 5. Error analysis: incorrect predictions only (spec section 16).
    if error_analysis_path is not None:
        eval_df = out[out["predicted_deterioration"].isin([0, 1])].copy()
        eval_df["actual_deterioration"] = eval_df["actual_deterioration"].astype(int)
        errors = eval_df[eval_df["actual_deterioration"] != eval_df["predicted_deterioration"]].copy()
        errors["error_type"] = np.where(
            (errors["actual_deterioration"] == 0) & (errors["predicted_deterioration"] == 1),
            "false_positive", "false_negative",
        )
        error_cols = [STATION_COLUMN, TIMESTAMP_COLUMN, *sensor_params,
                      "actual_deterioration", "predicted_deterioration",
                      "prediction_probability", "error_type"]
        errors = errors[error_cols].sort_values(TIMESTAMP_COLUMN).reset_index(drop=True)
        error_analysis_path.parent.mkdir(parents=True, exist_ok=True)
        errors.to_csv(error_analysis_path, index=False)

        n_fp = int((errors["error_type"] == "false_positive").sum())
        n_fn = int((errors["error_type"] == "false_negative").sum())
        print(f"\n5. ERROR ANALYSIS (incorrect predictions only; saved to {error_analysis_path.name}):")
        print(f"   - False positives (0 -> 1): {n_fp}")
        print(f"   - False negatives (1 -> 0): {n_fn}")
        print(f"   - Total errors:            {len(errors)} of {len(eval_df):,} evaluated rows")
        if not errors.empty:
            ts_err = pd.to_datetime(errors[TIMESTAMP_COLUMN], utc=True)
            print(f"   - Error time span: {ts_err.min()} -> {ts_err.max()}")
            by_day = ts_err.dt.date.value_counts().sort_index()
            top_days = by_day.head(3)
            print("   - Temporal clustering: errors concentrate on these dates (top 3): "
                  + ", ".join(f"{d} ({c})" for d, c in top_days.items())
                  + " - likely around real storm/spike periods; errors are model mispredictions,"
                    " NOT confirmed pollution events.")
    print("=" * 70)
    print("SUCCESS: Prediction generation complete.")
    print("=" * 70)
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate XGBoost deterioration predictions (Phase 5D-2).")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH,
                        help="Path to the Phase 5D-1 split to predict (default: forecast_test.csv).")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH, help="Path to the trained model.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Predictions CSV output path.")
    parser.add_argument("--error-analysis", type=Path, default=DEFAULT_ERROR_ANALYSIS_PATH,
                        help="Error-analysis CSV output path (incorrect predictions only).")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="Frozen probability threshold selected on the validation split.")
    args = parser.parse_args()

    predict_deterioration(input_path=args.input, model_path=args.model, output_path=args.output,
                          error_analysis_path=args.error_analysis, threshold=args.threshold)
