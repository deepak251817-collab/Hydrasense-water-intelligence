# HydraSense Dataset Cleaning Report

Generated: `2026-10-24T01:35:42.376277+00:00` by `ml/preprocessing/clean_datasets.py`.

> Cleaned copies only. Source datasets are opened read-only; each source file's SHA-256 is re-checked after cleaning and the run aborts if it changed.

- Datasets processed: **6**
- Total input rows: **140,809**
- Total output rows: **140,809**
- Total rows removed: **0**
- All verification checks passed: **True**

## `usgs_conductance_2024.csv`

- Source: `ml\data\external\usgs_conductance_2024.csv`
- Cleaned copy: `ml\data\processed\cleaned\cleaned_usgs_conductance_2024.csv`
- Recipe: `usgs_long`
- Rows: **10,000 -> 10,000** (0 removed)
- Source unmodified (SHA-256): **True**
- Row-count reconciliation: **True**
- Output is a row-subset of input: **True**

| Operation | Rows before | Rows after | Removed |
|---|---|---|---|
| parse `time` to UTC datetime; drop unparseable timestamps | 10,000 | 10,000 | 0 |
| coerce `value` to numeric; drop non-numeric values | 10,000 | 10,000 | 0 |
| drop columns that are entirely NULL | 10,000 | 10,000 | 0 |
| remove physically impossible values (per-parameter bounds) | 10,000 | 10,000 | 0 |
| drop duplicate (time_series_id, time) rows, keep first | 10,000 | 10,000 | 0 |
| sort chronologically by `time` | 10,000 | 10,000 | 0 |
| select canonical columns | 10,000 | 10,000 | 0 |

| Check | Passed | Detail |
|---|---|---|
| parameter_code 95 has a documented physical range | True | specific conductance, uS/cm: [0.0, 200000.0] |
| no NULL values in key/value columns | True | none |
| timestamps are non-decreasing | True | True |
| units are consistent inside the file | True | ['uS/cm'] |

## `usgs_ph_2024.csv`

- Source: `ml\data\external\usgs_ph_2024.csv`
- Cleaned copy: `ml\data\processed\cleaned\cleaned_usgs_ph_2024.csv`
- Recipe: `usgs_long`
- Rows: **10,000 -> 10,000** (0 removed)
- Source unmodified (SHA-256): **True**
- Row-count reconciliation: **True**
- Output is a row-subset of input: **True**

| Operation | Rows before | Rows after | Removed |
|---|---|---|---|
| parse `time` to UTC datetime; drop unparseable timestamps | 10,000 | 10,000 | 0 |
| coerce `value` to numeric; drop non-numeric values | 10,000 | 10,000 | 0 |
| drop columns that are entirely NULL | 10,000 | 10,000 | 0 |
| remove physically impossible values (per-parameter bounds) | 10,000 | 10,000 | 0 |
| drop duplicate (time_series_id, time) rows, keep first | 10,000 | 10,000 | 0 |
| sort chronologically by `time` | 10,000 | 10,000 | 0 |
| select canonical columns | 10,000 | 10,000 | 0 |

| Check | Passed | Detail |
|---|---|---|
| parameter_code 400 has a documented physical range | True | pH, pH units: [0.0, 14.0] |
| no NULL values in key/value columns | True | none |
| timestamps are non-decreasing | True | True |
| units are consistent inside the file | True | ['pH Units'] |

## `usgs_temperature_2024.csv`

- Source: `ml\data\external\usgs_temperature_2024.csv`
- Cleaned copy: `ml\data\processed\cleaned\cleaned_usgs_temperature_2024.csv`
- Recipe: `usgs_long`
- Rows: **10,000 -> 10,000** (0 removed)
- Source unmodified (SHA-256): **True**
- Row-count reconciliation: **True**
- Output is a row-subset of input: **True**

| Operation | Rows before | Rows after | Removed |
|---|---|---|---|
| parse `time` to UTC datetime; drop unparseable timestamps | 10,000 | 10,000 | 0 |
| coerce `value` to numeric; drop non-numeric values | 10,000 | 10,000 | 0 |
| drop columns that are entirely NULL | 10,000 | 10,000 | 0 |
| remove physically impossible values (per-parameter bounds) | 10,000 | 10,000 | 0 |
| drop duplicate (time_series_id, time) rows, keep first | 10,000 | 10,000 | 0 |
| sort chronologically by `time` | 10,000 | 10,000 | 0 |
| select canonical columns | 10,000 | 10,000 | 0 |

| Check | Passed | Detail |
|---|---|---|
| parameter_code 10 has a documented physical range | True | temperature, degC: [-5.0, 50.0] |
| no NULL values in key/value columns | True | none |
| timestamps are non-decreasing | True | True |
| units are consistent inside the file | True | ['degC'] |

## `usgs_turbidity_2024.csv`

- Source: `ml\data\external\usgs_turbidity_2024.csv`
- Cleaned copy: `ml\data\processed\cleaned\cleaned_usgs_turbidity_2024.csv`
- Recipe: `usgs_long`
- Rows: **10,000 -> 10,000** (0 removed)
- Source unmodified (SHA-256): **True**
- Row-count reconciliation: **True**
- Output is a row-subset of input: **True**

| Operation | Rows before | Rows after | Removed |
|---|---|---|---|
| parse `time` to UTC datetime; drop unparseable timestamps | 10,000 | 10,000 | 0 |
| coerce `value` to numeric; drop non-numeric values | 10,000 | 10,000 | 0 |
| drop columns that are entirely NULL | 10,000 | 10,000 | 0 |
| remove physically impossible values (per-parameter bounds) | 10,000 | 10,000 | 0 |
| drop duplicate (time_series_id, time) rows, keep first | 10,000 | 10,000 | 0 |
| sort chronologically by `time` | 10,000 | 10,000 | 0 |
| select canonical columns | 10,000 | 10,000 | 0 |

| Check | Passed | Detail |
|---|---|---|
| parameter_code 63680 has a documented physical range | True | turbidity, FNU: [0.0, 100000.0] |
| no NULL values in key/value columns | True | none |
| timestamps are non-decreasing | True | True |
| units are consistent inside the file | True | ['_FNU'] |

## `water_quality_dataset1.csv`

- Source: `ml\data\external\water_quality_dataset1.csv`
- Cleaned copy: `ml\data\processed\cleaned\cleaned_water_quality_dataset1.csv`
- Recipe: `benchmark`
- Rows: **100,800 -> 100,800** (0 removed)
- Source unmodified (SHA-256): **True**
- Row-count reconciliation: **True**
- Output is a row-subset of input: **True**

| Operation | Rows before | Rows after | Removed |
|---|---|---|---|
| rename columns to the pipeline's canonical names | 100,800 | 100,800 | 0 |
| coerce features to numeric; drop rows with NULL features/label | 100,800 | 100,800 | 0 |
| remove physically impossible feature values | 100,800 | 100,800 | 0 |
| keep only known labels (Safe / Unsafe) | 100,800 | 100,800 | 0 |
| drop fully duplicated rows | 100,800 | 100,800 | 0 |

| Check | Passed | Detail |
|---|---|---|
| no NULL values remain | True | 0 |
| labels stay inside the documented set | True | {'Unsafe': 70560, 'Safe': 30240} |
| all four model features present | True | ['pH', 'tds', 'turbidity', 'temperature', 'label'] |

Labels: `{'Unsafe': 70560, 'Safe': 30240}`

## `sensor_readings.csv`

- Source: `ml\data\raw\sensor_readings.csv`
- Cleaned copy: `ml\data\processed\cleaned\cleaned_sensor_readings.csv`
- Recipe: `telemetry`
- Rows: **9 -> 9** (0 removed)
- Source unmodified (SHA-256): **True**
- Row-count reconciliation: **True**
- Output is a row-subset of input: **True**

| Operation | Rows before | Rows after | Removed |
|---|---|---|---|
| delegate to ml/preprocessing/clean_data.clean_sensor_data (UTC timestamps, station sort, dedupe on (station_code, timestamp), physical range validation) | 9 | 9 | 0 |

| Check | Passed | Detail |
|---|---|---|
| no NULL sensor values remain | True | none |
| timestamps are ISO-8601 UTC strings | True | ['2026-08-31T18:30:48Z'] |
| ph inside physical bounds | True | [5.28, 7.33] within [0.0, 14.0] |
| tds inside physical bounds | True | [210.7, 1171.4] within [0.0, 1000000.0] |
| turbidity inside physical bounds | True | [3.13, 88.13] within [0.0, 100000.0] |
| temperature inside physical bounds | True | [25.9, 29.8] within [-10.0, 60.0] |

## What was deliberately NOT done

- No imputation, scaling, clipping or unit conversion: the cleaned copies keep the original numeric values so downstream leakage-safe splits still describe the same data.
- No rows were treated as anomalies here: unusual-but-physical readings are kept on purpose so the Isolation Forest has something to model.
- Existing processed artifacts (`train.csv`, `supervised_test.csv`, `anomaly_results.csv`, ...) were not modified or regenerated.
