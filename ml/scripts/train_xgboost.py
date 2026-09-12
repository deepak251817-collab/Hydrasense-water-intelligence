"""Train XGBoost Water-Quality Deterioration Prediction Model (Phase 5D-2).

Loads ONLY the Phase 5D-1 chronological training split
(ml/data/processed/forecast_train.csv), resolves the Phase 5D-1 feature
schema (current parameters + past-only lag/rolling/change features), and
trains a baseline xgboost.XGBClassifier to predict the binary
`deterioration_target` defined in Phase 5D-1 (1 = future deterioration
indicator within the horizon; 0 = no deterioration; NaN = not evaluable).

LEAKAGE CONTRACT (Phase 5D-2 section 3):
- The training split is used for model FITTING only. Validation and test
  splits are never read by this script.
- The target (and any target-derived column) is never a model input; this is
  enforced by ml.preprocessing.forecasting.resolve_feature_columns.
- All lag/rolling features are consumed exactly as produced by Phase 5D-1;
  no features are recomputed here, so no future information can enter.

HONESTY NOTE: feature importance reflects model contribution (split gain),
not physical causation. The target is a rule-based future deterioration
indicator from Phase 5D-1 - NOT confirmed contamination or pollution.

Phase 5D-1 STOP state: if forecast_train.csv does not exist (no suitable
chronological dataset was available), this script fails with a clear
instruction. No forecast data is fabricated.
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
import matplotlib
matplotlib.use("Agg")  # headless-safe rendering for scripts and tests
import matplotlib.pyplot as plt
import pandas as pd
import xgboost as xgb

from ml.preprocessing.forecasting import (
    STATION_COLUMN,
    TARGET_COLUMN,
    TIMESTAMP_COLUMN,
    resolve_feature_columns,
)

DEFAULT_TRAIN_DATA = PROJECT_ROOT / "ml" / "data" / "processed" / "forecast_train.csv"
DEFAULT_MODEL_OUTPUT = PROJECT_ROOT / "ml" / "models" / "xgboost_deterioration.joblib"
DEFAULT_IMPORTANCE_OUTPUT = PROJECT_ROOT / "ml" / "data" / "processed" / "xgboost_feature_importance.csv"
DEFAULT_IMPORTANCE_PLOT = PROJECT_ROOT / "ml" / "data" / "processed" / "xgboost_feature_importance.png"
DEFAULT_FEATURE_LIST_OUTPUT = PROJECT_ROOT / "ml" / "data" / "processed" / "xgboost_feature_list.txt"

# Phase 5D-1 message used whenever required inputs are missing.
MISSING_INPUT_MESSAGE = (
    "Phase 5D-1 ended in a documented STOP state: no suitable chronological "
    "water-quality dataset exists in the project, so the forecast_*.csv splits "
    "were never generated. Acquire a genuine time-series dataset (timestamps, "
    "station/site IDs, >= 50 sequential observations per station, the four core "
    "parameters) and build the splits with "
    "ml.preprocessing.forecasting.build_forecasting_dataset. Do NOT fabricate "
    "forecast data."
)


def _load_train_data(train_path: Path) -> pd.DataFrame:
    """Load the Phase 5D-1 training split, failing loudly when it is absent."""
    if not train_path.exists():
        raise FileNotFoundError(f"Training data not found at '{train_path}'. {MISSING_INPUT_MESSAGE}")
    return pd.read_csv(train_path)


def train_xgboost(
    train_path: Path = DEFAULT_TRAIN_DATA,
    model_output: Path | None = DEFAULT_MODEL_OUTPUT,
    importance_output: Path | None = DEFAULT_IMPORTANCE_OUTPUT,
    importance_plot_output: Path | None = DEFAULT_IMPORTANCE_PLOT,
    feature_list_output: Path | None = None,
    n_estimators: int = 200,
    learning_rate: float = 0.05,
    max_depth: int = 6,
    subsample: float = 0.8,
    colsample_bytree: float = 0.8,
    eval_metric: str = "logloss",
    random_state: int = 42,
    n_jobs: int = -1,
    scale_pos_weight: float | str = "auto",
) -> tuple[xgb.XGBClassifier, list[str], pd.DataFrame]:
    """Train the baseline XGBClassifier on the Phase 5D-1 training split.

    ``scale_pos_weight`` controls class-imbalance handling (Phase 5D-2 spec
    section 6). It is computed ONLY from the training split distribution:
    - "auto": negative_count / positive_count from forecast_train.csv
      (justified: the positive deterioration class is rare (~9%) and missed
      deterioration events are the costlier error for an alerting system);
    - "off": no weighting (pure baseline);
    - a float: an explicit override.
    The exact choice used is reported in the console output and reflected in
    the fitted model's get_params(). Information from validation/test sets is
    NEVER used to compute training weights.

    Returns (model, feature_columns, importance_dataframe). Any output path
    may be None to skip persisting that artifact (used by reproducibility
    checks and tests, which must not overwrite the saved artifacts); the CLI
    passes the default paths explicitly.
    """
    print("=" * 70)
    print("HYDRASENSE PHASE 5D-2: TRAIN XGBOOST DETERIORATION PREDICTION MODEL")
    print("=" * 70)
    print(f"Training Data:    {train_path}")
    if model_output:
        print(f"Model Output:     {model_output}")
    print(f"Hyperparameters:  n_estimators={n_estimators}, learning_rate={learning_rate}, "
          f"max_depth={max_depth}, subsample={subsample}, colsample_bytree={colsample_bytree}, "
          f"eval_metric={eval_metric}, random_state={random_state}, n_jobs={n_jobs}")

    # 1. Load ONLY the training split (validation/test are never read here).
    train_df = _load_train_data(train_path)
    print(f"\n1. Loaded training split: {len(train_df):,} rows, {len(train_df.columns)} columns.")

    # 2. Resolve the Phase 5D-1 feature schema (target is NEVER a feature).
    feature_cols = resolve_feature_columns(train_df, target_col=TARGET_COLUMN)
    print(f"2. Resolved {len(feature_cols)} Phase 5D-1 feature columns "
          f"(target '{TARGET_COLUMN}' and identifiers excluded).")
    print(f"   Features: {feature_cols}")

    # 3. Prepare X/y; rows whose target is not evaluable (NaN, e.g. series
    #    ends) cannot be fitted and are dropped with an explicit count.
    n_before = len(train_df)
    labeled = train_df.dropna(subset=[TARGET_COLUMN]).copy()
    dropped = n_before - len(labeled)
    if dropped:
        print(f"   Dropped {dropped:,} rows with non-evaluable (NaN) target - never fabricated.")
    X = labeled[feature_cols]
    y = labeled[TARGET_COLUMN].astype(int)

    classes = sorted(y.unique().tolist())
    if classes != [0, 1]:
        raise ValueError(
            f"Binary target requires exactly classes {{0, 1}}; found {classes}. "
            "The Phase 5D-1 deterioration_target must be binary where evaluable."
        )
    counts = y.value_counts().sort_index()
    n_pos, n_neg = int(counts.get(1, 0)), int(counts.get(0, 0))
    print(f"3. Target distribution (train): no-deterioration(0)={n_neg:,} "
          f"({n_neg / len(y) * 100:.2f}%), deterioration(1)={n_pos:,} ({n_pos / len(y) * 100:.2f}%).")
    if min(n_pos, n_neg) == 0:
        raise ValueError("Training split contains a single target class; cannot fit a binary classifier.")

    # 4. Class-imbalance handling: scale_pos_weight from TRAINING data only.
    if scale_pos_weight == "auto":
        spw_value = n_neg / n_pos
        spw_reason = (f"auto (negative_count/positive_count = {n_neg:,}/{n_pos:,} = {spw_value:.4f}, "
                      f"computed from the TRAINING split only; justified because the positive "
                      f"deterioration class is rare and missed events are the costlier error)")
    elif scale_pos_weight == "off":
        spw_value = 1.0
        spw_reason = "off (no reweighting; pure baseline)"
    else:
        spw_value = float(scale_pos_weight)
        spw_reason = f"explicit override = {spw_value:.4f}"
    print(f"4. Class imbalance handling: scale_pos_weight = {spw_reason}")

    # 5. Baseline XGBClassifier (deliberately NOT aggressively tuned).
    model = xgb.XGBClassifier(
        n_estimators=n_estimators,
        learning_rate=learning_rate,
        max_depth=max_depth,
        subsample=subsample,
        colsample_bytree=colsample_bytree,
        eval_metric=eval_metric,  # logloss: appropriate for binary classification
        random_state=random_state,
        n_jobs=n_jobs,
        scale_pos_weight=spw_value,
    )
    print("\n5. Fitting XGBClassifier on the training split only...")
    model.fit(X, y)
    print("   Training completed.")

    # 6. Feature importance (model contribution - NOT physical causation).
    importance_df = pd.DataFrame({"feature": feature_cols, "importance": model.feature_importances_})
    importance_df = importance_df.sort_values(by="importance", ascending=False).reset_index(drop=True)
    print("\n6. Feature importance (gain-based; association, NOT causation): top 10")
    for idx, row in importance_df.head(10).iterrows():
        print(f"   {idx + 1:>2}. {row['feature']:<32} {row['importance']:.6f}")

    # 7. Persist artifacts when requested.
    if feature_list_output is not None:
        feature_list_output.parent.mkdir(parents=True, exist_ok=True)
        feature_list_output.write_text("\n".join(feature_cols) + "\n", encoding="utf-8")
        print(f"\n7. Saved final feature list ({len(feature_cols)} features) to: {feature_list_output}")
    if importance_output is not None:
        importance_output.parent.mkdir(parents=True, exist_ok=True)
        importance_df.to_csv(importance_output, index=False)
        print(f"8. Saved feature importances to: {importance_output}")
    if importance_plot_output is not None:
        importance_plot_output.parent.mkdir(parents=True, exist_ok=True)
        plot_df = importance_df.sort_values(by="importance", ascending=True)
        fig, ax = plt.subplots(figsize=(9, max(4.0, 0.35 * len(plot_df))))
        ax.barh(plot_df["feature"], plot_df["importance"], color="#2b6cb0", edgecolor="#1a365d")
        ax.set_title("XGBoost Deterioration Prediction - Feature Importance\n(model contribution, not causation)",
                     fontsize=11, fontweight="bold")
        ax.set_xlabel("Importance (gain-based)")
        ax.set_ylabel("Phase 5D-1 Feature")
        for i, (val, feat) in enumerate(zip(plot_df["importance"], plot_df["feature"])):
            ax.text(val, i, f" {val:.4f}", va="center", fontsize=8)
        plt.tight_layout()
        plt.savefig(importance_plot_output, dpi=150)
        plt.close(fig)
        print(f"9. Saved feature importance plot to: {importance_plot_output}")
    if model_output is not None:
        model_output.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, model_output)
        print(f"10. Saved model artifact to: {model_output}")

    print("=" * 70)
    print("SUCCESS: XGBoost training completed (training split only).")
    print("=" * 70)
    return model, feature_cols, importance_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train XGBoost deterioration prediction model (Phase 5D-2).")
    parser.add_argument("--train-data", type=Path, default=DEFAULT_TRAIN_DATA, help="Path to forecast_train.csv.")
    parser.add_argument("--model-output", type=Path, default=DEFAULT_MODEL_OUTPUT, help="Model joblib output path.")
    parser.add_argument("--importance-output", type=Path, default=DEFAULT_IMPORTANCE_OUTPUT,
                        help="Feature importance CSV output path.")
    parser.add_argument("--importance-plot", type=Path, default=DEFAULT_IMPORTANCE_PLOT,
                        help="Feature importance PNG output path.")
    parser.add_argument("--n-estimators", type=int, default=200, help="Number of boosting rounds (baseline 200).")
    parser.add_argument("--learning-rate", type=float, default=0.05, help="Boosting learning rate (baseline 0.05).")
    parser.add_argument("--max-depth", type=int, default=6, help="Maximum tree depth (baseline 6).")
    parser.add_argument("--subsample", type=float, default=0.8, help="Row subsample ratio (baseline 0.8).")
    parser.add_argument("--colsample-bytree", type=float, default=0.8, help="Column subsample ratio (baseline 0.8).")
    parser.add_argument("--eval-metric", type=str, default="logloss",
                        help="Binary classification eval metric (logloss; use aucpr for strong imbalance).")
    parser.add_argument("--random-state", type=int, default=42, help="Deterministic seed.")
    parser.add_argument("--n-jobs", type=int, default=-1, help="Parallel workers (kept consistent across runs).")
    parser.add_argument("--scale-pos-weight", type=str, default="auto",
                        help="Class-imbalance handling: 'auto' = n_negative/n_positive from the "
                             "TRAINING split only; 'off' = no weighting; or an explicit float.")
    args = parser.parse_args()

    train_xgboost(
        train_path=args.train_data,
        model_output=args.model_output,
        importance_output=args.importance_output,
        importance_plot_output=args.importance_plot,
        feature_list_output=DEFAULT_FEATURE_LIST_OUTPUT,
        n_estimators=args.n_estimators,
        learning_rate=args.learning_rate,
        max_depth=args.max_depth,
        subsample=args.subsample,
        colsample_bytree=args.colsample_bytree,
        eval_metric=args.eval_metric,
        random_state=args.random_state,
        n_jobs=args.n_jobs,
        scale_pos_weight=args.scale_pos_weight,
    )
