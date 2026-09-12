"""Explain Random Forest Water-Quality Classification with SHAP (Phase 5E).

Loads the ALREADY-TRAINED Phase 5C-2 Random Forest classifier
(ml/models/random_forest_classifier.joblib) and produces SHAP explanations of
its predictions. The model is NEVER retrained, retuned, or modified; its
predictions and probabilities are captured before and after explanation and
must be identical (verified by --verify-consistency and the test suite).

Explanations are generated from a documented representative sample of the
Phase 5C test split (ml/data/processed/supervised_test.csv) using the exact
four model inputs: pH, tds, turbidity, temperature. No features are added or
removed. Test data is used only for explanation, never for training.

Outputs (all under ml/data/processed/):
- shap_random_forest_summary.csv   feature / mean_abs_shap, sorted descending
- shap_random_forest_summary.png   global feature-contribution bar chart
- shap_random_forest_local.csv     per-observation local explanation table
  (row_index, actual_label, predicted_label, prediction_probability, feature,
  shap_value) for one Safe, one Unsafe, one correct, and one incorrect
  prediction (a category is skipped if no such observation exists).

SIGN CONVENTION (Phase 5E section 9): positive SHAP values push the model
output toward the positive class, which for this model is label "Unsafe";
negative values push toward "Safe".

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

from ml.preprocessing.prepare_supervised import (
    STANDARDIZED_FEATURE_COLUMNS as RF_FEATURES,
    STANDARDIZED_TARGET_COLUMN as RF_LABEL,
)

DEFAULT_MODEL = PROJECT_ROOT / "ml" / "models" / "random_forest_classifier.joblib"
DEFAULT_DATA = PROJECT_ROOT / "ml" / "data" / "processed" / "supervised_test.csv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "ml" / "data" / "processed"

# Documented representative sample size for the GLOBAL explanation (Phase 5E
# section 12). Local explanations use at most 4 individually selected rows.
GLOBAL_SAMPLE_SIZE = 500
RANDOM_SEED = 42

POSITIVE_CLASS = "Unsafe"


def sha256_of_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_global_sample(test_df: pd.DataFrame, sample_size: int, seed: int) -> pd.DataFrame:
    """Return a deterministic shuffled sample for the global explanation."""
    if len(test_df) <= sample_size:
        return test_df
    return test_df.sample(n=sample_size, random_state=seed).sort_index()


def select_local_rows(test_df: pd.DataFrame, predictions: np.ndarray,
                      probabilities: np.ndarray) -> pd.DataFrame:
    """Pick representative local-explanation rows (Phase 5E section 5).

    Preference order: one Safe, one Unsafe, one correctly classified, and one
    incorrectly classified observation. Categories that do not exist are
    skipped without fabrication. Rows are deduplicated by index.
    """
    correct = predictions == test_df[RF_LABEL].to_numpy()

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
        predictions == "Safe",
        predictions == "Unsafe",
        correct,
        ~correct,
    ):
        idx = first_match(mask, chosen)
        if idx is not None and idx not in chosen:
            chosen.append(idx)
    return test_df.iloc[chosen]


def build_local_table(local_rows: pd.DataFrame, explainer, feature_columns,
                      predictions: np.ndarray, probabilities: np.ndarray) -> pd.DataFrame:
    """Long-format local explanation: one row per (observation, feature)."""
    X_local = local_rows[list(feature_columns)]
    shap_values = explainer.shap_values(X_local)
    # sklearn RandomForestClassifier with TreeExplainer returns either a list
    # [class0, class1] of (n, features) arrays or an (n, features, 2) ndarray.
    if isinstance(shap_values, list):
        shap_positive = shap_values[1]
    else:
        shap_positive = shap_values[:, :, 1]
    records = []
    for pos, (row_idx, row) in enumerate(local_rows.iterrows()):
        for feature, shap_value in zip(feature_columns, shap_positive[pos]):
            records.append({
                "row_index": int(row_idx),
                "actual_label": row[RF_LABEL],
                "predicted_label": predictions[pos],
                "prediction_probability": float(probabilities[pos]),
                "feature": feature,
                "shap_value": float(shap_value),
            })
    return pd.DataFrame(records)


def plot_global_summary(summary_df: pd.DataFrame, out_path: Path,
                        sample_size: int, model_name: str) -> None:
    """Horizontal bar chart of mean absolute SHAP contributions."""
    fig, ax = plt.subplots(figsize=(8, 5))
    ordered = summary_df.sort_values("mean_abs_shap")  # largest on top
    ax.barh(ordered["feature"], ordered["mean_abs_shap"], color="#3b6ea5")
    ax.set_xlabel("Mean |SHAP value| (average impact on model output)")
    ax.set_ylabel("Feature")
    ax.set_title(
        f"SHAP Global Feature Contribution - {model_name}\n"
        f"(positive class: {POSITIVE_CLASS}; n = {sample_size} test observations)"
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def explain_random_forest(
    model_path: Path = DEFAULT_MODEL,
    data_path: Path = DEFAULT_DATA,
    out_dir: Path = DEFAULT_OUT_DIR,
    global_sample_size: int = GLOBAL_SAMPLE_SIZE,
    verify_consistency: bool = False,
) -> dict:
    """Generate all Phase 5E Random Forest SHAP artifacts.

    Returns a result dictionary including the before/after prediction
    consistency verification required by Phase 5E sections 11 and 17.
    """
    import shap

    model_path = Path(model_path)
    data_path = Path(data_path)
    out_dir = Path(out_dir)
    if not model_path.exists():
        raise FileNotFoundError(
            f"Random Forest model not found: {model_path}. "
            "Run ml/scripts/train_random_forest.py first (Phase 5C-2)."
        )
    if not data_path.exists():
        raise FileNotFoundError(
            f"Test split not found: {data_path}. "
            "Run ml/scripts/prepare_supervised_splits.py first (Phase 5C-1)."
        )

    model_hash_before = sha256_of_file(model_path)
    model = joblib.load(model_path)

    test_df = pd.read_csv(data_path)
    missing = [c for c in [*RF_FEATURES, RF_LABEL] if c not in test_df.columns]
    if missing:
        raise ValueError(f"Test split is missing model columns: {missing}")

    # --- capture BEFORE state (Phase 5E section 17) ---
    X_all = test_df[list(RF_FEATURES)]
    predictions_before = model.predict(X_all)
    probabilities_before = model.predict_proba(X_all)[:, 1]

    # --- SHAP explanations (model untouched) ---
    sample = select_global_sample(test_df, global_sample_size, RANDOM_SEED)
    X_sample = sample[list(RF_FEATURES)]
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_sample)
    if isinstance(shap_values, list):
        shap_positive = shap_values[1]  # positive class = Unsafe
    else:
        shap_positive = shap_values[:, :, 1]
    mean_abs = np.abs(shap_positive).mean(axis=0)
    summary = (
        pd.DataFrame({"feature": list(RF_FEATURES), "mean_abs_shap": mean_abs})
        .sort_values("mean_abs_shap", ascending=False)
        .reset_index(drop=True)
    )
    summary.to_csv(out_dir / "shap_random_forest_summary.csv", index=False)
    plot_global_summary(
        summary, out_dir / "shap_random_forest_summary.png",
        sample_size=len(sample), model_name="Random Forest Water-Quality Classifier",
    )

    # --- local explanations on the FULL test split (so categories are found) ---
    local_rows = select_local_rows(test_df, predictions_before, probabilities_before)
    # Slice the before-state arrays down to the selected rows so table values
    # align with the explained observations (never index the full arrays by
    # enumeration position).
    local_positions = local_rows.index.to_numpy()
    local_table = build_local_table(
        local_rows, explainer, RF_FEATURES,
        predictions_before[local_positions],
        probabilities_before[local_positions],
    )
    local_table.to_csv(out_dir / "shap_random_forest_local.csv", index=False)

    # --- capture AFTER state and verify (Phase 5E sections 11 & 17) ---
    predictions_after = model.predict(X_all)
    probabilities_after = model.predict_proba(X_all)[:, 1]
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
        "n_local_rows": len(local_table) // len(RF_FEATURES),
        "summary": summary,
        "local_table": local_table,
        "consistency": consistency,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--global-sample-size", type=int, default=GLOBAL_SAMPLE_SIZE)
    parser.add_argument("--verify-consistency", action="store_true",
                        help="Fail loudly if SHAP changed model behavior.")
    args = parser.parse_args()

    result = explain_random_forest(
        model_path=args.model,
        data_path=args.data,
        out_dir=args.out_dir,
        global_sample_size=args.global_sample_size,
        verify_consistency=True,
    )
    print("Random Forest SHAP explanation complete:")
    print(f"  global sample size : {result['n_global_sample']}")
    print(f"  local rows         : {result['n_local_rows']}")
    print(result["summary"].to_string(index=False))
    c = result["consistency"]
    print(f"  model hash unchanged : {c['model_hash_unchanged']}")
    print(f"  predictions unchanged: {c['predictions_unchanged']}")
    print(f"  probabilities unchanged: {c['probabilities_unchanged']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
