"""Build the ML evaluation report from saved artifacts and prediction outputs.

Phase 12 deliverable: a machine-readable report containing the ACTUAL metrics
computed from the repository's saved test-split predictions, plus model and
dataset provenance. Nothing here is hardcoded: every number is recomputed
from the CSVs/joblib artifacts below, so the report is reproducible with:

    python ml/scripts/build_evaluation_report.py

Outputs:
    ml/reports/evaluation_report.json
    ml/reports/evaluation_report.md

Scope and honesty:
- Random Forest: supervised Safe/Unsafe classification on a stratified 15%
  test split of the benchmark dataset. Metrics are computed from
  `random_forest_predictions.csv` (written by evaluate_random_forest.py).
- Isolation Forest: unsupervised anomaly screening on live station telemetry.
  No ground-truth contamination labels exist, so precision/recall/accuracy are
  NOT reported — only anomaly rate and score distribution.
- XGBoost: offline deterioration prediction on a single USGS station. It is
  not connected to live inference (missing lag/USGS-only features).
- The Safe/Unsafe label is the benchmark dataset's labeling rule; it is not
  potability, laboratory confirmation, or a guarantee of safety.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

PROCESSED_DIR = PROJECT_ROOT / "ml" / "data" / "processed"
MODELS_DIR = PROJECT_ROOT / "ml" / "models"
REPORTS_DIR = PROJECT_ROOT / "ml" / "reports"

RF_PREDICTIONS = PROCESSED_DIR / "random_forest_predictions.csv"
SUPERVISED_TEST = PROCESSED_DIR / "supervised_test.csv"
ANOMALY_RESULTS = PROCESSED_DIR / "anomaly_results.csv"
XGBOOST_PREDICTIONS = PROCESSED_DIR / "xgboost_predictions.csv"

RF_MODEL = MODELS_DIR / "random_forest_classifier.joblib"
IF_MODEL = MODELS_DIR / "isolation_forest.joblib"
XGB_MODEL = MODELS_DIR / "xgboost_deterioration.joblib"

CLASS_LABELS = ["Safe", "Unsafe"]

LIMITATIONS = [
    "The Safe/Unsafe label is the benchmark dataset's labeling rule; it is not "
    "laboratory confirmation, potability, or a guarantee of safety.",
    "Random Forest metrics come from a stratified held-out test split of a static "
    "benchmark dataset, not from these live sensors; real-world performance depends "
    "on how closely future data matches that distribution.",
    "Isolation Forest has no ground-truth contamination labels; its anomaly rate is "
    "descriptive only. An anomaly is an unusual sensor pattern, not confirmed pollution.",
    "XGBoost deterioration prediction is offline-only: it requires USGS-specific "
    "lag/rolling and conductivity-derived features that live telemetry does not provide.",
    "Simulator telemetry is for pipeline testing only and is never treated as "
    "scientific ground truth.",
    "ESP32 turbidity is a provisional relative index 0-100, not NTU; relative-index "
    "readings are deliberately excluded from ML inference.",
]


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _model_metadata(path: Path, kind: str) -> dict[str, Any] | None:
    """Small, non-sensitive metadata read from the saved artifact."""
    if not path.exists():
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = joblib.load(path)
    meta: dict[str, Any] = {
        "file": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "estimator": type(model).__name__,
        "sklearn_version": sklearn.__version__,
        "n_features_in": int(getattr(model, "n_features_in_", 0)),
    }
    if kind == "random_forest":
        meta.update({
            "n_estimators": int(getattr(model, "n_estimators", 0)),
            "max_depth": getattr(model, "max_depth", None),
            "class_weight": getattr(model, "class_weight", None),
            "classes": [str(c) for c in getattr(model, "classes_", [])],
        })
    elif kind == "isolation_forest":
        meta.update({
            "n_estimators": int(getattr(model, "n_estimators", 0)),
            "contamination": getattr(model, "contamination", None),
            "max_samples": getattr(model, "max_samples", None),
        })
    elif kind == "xgboost":
        meta.update({
            "n_estimators": int(getattr(model, "n_estimators", 0)),
            "max_depth": getattr(model, "max_depth", None),
            "learning_rate": getattr(model, "learning_rate", None),
        })
    return meta


def _classification_metrics(
    y_true: pd.Series, y_pred: pd.Series, y_score: pd.Series | None
) -> dict[str, Any]:
    labels_present = [label for label in CLASS_LABELS if label in set(y_true) | set(y_pred)]
    cm = confusion_matrix(y_true, y_pred, labels=CLASS_LABELS)
    metrics: dict[str, Any] = {
        "n_samples": int(len(y_true)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "precision_macro": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1_weighted": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        "confusion_matrix": {
            "labels": CLASS_LABELS,
            "matrix": [[int(v) for v in row] for row in cm],
            "row_semantics": "true class (rows) vs predicted class (columns)",
        },
        "per_class": {
            label: {
                "precision": float(precision_score(y_true, y_pred, labels=[label], average="macro", zero_division=0)),
                "recall": float(recall_score(y_true, y_pred, labels=[label], average="macro", zero_division=0)),
                "f1": float(f1_score(y_true, y_pred, labels=[label], average="macro", zero_division=0)),
                "support": int((y_true == label).sum()),
            }
            for label in labels_present
        },
    }
    if y_score is not None:
        binary_true = (y_true == "Unsafe").astype(int)
        metrics["roc_auc_unsafe"] = float(roc_auc_score(binary_true, y_score))
    return metrics


def build_random_forest_section() -> dict[str, Any]:
    if not RF_PREDICTIONS.exists() or not SUPERVISED_TEST.exists():
        return {
            "available": False,
            "reason": "Prediction/test CSVs are missing. Run the Phase 5C-2 evaluation first.",
            "command": "python ml/scripts/evaluate_random_forest.py",
        }

    preds = pd.read_csv(RF_PREDICTIONS)
    test = pd.read_csv(SUPERVISED_TEST)
    required = {"actual_label", "predicted_label", "probability_unsafe"}
    if not required.issubset(preds.columns):
        raise ValueError(f"{RF_PREDICTIONS} is missing {sorted(required - set(preds.columns))}")
    if len(preds) != len(test) or "label" not in test.columns:
        raise ValueError("random_forest_predictions.csv does not align with supervised_test.csv")

    y_true = preds["actual_label"].astype(str)
    y_pred = preds["predicted_label"].astype(str)
    y_score = preds["probability_unsafe"].astype(float)

    # Alignment check: the prediction rows must be the same test rows, not a
    # shuffled or substituted split.
    feature_cols = [c for c in ["pH", "tds", "turbidity", "temperature"] if c in preds.columns and c in test.columns]
    aligned = all(np.allclose(preds[c], test[c]) for c in feature_cols)
    if not aligned:
        raise ValueError("Prediction rows do not match supervised_test.csv features")

    return {
        "available": True,
        "task": "Binary water-quality classification (Safe/Unsafe)",
        "live_inference": True,
        "model": _model_metadata(RF_MODEL, "random_forest"),
        "dataset": {
            "name": "water_quality_dataset1",
            "source_file": "ml/data/external/water_quality_dataset1.csv",
            "split_file": SUPERVISED_TEST.name,
            "split": "held-out stratified test split (15%, random_state=42)",
            "n_test_samples": int(len(y_true)),
            "class_distribution": {label: int((y_true == label).sum()) for label in CLASS_LABELS},
            "features": feature_cols,
            "target": "Safe/Unsafe label from the benchmark dataset",
            "provenance_note": (
                "Static benchmark dataset of physicochemical parameters; label semantics "
                "follow the source dataset and are not universal potability."
            ),
        },
        "metrics": _classification_metrics(y_true, y_pred, y_score),
    }


def build_isolation_forest_section() -> dict[str, Any]:
    if not ANOMALY_RESULTS.exists():
        return {
            "available": False,
            "reason": "anomaly_results.csv is missing. Run the Phase 5B inference step first.",
            "command": "python ml/scripts/detect_anomalies.py",
        }
    df = pd.read_csv(ANOMALY_RESULTS)
    scores = pd.to_numeric(df["anomaly_score"], errors="coerce").dropna()
    labels = pd.to_numeric(df.get("anomaly_label"), errors="coerce").dropna()
    return {
        "available": True,
        "task": "Unsupervised anomaly screening",
        "live_inference": True,
        "model": _model_metadata(IF_MODEL, "isolation_forest"),
        "dataset": {
            "name": "station telemetry (Phase 5B clean sensor readings)",
            "split_file": ANOMALY_RESULTS.name,
            "n_scored_readings": int(len(df)),
            "note": (
                "Unsupervised: there are no ground-truth contamination labels, so "
                "accuracy/precision/recall are intentionally not reported."
            ),
        },
        "summary": {
            "anomalies_flagged": int(labels.sum()) if len(labels) else None,
            "anomaly_rate": float(labels.mean()) if len(labels) else None,
            "score_min": float(scores.min()) if len(scores) else None,
            "score_max": float(scores.max()) if len(scores) else None,
            "score_mean": float(scores.mean()) if len(scores) else None,
        },
    }


def build_xgboost_section() -> dict[str, Any]:
    if not XGBOOST_PREDICTIONS.exists():
        return {
            "available": False,
            "reason": "xgboost_predictions.csv is missing. Run evaluate_xgboost.py first.",
            "command": "python ml/scripts/evaluate_xgboost.py",
        }
    df = pd.read_csv(XGBOOST_PREDICTIONS)
    y_true = pd.to_numeric(df["actual_deterioration"], errors="coerce")
    y_pred = pd.to_numeric(df["predicted_deterioration"], errors="coerce")
    mask = y_true.notna() & y_pred.notna()
    y_true = y_true[mask].astype(int)
    y_pred = y_pred[mask].astype(int)
    score = pd.to_numeric(df.loc[mask, "prediction_probability"], errors="coerce")

    y_true_lbl = y_true.map({1: "Unsafe", 0: "Safe"})
    y_pred_lbl = y_pred.map({1: "Unsafe", 0: "Safe"})
    metrics = _classification_metrics(y_true_lbl, y_pred_lbl, score)
    stations = sorted(df["station"].dropna().astype(str).unique().tolist()) if "station" in df else []
    return {
        "available": True,
        "task": "Rule-based future-deterioration prediction",
        "live_inference": False,
        "live_note": (
            "Offline analysis only: requires USGS lag/rolling and conductivity-derived "
            "features that live telemetry does not provide."
        ),
        "model": _model_metadata(XGB_MODEL, "xgboost"),
        "dataset": {
            "name": "USGS time series",
            "stations": stations,
            "split_file": XGBOOST_PREDICTIONS.name,
            "n_test_samples": int(len(y_true)),
            "target": "rule-based deterioration indicator over the next observation",
            "provenance_note": (
                "Single USGS station, ~5 weeks of synchronized 5-minute observations; "
                "temporal generalization is limited."
            ),
        },
        "metrics": metrics,
    }


def build_report() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "ml/scripts/build_evaluation_report.py",
        "environment": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "honesty_policy": (
            "Every metric in this report is computed from saved repository artifacts; "
            "none are hardcoded. Models are not laboratory instruments and their outputs "
            "are estimates, not confirmed water safety."
        ),
        "random_forest": build_random_forest_section(),
        "isolation_forest": build_isolation_forest_section(),
        "xgboost": build_xgboost_section(),
        "limitations": LIMITATIONS,
    }


def render_markdown(report: dict[str, Any]) -> str:
    rf = report["random_forest"]
    iso = report["isolation_forest"]
    xgb = report["xgboost"]

    lines = [
        "# HydraSense ML Evaluation Report",
        "",
        f"Generated: `{report['generated_at']}` by `{report['generator']}`.",
        "",
        "> Every metric below was computed from the saved prediction outputs and model "
        "artifacts in this repository. Nothing is hand-written or hardcoded. "
        "These are model estimates, not laboratory measurements.",
        "",
        "## Random Forest — Safe/Unsafe classification (live inference)",
        "",
    ]
    if rf.get("available"):
        m = rf["metrics"]
        lines += [
            f"- Test samples: **{m['n_samples']:,}** "
            f"({rf['dataset']['split']})",
            f"- Accuracy: **{m['accuracy']:.4f}** | Balanced accuracy: **{m['balanced_accuracy']:.4f}**",
            f"- Macro precision / recall / F1: **{m['precision_macro']:.4f} / "
            f"{m['recall_macro']:.4f} / {m['f1_macro']:.4f}**",
            f"- Weighted F1: **{m['f1_weighted']:.4f}**",
            f"- ROC-AUC (Unsafe): **{m['roc_auc_unsafe']:.4f}**",
            "",
            "| Class | Precision | Recall | F1 | Support |",
            "|---|---|---|---|---|",
        ]
        for label, p in m["per_class"].items():
            lines.append(
                f"| {label} | {p['precision']:.4f} | {p['recall']:.4f} | {p['f1']:.4f} | {p['support']:,} |"
            )
        cm = m["confusion_matrix"]
        lines += [
            "",
            f"Confusion matrix (rows = true, columns = {cm['labels']}):",
            "",
            f"```\n{cm['matrix']}\n```",
            "",
            f"Features: `{', '.join(rf['dataset']['features'])}`",
            "",
        ]
    else:
        lines += [f"_Unavailable_: {rf.get('reason')}", ""]

    lines += ["## Isolation Forest — anomaly screening (live inference)", ""]
    if iso.get("available"):
        s = iso["summary"]
        lines += [
            f"- Readings scored: **{iso['dataset']['n_scored_readings']:,}**",
            f"- Flagged anomalies: **{s['anomalies_flagged']}** "
            f"(rate = {s['anomaly_rate']:.4f})" if s["anomaly_rate"] is not None else "- No labels available",
            f"- Anomaly score range: **{s['score_min']:.4f} … {s['score_max']:.4f}** "
            f"(mean {s['score_mean']:.4f})" if s["score_min"] is not None else "",
            "",
            "Precision/recall/accuracy are **not reported**: no ground-truth contamination "
            "labels exist. An anomaly is an unusual sensor pattern, not confirmed pollution.",
            "",
        ]
    else:
        lines += [f"_Unavailable_: {iso.get('reason')}", ""]

    lines += ["## XGBoost — deterioration prediction (offline only)", ""]
    if xgb.get("available"):
        m = xgb["metrics"]
        lines += [
            f"- Test samples: **{m['n_samples']:,}** | stations: {', '.join(xgb['dataset']['stations'])}",
            f"- Accuracy: **{m['accuracy']:.4f}** | Balanced accuracy: **{m['balanced_accuracy']:.4f}**",
            f"- Macro F1: **{m['f1_macro']:.4f}** | ROC-AUC (Unsafe): **{m['roc_auc_unsafe']:.4f}**",
            "",
            xgb["live_note"],
            "",
        ]
    else:
        lines += [f"_Unavailable_: {xgb.get('reason')}", ""]

    lines += ["## Limitations", ""]
    lines += [f"- {item}" for item in report["limitations"]]
    lines += [""]
    return "\n".join(lines)


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report()

    json_path = REPORTS_DIR / "evaluation_report.json"
    md_path = REPORTS_DIR / "evaluation_report.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    rf = report["random_forest"]
    print(f"Wrote {json_path.relative_to(PROJECT_ROOT)}")
    print(f"Wrote {md_path.relative_to(PROJECT_ROOT)}")
    if rf.get("available"):
        print(
            "Random Forest test: "
            f"n={rf['metrics']['n_samples']}, acc={rf['metrics']['accuracy']:.4f}, "
            f"macro_f1={rf['metrics']['f1_macro']:.4f}, "
            f"roc_auc={rf['metrics']['roc_auc_unsafe']:.4f}"
        )
    else:
        print(f"Random Forest evaluation unavailable: {rf.get('reason')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
