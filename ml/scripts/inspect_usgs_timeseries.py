"""Inspect USGS Time-Series Source Files (Phase 5D-1, USGS edition).

For each of the four USGS NVWB-style CSV exports from monitoring station
USGS-01649190 this script reports:

- row count
- column names
- station ID (monitoring_location_id)
- parameter code
- unit of measure
- minimum / maximum timestamp
- duplicate timestamps
- missing timestamps where detectable (gaps vs the most common interval)
- missing measurement values (and non-numeric values)
- numeric range (min/max of the measurement)
- sampling interval distribution

It verifies that every file belongs to USGS-01649190 and prints a combined
verdict. The original source files are never modified.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

EXTERNAL_DIR = PROJECT_ROOT / "ml" / "data" / "external"

EXPECTED_STATION = "USGS-01649190"

# file stem -> (expected USGS parameter code, project parameter name)
USGS_FILES = {
    "usgs_temperature_2024.csv": ("00010", "temperature"),
    "usgs_ph_2024.csv": ("00000", "pH"),          # placeholder, fixed below
    "usgs_conductance_2024.csv": ("00095", "specific_conductance"),
    "usgs_turbidity_2024.csv": ("63680", "turbidity"),
}
USGS_FILES["usgs_ph_2024.csv"] = ("00400", "pH")


def describe_gaps(sorted_ts: pd.Series) -> dict:
    """Summarize the sampling interval distribution and detectable gaps."""
    gaps = sorted_ts.diff().dropna()
    if gaps.empty:
        return {"most_common": None, "median": None, "min": None, "max": None,
                "distribution": {}, "gap_rows": 0}
    dist = gaps.value_counts().sort_values(ascending=False)
    most_common = dist.index[0]
    return {
        "most_common": most_common,
        "median": gaps.median(),
        "min": gaps.min(),
        "max": gaps.max(),
        # top interval values with counts (readable distribution)
        "distribution": {str(k): int(v) for k, v in dist.head(5).items()},
        "gap_rows": int((gaps != most_common).sum()),
    }


def inspect_file(path: Path, expected_code: str, param_name: str) -> dict | None:
    """Inspect one USGS source file without modifying it."""
    print(f"\n{'-' * 70}")
    print(f"FILE: {path.name}  (project parameter: {param_name})")
    print("-" * 70)
    if not path.exists():
        print("MISSING FILE - cannot proceed with this parameter.")
        return None

    # dtype=str preserves zero-padded parameter codes like 00010 / 00400.
    df = pd.read_csv(path, dtype=str)
    print(f"Row count:        {len(df):,}")
    print(f"Column names:     {list(df.columns)}")

    stations = sorted(df["monitoring_location_id"].dropna().unique()) if "monitoring_location_id" in df else []
    print(f"Station ID(s):    {stations}")
    station_ok = stations == [EXPECTED_STATION]

    codes = sorted(df["parameter_code"].dropna().unique()) if "parameter_code" in df else []
    print(f"Parameter code:   {codes} (expected {expected_code})")
    code_ok = expected_code in codes

    units = sorted(df["unit_of_measure"].dropna().unique()) if "unit_of_measure" in df else []
    print(f"Unit of measure:  {units}")

    ts = pd.to_datetime(df["time"], errors="coerce", utc=True).sort_values().reset_index(drop=True)
    print(f"Timestamp range:  {ts.min()}  ->  {ts.max()}")
    print(f"Unparseable timestamps: {int(pd.to_datetime(df['time'], errors='coerce', utc=True).isna().sum())}")

    dup_ts = int(df["time"].duplicated().sum())
    print(f"Duplicate timestamps:   {dup_ts}")

    gaps = describe_gaps(ts)
    print(f"Sampling interval: most common={gaps['most_common']}, median={gaps['median']}, "
          f"min={gaps['min']}, max={gaps['max']}")
    print(f"Interval distribution (top): {gaps['distribution']}")
    print(f"Deviations from most common interval (detectable gaps): {gaps['gap_rows']:,}")

    value_num = pd.to_numeric(df["value"], errors="coerce")
    missing_values = int(value_num.isna().sum())
    non_numeric = int((df["value"].notna() & value_num.isna()).sum())
    print(f"Missing measurement values: {missing_values} (non-numeric: {non_numeric})")
    print(f"Numeric range: min={value_num.min()}, max={value_num.max()}")

    approval = df["approval_status"].value_counts().to_dict() if "approval_status" in df else {}
    print(f"Approval status:  {approval}")

    return {
        "file": path.name,
        "param": param_name,
        "rows": int(len(df)),
        "station_ok": station_ok,
        "code_ok": code_ok,
        "code": expected_code,
        "unit": units,
        "ts_min": str(ts.min()),
        "ts_max": str(ts.max()),
        "dup_ts": dup_ts,
        "gaps": gaps,
        "missing_values": missing_values,
        "non_numeric": non_numeric,
        "min": (None if value_num.dropna().empty else float(value_num.min())),
        "max": (None if value_num.dropna().empty else float(value_num.max())),
        "approval": approval,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect USGS time-series source files (Phase 5D-1).")
    parser.add_argument("--external-dir", type=Path, default=EXTERNAL_DIR)
    args = parser.parse_args()

    print("=" * 70)
    print("HYDRASENSE PHASE 5D-1: USGS TIME-SERIES SOURCE FILE INSPECTION")
    print("=" * 70)

    results = []
    for fname, (code, param) in USGS_FILES.items():
        r = inspect_file(args.external_dir / fname, code, param)
        if r:
            results.append(r)

    print("\n" + "=" * 70)
    print("STATION VERIFICATION")
    print("=" * 70)
    all_station_ok = all(r["station_ok"] for r in results) and len(results) == len(USGS_FILES)
    all_code_ok = all(r["code_ok"] for r in results)
    print(f"Files inspected:              {len(results)} / {len(USGS_FILES)}")
    print(f"All files from {EXPECTED_STATION}: {all_station_ok}")
    print(f"All expected parameter codes present: {all_code_ok}")
    if all_station_ok and all_code_ok:
        print("VERDICT: PASS - all four files belong to USGS-01649190 with the expected codes.")
        return 0
    print("VERDICT: FAIL - fix the issues above before building the forecasting dataset.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
