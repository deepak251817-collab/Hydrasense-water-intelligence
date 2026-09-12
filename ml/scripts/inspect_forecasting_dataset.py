"""Inspect Forecasting (Time-Series) Dataset (Phase 5D-1).

Searches the available project datasets (ml/data/external/ plus the processed
simulator telemetry) for a GENUINE chronological dataset that can support
future water-quality deterioration forecasting, and reports:

- number of rows
- number of stations/sites
- date range (min/max timestamp)
- timestamp frequency where detectable (dominant per-station sampling interval)
- missing values
- duplicate records
- available parameters (mapped to the four core parameters)
- number of observations per station
- chronological coverage and ordering

The script applies explicit, documented suitability criteria. If no dataset
satisfies them, it reports a clear STOP state. This phase deliberately does
NOT fabricate timestamps, stations, or synthetic time axes.

IMPORTANT (Phase 5D-1 scope):
- No XGBoost / model training happens here (dataset preparation only).
- The Phase 5C static benchmark (water_quality_dataset1.csv) is inspected for
  completeness but is NOT eligible as a forecasting dataset because it carries
  no timestamp and no station identifier.
- Conductivity columns are reported but never silently converted to TDS:
  no scientifically unsupported unit conversion is performed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to sys.path so ml.* packages can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

# ---------------------------------------------------------------------------
# Candidate datasets to assess (real project files; nothing invented).
# ---------------------------------------------------------------------------
EXTERNAL_DIR = PROJECT_ROOT / "ml" / "data" / "external"
SIMULATOR_TELEMETRY = PROJECT_ROOT / "ml" / "data" / "processed" / "clean_sensor_readings.csv"

# ---------------------------------------------------------------------------
# Core parameter mapping. Only explicit, supported aliases are mapped.
# NOTE: electrical conductivity (EC) / specific conductance is NOT mapped to
# TDS because a valid mg/L conversion depends on the ionic composition of the
# water (factor typically 0.55-0.80). Without dataset-supported conversion
# metadata, converting would fabricate values, which Phase 5D-1 forbids.
# ---------------------------------------------------------------------------
CORE_PARAMETER_ALIASES: dict[str, list[str]] = {
    "pH": ["pH", "ph", "ph_value", "potential_of_hydrogen"],
    "turbidity": ["turbidity", "turbidity_ntu", "turb"],
    "tds": ["tds", "tds_ppm", "total_dissolved_solids"],
    "temperature": ["temperature", "temperature_c", "water_temperature", "temp_c"],
}

# Columns that are reported but NOT mapped (unsupported conversion / aliases)
NON_MAPPED_REPORTED = ["conductivity", "ec", "specific_conductance", "conductivity_us_cm"]

STATION_ALIAS_HINTS = ["station", "site", "location", "well", "monitoring_point", "sensor"]
TIMESTAMP_ALIAS_HINTS = ["timestamp", "datetime", "date_time", "date", "time", "sampled_at", "measured_at"]

# ---------------------------------------------------------------------------
# Documented suitability criteria for a forecasting dataset (Phase 5D-1)
# ---------------------------------------------------------------------------
MIN_OBSERVATIONS_PER_STATION = 50   # need enough sequential points per station for lags/rolling windows/horizon
RECOMMENDED_OBSERVATIONS_PER_STATION = 200
FREQUENCY_DETECTABLE_COVERAGE = 0.80  # >=80% of per-station gaps equal the dominant gap -> "detectable frequency"


def detect_timestamp_columns(df: pd.DataFrame) -> list[str]:
    """Return column names whose values parse as datetimes (sampled check)."""
    parsed: list[str] = []
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            parsed.append(col)
            continue
        sample = df[col].dropna().astype(str).head(50)
        if sample.empty:
            continue
        try:
            # format="mixed": parse each element individually without pandas'
            # format-inference warning (we deliberately probe unknown columns).
            coerced = pd.to_datetime(sample, errors="coerce", format="mixed", utc=True)
            if coerced.notna().mean() >= 0.9:
                parsed.append(col)
        except Exception:
            continue
    return parsed


def detect_station_columns(df: pd.DataFrame) -> list[str]:
    """Return likely station/site identifier columns by name heuristics."""
    return [
        col for col in df.columns
        if col.lower() not in ("device_id",)
        and any(hint in col.lower() for hint in STATION_ALIAS_HINTS)
        and not pd.api.types.is_numeric_dtype(df[col])
    ]


def map_core_parameters(df: pd.DataFrame) -> tuple[dict[str, str], list[str]]:
    """Map dataset columns to the four core parameters.

    Returns (mapping, unmapped_reported) where mapping is {parameter: column}.
    Conductivity-like columns are reported separately and never converted.
    """
    lower_cols = {c.lower(): c for c in df.columns}
    mapping: dict[str, str] = {}
    for param, aliases in CORE_PARAMETER_ALIASES.items():
        for alias in aliases:
            if alias.lower() in lower_cols:
                mapping[param] = lower_cols[alias.lower()]
                break
    unmapped = [lower_cols[a] for a in NON_MAPPED_REPORTED if a in lower_cols]
    return mapping, unmapped


def detect_dominant_frequency(gaps: pd.Series) -> tuple[str | None, float]:
    """Detect the dominant sampling interval among consecutive gaps.

    Returns (human readable frequency or None, coverage fraction).
    """
    if gaps.empty:
        return None, 0.0
    dominant = gaps.mode().iloc[0]
    if pd.isna(dominant) or dominant <= pd.Timedelta(0):
        return None, 0.0
    coverage = float((gaps == dominant).mean())
    if coverage < FREQUENCY_DETECTABLE_COVERAGE:
        return None, coverage
    seconds = dominant.total_seconds()
    if seconds < 60:
        label = f"{seconds:.0f} seconds"
    elif seconds < 3600:
        label = f"{seconds / 60:.0f} minutes"
    elif seconds < 86400:
        label = f"{seconds / 3600:.1f} hours"
    else:
        label = f"{seconds / 86400:.1f} days"
    return label, coverage


def assess_time_series_suitability(df: pd.DataFrame, source_name: str) -> dict:
    """Assess one candidate dataset against the Phase 5D-1 suitability criteria."""
    assessment: dict = {"source": source_name}

    # 1. Basic dimensions
    assessment["rows"] = int(len(df))
    assessment["columns"] = list(df.columns)

    # 2. Timestamp detection
    ts_cols = detect_timestamp_columns(df)
    assessment["timestamp_columns"] = ts_cols
    has_time = len(ts_cols) > 0

    # 3. Station detection
    station_cols = detect_station_columns(df)
    assessment["station_columns"] = station_cols
    if station_cols:
        station_col = station_cols[0]
        assessment["n_stations"] = int(df[station_col].nunique(dropna=True))
    else:
        station_col = None
        assessment["n_stations"] = 0
    assessment["station_column"] = station_col

    # 4. Core parameter mapping
    mapping, unmapped = map_core_parameters(df)
    assessment["parameter_mapping"] = mapping
    assessment["missing_core_parameters"] = [p for p in CORE_PARAMETER_ALIASES if p not in mapping]
    assessment["unmapped_reported_columns"] = unmapped

    # 5. Data quality
    assessment["missing_values_total"] = int(df.isnull().sum().sum())
    assessment["exact_duplicates"] = int(df.duplicated().sum())

    # 6. Chronological structure (only meaningful when timestamps exist)
    obs_per_station: dict = {}
    date_range: dict = {"min": None, "max": None}
    frequency_report: dict = {}
    chronologically_sorted = False
    if has_time:
        ts_col = ts_cols[0]
        ts = pd.to_datetime(df[ts_col], errors="coerce")
        date_range = {"min": str(ts.min()), "max": str(ts.max())}
        if station_col is not None:
            per_station = df.assign(_ts=ts).groupby(station_col)["_ts"]
            for station, series in per_station:
                s = series.dropna().sort_values()
                obs_per_station[str(station)] = int(len(s))
                gaps = s.diff().dropna()
                freq, coverage = detect_dominant_frequency(gaps)
                frequency_report[str(station)] = {
                    "dominant_frequency": freq,
                    "gap_coverage": round(coverage, 3),
                    "median_gap_seconds": (gaps.median().total_seconds() if not gaps.empty else None),
                    "span_days": ((s.max() - s.min()).total_seconds() / 86400.0 if len(s) > 1 else 0.0),
                }
            # ordering check on the raw file
            chronologically_sorted = bool(
                df.assign(_ts=ts).sort_values([station_col, "_ts"]).index.equals(df.index)
            )
        else:
            s = ts.dropna().sort_values()
            obs_per_station["<single-series>"] = int(len(s))
            gaps = s.diff().dropna()
            freq, coverage = detect_dominant_frequency(gaps)
            frequency_report["<single-series>"] = {
                "dominant_frequency": freq,
                "gap_coverage": round(coverage, 3),
                "median_gap_seconds": (gaps.median().total_seconds() if not gaps.empty else None),
                "span_days": ((s.max() - s.min()).total_seconds() / 86400.0 if len(s) > 1 else 0.0),
            }
            chronologically_sorted = bool(df.assign(_ts=ts).sort_values("_ts").index.equals(df.index))

    assessment["date_range"] = date_range
    assessment["observations_per_station"] = obs_per_station
    assessment["frequency_report"] = frequency_report
    assessment["chronologically_sorted_in_file"] = chronologically_sorted

    # 7. Suitability verdict against the documented criteria
    reasons: list[str] = []
    if not has_time:
        reasons.append("NO TIMESTAMP COLUMN: the dataset has no parseable date/time column, "
                       "so no chronological forecasting is possible (fabricating time is forbidden).")
    if has_time and station_col is None:
        reasons.append("NO STATION/SITE IDENTIFIER: repeated observations cannot be attributed "
                       "to independent time series per location.")
    max_obs = max(obs_per_station.values()) if obs_per_station else 0
    if has_time and station_col is not None and max_obs < MIN_OBSERVATIONS_PER_STATION:
        reasons.append(
            f"INSUFFICIENT SEQUENCE LENGTH: maximum observations at one station is {max_obs}, "
            f"below the documented minimum of {MIN_OBSERVATIONS_PER_STATION} sequential observations "
            "required to build lag/rolling features plus a future horizon without degenerate windows."
        )
    if assessment["missing_core_parameters"]:
        reasons.append(
            f"MISSING CORE PARAMETERS (not fabricated): {assessment['missing_core_parameters']}. "
            "The dataset is reportable but incomplete for the four-parameter forecasting design."
        )
    # Note: a missing parameter alone does not disqualify if clearly reported;
    # fabrication is what is forbidden. Timestamp+stations+length are hard requirements.

    assessment["suitable"] = bool(has_time and station_col is not None
                                  and max_obs >= MIN_OBSERVATIONS_PER_STATION)
    assessment["unsuitability_reasons"] = reasons
    return assessment


def print_assessment(a: dict) -> None:
    """Pretty-print one dataset assessment."""
    print(f"\n{'-' * 70}")
    print(f"CANDIDATE: {a['source']}")
    print("-" * 70)
    print(f"Rows:                        {a['rows']:,}")
    print(f"Columns:                     {a['columns']}")
    print(f"Timestamp column(s):         {a['timestamp_columns'] or 'NONE FOUND'}")
    print(f"Station column(s):           {a['station_columns'] or 'NONE FOUND'}")
    print(f"Number of stations/sites:    {a['n_stations']}")
    print(f"Date range:                  {a['date_range']}")
    print(f"Core parameter mapping:      {a['parameter_mapping']}")
    print(f"Missing core parameters:     {a['missing_core_parameters'] or 'none'}")
    if a["unmapped_reported_columns"]:
        print(f"Reported, NOT mapped:        {a['unmapped_reported_columns']} "
              "(conductivity-like; no supported TDS conversion performed)")
    print(f"Missing values (total):      {a['missing_values_total']:,}")
    print(f"Exact duplicate rows:        {a['exact_duplicates']:,}")
    print(f"Observations per station:    {a['observations_per_station']}")
    for station, fr in a["frequency_report"].items():
        print(f"Frequency @ {station}: dominant={fr['dominant_frequency']} "
              f"(gap coverage {fr['gap_coverage']:.0%}), median gap="
              f"{fr['median_gap_seconds']} s, span={fr['span_days']:.2f} days")
    print(f"Chronologically sorted in file: {a['chronologically_sorted_in_file']}")
    if a["suitable"]:
        print("SUITABILITY: SUITABLE - meets Phase 5D-1 chronological forecasting criteria")
    else:
        print("SUITABILITY: NOT SUITABLE")
        for r in a["unsuitability_reasons"]:
            print(f"  - {r}")


def run_inspection(external_dir: Path = EXTERNAL_DIR) -> tuple[list[dict], bool]:
    """Inspect every candidate dataset and return (assessments, any_suitable)."""
    print("=" * 70)
    print("HYDRASENSE PHASE 5D-1: FORECASTING (TIME-SERIES) DATASET INSPECTION")
    print("=" * 70)

    candidates: list[Path] = []
    if external_dir.exists():
        candidates.extend(sorted(external_dir.glob("*.csv")))
    if SIMULATOR_TELEMETRY.exists():
        candidates.append(SIMULATOR_TELEMETRY)

    if not candidates:
        print("No candidate datasets found in ml/data/external/ or ml/data/processed/.")
        return [], False

    assessments: list[dict] = []
    for path in candidates:
        try:
            df = pd.read_csv(path)
        except Exception as e:
            print(f"\nCould not read '{path}': {e}")
            continue
        a = assess_time_series_suitability(df, source_name=str(path))
        assessments.append(a)
        print_assessment(a)

    any_suitable = any(a["suitable"] for a in assessments)
    print("\n" + "=" * 70)
    print("PHASE 5D-1 DATASET SELECTION VERDICT")
    print("=" * 70)
    if any_suitable:
        suitable = [a["source"] for a in assessments if a["suitable"]]
        print(f"VERDICT: PROCEED - suitable chronological dataset(s) found: {suitable}")
    else:
        print("VERDICT: STOP - NO SUITABLE FORECASTING DATASET IS AVAILABLE.")
        print()
        print("Requirement (documented in ml/README.md, Phase 5D-1):")
        print("  A genuine time-series water-quality dataset with:")
        print("    1. A real timestamp/date column (no invented time axes)")
        print("    2. A station/site identifier enabling per-location series")
        print(f"    3. At least {MIN_OBSERVATIONS_PER_STATION} sequential observations per station "
              f"(recommended {RECOMMENDED_OBSERVATIONS_PER_STATION})")
        print("    4. The four core parameters: pH, turbidity, TDS, temperature")
        print("       (a missing parameter may be reported, never fabricated)")
        print()
        print("The Phase 5C benchmark (water_quality_dataset1.csv) is a STATIC")
        print("classification dataset: it has no timestamp and no site identifier,")
        print("so it cannot support future-looking deterioration prediction and is")
        print("NOT eligible as a forecasting dataset merely because it has many rows.")
        print()
        print("Per the Phase 5D-1 specification, dataset preparation STOPS here.")
        print("No forecast_*.csv files were generated and no time information was fabricated.")
    print("=" * 70)
    return assessments, any_suitable


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect and assess datasets for Phase 5D-1 time-series forecasting suitability."
    )
    parser.add_argument(
        "--external-dir",
        type=Path,
        default=EXTERNAL_DIR,
        help="Directory containing external candidate datasets.",
    )
    args = parser.parse_args()

    _, any_suitable = run_inspection(external_dir=args.external_dir)
    # Exit code 0 = suitable dataset found (preparation may proceed),
    # exit code 1 = STOP: no suitable forecasting dataset (documented outcome).
    return 0 if any_suitable else 1


if __name__ == "__main__":
    sys.exit(main())
