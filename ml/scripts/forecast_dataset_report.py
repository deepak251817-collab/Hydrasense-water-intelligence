"""Forecast Dataset Report (Phase 5D-1, USGS edition).

Reads the generated forecasting artifacts and prints a summary report:
- total synchronized observations
- date range
- station count
- sampling interval
- missing values
- duplicate count
- invalid-value count
- number of targetable observations
- deterioration / non-deterioration counts (overall and per split)
- train/validation/test sizes
- class distribution per split

All numbers are measured from the generated datasets; nothing is fabricated.
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
    target_distribution,
)
from ml.scripts.prepare_usgs_forecast_dataset import (
    COMBINED_CSV,
    FORECAST_TEST_CSV,
    FORECAST_TRAIN_CSV,
    FORECAST_VAL_CSV,
    USGS_PARAMETERS,
    check_data_quality,
)

MISSING_MESSAGE = (
    "Run ml/scripts/prepare_usgs_forecast_dataset.py first to generate the "
    "USGS forecasting dataset artifacts."
)


def _read(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        print(f"MISSING: {path}. {MISSING_MESSAGE}", file=sys.stderr)
        return None
    return pd.read_csv(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Report USGS forecasting dataset statistics (Phase 5D-1).")
    parser.add_argument("--processed-dir", type=Path, default=PROJECT_ROOT / "ml" / "data" / "processed")
    args = parser.parse_args()

    combined = _read(args.processed_dir / COMBINED_CSV.name)
    train = _read(args.processed_dir / FORECAST_TRAIN_CSV.name)
    val = _read(args.processed_dir / FORECAST_VAL_CSV.name)
    test = _read(args.processed_dir / FORECAST_TEST_CSV.name)
    if combined is None or train is None or val is None or test is None:
        return 1

    combined[TIMESTAMP_COLUMN] = pd.to_datetime(combined[TIMESTAMP_COLUMN], utc=True)

    print("=" * 70)
    print("HYDRASENSE PHASE 5D-1: USGS FORECASTING DATASET REPORT")
    print("=" * 70)

    # Synchronized dataset summary
    print(f"\n1. SYNCHRONIZED OBSERVATIONS: {len(combined):,}")
    print(f"   Date range:  {combined[TIMESTAMP_COLUMN].min()}  ->  {combined[TIMESTAMP_COLUMN].max()}")
    print(f"   Station count: {combined[STATION_COLUMN].nunique()} "
          f"({sorted(combined[STATION_COLUMN].unique())})")

    quality = check_data_quality(combined)
    si = quality["sampling_interval"]
    print(f"   Sampling interval: most common={si['most_common']} "
          f"({si.get('most_common_share', 0) * 100:.1f}% of gaps), median={si['median']}, "
          f"min={si['min']}, max={si['max']}")
    print(f"   Gaps where the expected interval is missing: "
          f"{si.get('gaps_missing_expected_interval', 0):,}")

    print(f"\n2. DATA QUALITY")
    print(f"   Missing values: {quality['missing_values_per_parameter']} "
          f"(total {quality['missing_values_total']})")
    print(f"   Duplicates: timestamps={quality['duplicate_timestamps']}, "
          f"(station,timestamp) pairs={quality['duplicate_station_timestamp_pairs']}")
    print(f"   Invalid/physically impossible values: "
          f"{quality['invalid_or_impossible_values']} "
          f"(total {quality['invalid_or_impossible_total']}; reported, never deleted)")

    # Target summary (the target lives in the forecast splits, not the combined file)
    print(f"\n3. TARGETABLE OBSERVATIONS (with a valid future target): "
          f"{len(train) + len(val) + len(test):,}")
    dist_train = target_distribution(train)
    dist_val = target_distribution(val)
    dist_test = target_distribution(test)
    det = dist_train["counts"].get("1.0", 0) + dist_val["counts"].get("1.0", 0) + dist_test["counts"].get("1.0", 0)
    non = dist_train["counts"].get("0.0", 0) + dist_val["counts"].get("0.0", 0) + dist_test["counts"].get("0.0", 0)
    print(f"   Deterioration (1):        {det:,}")
    print(f"   Non-deterioration (0):    {non:,}")

    # Split sizes and class distribution
    print("\n4. CHRONOLOGICAL SPLIT (70/15/15 by global timestamp boundaries)")
    for name, part, dist in (("train", train, dist_train),
                             ("validation", val, dist_val),
                             ("test", test, dist_test)):
        ts = pd.to_datetime(part[TIMESTAMP_COLUMN], utc=True)
        print(f"   {name:<10}: {len(part):>6,} rows | {ts.min()} -> {ts.max()}")
        print(f"              class distribution: {dist['counts']} = {dist['percentages']}%")

    print(f"\n5. COLUMNS: {list(combined.columns)}")
    print(f"   (forecast splits add lag/rolling/change features and '{TARGET_COLUMN}'; "
          f"specific_conductance is retained as a DISTINCT measurement, not TDS)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
