"""Explain XGBoost Deterioration Prediction with SHAP (Phase 5E).

Loads the ALREADY-TRAINED Phase 5D-2 XGBoost model
(ml/models/xgboost_deterioration.joblib) and produces SHAP explanations of
its predictions. The model is NEVER retrained, retuned, or modified; its
predictions and probabilities are captured before and after explanation and
must be identical (verified by --verify-consistency and the test suite).

The exact feature set is read from ml/data/processed/xgboost_feature_list.txt
(Phase 5D-2 output: current measurements + past-only lag/rolling/change
features). No features are added or removed; station, timestamp, and
deterioration_target are rejected if present in the list.

Explanations are generated from a documented representative sample of the
Phase 5D-1 FINAL TEST split (ml/data/processed/forecast_test.csv). Test data
is used only for explanation, never for training or tuning.

Local explanations use the decision threshold FROZEN in Phase 5D-2
(default 0.2, selected on the validation split only - the test set never
influenced the choice) so predicted labels match the official
xgboost_predictions.csv.

Outputs (all under ml/data/processed/):
- shap_xgboost_summary.csv   feature / mean_abs_shap, sorted descending
- shap_xgboost_summary.png   global feature-contribution bar chart
- shap_xgboost_local.csv     per-observation local explanation table
  (station, timestamp, actual_deterioration, predicted_deterioration,
  prediction_probability, feature, shap_value) for one correctly predicted
  deterioration event, one correctly predicted non-deterioration observation,
  one false positive, and one false negative (a category is skipped if it
  does not exist - no fabricated examples).

SIGN CONVENTION (Phase 5E section 9): SHAP values are in the model's raw
margin (log-odds) space for positive class deterioration_target = 1.
Positive SHAP values push the prediction toward "deterioration"; negative
values push toward "no deterioration".

HONESTY NOTE (Phase 5E section 10): SHAP explains how individual input
features contributed to a model prediction. These contributions describe
model behavior and are NOT proof of pollution, contamination, or physical
causation.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

# Add project root to sys.path so ml.* packages can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import joblib
import matplotlib
matplotlib.use("Agg")  # headless-safe rendering for scripts and tests
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ml.preprocessing.forecasting import STATION_COLUMN, TARGET_COLUMN, TIMESTAMP_COLUMN
from ml.utils.shap_compat import apply_shap_xgboost_compat

DEFAULT_MODEL = PROJECT_ROOT / "ml" / "models" / "xgboost_deterioration.joblib"
DEFAULT_DATA = PROJECT_ROOT / "ml" / "data" / "processed" / "forecast_test.csv"
DEFAULT_FEATURE_LIST = PROJECT_ROOT / "ml" / "data" / "processed" / "xgboost_feature_list.txt"
DEFAULT_OUT_DIR = PROJECT_ROOT / "ml" / "data" / "processed"

# Frozen in Phase 5D-2: selected on the VALIDATION split only (max F1); the
# test set was never used for the choice. Override only with a documented reason.
FROZEN_THRESHOLD = 0.2

# Documented representative sample size for the GLOBAL explanation (Phase 5E
# section 12). Local explanations use at most 4 individually selected rows.
GLOBAL_SAMPLE_SIZE = 500
RANDOM_SEED = 42


def sha256_of_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_feature_list(path: Path) -> list[str]:
    """Read the Phase 5D-2 feature contract and reject forbidden columns."""
    features = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    if not features:
        raise ValueError(f"Feature list is empty: {path}")
    forbidden = {STATION_COLUMN, TIMESTAMP_COLUMN, TARGET_COLUMN}
    present = forbidden.intersection(features)
    if present:
        raise ValueError(f"Feature list must not contain identifier/target columns: {sorted(present)}")
    return features


def select_global_sample(test_df: pd.DataFrame, sample_size: int, seed: int) -> pd.DataFrame:
    """Return a deterministic shuffled sample for the global explanation."""
    if len(test_df) <= sample_size:
        return test_df
    return test_df.sample(n=sample_size, random_state=seed).sort_index()


def select_local_positions(actual: np.ndarray, predicted: np.ndarray) -> list[int]:
    """Pick positions of representative local-explanation rows (Phase 5E section 8).

    Preference order: one correctly predicted deterioration event, one
    correctly predicted non-deterioration observation, one false positive,
    one false negative. Categories that do not exist are skipped without
    fabrication. Returned positions are unique and ascending.
    """
    correct_deterioration = (predicted == 1) & (actual == 1)
    correct_non = (predicted == 0) & (actual == 0)
    false_positive = (predicted == 1) & (actual == 0)
    false_negative = (predicted == 0) & (actual == 1)

    def first_match(mask: np.ndarray, chosen: list[int]) -> int | None:
        idxs = np.where(mask)[0]
        if len(idxs) == 0:
            return None
        for i in idxs:  # prefer a row not already representing another category
            if int(i) not in chosen:
                return int(i)
        return int(idxs[0])

    chosen: list[int] = []
    for mask in (
        correct_deterioration,
        correct_non,
        false_positive,
        false_negative,
    ):
        idx = first_match(mask, chosen)
        if idx is not None and idx not in chosen:
            chosen.append(idx)
    return chosen


def build_local_table(local_rows: pd.DataFrame, explainer, feature_columns: list[str],
                      actual: np.ndarray, predicted: np.ndarray,
                      probabilities: np.ndarray) -> pd.DataFrame:
    """Long-format local explanation: one row per (observation, feature).

    SHAP values keep their sign (Phase 5E section 9): positive pushes toward
    deterioration_target = 1, negative toward 0.
    """
    shap_values = explainer.shap_values(local_rows[list(feature_columns)])
    if isinstance(shap_values, list):
        shap_positive = shap_values[1]
    elif isinstance(shap_values, np.ndarray) and shap_values.ndim == 3:
        shap_positive = shap_values[:, :, 1]
    else:
        shap_positive = shap_values  # binary XGBoost: (n, features), class-1 margin
    records = []
    for pos, (row_idx, row) in enumerate(local_rows.iterrows()):
        for feature, shap_value in zip(feature_columns, shap_positive[pos]):
            records.append({
                "row_index": int(row_idx),
                STATION_COLUMN: row[STATION_COLUMN],
                TIMESTAMP_COLUMN: row[TIMESTAMP_COLUMN],
                "actual_deterioration": int(actual[pos]),
                "predicted_deterioration": int(predicted[pos]),
                "prediction_probability": float(probabilities[pos]),
                "feature": feature,
                "shap_value": float(shap_value),
            })
    return pd.DataFrame(records)


def plot_global_summary(summary_df: pd.DataFrame, out_path: Path,
                        sample_size: int) -> None:
    """Horizontal bar chart of mean absolute SHAP contributions (all features)."""
    fig, ax = plt.subplots(figsize=(9, 9))
    ordered = summary_df.sort_values("mean_abs_shap")  # largest on top
    ax.barh(ordered["feature"], ordered["mean_abs_shap"], color="#3b6ea5")
    ax.set_xlabel("Mean |SHAP value| (average impact on model output, log-odds)")
    ax.set_ylabel("Feature")
    ax.set_title(
        "SHAP Global Feature Contribution - XGBoost Deterioration Prediction\n"
        f"(positive class: deterioration_target = 1; n = {sample_size} final-test observations)"
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def explain_xgboost(
    model_path: Path = DEFAULT_MODEL,
    data_path: Path = DEFAULT_DATA,
    feature_list_path: Path = DEFAULT_FEATURE_LIST,
    out_dir: Path = DEFAULT_OUT_DIR,
    global_sample_size: int = GLOBAL_SAMPLE_SIZE,
    threshold: float = FROZEN_THRESHOLD,
    verify_consistency: bool = False,
) -> dict:
    """Generate all Phase 5E XGBoost SHAP artifacts.

    Returns a result dictionary including the before/after prediction
    consistency verification required by Phase 5E sections 11 and 17.
    """
    apply_shap_xgboost_compat()  # documented shim; model artifact untouched
    import shap

    model_path = Path(model_path)
    data_path = Path(data_path)
    feature_list_path = Path(feature_list_path)
    out_dir = Path(out_dir)
    if not model_path.exists():
        raise FileNotFoundError(
            f"XGBoost model not found: {model_path}. "
            "Run ml/scripts/train_xgboost.py first (Phase 5D-2)."
        )
    if not data_path.exists():
        raise FileNotFoundError(
            f"Final test split not found: {data_path}. "
            "Run ml/scripts/prepare_usgs_forecast_dataset.py first (Phase 5D-1)."
        )
    if not feature_list_path.exists():
        raise FileNotFoundError(
            f"Feature list not found: {feature_list_path}. "
            "Run ml/scripts/train_xgboost.py first (Phase 5D-2)."
        )

    model_hash_before = sha256_of_file(model_path)
    model = joblib.load(model_path)

    feature_columns = load_feature_list(feature_list_path)
    test_df = pd.read_csv(data_path)
    missing = [c for c in feature_columns if c not in test_df.columns]
    if missing:
        raise ValueError(f"Final test split is missing model features: {missing}")

    # Evaluable rows only: the target is NaN where no future observation exists.
    evaluable = test_df[TARGET_COLUMN].notna().to_numpy()
    X_eval = test_df.loc[evaluable, list(feature_columns)]
    actual = test_df.loc[evaluable, TARGET_COLUMN].to_numpy(dtype=int)

    # --- capture BEFORE state (Phase 5E section 17) ---
    probabilities_before = model.predict_proba(X_eval)[:, 1]
    predictions_before = (probabilities_before >= threshold).astype(int)

    # --- SHAP explanations (model untouched) ---
    sample = select_global_sample(test_df, global_sample_size, RANDOM_SEED)
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(sample[list(feature_columns)])
    if isinstance(shap_values, list):
        shap_positive = shap_values[1]
    elif isinstance(shap_values, np.ndarray) and shap_values.ndim == 3:
        shap_positive = shap_values[:, :, 1]
    else:
        shap_positive = shap_values
    mean_abs = np.abs(shap_positive).mean(axis=0)
    summary = (
        pd.DataFrame({"feature": list(feature_columns), "mean_abs_shap": mean_abs})
        .sort_values("mean_abs_shap", ascending=False)
        .reset_index(drop=True)
    )
    summary.to_csv(out_dir / "shap_xgboost_summary.csv", index=False)
    plot_global_summary(
        summary, out_dir / "shap_xgboost_summary.png", sample_size=len(sample)
    )

    # --- local explanations on the FULL evaluable test split (so all categories are found) ---
    # select_local_positions indexes the evaluable subset; map back to the
    # dataframe's own positions so multi-station NaN-target rows can never
    # cause a misaligned selection.
    evaluable_indices = np.where(evaluable)[0]
    local_positions = evaluable_indices[np.asarray(select_local_positions(actual, predictions_before))]
    local_rows = test_df.iloc[local_positions]
    local_table = build_local_table(
        local_rows, explainer, feature_columns,
        actual[local_positions],
        predictions_before[local_positions],
        probabilities_before[local_positions],
    )
    local_table.to_csv(out_dir / "shap_xgboost_local.csv", index=False)

    # --- capture AFTER state and verify (Phase 5E sections 11 & 17) ---
    probabilities_after = model.predict_proba(X_eval)[:, 1]
    predictions_after = (probabilities_after >= threshold).astype(int)
    model_hash_after = sha256_of_file(model_path)
    consistency = {
        "model_hash_unchanged": model_hash_before == model_hash_after,
        "predictions_unchanged": bool(np.array_equal(predictions_before, predictions_after)),
        "probabilities_unchanged": bool(
            np.array_equal(probabilities_before, probabilities_after)
        ),
    }
    if verify_consistency and not all(consistency.values()):
        raise RuntimeError(f"SHAP modified model behavior: {consistency}")

    return {
        "n_global_sample": len(sample),
        "n_local_rows": len(local_rows),
        "threshold": float(threshold),
        "summary": summary,
        "local_table": local_table,
        "consistency": consistency,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--feature-list", type=Path, default=DEFAULT_FEATURE_LIST)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--global-sample-size", type=int, default=GLOBAL_SAMPLE_SIZE)
    parser.add_argument("--threshold", type=float, default=FROZEN_THRESHOLD,
                        help="Frozen probability threshold from Phase 5D-2 validation selection.")
    parser.add_argument("--verify-consistency", action="store_true",
                        help="Fail loudly if SHAP changed model behavior.")
    args = parser.parse_args()

    result = explain_xgboost(
        model_path=args.model,
        data_path=args.data,
        feature_list_path=args.feature_list,
        out_dir=args.out_dir,
        global_sample_size=args.global_sample_size,
        threshold=args.threshold,
        verify_consistency=True,
    )
    print("XGBoost SHAP explanation complete:")
    print(f"  global sample size : {result['n_global_sample']}")
    print(f"  local rows         : {result['n_local_rows']}")
    print(f"  decision threshold : {result['threshold']} (frozen from Phase 5D-2 validation selection)")
    print(result["summary"].head(10).to_string(index=False))
    c = result["consistency"]
    print(f"  model hash unchanged : {c['model_hash_unchanged']}")
    print(f"  predictions unchanged: {c['predictions_unchanged']}")
    print(f"  probabilities unchanged: {c['probabilities_unchanged']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
