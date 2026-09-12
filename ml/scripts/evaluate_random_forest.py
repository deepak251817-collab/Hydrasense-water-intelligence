"""Evaluate Random Forest Water-Quality Classifier (Phase 5C-2).

Evaluates the persisted Random Forest model against validation or test splits.
Generates comprehensive classification metrics:
- Overall accuracy, macro/weighted precision, recall, F1-score
- Class-wise metrics for 'Safe' and 'Unsafe'
- Prediction frequencies (Safe vs Unsafe)
- Detailed confusion matrix
- Error analysis (False Positives, False Negatives, and sample misclassifications)
- Generates confusion matrix visualization (ml/data/processed/confusion_matrix.png)
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
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

from ml.preprocessing.prepare_supervised import (
    STANDARDIZED_FEATURE_COLUMNS,
    STANDARDIZED_TARGET_COLUMN,
    SupervisedPreprocessor,
)

DEFAULT_MODEL_PATH = PROJECT_ROOT / "ml" / "models" / "random_forest_classifier.joblib"
DEFAULT_TRAIN_DATA = PROJECT_ROOT / "ml" / "data" / "processed" / "supervised_train.csv"
DEFAULT_VAL_DATA = PROJECT_ROOT / "ml" / "data" / "processed" / "supervised_validation.csv"
DEFAULT_TEST_DATA = PROJECT_ROOT / "ml" / "data" / "processed" / "supervised_test.csv"
DEFAULT_CONFUSION_PLOT = PROJECT_ROOT / "ml" / "data" / "processed" / "confusion_matrix.png"


def evaluate_random_forest(
    data_path: Path,
    model_path: Path = DEFAULT_MODEL_PATH,
    plot_output: Path | None = DEFAULT_CONFUSION_PLOT,
    split_name: str = "Validation",
) -> dict:
    """Evaluate trained Random Forest model and return metrics dict."""
    print("=" * 70)
    print(f"HYDRASENSE PHASE 5C-2: RANDOM FOREST EVALUATION ({split_name.upper()})")
    print("=" * 70)
    print(f"Dataset:       {data_path}")
    print(f"Model File:    {model_path}")

    if not model_path.exists():
        raise FileNotFoundError(f"Trained model not found at '{model_path}'. Run training first.")
    if not data_path.exists():
        raise FileNotFoundError(f"Evaluation dataset not found at '{data_path}'.")

    # Training data is used ONLY to fit the preprocessing schema (never for metric computation).
    train_path = PROJECT_ROOT / "ml" / "data" / "processed" / "supervised_train.csv"
    if not train_path.exists():
        raise FileNotFoundError(f"Training dataset not found at '{train_path}'.")
    train_df = pd.read_csv(train_path)

    # 1. Load Data and Model
    df = pd.read_csv(data_path)
    model = joblib.load(model_path)
    print(f"\n1. Loaded evaluation dataset: {len(df):,} rows.")

    if STANDARDIZED_TARGET_COLUMN not in df.columns:
        raise ValueError(f"Target column '{STANDARDIZED_TARGET_COLUMN}' missing from dataset.")

    X_eval_raw = df.drop(columns=[STANDARDIZED_TARGET_COLUMN])
    y_true = df[STANDARDIZED_TARGET_COLUMN]

    # Use the pre-fitted transformation schema (fitted ONLY on training data during training).
    # Random Forest requires no feature scaling; this is an identity, order-preserving pass-through.
    preprocessor = SupervisedPreprocessor(feature_cols=list(STANDARDIZED_FEATURE_COLUMNS))
    preprocessor.fit(train_df.drop(columns=[STANDARDIZED_TARGET_COLUMN]))  # training data ONLY - never evaluation data
    X_eval = preprocessor.transform(X_eval_raw)

    # 2. Generate Predictions
    y_pred = model.predict(X_eval)
    y_prob = model.predict_proba(X_eval)

    # Map class indices for Safe and Unsafe
    classes = list(model.classes_)
    safe_idx = classes.index("Safe")
    unsafe_idx = classes.index("Unsafe")

    # 3. Overall Metrics
    acc = accuracy_score(y_true, y_pred)
    # Binary metrics considering 'Unsafe' as the primary alert/positive class
    prec_unsafe = precision_score(y_true, y_pred, pos_label="Unsafe", zero_division=0)
    rec_unsafe = recall_score(y_true, y_pred, pos_label="Unsafe", zero_division=0)
    f1_unsafe = f1_score(y_true, y_pred, pos_label="Unsafe", zero_division=0)

    # Binary metrics for 'Safe'
    prec_safe = precision_score(y_true, y_pred, pos_label="Safe", zero_division=0)
    rec_safe = recall_score(y_true, y_pred, pos_label="Safe", zero_division=0)
    f1_safe = f1_score(y_true, y_pred, pos_label="Safe", zero_division=0)

    # Macro & Weighted metrics
    prec_macro = precision_score(y_true, y_pred, average="macro", zero_division=0)
    rec_macro = recall_score(y_true, y_pred, average="macro", zero_division=0)
    f1_macro = f1_score(y_true, y_pred, average="macro", zero_division=0)

    prec_weighted = precision_score(y_true, y_pred, average="weighted", zero_division=0)
    rec_weighted = recall_score(y_true, y_pred, average="weighted", zero_division=0)
    f1_weighted = f1_score(y_true, y_pred, average="weighted", zero_division=0)

    # 4. Prediction Counts
    pred_counts = pd.Series(y_pred).value_counts().to_dict()
    safe_preds = int(pred_counts.get("Safe", 0))
    unsafe_preds = int(pred_counts.get("Unsafe", 0))

    actual_counts = y_true.value_counts().to_dict()
    safe_actual = int(actual_counts.get("Safe", 0))
    unsafe_actual = int(actual_counts.get("Unsafe", 0))

    print("\n2. PREDICTION DISTRIBUTION vs ACTUAL:")
    print("-" * 55)
    print(f"   - Actual:    Safe={safe_actual:,} ({(safe_actual/len(df))*100:.2f}%), "
          f"Unsafe={unsafe_actual:,} ({(unsafe_actual/len(df))*100:.2f}%)")
    print(f"   - Predicted: Safe={safe_preds:,} ({(safe_preds/len(df))*100:.2f}%), "
          f"Unsafe={unsafe_preds:,} ({(unsafe_preds/len(df))*100:.2f}%)")

    print("\n3. PERFORMANCE METRICS:")
    print("-" * 55)
    print("   Positive class (primary alert class): 'Unsafe'")
    print("   (True Positive = actual Unsafe correctly flagged; False Positive = Safe water flagged Unsafe.)")
    print("-" * 55)
    print(f"   Accuracy:            {acc:.4f} ({acc * 100:.2f}%)")
    print(f"   Macro Precision:     {prec_macro:.4f}")
    print(f"   Macro Recall:        {rec_macro:.4f}")
    print(f"   Macro F1-score:      {f1_macro:.4f}")
    print(f"   Weighted F1-score:   {f1_weighted:.4f}")

    print("\n4. CLASS-WISE METRICS:")
    print("-" * 55)
    print(f"   {'Class':<10} | {'Precision':>10} | {'Recall':>10} | {'F1-score':>10} | {'Support':>10}")
    print("-" * 55)
    print(f"   {'Unsafe':<10} | {prec_unsafe:>10.4f} | {rec_unsafe:>10.4f} | {f1_unsafe:>10.4f} | {unsafe_actual:>10,}")
    print(f"   {'Safe':<10} | {prec_safe:>10.4f} | {rec_safe:>10.4f} | {f1_safe:>10.4f} | {safe_actual:>10,}")
    print("-" * 55)

    # 5. Confusion Matrix
    # Labels ordered: Safe, Unsafe
    cm = confusion_matrix(y_true, y_pred, labels=["Safe", "Unsafe"])
    tn, fp, fn, tp = cm[0, 0], cm[0, 1], cm[1, 0], cm[1, 1]

    # 6. sklearn classification report (required for the final test evaluation report)
    report_text = classification_report(
        y_true,
        y_pred,
        labels=["Safe", "Unsafe"],
        target_names=["Safe", "Unsafe"],
        digits=4,
        zero_division=0,
    )
    print("\n6. SKLEARN CLASSIFICATION REPORT:")
    print("-" * 55)
    print(report_text)
    print("-" * 55)

    print("\n5. CONFUSION MATRIX (Rows: Actual, Columns: Predicted):")
    print("-" * 55)
    print(f"                Predicted Safe | Predicted Unsafe")
    print(f"   Actual Safe:   {tn:>12,} | {fp:>16,}")
    print(f"   Actual Unsafe: {fn:>12,} | {tp:>16,}")
    print("-" * 55)

    # 7. Error Analysis
    # False Positive (Actual Safe, Predicted Unsafe)
    # False Negative (Actual Unsafe, Predicted Safe)
    fp_mask = (y_true == "Safe") & (y_pred == "Unsafe")
    fn_mask = (y_true == "Unsafe") & (y_pred == "Safe")

    print("\n7. ERROR ANALYSIS:")
    print("-" * 55)
    print(f"   Total Errors:                  {int(fp + fn):,} ({(fp + fn)/len(df)*100:.2f}%)")
    print(f"   False Positives (Safe->Unsafe):{int(fp):,} ({(fp / safe_actual)*100:.2f}% of Safe)")
    print(f"   False Negatives (Unsafe->Safe):{int(fn):,} ({(fn / unsafe_actual)*100:.2f}% of Unsafe)")

    if int(fp) > 0:
        print("\n   Sample False Positive Misclassifications (Actual Safe, Predicted Unsafe):")
        fp_samples = df[fp_mask].head(3)
        for idx, row in fp_samples.iterrows():
            prob_u = y_prob[idx, unsafe_idx]
            print(f"     Row {idx}: pH={row['pH']}, tds={row['tds']}, turb={row['turbidity']}, "
                  f"temp={row['temperature']} -> P(Unsafe)={prob_u:.3f}")

    if int(fn) > 0:
        print("\n   Sample False Negative Misclassifications (Actual Unsafe, Predicted Safe):")
        fn_samples = df[fn_mask].head(3)
        for idx, row in fn_samples.iterrows():
            prob_s = y_prob[idx, safe_idx]
            print(f"     Row {idx}: pH={row['pH']}, tds={row['tds']}, turb={row['turbidity']}, "
                  f"temp={row['temperature']} -> P(Safe)={prob_s:.3f}")

    # 8. Visualization: Confusion Matrix Plot
    if plot_output:
        plot_output.parent.mkdir(parents=True, exist_ok=True)
        fig, ax = plt.subplots(figsize=(6, 5))
        cax = ax.matshow(cm, cmap="Blues", alpha=0.85)

        for i in range(2):
            for j in range(2):
                val = cm[i, j]
                pct = (val / len(df)) * 100.0
                ax.text(j, i, f"{val:,}\n({pct:.1f}%)", ha="center", va="center",
                        color="white" if val > cm.max() / 2 else "black", fontsize=11, fontweight="bold")

        fig.colorbar(cax)
        ax.set_xticks([0, 1])
        ax.set_yticks([0, 1])
        ax.set_xticklabels(["Safe", "Unsafe"], fontsize=10)
        ax.set_yticklabels(["Safe", "Unsafe"], fontsize=10)
        plt.xlabel("Predicted Label", fontsize=11, labelpad=10)
        plt.ylabel("Actual Ground Truth Label", fontsize=11)
        plt.title(f"Random Forest Confusion Matrix ({split_name})", fontsize=12, fontweight="bold", pad=15)
        plt.tight_layout()
        plt.savefig(plot_output, dpi=150)
        plt.close()
        print(f"\n8. Saved confusion matrix plot to: {plot_output}")

    print("=" * 70)

    return {
        "split_name": split_name,
        "total_rows": len(df),
        "accuracy": acc,
        "precision_macro": prec_macro,
        "recall_macro": rec_macro,
        "f1_macro": f1_macro,
        "f1_weighted": f1_weighted,
        "precision_unsafe": prec_unsafe,
        "recall_unsafe": rec_unsafe,
        "f1_unsafe": f1_unsafe,
        "precision_safe": prec_safe,
        "recall_safe": rec_safe,
        "f1_safe": f1_safe,
        "safe_preds": safe_preds,
        "unsafe_preds": unsafe_preds,
        "safe_actual": safe_actual,
        "unsafe_actual": unsafe_actual,
        "confusion_matrix": {
            "tn": int(tn),
            "fp": int(fp),
            "fn": int(fn),
            "tp": int(tp),
        },
        "false_positives": int(fp),
        "false_negatives": int(fn),
    }


def verify_reproducibility(
    n_estimators: int = 100,
    max_depth: int | None = None,
    class_weight: str | None = None,
    random_state: int = 42,
) -> bool:
    """Train two full Random Forests with the same random_state and verify identical results.

    Spec 5C-2 section 8: train the model twice with random_state=42 on the same training
    data/configuration and confirm reproducibility (identical feature importances and
    identical predictions/probabilities on the validation split).
    """
    print("=" * 70)
    print("HYDRASENSE PHASE 5C-2: REPRODUCIBILITY VERIFICATION (random_state=42)")
    print("=" * 70)

    # Validation data is used ONLY for comparison after both trainings; never fitted on.
    val_df = pd.read_csv(DEFAULT_VAL_DATA)
    X_val = val_df[STANDARDIZED_FEATURE_COLUMNS]

    models = []
    for run in (1, 2):
        print(f"\nTraining run {run}/2 (random_state={random_state})...")
        train_df = pd.read_csv(DEFAULT_TRAIN_DATA)
        preprocessor = SupervisedPreprocessor(feature_cols=list(STANDARDIZED_FEATURE_COLUMNS))
        X_train = preprocessor.fit_transform(train_df.drop(columns=[STANDARDIZED_TARGET_COLUMN]))
        y_train = train_df[STANDARDIZED_TARGET_COLUMN]
        rf = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            class_weight=class_weight,
            random_state=random_state,
            n_jobs=-1,
        )
        rf.fit(X_train, y_train)
        models.append(rf)

    m1, m2 = models
    imp_equal = bool(np.array_equal(m1.feature_importances_, m2.feature_importances_))
    pred1, pred2 = m1.predict(X_val), m2.predict(X_val)
    prob1, prob2 = m1.predict_proba(X_val), m2.predict_proba(X_val)
    preds_equal = bool(np.array_equal(pred1, pred2))
    probs_equal = bool(np.array_equal(prob1, prob2))

    print("\nREPRODUCIBILITY COMPARISON:")
    print("-" * 55)
    print(f"   Feature importances identical:  {'PASS' if imp_equal else 'FAIL'}")
    print(f"   Validation predictions equal:   {'PASS' if preds_equal else 'FAIL'}")
    print(f"   Validation probabilities equal: {'PASS' if probs_equal else 'FAIL'}")
    print("-" * 55)
    reproducible = imp_equal and preds_equal and probs_equal
    print(f"REPRODUCIBILITY RESULT: {'PASS - results are deterministic with random_state=42' if reproducible else 'FAIL - results differ between runs'}")
    print("=" * 70)
    return reproducible


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Random Forest classifier.")
    parser.add_argument("--split", type=str, default="validation", choices=["validation", "test"],
                        help="Split to evaluate ('validation' or 'test').")
    parser.add_argument("--data", type=Path, default=None, help="Custom data path (overrides split).")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH, help="Path to trained model.")
    parser.add_argument("--plot-output", type=Path, default=DEFAULT_CONFUSION_PLOT, help="Path for confusion matrix plot.")
    parser.add_argument("--verify-reproducibility", action="store_true", help="Train twice with random_state=42 and verify identical results.")
    args = parser.parse_args()

    if args.data:
        target_data = args.data
        split_label = "Custom"
    elif args.split == "validation":
        target_data = DEFAULT_VAL_DATA
        split_label = "Validation"
    else:
        target_data = DEFAULT_TEST_DATA
        split_label = "Test"

    evaluate_random_forest(
        data_path=target_data,
        model_path=args.model,
        plot_output=args.plot_output,
        split_name=split_label,
    )

    if args.verify_reproducibility:
        ok = verify_reproducibility()
        if not ok:
            raise SystemExit(1)
