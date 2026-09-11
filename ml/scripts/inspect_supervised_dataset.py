"""Inspect Supervised Water Quality Dataset (Phase 5C-1).

Reads the external dataset (ml/data/external/water_quality_dataset1.csv)
without modifying it, and produces a comprehensive inspection and validation report:
- Total rows and columns
- Column names and data types
- Missing value counts
- Duplicate row analysis (exact and feature-only)
- Unique label values, counts, and class percentages
- Class imbalance ratio
- Numerical statistics (min, max, mean, median, std) for the 4 core parameters
- Physical and chemical range validation sanity checks
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to sys.path so ml.preprocessing can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from ml.preprocessing.prepare_supervised import (
    RAW_FEATURE_COLUMNS,
    RAW_TARGET_COLUMN,
    inspect_dataset,
    validate_dataset,
)

DEFAULT_DATASET_PATH = PROJECT_ROOT / "ml" / "data" / "external" / "water_quality_dataset1.csv"


def inspect_supervised_dataset(file_path: Path) -> int:
    """Load, inspect, and validate the supervised dataset."""
    print("=" * 70)
    print("HYDRASENSE PHASE 5C-1: SUPERVISED DATASET INSPECTION & VALIDATION")
    print("=" * 70)
    print(f"Dataset Path: {file_path}")

    if not file_path.exists():
        print(f"ERROR: Dataset file not found at '{file_path}'.", file=sys.stderr)
        return 1

    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(f"ERROR: Failed to read CSV file: {e}", file=sys.stderr)
        return 1

    # 1. Dataset Dimensions & Schema
    stats = inspect_dataset(df, is_raw=True)
    val_report = validate_dataset(df, is_raw=True)

    print("\n1. DATASET DIMENSIONS & SCHEMA")
    print("-" * 50)
    print(f"Total Rows:     {stats['total_rows']:,}")
    print(f"Total Columns:  {stats['total_columns']}")
    print(f"Column Names:   {stats['columns']}")
    print("\nColumn Data Types:")
    for col, dtype in stats["dtypes"].items():
        print(f"  - {col:<16}: {dtype}")

    # 2. Missing Values & Duplicate Records
    print("\n2. DATA INTEGRITY (MISSING VALUES & DUPLICATES)")
    print("-" * 50)
    print("Missing Values per Column:")
    for col, null_cnt in stats["missing_values"].items():
        print(f"  - {col:<16}: {null_cnt} missing")
    total_missing = sum(stats["missing_values"].values())
    print(f"Total Missing Values:     {total_missing}")
    print(f"Exact Duplicate Rows:     {stats['exact_duplicates']}")
    print(f"Duplicate Feature Rows:   {stats['feature_duplicates']}")

    # 3. Label Validation & Class Distribution
    print("\n3. TARGET LABEL VALIDATION & CLASS DISTRIBUTION")
    print("-" * 50)
    class_dist = stats.get("class_distribution", {})
    unique_labels = class_dist.get("unique_labels", [])
    print(f"Target Column:            {RAW_TARGET_COLUMN}")
    print(f"Unique Label Values:      {unique_labels}")

    counts = class_dist.get("counts", {})
    pcts = class_dist.get("percentages", {})
    print("Label Frequencies:")
    for lbl in unique_labels:
        cnt = counts.get(lbl, 0)
        pct = pcts.get(lbl, 0.0)
        print(f"  - {lbl:<10}: {cnt:>7,} rows ({pct:5.2f}%)")

    imbalance_ratio = class_dist.get("imbalance_ratio", 0.0)
    print(f"Class Imbalance Ratio:    {imbalance_ratio:.4f} : 1 (Unsafe : Safe)")
    print("Policy Note: Imbalance preserved as-is. No rebalancing or SMOTE applied in Phase 5C-1.")

    # 4. Feature Summary Statistics (min, max, mean, median, std)
    print("\n4. NUMERICAL FEATURE DESCRIPTIVE STATISTICS")
    print("-" * 70)
    print(f"{'Feature':<16} | {'Min':>8} | {'Max':>10} | {'Mean':>10} | {'Median':>8} | {'Std Dev':>10}")
    print("-" * 70)
    for col in RAW_FEATURE_COLUMNS:
        fstat = stats["feature_statistics"].get(col, {})
        if fstat:
            print(
                f"{col:<16} | {fstat['min']:>8.2f} | {fstat['max']:>10.2f} | "
                f"{fstat['mean']:>10.4f} | {fstat['median']:>8.2f} | {fstat['std']:>10.4f}"
            )
    print("-" * 70)

    # 5. Physical Range & Quality Sanity Checks
    print("\n5. PHYSICAL & QUALITY RANGE SANITY CHECKS")
    print("-" * 50)
    violations = val_report["checks"].get("physical_violations", {})
    non_numeric = val_report["checks"].get("non_numeric_features", [])

    print(f"Non-numeric values in features:       {len(non_numeric)}")
    print(f"Negative TDS (< 0 ppm):                {violations.get('negative_tds', 0)} failing rows")
    print(f"Negative Turbidity (< 0 NTU):          {violations.get('negative_turbidity', 0)} failing rows")
    print(f"Invalid pH (outside [0.0, 14.0]):      {violations.get('invalid_pH', 0)} failing rows")
    print(f"Unreasonable Temp (outside [-10, 60]C): {violations.get('unreasonable_temperature', 0)} failing rows")

    # 6. Overall Validation Verdict
    print("\n6. VALIDATION SUMMARY REPORT")
    print("-" * 50)
    if val_report["valid"]:
        print("Status: ALL DATASET CHECKS PASSED SUCCESSFULLY (READY FOR SPLITTING)")
    else:
        print("Status: VALIDATION FAILED WITH ISSUES:")
        for err in val_report["errors"]:
            print(f"  - ERROR: {err}")
    if val_report["warnings"]:
        for warn in val_report["warnings"]:
            print(f"  - WARNING: {warn}")

    print("=" * 70)
    return 0 if val_report["valid"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect and validate supervised water quality dataset.")
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_DATASET_PATH,
        help="Path to external dataset CSV file.",
    )
    args = parser.parse_args()
    sys.exit(inspect_supervised_dataset(args.file))
