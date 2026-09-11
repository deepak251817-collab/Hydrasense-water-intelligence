"""Create Supervised Train / Validation / Test Splits (Phase 5C-1).

Loads ml/data/external/water_quality_dataset1.csv without modifying it,
maps column names to project standards (pH, tds, turbidity, temperature, label),
performs reproducible stratified splitting (70% train, 15% validation, 15% test),
validates data leakage guarantees, and saves the split CSV files to ml/data/processed/:
- ml/data/processed/supervised_train.csv
- ml/data/processed/supervised_validation.csv
- ml/data/processed/supervised_test.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from ml.preprocessing.prepare_supervised import (
    STANDARDIZED_COLUMNS,
    STANDARDIZED_FEATURE_COLUMNS,
    STANDARDIZED_TARGET_COLUMN,
    SupervisedPreprocessor,
    map_features,
    split_supervised_data,
    validate_dataset,
)

DEFAULT_INPUT_PATH = PROJECT_ROOT / "ml" / "data" / "external" / "water_quality_dataset1.csv"
PROCESSED_DIR = PROJECT_ROOT / "ml" / "data" / "processed"


def prepare_and_save_splits(
    input_path: Path,
    output_dir: Path,
    random_state: int = 42,
) -> int:
    """Run validation, feature mapping, reproducible stratified splitting, and write CSVs."""
    print("=" * 70)
    print("HYDRASENSE PHASE 5C-1: PREPARE SUPERVISED DATASET SPLITS")
    print("=" * 70)
    print(f"Source Dataset:  {input_path}")
    print(f"Output Directory:{output_dir}")
    print(f"Random State:    {random_state}")

    if not input_path.exists():
        print(f"ERROR: Source file '{input_path}' does not exist.", file=sys.stderr)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load raw dataset (read-only)
    df_raw = pd.read_csv(input_path)
    print(f"\n1. Loaded raw dataset: {len(df_raw):,} rows, {len(df_raw.columns)} columns.")

    # 2. Validation
    val_report = validate_dataset(df_raw, is_raw=True)
    if not val_report["valid"]:
        print("ERROR: Dataset validation failed!", file=sys.stderr)
        for err in val_report["errors"]:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("2. Raw dataset validation PASSED (0 nulls, 0 duplicates, physical bounds verified).")

    # 3. Feature Mapping
    df_mapped = map_features(df_raw)
    print(f"3. Feature mapping complete. Standardized columns: {list(df_mapped.columns)}")

    # 4. Stratified Train / Validation / Test Split (70 / 15 / 15)
    train_df, val_df, test_df = split_supervised_data(
        df_mapped,
        test_size=0.30,
        val_ratio_of_test=0.50,
        random_state=random_state,
        stratify_col=STANDARDIZED_TARGET_COLUMN,
    )

    print("\n4. SPLIT SIZES & CLASS DISTRIBUTION:")
    print("-" * 65)
    for name, split in [("Train (70%)", train_df), ("Val (15%)", val_df), ("Test (15%)", test_df)]:
        counts = split[STANDARDIZED_TARGET_COLUMN].value_counts().to_dict()
        safe_cnt = counts.get("Safe", 0)
        unsafe_cnt = counts.get("Unsafe", 0)
        total = len(split)
        safe_pct = (safe_cnt / total) * 100.0 if total > 0 else 0.0
        unsafe_pct = (unsafe_cnt / total) * 100.0 if total > 0 else 0.0
        print(
            f"  {name:<15}: {total:>7,} rows | "
            f"Unsafe: {unsafe_cnt:>6,} ({unsafe_pct:5.2f}%) | "
            f"Safe: {safe_cnt:>6,} ({safe_pct:5.2f}%)"
        )
    print("-" * 65)

    # 5. Data Leakage Verification
    print("\n5. DATA LEAKAGE VERIFICATION:")
    train_idx = set(train_df.index)
    val_idx = set(val_df.index)
    test_idx = set(test_df.index)

    leakage_checks = [
        ("Train & Val index disjoint", len(train_idx.intersection(val_idx)) == 0),
        ("Train & Test index disjoint", len(train_idx.intersection(test_idx)) == 0),
        ("Val & Test index disjoint", len(val_idx.intersection(test_idx)) == 0),
        ("Columns identical across splits", list(train_df.columns) == list(val_df.columns) == list(test_df.columns)),
        ("Target excluded from feature list", STANDARDIZED_TARGET_COLUMN not in STANDARDIZED_FEATURE_COLUMNS),
    ]

    all_leakage_passed = True
    for check_title, passed in leakage_checks:
        status = "PASSED" if passed else "FAILED"
        print(f"  - {check_title:<38}: {status}")
        if not passed:
            all_leakage_passed = False

    if not all_leakage_passed:
        print("ERROR: Data leakage checks failed!", file=sys.stderr)
        return 1

    # Test preprocessor leakage resistance
    preprocessor = SupervisedPreprocessor()
    X_train = train_df[STANDARDIZED_FEATURE_COLUMNS]
    preprocessor.fit(X_train)
    X_val = preprocessor.transform(val_df[STANDARDIZED_FEATURE_COLUMNS])
    X_test = preprocessor.transform(test_df[STANDARDIZED_FEATURE_COLUMNS])
    print(f"  - Preprocessor fit/transform check       : PASSED (features={preprocessor.feature_names_in_})")

    # 6. Save Processed Splits
    train_path = output_dir / "supervised_train.csv"
    val_path = output_dir / "supervised_validation.csv"
    test_path = output_dir / "supervised_test.csv"

    train_df.to_csv(train_path, index=False)
    val_df.to_csv(val_path, index=False)
    test_df.to_csv(test_path, index=False)

    print("\n6. OUTPUT CSV FILES GENERATED:")
    print(f"  - Training split:   {train_path} ({len(train_df):,} rows)")
    print(f"  - Validation split: {val_path} ({len(val_df):,} rows)")
    print(f"  - Test split:       {test_path} ({len(test_df):,} rows)")
    print("=" * 70)
    print("SUCCESS: Phase 5C-1 supervised splits created and verified successfully.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate supervised train/val/test splits.")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help="Path to external dataset CSV file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROCESSED_DIR,
        help="Directory to save processed split CSV files.",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Random seed for reproducible stratified split.",
    )
    args = parser.parse_args()
    sys.exit(prepare_and_save_splits(args.input, args.output_dir, args.random_state))
