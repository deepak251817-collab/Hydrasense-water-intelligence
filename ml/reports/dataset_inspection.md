# HydraSense dataset inspection

Generated: `2026-10-30T05:43:05.201673+00:00` by `ml/scripts/inspect_datasets.py`.

> Every figure below is measured from the source files. Licence/provenance is reported only where documented; otherwise it says **unable to verify**.

## `water_quality_dataset1.csv`

- Kind: static classification benchmark
- Rows: **100,800**
- Columns: `pH, TDS_ppm, Turbidity_NTU, Temperature_C, Label`
- Duplicate rows: **0**
- Empty optional columns: none
- Missing values across all columns: **0**
- Unit — `pH`: pH units
- Unit — `TDS_ppm`: mg/L (ppm), NaCl-equivalent scale as distributed
- Unit — `Turbidity_NTU`: NTU (laboratory-style turbidity unit — NOT the hardware index)
- Unit — `Temperature_C`: °C
- Labels: `{'Unsafe': 70560, 'Safe': 30240}`
- Class balance: `{'Unsafe': 0.7, 'Safe': 0.3}`
- Feature ranges: pH 6.09–9.96; TDS_ppm 28.6–2806.1; Turbidity_NTU 0–72.75; Temperature_C 16.56–31.51
- Provenance: Not documented in this repository. The source, access date and licence must be confirmed before redistribution or publication (unable to verify).
- Use in this project: Used only to bootstrap/benchmark the anomaly and Safe/Unsafe models on matching pH/TDS/turbidity/temperature units. Its NTU turbidity is NOT fed from the ESP32 relative index, and its labels never define suitability.

## `usgs_ph_2024.csv`

- Kind: USGS time series (long format)
- Rows: **10,000**
- Columns: `x, y, time_series_id, monitoring_location_id, parameter_code, statistic_id, time, value, unit_of_measure, approval_status, qualifier, last_modified`
- Duplicate rows: **0**
- Missing key values (time/value/station/parameter): **0**
- Empty optional columns: `qualifier`
- Missing values across all columns: **10,000**
- Units: pH Units
- Time range: 2024-01-01T00:00:00+00:00 → 2024-02-04T19:55:00+00:00
- Stations: USGS-01649190
- Parameter codes: 00400
- Approval status: `{'Approved': 10000}`
- Provenance: USGS Water Data for the Nation export (station USGS-01649190, 2024). USGS data are public-domain U.S. Government works; retain the USGS attribution when redistributing.
- Use in this project: Used for chronological forecasting/deterioration research only. Specific conductance is kept distinct from TDS and is never converted or renamed.

## `usgs_conductance_2024.csv`

- Kind: USGS time series (long format)
- Rows: **10,000**
- Columns: `x, y, time_series_id, monitoring_location_id, parameter_code, statistic_id, time, value, unit_of_measure, approval_status, qualifier, last_modified`
- Duplicate rows: **0**
- Missing key values (time/value/station/parameter): **0**
- Empty optional columns: `qualifier`
- Missing values across all columns: **10,000**
- Units: uS/cm
- Time range: 2024-01-01T00:00:00+00:00 → 2024-02-05T15:00:00+00:00
- Stations: USGS-01649190
- Parameter codes: 00095
- Approval status: `{'Approved': 10000}`
- Provenance: USGS Water Data for the Nation export (station USGS-01649190, 2024). USGS data are public-domain U.S. Government works; retain the USGS attribution when redistributing.
- Use in this project: Used for chronological forecasting/deterioration research only. Specific conductance is kept distinct from TDS and is never converted or renamed.

## `usgs_temperature_2024.csv`

- Kind: USGS time series (long format)
- Rows: **10,000**
- Columns: `x, y, time_series_id, monitoring_location_id, parameter_code, statistic_id, time, value, unit_of_measure, approval_status, qualifier, last_modified`
- Duplicate rows: **0**
- Missing key values (time/value/station/parameter): **0**
- Empty optional columns: `qualifier`
- Missing values across all columns: **10,000**
- Units: degC
- Time range: 2024-01-01T00:00:00+00:00 → 2024-02-04T19:55:00+00:00
- Stations: USGS-01649190
- Parameter codes: 00010
- Approval status: `{'Approved': 10000}`
- Provenance: USGS Water Data for the Nation export (station USGS-01649190, 2024). USGS data are public-domain U.S. Government works; retain the USGS attribution when redistributing.
- Use in this project: Used for chronological forecasting/deterioration research only. Specific conductance is kept distinct from TDS and is never converted or renamed.

## `usgs_turbidity_2024.csv`

- Kind: USGS time series (long format)
- Rows: **10,000**
- Columns: `x, y, time_series_id, monitoring_location_id, parameter_code, statistic_id, time, value, unit_of_measure, approval_status, qualifier, last_modified`
- Duplicate rows: **0**
- Missing key values (time/value/station/parameter): **0**
- Empty optional columns: `qualifier`
- Missing values across all columns: **10,000**
- Units: _FNU
- Time range: 2024-01-01T00:00:00+00:00 → 2024-02-13T05:10:00+00:00
- Stations: USGS-01649190
- Parameter codes: 63680
- Approval status: `{'Provisional': 10000}`
- Provenance: USGS Water Data for the Nation export (station USGS-01649190, 2024). USGS data are public-domain U.S. Government works; retain the USGS attribution when redistributing.
- Use in this project: Used for chronological forecasting/deterioration research only. Specific conductance is kept distinct from TDS and is never converted or renamed.

## Not used for suitability

No dataset here changes a suitability verdict: suitability is rule-based on the four live sensor values and the configured threshold profile. These datasets are used for model benchmarking/research only.
