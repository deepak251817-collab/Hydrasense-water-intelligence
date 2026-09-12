"""Train Random Forest Water-Quality Classifier (Phase 5C-2).

Loads supervised training data (ml/data/processed/supervised_train.csv),
validates feature columns, enforces strict leakage rules, trains a
deterministic RandomForestClassifier, extracts feature importances,
generates a feature importance plot, and saves the trained model artifact.
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
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from ml.preprocessing.prepare_supervised import (
    STANDARDIZED_FEATURE_COLUMNS,
    STANDARDIZED_TARGET_COLUMN,
    SupervisedPreprocessor,
)

DEFAULT_TRAIN_DATA = PROJECT_ROOT / "ml" / "data" / "processed" / "supervised_train.csv"
DEFAULT_MODEL_OUTPUT = PROJECT_ROOT / "ml" / "models" / "random_forest_classifier.joblib"
DEFAULT_IMPORTANCE_OUTPUT = PROJECT_ROOT / "ml" / "data" / "processed" / "random_forest_feature_importance.csv"
DEFAULT_PLOT_OUTPUT = PROJECT_ROOT / "ml" / "data" / "processed" / "feature_importance.png"


def train_random_forest(
    train_path: Path = DEFAULT_TRAIN_DATA,
    model_output: Path = DEFAULT_MODEL_OUTPUT,
    importance_output: Path = DEFAULT_IMPORTANCE_OUTPUT,
    plot_output: Path = DEFAULT_PLOT_OUTPUT,
    n_estimators: int = 100,
    max_depth: int | None = None,
    class_weight: str | None = None,
    random_state: int = 42,
    n_jobs: int = -1,
) -> tuple[RandomForestClassifier, pd.DataFrame]:
    """Train RandomForestClassifier on supervised training dataset and persist artifacts."""
    print("=" * 70)
    print("HYDRASENSE PHASE 5C-2: TRAIN RANDOM FOREST WATER-QUALITY CLASSIFIER")
    print("=" * 70)
    print(f"Training Data:      {train_path}")
    print(f"Model Output:       {model_output}")
    print(f"Importance Output:  {importance_output}")
    print(f"Hyperparameters:    n_estimators={n_estimators}, max_depth={max_depth}, "
          f"class_weight={class_weight}, random_state={random_state}")

    if not train_path.exists():
        raise FileNotFoundError(f"Training dataset not found at '{train_path}'. Run Phase 5C-1 preparation first.")

    # 1. Load Training Data
    train_df = pd.read_csv(train_path)
    print(f"\n1. Loaded training dataset: {len(train_df):,} rows, {len(train_df.columns)} columns.")

    # 2. Strict Data Leakage Checks
    if STANDARDIZED_TARGET_COLUMN not in train_df.columns:
        raise ValueError(f"Target column '{STANDARDIZED_TARGET_COLUMN}' missing from training data.")

    # Separate features and target
    X_train_raw = train_df.drop(columns=[STANDARDIZED_TARGET_COLUMN])
    y_train = train_df[STANDARDIZED_TARGET_COLUMN]

    # Verify target is excluded from features
    if STANDARDIZED_TARGET_COLUMN in X_train_raw.columns or "Label" in X_train_raw.columns:
        raise ValueError("Data Leakage: Target column present in feature matrix.")

    # Fit preprocessor strictly on training data
    preprocessor = SupervisedPreprocessor(feature_cols=list(STANDARDIZED_FEATURE_COLUMNS))
    X_train = preprocessor.fit_transform(X_train_raw)

    print(f"2. Features validated: {list(X_train.columns)}")
    print(f"   Target distribution in training set:")
    for label, count in y_train.value_counts().items():
        pct = (count / len(y_train)) * 100.0
        print(f"   - {label:<10}: {count:>6,} rows ({pct:5.2f}%)")

    # Class imbalance reporting for train / validation / test (spec 5C-2 section 9).
    # Rebalancing (SMOTE / over- / under-sampling) is NOT applied automatically; the
    # baseline model is trained on the natural distribution first.
    val_path = PROJECT_ROOT / "ml" / "data" / "processed" / "supervised_validation.csv"
    test_path = PROJECT_ROOT / "ml" / "data" / "processed" / "supervised_test.csv"
    print("\n   Class distribution across splits (imbalance is reported, not hidden):")
    for split_name, split_df in (("train", train_df), ("validation", pd.read_csv(val_path)), ("test", pd.read_csv(test_path))):
        counts = split_df[STANDARDIZED_TARGET_COLUMN].value_counts()
        n = len(split_df)
        unsafe = int(counts.get("Unsafe", 0))
        safe = int(counts.get("Safe", 0))
        ratio = (unsafe / safe) if safe > 0 else float("inf")
        print(f"   - {split_name:<10}: Unsafe={unsafe:>6,} ({unsafe / n * 100:5.2f}%) | "
              f"Safe={safe:>6,} ({safe / n * 100:5.2f}%) | imbalance ratio (Unsafe:Safe)={ratio:.4f}:1")
    majority_share = max(y_train.value_counts(normalize=True))
    if majority_share < 0.60:
        print("   - Decision: imbalance is mild (majority class < 60%); baseline RandomForest")
        print("     trained on the natural distribution WITHOUT class weights, SMOTE, or resampling.")
        print("     class_weight is configurable via --class-weight balanced if future analysis")
        print("     shows the minority class is under-served.")

    # 3. Model Training
    print("\n3. Training RandomForestClassifier...")
    rf_model = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        class_weight=class_weight,
        random_state=random_state,
        n_jobs=n_jobs,
    )
    rf_model.fit(X_train, y_train)
    print("   RandomForestClassifier training completed successfully.")

    # 4. Feature Importance Extraction
    importances = rf_model.feature_importances_
    importance_df = pd.DataFrame({
        "feature": STANDARDIZED_FEATURE_COLUMNS,
        "importance": importances,
    }).sort_values(by="importance", ascending=False).reset_index(drop=True)

    print("\n4. Feature Importance Ranking:")
    print("-" * 45)
    for idx, row in importance_df.iterrows():
        print(f"   {idx + 1}. {row['feature']:<15}: {row['importance']:.6f} ({row['importance'] * 100:5.2f}%)")
    print("-" * 45)
    print("   Note: Feature importance indicates tree Gini split contribution, NOT real-world causation.")

    # 5. Save Feature Importance CSV
    importance_output.parent.mkdir(parents=True, exist_ok=True)
    importance_df.to_csv(importance_output, index=False)
    print(f"\n5. Saved feature importances to: {importance_output}")

    # 6. Generate Feature Importance Plot
    plot_output.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(8, 5))
    sorted_df = importance_df.sort_values(by="importance", ascending=True)
    plt.barh(sorted_df["feature"], sorted_df["importance"], color="#2b6cb0", edgecolor="#1a365d")
    plt.title("Random Forest Water-Quality Feature Importance", fontsize=12, fontweight="bold")
    plt.xlabel("Mean Decrease in Impurity (Gini Importance)", fontsize=10)
    plt.ylabel("Water Quality Feature", fontsize=10)
    plt.xlim(0, max(importance_df["importance"]) * 1.15)
    for idx, (val, feat) in enumerate(zip(sorted_df["importance"], sorted_df["feature"])):
        plt.text(val + 0.005, idx, f"{val:.4f} ({val * 100:.1f}%)", va="center", fontsize=9)
    plt.tight_layout()
    plt.savefig(plot_output, dpi=150)
    plt.close()
    print(f"6. Saved feature importance visualization to: {plot_output}")

    # 7. Persist Model Artifact
    model_output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(rf_model, model_output)
    print(f"7. Persisted trained model artifact to: {model_output}")
    print("=" * 70)
    print("SUCCESS: Model training and persistence completed.")
    print("=" * 70)

    return rf_model, importance_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train RandomForestClassifier for water quality.")
    parser.add_argument("--train-data", type=Path, default=DEFAULT_TRAIN_DATA, help="Path to train CSV.")
    parser.add_argument("--model-output", type=Path, default=DEFAULT_MODEL_OUTPUT, help="Path for model joblib.")
    parser.add_argument("--importance-output", type=Path, default=DEFAULT_IMPORTANCE_OUTPUT, help="Path for importance CSV.")
    parser.add_argument("--plot-output", type=Path, default=DEFAULT_PLOT_OUTPUT, help="Path for importance PNG.")
    parser.add_argument("--n-estimators", type=int, default=100, help="Number of trees in forest.")
    parser.add_argument("--max-depth", type=int, default=None, help="Maximum tree depth (None for unlimited).")
    parser.add_argument("--class-weight", type=str, default=None, choices=[None, "balanced"], help="Class weighting.")
    parser.add_argument("--random-state", type=int, default=42, help="Deterministic random seed.")
    parser.add_argument("--n-jobs", type=int, default=-1, help="Parallel CPU workers.")
    args = parser.parse_args()

    train_random_forest(
        train_path=args.train_data,
        model_output=args.model_output,
        importance_output=args.importance_output,
        plot_output=args.plot_output,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        class_weight=args.class_weight,
        random_state=args.random_state,
        n_jobs=args.n_jobs,
    )
