# HydraSense — Data Cleaning Report

> **What was executed.** `python ml/preprocessing/clean_datasets.py` was written and run in this
> checkout on 2026-10-24. It produced cleaned **copies** in `ml/data/processed/cleaned/` and two
> reports: `ml/reports/dataset_cleaning_report.json` (machine-readable) and
> `ml/reports/dataset_cleaning_report.md` (the generated summary). Every number below comes from
> that run — none is estimated.
>
> **Headline result:** 6 datasets, **140,809 rows in → 140,809 rows out, 0 rows removed**, all
> verification checks passed, and every source file's SHA-256 was identical before and after.

---

## 1. Safety guarantees (enforced by the script, not by convention)

| Guarantee | How it is enforced |
|---|---|
| Source files are never modified | Files are opened read-only; SHA-256 is taken before and after; the run raises `RuntimeError` if the hash changes |
| Existing processed artifacts are never overwritten | Outputs go to a new directory, `ml/data/processed/cleaned/`, with a `cleaned_` prefix |
| No data is silently invented | Cleaning only removes rows, normalizes timestamps, renames columns, or drops columns that are **entirely NULL**. No imputation, scaling, clipping, smoothing or unit conversion |
| Counts reconcile | For each dataset, `input_rows − sum(rows removed per step) == output_rows`; a mismatch aborts the run |
| No fabricated rows | The output is verified to be a **row-subset of the input** on each dataset's key columns |
| Failing checks stop the run | Exit code 2 when any check fails; the run is not allowed to silently report success |

Two bugs were found and fixed **during** this work, and they are reported here rather than hidden:

1. First run crashed on the benchmark table because the rename map produced `pH` while the range
   table used `ph`. Fixed by using the canonical names and a separate telemetry range map.
2. First run failed the subset check for telemetry because the cleaner rewrites timestamps to
   second-precision UTC (`2026-08-31T18:30:48Z`). Fixed by comparing against the same normalization
   of the input instead of the raw string.

---

## 2. What was applied to each dataset

### 2.1 USGS long-format series (4 files)

| Step | Rows before | Rows after | Removed |
|---|---|---|---|
| Parse `time` to UTC datetime; drop unparseable | 10,000 | 10,000 | 0 |
| Coerce `value` to numeric; drop non-numeric | 10,000 | 10,000 | 0 |
| Drop columns that are 100 % NULL (`qualifier`) | 10,000 | 10,000 | 0 |
| Remove physically impossible values (per parameter code) | 10,000 | 10,000 | 0 |
| Drop duplicate `(time_series_id, time)` rows | 10,000 | 10,000 | 0 |
| Sort chronologically | 10,000 | 10,000 | 0 |
| Select canonical columns (12 → 6) | 10,000 | 10,000 | 0 |

Applied bounds (a value outside these cannot come from a working sensor):

| Parameter code | Meaning | Accepted range |
|---|---|---|
| 10 | water temperature | −5 … 50 °C |
| 95 | specific conductance | 0 … 200,000 µS/cm |
| 400 | pH | 0 … 14 |
| 63680 | turbidity | 0 … 100,000 FNU |

Columns **dropped**: `x`, `y`, `time_series_id`, `statistic_id`, `qualifier`, `last_modified`.
Rationale: the first two are constant station coordinates; `time_series_id` and `statistic_id` are
constant per file; `qualifier` is empty in all 10,000 rows of all four files; `last_modified` is
USGS revision metadata with no modelling value. They remain in the untouched source files.

Columns **kept**: `monitoring_location_id`, `parameter_code`, `time`, `value`, `unit_of_measure`,
`approval_status`.

Verified checks per file: no NULLs in key/value columns, timestamps non-decreasing, exactly one
unit, and a documented physical range for the parameter code.

### 2.2 `water_quality_dataset1.csv` (benchmark)

| Step | Rows before | Rows after | Removed |
|---|---|---|---|
| Rename to canonical names (`pH`, `tds`, `turbidity`, `temperature`, `label`) | 100,800 | 100,800 | 0 |
| Coerce features numeric; drop NULL rows | 100,800 | 100,800 | 0 |
| Remove physically impossible feature values | 100,800 | 100,800 | 0 |
| Keep only known labels (`Safe`, `Unsafe`) | 100,800 | 100,800 | 0 |
| Drop fully duplicated rows | 100,800 | 100,800 | 0 |

Verified checks: zero NULLs remain; label counts stay `Unsafe 70,560 / Safe 30,240`; the output has
exactly the five expected columns in order.

**Unit note:** `TDS_ppm` is renamed to `tds` because that is the modelling contract used by
`prepare_supervised.py`. It is still a TDS concentration in ppm (≈ mg/L), **not** specific
conductance. The USGS conductance series keeps its own name and is never merged into this column.

### 2.3 `sensor_readings.csv` (telemetry export)

Delegated to the existing Phase-5A cleaner `ml/preprocessing/clean_data.py`
(`clean_sensor_data`), which performs: UTC timestamp parsing, station-wise chronological sort,
dedupe on `(station_code, timestamp)`, and physical range validation
(pH 0–14, turbidity ≥ 0, TDS ≥ 0, temperature −10…60 °C).

| Metric | Value |
|---|---|
| Initial rows | 9 |
| Duplicates removed | 0 |
| Invalid rows removed | 0 |
| Final rows | 9 |

Verified checks: no NULL sensor values; all timestamps ISO-8601 UTC; observed ranges pH 5.28–7.33,
TDS 210.7–1,171.4, turbidity 3.13–88.13, temperature 25.9–29.8.

---

## 3. Aggregate result

| Metric | Value |
|---|---|
| Datasets processed | **6** |
| Input rows | **140,809** |
| Output rows | **140,809** |
| Rows removed | **0** |
| Sources unmodified (SHA-256) | **True for all 6** |
| Row-count reconciliation | **True for all 6** |
| Output is a row-subset of input | **True for all 6** |
| Individual checks passed | **all** |

**Interpretation (say this, don't skip it):** the datasets were already tidy — no duplicates, no
missing values, no physically impossible readings. The value of this exercise is therefore not "we
removed N bad rows"; it is:

1. a **reproducible, auditable recipe** now exists for every dataset shape in the repo
   (previously only the telemetry shape had one), and
2. an **independent corruption check**: the cleaned numeric values are provably identical to the
   originals (verified separately by sorting each numeric column and comparing with
   `numpy.allclose`), so downstream splits still describe the same data.

Independent verification performed after the run:

| File pair | Shapes | Numeric values identical |
|---|---|---|
| `usgs_ph_2024.csv` → `cleaned_usgs_ph_2024.csv` | (10000, 12) → (10000, 6) | **True** (`parameter_code`, `value`) |
| `usgs_turbidity_2024.csv` → cleaned | (10000, 12) → (10000, 6) | **True** |
| `water_quality_dataset1.csv` → cleaned | (100800, 5) → (100800, 5) | **True** (`pH`; others renamed) |
| `sensor_readings.csv` → cleaned | (9, 7) → (9, 7) | **True** (all four sensors) |

---

## 4. INVALID vs UNUSUAL — the policy that makes anomaly detection possible

The cleaners remove only **physically impossible** values. They deliberately keep **statistically
unusual but physically plausible** values:

- **Removed (INVALID):** pH 17, a negative turbidity, a temperature of 300 °C, a non-numeric string,
  a missing timestamp, an exact duplicate row.
- **Kept (UNUSUAL):** the third telemetry snapshot (pH 5.3, turbidity 88, TDS 1,170) and the USGS
  turbidity spike to 591 FNU. These are exactly the events the Isolation Forest exists to flag.

If cleaning removed every outlier, the anomaly model would have nothing to learn from and the
anomaly rate would be meaningless. This is stated in `ml/README.md` and implemented in both cleaners.

---

## 5. What was deliberately NOT done

| Not done | Why |
|---|---|
| Imputation of missing values | Would fabricate measurements; the schema and UI are built to show `NULL` honestly |
| Clipping outliers to a percentile | Destroys the anomaly signal |
| Scaling / normalization in the stored CSV | Scaling belongs inside the model pipeline, not the dataset |
| Unit conversion (`_FNU` → NTU, `µS/cm` → TDS) | Not physically valid without calibration data; the repo explicitly refuses this |
| Regenerating existing splits or predictions | They must stay byte-stable for the evaluation report to remain meaningful |
| Deleting or rewriting the original files | Sources stay read-only; cleaned copies are additive |

---

## 6. Reproduce it

```bash
# from the repository root
python ml/preprocessing/clean_datasets.py

# outputs
ml/data/processed/cleaned/cleaned_usgs_ph_2024.csv
ml/data/processed/cleaned/cleaned_usgs_turbidity_2024.csv
ml/data/processed/cleaned/cleaned_usgs_temperature_2024.csv
ml/data/processed/cleaned/cleaned_usgs_conductance_2024.csv
ml/data/processed/cleaned/cleaned_water_quality_dataset1.csv
ml/data/processed/cleaned/cleaned_sensor_readings.csv
ml/reports/dataset_cleaning_report.json
ml/reports/dataset_cleaning_report.md
```

Exit codes: `0` = every check passed, `1` = no datasets found, `2` = a verification check failed.

---

## 7. Related cleaning code in the repository

| Module | Scope | Note |
|---|---|---|
| `ml/preprocessing/clean_data.py` | Telemetry export only | The Phase-5A cleaner, reused by `clean_datasets.py`; also the source of the `PHYSICAL_VALID_RANGES` policy |
| `ml/preprocessing/prepare_supervised.py` | Benchmark table mapping + validation + stratified split | Canonical column names and the leakage contract |
| `ml/preprocessing/forecasting.py` | USGS merge, join validation, past-only features, target rule | Rejects future leakage by construction |
| `ml/preprocessing/clean_datasets.py` | **All three dataset shapes** | This audit's addition: recipes, reconciliation, subset proof, JSON + Markdown report |

---

## 8. Honest limitations of the cleaning step

1. **Zero rows removed** means the cleaning did not demonstrate its rejection paths on this data.
   The ranges are exercised by the unit tests in `ml/tests/`, but not by these files.
2. The USGS files are **row-capped exports**, not complete series; cleaning cannot restore the
   truncated period.
3. `approval_status` is preserved but not enforced: 100 % of the turbidity rows are `Provisional`,
   and nothing in the pipeline currently downgrades or filters provisional data.
4. Cleaning does not address the provenance gap for `water_quality_dataset1.csv` — see
   [DATASET_CATALOG.md](DATASET_CATALOG.md#32-provenance-status).
5. The cleaned copies are **not** wired into training yet. Training still reads the original
   `external/` files (which is safe, because their values are provably identical), but if you want
   the audit trail to be end-to-end, point `prepare_*` scripts at `processed/cleaned/` in a future
   change.
