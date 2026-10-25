# Turbidity Index ML — Data Requirements & Reproducible Training Workflow

> **Status: no index-trained model exists yet.** This document specifies the
> data requirements and a reproducible training/evaluation workflow for a
> future model that accepts relative turbidity **index** inputs (0–100).
> Until such a model is trained and evaluated, the API reports
> **"ML prediction unavailable for Turbidity Index readings."** for every
> relative-index reading (`backend/app/services/ml_availability.py`), and the
> NTU-trained Phase 6 models never receive an index value.

## 1. Why the exclusion exists

The shipped Isolation Forest and Random Forest were trained with **NTU-style
turbidity** features (`ml/scripts/train_isolation_forest.py`,
`ml/scripts/train_random_forest.py`, contract in `ml_service.py`). A relative
0–100 index produced by the analog sensor is a *different quantity*:

- it is uncalibrated against any optical standard,
- its direction and bands are project/firmware conventions
  (0–100, higher = cloudier; CLEARER < 30, MODERATE 30–54, CLOUDIER ≥ 55),
- there is **no validated conversion** from index to NTU.

Passing it to an NTU-trained model would silently corrupt the feature
distribution and produce an unevaluable — and unclaimable — prediction.

## 2. Data requirements for an index-compatible model

A future training dataset must contain, at minimum:

| Requirement | Detail |
|---|---|
| **Paired measurements** | Each row: `turbidity_index` (0–100) **and** the target label/quantity it will predict, measured at the same time from the same water. |
| **Labels from a reference method** | Classification targets must come from laboratory or calibrated-instrument results (e.g. NTU from a calibrated turbidimeter, or a lab water-quality class) — never from the index bands themselves (that would only learn the demo bands back). |
| **Range coverage** | Samples spread across the full 0–100 index range and across water conditions (clear, moderate, cloudy), not just one operating point. |
| **Multiple conditions** | Different stations/rivers, seasons, day/night, and sensor warm-up states, so the model is not learning one site or one day. |
| **Scale** | Hundreds of labelled rows minimum for a linear/tree baseline; thousands before claiming any generalisation. (Compare: the telemetry split usable today is 9 rows — see `docs/FEATURE_STATUS.md` §5.) |
| **Provenance columns** | `timestamp`, `station_code`, `source` (`esp32` only — simulated rows must be excluded from ground truth), sensor calibration status, firmware index-mapping version. |
| **Train/val/test split** | Chronological (time-aware) split with global timestamp boundaries, matching `ml/scripts/prepare_supervised_splits.py` conventions — no random shuffle across time. |
| **Held-out final test** | An untouched test period never seen during tuning; all reported metrics come from it. |

## 3. Reproducible training & evaluation workflow

All commands run from the repository root with the `ml/` environment
(`ml/requirements.txt`). Follow the existing pipeline's conventions.

1. **Assemble the labelled dataset** into
   `ml/data/raw/index_model_dataset.csv` with the columns from §2. Keep the
   source file unmodified; document its provenance (source URL/collection
   date, license) — a known gap for the existing benchmark table
   (`docs/FEATURE_STATUS.md` §5).

   ```bash
   # No dataset exists yet — this step produces nothing until real
   # paired index+reference measurements are collected.
   ls ml/data/raw/index_model_dataset.csv
   ```

2. **Prepare reproducible splits**, mirroring the existing supervised pipeline:

   ```bash
   python ml/scripts/prepare_supervised_splits.py \
     --input ml/data/raw/index_model_dataset.csv \
     --output-dir ml/data/processed \
     --random-state 42
   ```

   The script performs the project's stratified 70/15/15 split (seed 42) and
   prints the resulting row counts. If the prediction target is time-dependent,
   add a chronological-split variant (global timestamp boundaries, `max(train) <
   min(val) < min(test)`) following `ml/scripts/prepare_usgs_forecast_dataset.py` —
   record the split boundaries in the run log either way.

3. **Train a candidate model** with an index-specific feature list (the
   `turbidity_index` column, plus whatever *measured* features are justified).
   Reuse the artefact conventions of `train_random_forest.py`: deterministic
   seed, `joblib` dump to `ml/models/<name>.joblib`, JSON metrics to
   `ml/reports/`.

4. **Evaluate against naive baselines on the held-out test period** and report
   honest metrics:
   - classification: accuracy, macro-F1, per-class recall **and** the majority
     class baseline,
   - regression: MAE/RMSE **and** a persistence/mean baseline — the model only
     earns deployment if it beats the baseline, the same gate used by
     `backend/app/services/forecasting.py`.

5. **Wire-up only after the evaluation passes** (checklist):
   - [ ] artefact loads in `ml_service.py` without changing the NTU feature
     contract of the existing models,
   - [ ] inference path branches on `turbidity_unit == "relative_index_0_100"`
     and never routes index rows to the NTU models,
   - [ ] `backend/app/services/ml_availability.py` updated so index rows report
     the model's real result (keeping the honest "unavailable" message only
     when the artefact is absent),
   - [ ] backend tests updated: `tests/test_ml_availability.py` currently pins
     the exclusion behaviour and must be switched deliberately, not by
     accident,
   - [ ] evaluation report regenerated with `ml/scripts/build_evaluation_report.py`
     so `/api/authority/ml/status` publishes the new metrics.

## 4. What is explicitly NOT acceptable

- Converting index → NTU with an invented formula and feeding it to the NTU
  models.
- Training on simulated rows (`source = "simulator"`) and reporting the result
  as real-world accuracy.
- Reporting accuracy without a baseline comparison or without the held-out
  time period.
- Showing a prediction, confidence or SHAP value for an index reading before
  every item in §3's checklist passes.
