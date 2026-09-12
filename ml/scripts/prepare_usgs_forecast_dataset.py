"""Build the USGS Time-Series Forecasting Dataset (Phase 5D-1, USGS edition).

Combines the four USGS source files (station USGS-01649190) into one
synchronized chronological dataset, engineers past-only historical features,
creates the future deterioration target, and writes the chronological
train/validation/test splits.

Parameter mapping (CRITICAL - see spec section 2):
    USGS parameter            Project column
    Water temperature (00010)  temperature
    pH (00400)                 pH
    Specific conductance(00095) specific_conductance
    Turbidity (63680)          turbidity

Specific conductance is NOT TDS. It is never renamed to tds and never
converted into TDS; the forecasting dataset explicitly retains
`specific_conductance` as a distinct measurement (uS/cm, as reported by USGS).

Pipeline (in order):
1.  Load the four files (originals never modified), parse timestamps to UTC.
2.  Merge on (station, timestamp) with an INNER join: only synchronized
    observations enter the forecasting dataset.
3.  Data-quality checks: missing/non-numeric values, duplicate timestamps and
    (station, timestamp) pairs, physically impossible values. Invalid
    observations are REPORTED separately - unusual but physically valid
    values (storm spikes) are kept.
4.  Determine the actual sampling interval (expected ~5 minutes, verified).
5.  Sort by (station, timestamp) and verify strict temporal ordering.
6.  Past-only features: lags (1, 2, 3), rolling mean/std over the 3 and 6
    observations strictly BEFORE the current row, and recent change (current
    minus previous). No centered windows, no future rows.
7.  Future deterioration target (horizon = 1, the next observation of the
    same station): 1 if turbidity increases by at least 10% (relative),
    OR specific conductance increases by at least 10% (relative), OR pH moves
    more than 0.20 units farther from neutral pH 7. Temperature never
    triggers the target. This is ONLY a rule-based future deterioration
    indicator - NOT contamination confirmation, pollution confirmation,
    potability classification, or universal water-safety classification.
8.  Drop rows for which no future observation exists (end of series) - their
    target is never filled with 0; the count is reported.
9.  Chronological 70/15/15 split with global timestamp boundaries (no
    shuffling, no overlap).

Outputs:
    ml/data/processed/usgs_timeseries_combined.csv   (synchronized core data)
    ml/data/processed/forecast_train.csv
    ml/data/processed/forecast_validation.csv
    ml/data/processed/forecast_test.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from ml.preprocessing.forecasting import (
    STATION_COLUMN,
    TARGET_COLUMN,
    TIMESTAMP_COLUMN,
    build_forecasting_dataset,
    chronological_split,
    target_distribution,
)

EXTERNAL_DIR = PROJECT_ROOT / "ml" / "data" / "external"
PROCESSED_DIR = PROJECT_ROOT / "ml" / "data" / "processed"

EXPECTED_STATION = "USGS-01649190"

# Source file -> (USGS parameter code, project column). specific_conductance
# is a DISTINCT measurement; no conversion or renaming to tds occurs.
USGS_SOURCES = {
    "usgs_temperature_2024.csv": ("00010", "temperature"),
    "usgs_ph_2024.csv": ("00400", "pH"),
    "usgs_conductance_2024.csv": ("00095", "specific_conductance"),
    "usgs_turbidity_2024.csv": ("63680", "turbidity"),
}

# Project-facing parameter order for the output datasets (spec section 14)
USGS_PARAMETERS = ["pH", "turbidity", "temperature", "specific_conductance"]

USGS_PARAM_MAP = {p: p for p in USGS_PARAMETERS}  # already project-facing

# Documented physical ranges for validity reporting (violations are reported
# separately and NEVER deleted - unusual but physically valid values are kept).
PHYSICAL_BOUNDS = {
    "pH": (0.0, 14.0),
    "turbidity": (0.0, None),           # non-negative
    "specific_conductance": (0.0, None),  # non-negative
    # Reasonable range for natural freshwater (degC), documented: allows
    # slight supercooling in shallow winter waters up to hot summer extremes.
    "temperature": (-5.0, 45.0),
}

COMBINED_CSV = PROCESSED_DIR / "usgs_timeseries_combined.csv"
FORECAST_TRAIN_CSV = PROCESSED_DIR / "forecast_train.csv"
FORECAST_VAL_CSV = PROCESSED_DIR / "forecast_validation.csv"
FORECAST_TEST_CSV = PROCESSED_DIR / "forecast_test.csv"

# Feature configuration (documented in the module docstring)
LAGS = (1, 2, 3)
ROLLING_WINDOWS = (3, 6)
HORIZON = 1


def load_usgs_file(path: Path, expected_code: str, param: str) -> tuple[pd.DataFrame, dict]:
    """Load one USGS source file into a minimal (station, timestamp, param) frame."""
    if not path.exists():
        raise FileNotFoundError(f"Required USGS source file not found: '{path}'.")
    raw = pd.read_csv(path, dtype=str)  # dtype=str preserves zero-padded codes

    stations = sorted(raw["monitoring_location_id"].dropna().unique())
    codes = sorted(raw["parameter_code"].dropna().unique())
    units = sorted(raw["unit_of_measure"].dropna().unique())
    info = {
        "file": path.name,
        "param": param,
        "rows": int(len(raw)),
        "stations": stations,
        "codes": codes,
        "units": units,
        "code_ok": expected_code in codes,
        "station_ok": stations == [EXPECTED_STATION],
    }
    if not info["station_ok"]:
        raise ValueError(
            f"{path.name}: expected all rows from {EXPECTED_STATION}, found {stations}."
        )
    if not info["code_ok"]:
        raise ValueError(f"{path.name}: expected USGS parameter code {expected_code}, found {codes}.")

    df = pd.DataFrame({
        "station": raw["monitoring_location_id"],
        "timestamp": pd.to_datetime(raw["time"], errors="coerce", utc=True),
        param: pd.to_numeric(raw["value"], errors="coerce"),
    })
    info["unparseable_timestamps"] = int(df["timestamp"].isna().sum())
    info["non_numeric_values"] = int(df[param].isna().sum())
    df = df.dropna(subset=["timestamp"])
    return df, info


def merge_usgs_sources(external_dir: Path = EXTERNAL_DIR) -> tuple[pd.DataFrame, dict]:
    """Load and inner-join the four USGS files on (station, timestamp).

    Returns the synchronized frame with columns [station, timestamp,
    pH, turbidity, temperature, specific_conductance] plus a meta dict with
    per-file info and merge statistics (rows before/after, rows lost,
    percentage retained).
    """
    file_infos = []
    frames = []
    total_rows_before = 0
    for fname, (code, param) in USGS_SOURCES.items():
        df, info = load_usgs_file(external_dir / fname, code, param)
        file_infos.append(info)
        total_rows_before += len(df)
        frames.append(df)

    merged = frames[0]
    for other in frames[1:]:
        # Inner join on (station, timestamp): only synchronized observations.
        merged = merged.merge(other, on=[STATION_COLUMN, TIMESTAMP_COLUMN], how="inner")

    merged = merged[[STATION_COLUMN, TIMESTAMP_COLUMN, *USGS_PARAMETERS]]
    sync_rows = len(merged)
    meta = {
        "files": file_infos,
        "rows_before_merge": total_rows_before,
        "synchronized_rows": sync_rows,
        "rows_lost_during_alignment": total_rows_before - sync_rows,
        "percentage_retained": round(100.0 * sync_rows / total_rows_before, 2) if total_rows_before else 0.0,
        "stations": int(merged[STATION_COLUMN].nunique()),
        "date_range": {
            "min": str(merged[TIMESTAMP_COLUMN].min()),
            "max": str(merged[TIMESTAMP_COLUMN].max()),
        },
    }
    return merged, meta


def check_data_quality(df: pd.DataFrame) -> dict:
    """Data-quality checks. Violations are REPORTED, never deleted here."""
    report: dict = {}
    report["missing_values_per_parameter"] = {
        p: int(df[p].isna().sum()) for p in USGS_PARAMETERS
    }
    report["missing_values_total"] = int(sum(report["missing_values_per_parameter"].values()))
    report["duplicate_timestamps"] = int(df[TIMESTAMP_COLUMN].duplicated().sum())
    report["duplicate_station_timestamp_pairs"] = int(
        df.duplicated(subset=[STATION_COLUMN, TIMESTAMP_COLUMN]).sum()
    )

    violations: dict[str, int] = {}
    for p, (low, high) in PHYSICAL_BOUNDS.items():
        series = pd.to_numeric(df[p], errors="coerce")
        bad = series.isna()  # non-numeric measurements count as invalid values
        if low is not None:
            bad = bad | (series < low)
        if high is not None:
            bad = bad | (series > high)
        violations[p] = int(bad.sum())
    report["invalid_or_impossible_values"] = violations
    report["invalid_or_impossible_total"] = int(sum(violations.values()))

    # Sampling interval of the synchronized data (verified, not assumed).
    gaps = df.sort_values(TIMESTAMP_COLUMN)[TIMESTAMP_COLUMN].diff().dropna()
    gaps = gaps[gaps > pd.Timedelta(0)]
    if gaps.empty:
        report["sampling_interval"] = {"median": None, "min": None, "max": None, "most_common": None}
    else:
        dist = gaps.value_counts()
        report["sampling_interval"] = {
            "median": str(gaps.median()),
            "min": str(gaps.min()),
            "max": str(gaps.max()),
            "most_common": str(dist.index[0]),
            "most_common_share": round(float(dist.iloc[0] / dist.sum()), 4),
        }
        expected = dist.index[0]
        report["sampling_interval"]["gaps_missing_expected_interval"] = int((gaps != expected).sum())
    return report


def prepare_usgs_forecasting_dataset(
    external_dir: Path = EXTERNAL_DIR,
    processed_dir: Path = PROCESSED_DIR,
    write_outputs: bool = True,
) -> dict:
    """End-to-end USGS forecasting dataset preparation.

    Returns a dict with the combined frame, the three chronological splits,
    and all report metadata. When ``write_outputs`` is True the combined CSV
    and the three forecast split CSVs are written to ``processed_dir``.
    """
    print("=" * 70)
    print("HYDRASENSE PHASE 5D-1: USGS TIME-SERIES FORECASTING DATASET PREPARATION")
    print("=" * 70)

    # 1-2. Load + synchronized merge (never concatenate rows).
    merged, merge_meta = merge_usgs_sources(external_dir)
    print(f"\n1. Loaded 4 USGS files ({merge_meta['rows_before_merge']:,} parameter rows total).")
    for info in merge_meta["files"]:
        print(f"   - {info['file']:<30} {info['rows']:>6,} rows  code={info['codes']}  unit={info['units']}")
    print(f"2. Synchronized (station+timestamp inner join): {merge_meta['synchronized_rows']:,} rows "
          f"({merge_meta['percentage_retained']}% of source rows; "
          f"{merge_meta['rows_lost_during_alignment']:,} rows not aligned across all four parameters).")
    print(f"   Stations: {merge_meta['stations']} | Range: {merge_meta['date_range']['min']} -> "
          f"{merge_meta['date_range']['max']}")

    # 3. Data-quality checks (report-only; no deletion of valid-but-unusual data).
    quality = check_data_quality(merged)
    print("\n3. DATA QUALITY (reported, not deleted):")
    print(f"   Missing values: {quality['missing_values_per_parameter']} "
          f"(total {quality['missing_values_total']})")
    print(f"   Duplicate timestamps: {quality['duplicate_timestamps']} | "
          f"duplicate (station,timestamp) pairs: {quality['duplicate_station_timestamp_pairs']}")
    print(f"   Invalid/physically impossible values: {quality['invalid_or_impossible_values']} "
          f"(total {quality['invalid_or_impossible_total']})")
    si = quality["sampling_interval"]
    print(f"   Sampling interval: most common={si['most_common']}, median={si['median']}, "
          f"min={si['min']}, max={si['max']} "
          f"(gaps where the expected interval is missing: {si.get('gaps_missing_expected_interval', 0)})")

    # 4-8. Chronological features + target + end-of-series handling via the
    #      shared, leakage-safe 5D-1 machinery (single station preserved).
    built, build_meta = build_forecasting_dataset(
        merged,
        station_col=STATION_COLUMN,
        timestamp_col=TIMESTAMP_COLUMN,
        param_mapping=USGS_PARAM_MAP,
        lags=LAGS,
        windows=ROLLING_WINDOWS,
        horizon=HORIZON,
        required_parameters=USGS_PARAMETERS,
        conductance_column="specific_conductance",
    )
    n_unlabellable = int(built[TARGET_COLUMN].isna().sum())
    built = built.dropna(subset=[TARGET_COLUMN]).reset_index(drop=True)
    print(f"\n4. Engineered features: {len(build_meta['lags'])} lags {build_meta['lags']}, "
          f"rolling windows {build_meta['rolling_windows']}, recent changes (all past-only).")
    print(f"5. Target (horizon={build_meta['horizon']}, rule: turbidity +>=10% OR specific "
          f"conductance +>=10% OR pH >0.20 farther from 7):")
    print(f"   - Rows removed because no future observation exists (end of series, "
          f"never filled with 0): {n_unlabellable}")
    dist = target_distribution(built)
    print(f"   - Target distribution: {dist['counts']} = {dist['percentages']}% "
          f"(deterioration=1 is the positive class)")

    # 9. Chronological 70/15/15 split (global timestamp boundaries).
    train_df, val_df, test_df, split_meta = chronological_split(built)
    print(f"\n6. Chronological split (no shuffling): train={split_meta['train_rows']:,} "
          f"(<= {split_meta['train_boundary']}), validation={split_meta['validation_rows']:,} "
          f"(<= {split_meta['validation_boundary']}), test={split_meta['test_rows']:,}.")
    print(f"   Boundary checks: max(train.ts) < min(val.ts): "
          f"{train_df[TIMESTAMP_COLUMN].max() < val_df[TIMESTAMP_COLUMN].min()} | "
          f"max(val.ts) < min(test.ts): "
          f"{val_df[TIMESTAMP_COLUMN].max() < test_df[TIMESTAMP_COLUMN].min()}")

    feature_cols = [c for c in built.columns
                    if c not in (STATION_COLUMN, TIMESTAMP_COLUMN, TARGET_COLUMN)]
    print(f"\n7. Final schema: {len(feature_cols)} feature columns + target "
          f"'{TARGET_COLUMN}' (includes specific_conductance as a DISTINCT measurement).")

    # 10. Write outputs.
    if write_outputs:
        processed_dir.mkdir(parents=True, exist_ok=True)
        combined_cols = [STATION_COLUMN, TIMESTAMP_COLUMN, *USGS_PARAMETERS]
        merged.sort_values([STATION_COLUMN, TIMESTAMP_COLUMN], kind="mergesort").reset_index(drop=True)
        merged[combined_cols].to_csv(processed_dir / "usgs_timeseries_combined.csv", index=False)
        train_df.to_csv(processed_dir / "forecast_train.csv", index=False)
        val_df.to_csv(processed_dir / "forecast_validation.csv", index=False)
        test_df.to_csv(processed_dir / "forecast_test.csv", index=False)
        print(f"\n8. Wrote: usgs_timeseries_combined.csv ({len(merged):,} rows), "
              f"forecast_train.csv ({len(train_df):,}), forecast_validation.csv ({len(val_df):,}), "
              f"forecast_test.csv ({len(test_df):,}).")

    print("=" * 70)
    return {
        "combined": merged,
        "train": train_df,
        "validation": val_df,
        "test": test_df,
        "merge_meta": merge_meta,
        "quality": quality,
        "build_meta": build_meta,
        "split_meta": split_meta,
        "target_distribution": dist,
        "unlabellable_rows_removed": n_unlabellable,
        "feature_columns": feature_cols,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the USGS forecasting dataset (Phase 5D-1).")
    parser.add_argument("--external-dir", type=Path, default=EXTERNAL_DIR)
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DIR)
    args = parser.parse_args()

    result = prepare_usgs_forecasting_dataset(
        external_dir=args.external_dir, processed_dir=args.processed_dir, write_outputs=True
    )
    if len(result["train"]) < 100 or len(result["test"]) < 50:
        print("STOP: synchronized data does not support a meaningful forecasting split.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
