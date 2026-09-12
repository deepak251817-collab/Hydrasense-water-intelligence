"""Evaluate XGBoost Deterioration Prediction Model (Phase 5D-2).

Evaluates the persisted XGBoost model against a Phase 5D-1 chronological
split:

- `--split validation`  -> forecast_validation.csv  (model selection / evaluation ONLY)
- `--split test`        -> forecast_test.csv        (final evaluation, run ONCE
                          after the configuration is finalized; never used
                          for parameter selection)

Reports accuracy, precision, recall, F1-score, and the confusion matrix for
the positive class `deterioration_target = 1` (future deterioration
indicator). When class imbalance is significant (minority class < 20% or >
80%), balanced accuracy and ROC-AUC are additionally reported (ROC-AUC is
mathematically appropriate here: the target is binary and the model produces
continuous probabilities).

LEAKAGE CONTRACT: this script never trains; the model is loaded from disk.
Each split is used strictly for the purpose documented above.

Phase 5D-1 STOP state: if the requested split or the model artifact does not
exist, the script fails with a clear instruction. Nothing is fabricated.
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
matplotlib.use("Agg")  # headless-safe rendering
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from ml.preprocessing.forecasting import (
    STATION_COLUMN,
    TARGET_COLUMN,
    resolve_feature_columns,
)
from ml.scripts.train_xgboost import (
    DEFAULT_MODEL_OUTPUT,
    MISSING_INPUT_MESSAGE,
    _load_train_data,  # reuse the exact same loud-failure loader for splits
)

DEFAULT_VAL_DATA = PROJECT_ROOT / "ml" / "data" / "processed" / "forecast_validation.csv"
DEFAULT_TEST_DATA = PROJECT_ROOT / "ml" / "data" / "processed" / "forecast_test.csv"
DEFAULT_CONFUSION_PLOT = PROJECT_ROOT / "ml" / "data" / "processed" / "xgboost_confusion_matrix.png"

# Imbalance threshold for reporting balanced accuracy / ROC-AUC
IMBALANCE_MINORITY_SHARE = 0.20


def evaluate_split(
    data_path: Path,
    model_path: Path = DEFAULT_MODEL_OUTPUT,
    plot_output: Path | None = DEFAULT_CONFUSION_PLOT,
    split_name: str = "Validation",
    threshold: float = 0.5,
) -> dict:
    """Evaluate the persisted model on one chronological split at a fixed
    probability threshold (frozen before the final test evaluation)."""
    print("=" * 70)
    print(f"HYDRASENSE PHASE 5D-2: XGBOOST EVALUATION ({split_name.upper()} SPLIT)")
    print("=" * 70)
    print(f"Dataset:    {data_path}")
    print(f"Model File: {model_path}")

    if not model_path.exists():
        raise FileNotFoundError(
            f"Model artifact not found at '{model_path}'. Run ml/scripts/train_xgboost.py first."
        )
    if not data_path.exists():
        raise FileNotFoundError(f"Evaluation split not found at '{data_path}'. {MISSING_INPUT_MESSAGE}")

    # 1. Load model and split (evaluation only - no fitting happens here).
    df = pd.read_csv(data_path)
    model = joblib.load(model_path)
    print(f"\n1. Loaded split: {len(df):,} rows; model loaded from disk.")

    # 2. Resolve the Phase 5D-1 feature schema for this split.
    feature_cols = resolve_feature_columns(df, target_col=TARGET_COLUMN)

    # 3. Drop non-evaluable target rows (never fabricated) for metric computation.
    labeled = df.dropna(subset=[TARGET_COLUMN]).copy()
    dropped = len(df) - len(labeled)
    if dropped:
        print(f"2. Dropped {dropped:,} rows with non-evaluable (NaN) target for metric computation.")
    X = labeled[feature_cols]
    y_true = labeled[TARGET_COLUMN].astype(int)

    y_prob = model.predict_proba(X)[:, 1]
    # Thresholded labels: 1 (deterioration) when probability >= threshold.
    y_pred = (y_prob >= threshold).astype(int)
    print(f"   Probability threshold: {threshold} "
          f"({'default' if threshold == 0.5 else 'frozen from validation selection'})")

    # 4. Metrics (positive class = 1, the future deterioration indicator).
    acc = accuracy_score(y_true, y_pred)
    prec = precision_score(y_true, y_pred, pos_label=1, zero_division=0)
    rec = recall_score(y_true, y_pred, pos_label=1, zero_division=0)
    f1 = f1_score(y_true, y_pred, pos_label=1, zero_division=0)
    minority_share = min(y_true.mean(), 1.0 - y_true.mean())
    imbalance_significant = minority_share < IMBALANCE_MINORITY_SHARE

    print("\n3. CLASS DISTRIBUTION (observed):")
    counts = y_true.value_counts().sort_index()
    n_non_det, n_det = int(counts.get(0, 0)), int(counts.get(1, 0))
    print(f"   - non-deterioration (0): {n_non_det:,} ({n_non_det / len(y_true) * 100:.2f}%)")
    print(f"   - deterioration (1):     {n_det:,} ({n_det / len(y_true) * 100:.2f}%)")
    print(f"   Minority share: {minority_share * 100:.2f}% -> "
          f"{'IMBALANCE SIGNIFICANT' if imbalance_significant else 'imbalance not significant'}")

    print("\n4. METRICS (positive class = 1: future deterioration indicator):")
    print("-" * 55)
    print(f"   Accuracy:   {acc:.4f}  (reported for completeness, NOT relied upon: the positive class is rare)")
    print(f"   Precision:  {prec:.4f}")
    print(f"   Recall:     {rec:.4f}")
    print(f"   F1-score:   {f1:.4f}")
    bal_acc = balanced_accuracy_score(y_true, y_pred)
    print(f"   Balanced Accuracy: {bal_acc:.4f}")
    if len(np.unique(y_true)) == 2:
        auc = roc_auc_score(y_true, y_prob)
        print(f"   ROC-AUC:           {auc:.4f} (threshold-independent; binary target + continuous probabilities)")
    else:
        auc = float("nan")
        print("   ROC-AUC:           undefined (single class present)")

    # 5. Confusion matrix [rows: actual, cols: predicted]; labels ordered 0, 1.
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm[0, 0], cm[0, 1], cm[1, 0], cm[1, 1]
    print("\n5. CONFUSION MATRIX (rows: actual, cols: predicted):")
    print("-" * 55)
    print(f"                Predicted 0 | Predicted 1")
    print(f"   Actual 0:    {tn:>10,} | {fp:>11,}")
    print(f"   Actual 1:    {fn:>10,} | {tp:>11,}")
    print("-" * 55)

    # 6. Confusion matrix plot.
    if plot_output is not None:
        plot_output.parent.mkdir(parents=True, exist_ok=True)
        fig, ax = plt.subplots(figsize=(6, 5))
        cax = ax.matshow(cm, cmap="Blues", alpha=0.85)
        for i in range(2):
            for j in range(2):
                val = int(cm[i, j])
                ax.text(j, i, f"{val:,}\n({val / cm.sum() * 100:.1f}%)",
                        ha="center", va="center",
                        color="white" if val > cm.max() / 2 else "black",
                        fontsize=11, fontweight="bold")
        fig.colorbar(cax)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["0 (no deterioration)", "1 (deterioration)"], fontsize=9)
        ax.set_yticks([0, 1])
        ax.set_yticklabels(["0 (no deterioration)", "1 (deterioration)"], fontsize=9)
        ax.set_xlabel("Predicted label", fontsize=10, labelpad=8)
        ax.set_ylabel("Actual label", fontsize=10)
        ax.set_title(f"XGBoost Deterioration Prediction - Confusion Matrix ({split_name})",
                     fontsize=11, fontweight="bold", pad=14)
        plt.tight_layout()
        plt.savefig(plot_output, dpi=150)
        plt.close(fig)
        print(f"\n6. Saved confusion matrix plot to: {plot_output}")

    print("=" * 70)
    return {
        "split_name": split_name,
        "total_rows": int(len(df)),
        "evaluable_rows": int(len(labeled)),
        "threshold": float(threshold),
        "accuracy": float(acc),
        "precision": float(prec),
        "recall": float(rec),
        "f1": float(f1),
        "balanced_accuracy": float(bal_acc),
        "roc_auc": (float(auc) if len(np.unique(y_true)) == 2 else None),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "false_positives": int(fp),
        "false_negatives": int(fn),
        "deterioration_count": int(n_det),
        "non_deterioration_count": int(n_non_det),
        "imbalance_significant": bool(imbalance_significant),
    }


def select_threshold_on_validation(
    data_path: Path = DEFAULT_VAL_DATA,
    model_path: Path = DEFAULT_MODEL_OUTPUT,
    candidates: tuple[float, ...] = (0.5, 0.4, 0.3, 0.2, 0.15, 0.1),
) -> dict:
    """Select the probability threshold on the VALIDATION split ONLY.

    Scans candidate thresholds and reports the full trade-off table (F1,
    balanced accuracy, false positives, false negatives). The recommended
    threshold maximizes F1 (balancing precision/recall for a rare positive
    class); ties prefer the default 0.5. The TEST set is never touched here
    (Phase 5D-2 spec section 9).
    """
    print("=" * 70)
    print("HYDRASENSE PHASE 5D-2: THRESHOLD SELECTION (VALIDATION SPLIT ONLY)")
    print("=" * 70)
    df = _load_train_data(data_path)
    model = joblib.load(model_path)
    feature_cols = resolve_feature_columns(df, target_col=TARGET_COLUMN)
    labeled = df.dropna(subset=[TARGET_COLUMN])
    X, y_true = labeled[feature_cols], labeled[TARGET_COLUMN].astype(int)
    y_prob = model.predict_proba(X)[:, 1]

    rows = []
    for t in candidates:
        y_pred = (y_prob >= t).astype(int)
        rows.append({
            "threshold": t,
            "precision": precision_score(y_true, y_pred, zero_division=0),
            "recall": recall_score(y_true, y_pred, zero_division=0),
            "f1": f1_score(y_true, y_pred, zero_division=0),
            "balanced_accuracy": balanced_accuracy_score(y_true, y_pred),
            "false_positives": int(((y_true == 0) & (y_pred == 1)).sum()),
            "false_negatives": int(((y_true == 1) & (y_pred == 0)).sum()),
        })
    table = pd.DataFrame(rows)
    print("\nTHRESHOLD TRADE-OFF TABLE (validation split):")
    print(table.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    best = table.loc[table["f1"].idxmax()]
    # Prefer the default 0.5 when it ties the best F1.
    max_f1 = table["f1"].max()
    chosen = 0.5 if (table["f1"] == max_f1).any() and \
        table.loc[table["threshold"] == 0.5, "f1"].iloc[0] == max_f1 else float(best["threshold"])
    print(f"\nSELECTED THRESHOLD: {chosen} (maximizes validation F1; default preferred on ties)")
    print("The final test evaluation must use this frozen threshold and the test set must")
    print("never be used to revisit it.")
    print("=" * 70)
    return {
        "selected_threshold": float(chosen),
        "reason": "maximizes F1 on the VALIDATION split (default 0.5 preferred on ties)",
        "table": table,
        "validation_metrics_at_selected": {
            "precision": float(best["precision"]),
            "recall": float(best["recall"]),
            "f1": float(best["f1"]),
            "balanced_accuracy": float(best["balanced_accuracy"]),
        },
    }


def verify_reproducibility(
    train_path: Path = PROJECT_ROOT / "ml" / "data" / "processed" / "forecast_train.csv",
    val_path: Path = DEFAULT_VAL_DATA,
    random_state: int = 42,
) -> bool:
    """Train twice (identical data, hyperparameters, seed, n_jobs) and verify
    that predictions, probabilities, and feature importances are identical.
    Does not overwrite any saved artifacts."""
    from ml.scripts.train_xgboost import train_xgboost

    print("=" * 70)
    print("HYDRASENSE PHASE 5D-2: REPRODUCIBILITY VERIFICATION (seed=42)")
    print("=" * 70)
    print("Training run 1/2 ...")
    m1, feats, imp1 = train_xgboost(train_path=train_path, model_output=None,
                                    importance_output=None, importance_plot_output=None,
                                    random_state=random_state)
    print("Training run 2/2 ...")
    m2, _, imp2 = train_xgboost(train_path=train_path, model_output=None,
                                importance_output=None, importance_plot_output=None,
                                random_state=random_state)

    val_df = _load_train_data(val_path)  # same loud-failure semantics
    labeled = val_df.dropna(subset=[TARGET_COLUMN])
    X_val = labeled[feats]
    preds_equal = bool(np.array_equal(m1.predict(X_val), m2.predict(X_val)))
    probs_equal = bool(np.array_equal(m1.predict_proba(X_val), m2.predict_proba(X_val)))
    imp_equal = bool(np.array_equal(imp1["importance"].values, imp2["importance"].values))

    print("\nREPRODUCIBILITY COMPARISON:")
    print("-" * 55)
    print(f"   Predictions identical:        {'PASS' if preds_equal else 'FAIL'}")
    print(f"   Probabilities identical:      {'PASS' if probs_equal else 'FAIL'}")
    print(f"   Feature importances equal:    {'PASS' if imp_equal else 'FAIL'}")
    ok = preds_equal and probs_equal and imp_equal
    print(f"REPRODUCIBILITY RESULT: {'PASS' if ok else 'FAIL'}")
    print("=" * 70)
    return ok


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate XGBoost deterioration prediction (Phase 5D-2).")
    parser.add_argument("--split", type=str, default="validation", choices=["validation", "test"],
                        help="Which chronological split to evaluate.")
    parser.add_argument("--data", type=Path, default=None, help="Custom split path (overrides --split).")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_OUTPUT, help="Path to the trained model.")
    parser.add_argument("--plot-output", type=Path, default=DEFAULT_CONFUSION_PLOT,
                        help="Confusion matrix PNG output path.")
    parser.add_argument("--verify-reproducibility", action="store_true",
                        help="Train twice with the same seed and verify identical results.")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="Probability threshold for the positive class (frozen before test evaluation).")
    parser.add_argument("--select-threshold", action="store_true",
                        help="Run threshold selection on the VALIDATION split only and exit.")
    args = parser.parse_args()

    if args.verify_reproducibility:
        if not verify_reproducibility(random_state=42):
            raise SystemExit(1)

    if args.select_threshold:
        select_threshold_on_validation(model_path=args.model)
        raise SystemExit(0)

    target_data = args.data
    if target_data is None:
        target_data = DEFAULT_VAL_DATA if args.split == "validation" else DEFAULT_TEST_DATA
        split_label = "Validation" if args.split == "validation" else "Test"
    else:
        split_label = "Custom"
    metrics = evaluate_split(data_path=target_data, model_path=args.model,
                             plot_output=args.plot_output, split_name=split_label,
                             threshold=args.threshold)
    print(f"\n{split_label.upper()}-SPLIT METRICS SUMMARY: {metrics}")
