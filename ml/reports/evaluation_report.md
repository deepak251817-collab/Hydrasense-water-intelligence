# HydraSense ML Evaluation Report

Generated: `2026-10-31T05:29:41.983670+00:00` by `ml/scripts/build_evaluation_report.py`.

> Every metric below was computed from the saved prediction outputs and model artifacts in this repository. Nothing is hand-written or hardcoded. These are model estimates, not laboratory measurements.

## Random Forest — Safe/Unsafe classification (live inference)

- Test samples: **15,120** (held-out stratified test split (15%, random_state=42))
- Accuracy: **0.9999** | Balanced accuracy: **0.9998**
- Macro precision / recall / F1: **0.9998 / 0.9998 / 0.9998**
- Weighted F1: **0.9999**
- ROC-AUC (Unsafe): **1.0000**

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| Safe | 0.9998 | 0.9998 | 0.9998 | 4,536 |
| Unsafe | 0.9999 | 0.9999 | 0.9999 | 10,584 |

Confusion matrix (rows = true, columns = ['Safe', 'Unsafe']):

```
[[4535, 1], [1, 10583]]
```

Features: `pH, tds, turbidity, temperature`

## Isolation Forest — anomaly screening (live inference)

- Readings scored: **15,120**
- Flagged anomalies: **727** (rate = 0.0481)
- Anomaly score range: **-0.1002 … 0.1582** (mean 0.0860)

Precision/recall/accuracy are **not reported**: no ground-truth contamination labels exist. An anomaly is an unusual sensor pattern, not confirmed pollution.

## XGBoost — deterioration prediction (offline only)

- Test samples: **1,139** | stations: USGS-01649190
- Accuracy: **0.9438** | Balanced accuracy: **0.5376**
- Macro F1: **0.5284** | ROC-AUC (Unsafe): **0.6288**

Offline analysis only: requires USGS lag/rolling and conductivity-derived features that live telemetry does not provide.

## Limitations

- The Safe/Unsafe label is the benchmark dataset's labeling rule; it is not laboratory confirmation, potability, or a guarantee of safety.
- Random Forest metrics come from a stratified held-out test split of a static benchmark dataset, not from these live sensors; real-world performance depends on how closely future data matches that distribution.
- Isolation Forest has no ground-truth contamination labels; its anomaly rate is descriptive only. An anomaly is an unusual sensor pattern, not confirmed pollution.
- XGBoost deterioration prediction is offline-only: it requires USGS-specific lag/rolling and conductivity-derived features that live telemetry does not provide.
- Simulator telemetry is for pipeline testing only and is never treated as scientific ground truth.
- ESP32 turbidity is a provisional relative index 0-100, not NTU; relative-index readings are deliberately excluded from ML inference.
