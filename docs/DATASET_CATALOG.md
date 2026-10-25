# HydraSense — Dataset Catalog

> **Rule for this document:** every row count, column list, range and label count below was
> produced by loading the file in this checkout (pandas 2.2.2). Anything that could not be verified
> is labelled **UNVERIFIED** or **INFERRED**. Nothing here is copied from a vendor page or invented.

Inventory date: 2026-10-24. Datasets found by scanning `ml/data/**` for CSV files: **6 source files
+ 21 derived CSVs + 6 cleaned copies** (27 derived tables, plus six PNG plots).

---

## 1. Inventory at a glance

| # | File | Rows | Cols | Size | Role | Provenance |
|---|---|---|---|---|---|---|
| 1 | `ml/data/external/usgs_ph_2024.csv` | 10,000 | 12 | 1.79 MB | USGS pH series | USGS NWIS continuous record, station `USGS-01649190` |
| 2 | `ml/data/external/usgs_turbidity_2024.csv` | 10,000 | 12 | 1.78 MB | USGS turbidity series | same station, **all rows Provisional** |
| 3 | `ml/data/external/usgs_temperature_2024.csv` | 10,000 | 12 | 1.75 MB | USGS water temperature | same station |
| 4 | `ml/data/external/usgs_conductance_2024.csv` | 10,000 | 12 | 1.76 MB | USGS specific conductance | same station |
| 5 | `ml/data/external/water_quality_dataset1.csv` | 100,800 | 5 | 2.96 MB | Safe/Unsafe benchmark | **UNVERIFIED** — no source metadata in repo |
| 6 | `ml/data/raw/sensor_readings.csv` | 9 | 7 | 782 B | PostgreSQL telemetry export | Own simulator/demo data (2026-08-31) |

Totals: **140,809 source rows**, 9.6 MB on disk.

---

## 2. USGS time-series files (4 files)

All four share one schema — the USGS `waterdata` continuous-values export (long format):

| Column | Type | Meaning | Observed |
|---|---|---|---|
| `x` | float | longitude | −76.964 (constant) |
| `y` | float | latitude | 39.033 (constant) |
| `time_series_id` | string | USGS series UUID | one per file |
| `monitoring_location_id` | string | station id | `USGS-01649190` only |
| `parameter_code` | int | USGS parameter code | 400 / 63680 / 10 / 95 |
| `statistic_id` | int | 11 = instantaneous value | constant 11 |
| `time` | string | ISO-8601 timestamp with `+00:00` | 5-minute cadence |
| `value` | numeric | measured value | see below |
| `unit_of_measure` | string | unit | per file |
| `approval_status` | string | `Approved` / `Provisional` | see below |
| `qualifier` | float | data qualifier | **100 % empty in all four files** |
| `last_modified` | string | USGS revision timestamp | Aug 2025 |

### 2.1 Per-file verified statistics

| Parameter | Code | Unit | Value range | Mean | `approval_status` | Time span |
|---|---|---|---|---|---|---|
| pH | 400 | `pH Units` | **7.2 – 7.7** | 7.490 | Approved (10,000) | 2024-01-01 00:00 → 2024-02-04 19:55 UTC |
| Turbidity | 63680 | `_FNU` | **0.6 – 591.0** | 7.803 | **Provisional (10,000)** | 2024-01-01 00:00 → 2024-02-13 05:10 UTC |
| Temperature | 10 | `degC` | **−0.2 – 10.5** | 4.349 | Approved (10,000) | 2024-01-01 00:00 → 2024-02-04 19:55 UTC |
| Specific conductance | 95 | `uS/cm` | **28 – 4,440** | 948.028 | Approved (10,000) | 2024-01-01 00:00 → 2024-02-05 15:00 UTC |

Other verified properties:

- One monitoring location in every file (`USGS-01649190`), ~39.03 °N / 76.96 °W — **INFERRED** to be
  in Maryland, USA, from the coordinates.
- 5-minute sampling interval (confirmed by consecutive timestamps and by
  `prepare_usgs_forecast_dataset.py`).
- **No duplicate `(time_series_id, time)` rows** in any file.
- The filename says "2024" but each file is a **10,000-row export cap**, not a full year — the data
  covers roughly five to six weeks. Do not call it "a year of USGS data".
- Turbidity is `_FNU` (formazin nephelometric units), which is **not** the same calibration as the
  ESP32's relative index and is never substituted for it.
- `specific_conductance` is **not TDS**. The forecasting pipeline keeps it under its own name and
  never converts it to TDS (documented in `prepare_usgs_forecast_dataset.py`).

### 2.2 Provenance status

| Claim | Evidence | Status |
|---|---|---|
| Data is USGS monitoring data | USGS column schema, parameter codes, `USGS-` station id, `last_modified` timestamps | **Verified by structure** |
| Downloaded from the USGS Water Data API | No download script, no URL, no query parameters stored in the repo | **UNVERIFIED** |
| Station is `USGS-01649190` | `monitoring_location_id` constant across all rows | **Verified** |
| License / terms | Not recorded in the repo | **UNVERIFIED** — USGS data is generally public domain in the US, but the repo does not state it |

**For the presentation:** "Four USGS continuous-monitoring series from a single station
(`USGS-01649190`), covering January–February 2024 at 5-minute resolution, capped at 10,000 rows per
parameter. Turbidity rows are provisional USGS values."

---

## 3. `water_quality_dataset1.csv` — the Safe/Unsafe benchmark

| Property | Value |
|---|---|
| Path | `ml/data/external/water_quality_dataset1.csv` |
| Rows × cols | **100,800 × 5** |
| Size | 2,964,409 bytes |
| Columns | `pH`, `TDS_ppm`, `Turbidity_NTU`, `Temperature_C`, `Label` |
| Missing values | **0 in every column** |
| Exact duplicate rows | **0** |
| Labels | `Safe` **30,240** (30.0 %), `Unsafe` **70,560** (70.0 %) |

Verified feature ranges:

| Feature | Min | 25 % | Median | 75 % | Max | Mean | Std |
|---|---|---|---|---|---|---|---|
| `pH` | 6.09 | 7.01 | 7.38 | 8.10 | 9.96 | 7.594 | 0.799 |
| `TDS_ppm` | 28.6 | 163.0 | 472.85 | 1,023.33 | 2,806.1 | 692.65 | 647.33 |
| `Turbidity_NTU` | 0.00 | 1.92 | 9.97 | 18.54 | 72.75 | 11.31 | 9.87 |
| `Temperature_C` | 16.56 | 23.09 | 25.04 | 26.93 | 31.51 | 24.88 | 2.69 |

### 3.1 What the label actually is

The label is **not** a laboratory potability result. Two observations from the data itself:

1. The feature ranges are bounded and synthetic-looking (pH never leaves 6.09–9.96, turbidity never
   exceeds 72.75, TDS never exceeds 2,806) — consistent with a generated/gridded dataset rather
   than field sampling.
2. The Random Forest reproduces the label with **2 errors in 15,120 test rows** (accuracy
   0.999868). A model cannot learn real-world potability that precisely from four numbers; it can
   trivially learn a deterministic rule. The label is therefore a **rule over these four
   features** — almost certainly thresholds on pH/TDS/turbidity.

**Consequence:** report accuracy as "agreement with the source dataset's label rule", never as
"water-safety accuracy".

### 3.2 Provenance status

| Question | Answer |
|---|---|
| Where did this file come from? | **UNVERIFIED.** No URL, citation, license or README entry exists. |
| Is it real field data? | **UNVERIFIED / likely synthetic** (see range analysis). |
| What rule defines `Safe`? | **UNVERIFIED.** The repo never states it; the model infers it. |
| Can it be published as a cited dataset? | Only after the real source is recorded. Add a `ml/data/external/SOURCES.md` before submission. |

The column names (`TDS_ppm`, `Turbidity_NTU`) are the only naming convention in the repo that
looks like a public Kaggle-style water-quality table, but that is a **guess**, not evidence.

---

## 4. `ml/data/raw/sensor_readings.csv` — telemetry export

| Property | Value |
|---|---|
| Rows × cols | **9 × 7** |
| Columns | `station_code`, `device_id`, `timestamp`, `ph`, `turbidity`, `tds`, `temperature` |
| Stations | `ARK-001`, `ARK-002`, `ARK-003` |
| Devices | `STATION-ARK-001`, `STATION-ARK-002`, `STATION-ARK-003` |
| Timestamp span | 2026-08-31 18:30:48.888 → 18:30:53.977 UTC (**5.1 seconds**) |
| Missing values | 0 |

The nine rows are three snapshots of three stations:

| Snapshot | pH | Turbidity | TDS | Temperature | Interpretation |
|---|---|---|---|---|---|
| 1 | 7.03 / 7.13 / 7.33 | 3.58 / 4.48 / 3.13 | 211.6 / 210.7 / 230.8 | 28.0 / 25.9 / 26.8 | normal conditions |
| 2 | 7.10 / 7.15 / 6.97 | 11.09 / 12.51 / 14.91 | 308.8 / 313.7 / 335.5 | 27.1 / 26.7 / 27.5 | mildly elevated |
| 3 | 5.32 / 5.42 / 5.28 | 83.49 / 88.13 / 83.11 | 1,133.5 / 1,112.6 / 1,171.4 | 29.6 / 28.7 / 29.8 | sudden-event scenario |

**Honest reading:** this is a **demo export from the simulator**, not field data. It is the entire
training corpus of the shipped Isolation Forest (6 of the 9 rows are its chronological train split).
Any statement about the Isolation Forest's real-world sensitivity is therefore unsupported.

---

## 5. Derived datasets (all under `ml/data/processed/`)

| File | Rows | Cols | Produced by | Used by |
|---|---|---|---|---|
| `clean_sensor_readings.csv` | 9 | 7 | `preprocessing/clean_data.py` | splits |
| `train.csv` | 6 | 13 | `scripts/create_splits.py` | Isolation Forest training |
| `validation.csv` | **0** | 13 | `create_splits.py` | — (empty: 15 % of 9 rows) |
| `test.csv` | 3 | 13 | `create_splits.py` | IF evaluation |
| `anomaly_results.csv` | 9 | 9 | `detect_anomalies.py` | IF summary (4 flagged, 44.4 %) |
| `supervised_train.csv` | 70,560 | 5 | `prepare_supervised_splits.py` | Random Forest training |
| `supervised_validation.csv` | 15,120 | 5 | same | validation |
| `supervised_test.csv` | 15,120 | 5 | same | reported test metrics |
| `random_forest_predictions.csv` | 15,120 rows | — | `predict_water_quality.py` | evaluation report |
| `random_forest_feature_importance.csv` | 4 | 2 | `train_random_forest.py` | plots / docs |
| `usgs_timeseries_combined.csv` | **7,601** | 6 | `prepare_usgs_forecast_dataset.py` (INNER join of the 4 series) | forecasting |
| `forecast_train.csv` | 5,321 | **39** | same | XGBoost training |
| `forecast_validation.csv` | 1,140 | 39 | same | validation |
| `forecast_test.csv` | 1,139 | 39 | same | reported test metrics |
| `xgboost_predictions.csv` | 1,139 | — | `predict_deterioration.py` | evaluation report |
| `xgboost_error_analysis.csv` | — | — | `evaluate_xgboost.py` | error inspection |
| `shap_random_forest_summary.csv` | 4 | — | `explain_random_forest.py` | explainability |
| `shap_random_forest_local.csv` | — | — | same | per-row explanations |
| `shap_xgboost_summary.csv` | 36 | — | `explain_xgboost.py` | explainability |
| `shap_xgboost_local.csv` | — | — | same | per-row explanations |
| `cleaned/cleaned_*.csv` | 6 files | — | `preprocessing/clean_datasets.py` (this audit) | review / re-use |

Forecast feature set (39 columns = 4 identifiers/targets + 36 features, matching
`n_features_in_=36` in the model):

- current values: `pH`, `turbidity`, `temperature`, `specific_conductance`
- lags 1–3 for each of the four
- rolling mean/std over 3 and 6 **strictly past** observations
- one-step change for each parameter
- target `deterioration_target` (rule-based, next observation; train positive rate **9.04 %**)

Images: `confusion_matrix.png`, `feature_importance.png`, `xgboost_confusion_matrix.png`,
`xgboost_feature_importance.png`, `shap_random_forest_summary.png`, `shap_xgboost_summary.png`.

---

## 6. Models trained from these datasets

| Artifact | Trained on | Rows used | Reported test performance |
|---|---|---|---|
| `isolation_forest.joblib` | `train.csv` | 6 | 4 of 9 readings flagged (descriptive only) |
| `random_forest_classifier.joblib` | `supervised_train.csv` | 70,560 | accuracy 0.999868, macro F1 0.999843 |
| `xgboost_deterioration.joblib` | `forecast_train.csv` | 5,321 | accuracy 0.9438, **balanced accuracy 0.5376** |

Full metrics, confusion matrices and limitations: `ml/reports/evaluation_report.{json,md}`.

---

## 7. Gaps to close before submission

| Gap | Why it matters | Suggested action |
|---|---|---|
| No provenance record for `water_quality_dataset1.csv` | An examiner will ask where the 100,800 rows came from; "I don't know" is the weakest possible answer | Add `ml/data/external/SOURCES.md` with URL, publisher, access date, license, and how the file was obtained |
| No download script for the USGS files | The pipeline cannot be reproduced from scratch | Add `ml/scripts/fetch_usgs.py` documenting the exact query (station, parameter codes, period), even if it is not re-run |
| Filenames imply a full year | `*_2024.csv` holds ~5 weeks | Rename to `usgs_<param>_20240101_20240213.csv` or document the cap in the README |
| Benchmark is 70 % Unsafe | Class imbalance shapes every metric | Already handled with stratified splits and macro metrics — keep doing that |
| Telemetry training set is 9 rows | Isolation Forest cannot be defended as trained | State it as a pipeline demonstration; collect real readings or use the USGS series for anomaly training |
| Provisional turbidity | 100 % of USGS turbidity rows are Provisional | Say "provisional" whenever those numbers are shown |
| Specific conductance vs TDS | Conflating them is a chemistry error | Already avoided in code; keep it that way in slides |
