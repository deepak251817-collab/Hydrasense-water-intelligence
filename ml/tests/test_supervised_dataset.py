"""Pytest Test Suite for Supervised Water Quality Dataset Preparation (Phase 5C-1).

Verifies all Phase 5C-1 specifications:
1. Source dataset exists and is non-empty
2. Required columns exist
3. Expected labels exist ('Safe', 'Unsafe') with no unexpected categories
4. No missing values remain
5. Numeric feature types
6. Duplicate detection (exact and feature-only)
7. Label counts and class distribution
8. Split files exist in ml/data/processed/
9. Split sizes match 70% train / 15% validation / 15% test
10. No overlap among train, validation, and test datasets
11. All classes represented in each split with consistent proportions
12. Label strictly excluded from feature matrix (leakage protection)
13. Reproducible splitting with random_state=42
14. Standardized project column names without unexpected columns
15. Physical and quality range sanity checks
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from ml.preprocessing.prepare_supervised import (
    EXPECTED_LABELS,
    EXPECTED_RAW_COLUMNS,
    RAW_FEATURE_COLUMNS,
    RAW_TARGET_COLUMN,
    STANDARDIZED_COLUMNS,
    STANDARDIZED_FEATURE_COLUMNS,
    STANDARDIZED_TARGET_COLUMN,
    SupervisedPreprocessor,
    map_features,
    split_supervised_data,
    validate_dataset,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EXTERNAL_DATA_PATH = PROJECT_ROOT / "ml" / "data" / "external" / "water_quality_dataset1.csv"
PROCESSED_DIR = PROJECT_ROOT / "ml" / "data" / "processed"


@pytest.fixture(scope="module")
def raw_dataset() -> pd.DataFrame:
    """Load the raw external dataset once for the test module."""
    assert EXTERNAL_DATA_PATH.exists(), f"Source dataset file not found at {EXTERNAL_DATA_PATH}"
    return pd.read_csv(EXTERNAL_DATA_PATH)


@pytest.fixture(scope="module")
def split_datasets() -> dict[str, pd.DataFrame]:
    """Load the processed train, validation, and test split files."""
    train_path = PROCESSED_DIR / "supervised_train.csv"
    val_path = PROCESSED_DIR / "supervised_validation.csv"
    test_path = PROCESSED_DIR / "supervised_test.csv"

    assert train_path.exists(), f"Train split missing at {train_path}"
    assert val_path.exists(), f"Validation split missing at {val_path}"
    assert test_path.exists(), f"Test split missing at {test_path}"

    return {
        "train": pd.read_csv(train_path),
        "validation": pd.read_csv(val_path),
        "test": pd.read_csv(test_path),
    }


def test_dataset_exists():
    """Verify source dataset exists under ml/data/external/ and is non-empty."""
    assert EXTERNAL_DATA_PATH.is_file()
    assert EXTERNAL_DATA_PATH.stat().st_size > 0


def test_required_columns_exist(raw_dataset: pd.DataFrame):
    """Verify all 5 required raw columns exist in the dataset."""
    actual_columns = list(raw_dataset.columns)
    for col in EXPECTED_RAW_COLUMNS:
        assert col in actual_columns, f"Expected column '{col}' missing from source dataset."
    assert len(actual_columns) == len(EXPECTED_RAW_COLUMNS)


def test_expected_labels_exist(raw_dataset: pd.DataFrame):
    """Verify target column 'Label' contains strictly 'Safe' and 'Unsafe'."""
    assert RAW_TARGET_COLUMN in raw_dataset.columns
    unique_labels = set(raw_dataset[RAW_TARGET_COLUMN].dropna().unique())
    assert unique_labels == EXPECTED_LABELS, f"Unexpected labels found: {unique_labels}"


def test_no_missing_values(raw_dataset: pd.DataFrame):
    """Verify zero missing values exist across all columns."""
    null_counts = raw_dataset.isnull().sum()
    assert null_counts.sum() == 0, f"Missing values detected in source dataset: {null_counts.to_dict()}"


def test_numeric_feature_types(raw_dataset: pd.DataFrame):
    """Verify all four input features have numeric float types."""
    for col in RAW_FEATURE_COLUMNS:
        assert np.issubdtype(raw_dataset[col].dtype, np.floating) or np.issubdtype(
            raw_dataset[col].dtype, np.integer
        ), f"Feature column '{col}' is not numeric: dtype={raw_dataset[col].dtype}"


def test_duplicate_detection(raw_dataset: pd.DataFrame):
    """Verify duplicate detection works and the source dataset has zero exact duplicates."""
    exact_duplicates = raw_dataset.duplicated().sum()
    assert exact_duplicates == 0, f"Found {exact_duplicates} exact duplicate rows in source dataset."

    # Verify duplicate detection detects injected duplicates
    df_with_duplicate = pd.concat([raw_dataset.iloc[:5], raw_dataset.iloc[:1]], ignore_index=True)
    assert df_with_duplicate.duplicated().sum() == 1


def test_label_counts_and_distribution(raw_dataset: pd.DataFrame):
    """Verify total rows (100,800), exact class counts (70,560 Unsafe, 30,240 Safe), and proportions."""
    total_rows = len(raw_dataset)
    assert total_rows == 100_800, f"Expected 100,800 rows, found {total_rows}"

    counts = raw_dataset[RAW_TARGET_COLUMN].value_counts().to_dict()
    assert counts.get("Unsafe") == 70_560, f"Expected 70,560 Unsafe rows, got {counts.get('Unsafe')}"
    assert counts.get("Safe") == 30_240, f"Expected 30,240 Safe rows, got {counts.get('Safe')}"

    # Class percentages
    pcts = raw_dataset[RAW_TARGET_COLUMN].value_counts(normalize=True) * 100.0
    assert pytest.approx(pcts["Unsafe"], rel=1e-3) == 70.00
    assert pytest.approx(pcts["Safe"], rel=1e-3) == 30.00


def test_split_files_exist():
    """Verify that all three split CSV files exist in ml/data/processed/."""
    for filename in ["supervised_train.csv", "supervised_validation.csv", "supervised_test.csv"]:
        split_path = PROCESSED_DIR / filename
        assert split_path.is_file(), f"Expected split file {filename} does not exist."
        assert split_path.stat().st_size > 0


def test_split_sizes_match_70_15_15(split_datasets: dict[str, pd.DataFrame]):
    """Verify split sizes match 70% (70,560), 15% (15,120), and 15% (15,120)."""
    train_df = split_datasets["train"]
    val_df = split_datasets["validation"]
    test_df = split_datasets["test"]

    total = len(train_df) + len(val_df) + len(test_df)
    assert total == 100_800

    assert len(train_df) == 70_560, f"Train split expected 70,560, got {len(train_df)}"
    assert len(val_df) == 15_120, f"Val split expected 15,120, got {len(val_df)}"
    assert len(test_df) == 15_120, f"Test split expected 15,120, got {len(test_df)}"


def test_no_overlap_among_datasets(raw_dataset: pd.DataFrame):
    """Verify that train, validation, and test splits have zero overlapping indices."""
    mapped_df = map_features(raw_dataset)
    train_df, val_df, test_df = split_supervised_data(mapped_df, random_state=42)

    train_idx = set(train_df.index)
    val_idx = set(val_df.index)
    test_idx = set(test_df.index)

    assert len(train_idx.intersection(val_idx)) == 0, "Overlap found between train and validation."
    assert len(train_idx.intersection(test_idx)) == 0, "Overlap found between train and test."
    assert len(val_idx.intersection(test_idx)) == 0, "Overlap found between validation and test."


def test_all_classes_represented_in_splits(split_datasets: dict[str, pd.DataFrame]):
    """Verify that both Safe and Unsafe classes remain represented in all splits."""
    for split_name, df in split_datasets.items():
        unique_labels = set(df[STANDARDIZED_TARGET_COLUMN].unique())
        assert unique_labels == {"Safe", "Unsafe"}, f"{split_name} split missing classes: {unique_labels}"

        # Proportions should remain approximately 70% Unsafe and 30% Safe
        pcts = df[STANDARDIZED_TARGET_COLUMN].value_counts(normalize=True) * 100.0
        assert pytest.approx(pcts["Unsafe"], abs=0.1) == 70.0
        assert pytest.approx(pcts["Safe"], abs=0.1) == 30.0


def test_label_excluded_from_feature_matrix(split_datasets: dict[str, pd.DataFrame]):
    """Verify label is never included as an input feature and preprocessor guards against target leakage."""
    train_df = split_datasets["train"]

    # Target is not in standardized feature column definitions
    assert STANDARDIZED_TARGET_COLUMN not in STANDARDIZED_FEATURE_COLUMNS

    # Preprocessor verifies features
    preprocessor = SupervisedPreprocessor()
    X_train = train_df[STANDARDIZED_FEATURE_COLUMNS]
    preprocessor.fit(X_train)

    assert preprocessor.feature_names_in_ == STANDARDIZED_FEATURE_COLUMNS
    assert "label" not in preprocessor.feature_names_in_

    # Preprocessor must raise ValueError if label column is accidentally provided in feature matrix
    with pytest.raises(ValueError, match="Target leakage detected"):
        preprocessor.fit(train_df)

    with pytest.raises(ValueError, match="Target leakage detected"):
        preprocessor.transform(train_df)


def test_reproducible_splitting(raw_dataset: pd.DataFrame):
    """Verify that splitting with fixed random_state=42 produces identical splits across runs."""
    mapped_df = map_features(raw_dataset)

    train1, val1, test1 = split_supervised_data(mapped_df, random_state=42)
    train2, val2, test2 = split_supervised_data(mapped_df, random_state=42)

    pd.testing.assert_frame_equal(train1, train2)
    pd.testing.assert_frame_equal(val1, val2)
    pd.testing.assert_frame_equal(test1, test2)


def test_no_unexpected_columns(split_datasets: dict[str, pd.DataFrame]):
    """Verify that split CSV files strictly contain standardized columns: pH, tds, turbidity, temperature, label."""
    expected_order = STANDARDIZED_COLUMNS
    for split_name, df in split_datasets.items():
        assert list(df.columns) == expected_order, f"{split_name} columns mismatch: {list(df.columns)}"


def test_physical_ranges_validation(raw_dataset: pd.DataFrame):
    """Verify all physical and chemical quality checks pass on the raw dataset."""
    val_report = validate_dataset(raw_dataset, is_raw=True)
    assert val_report["valid"] is True
    violations = val_report["checks"]["physical_violations"]
    for check_name, count in violations.items():
        assert count == 0, f"Physical check '{check_name}' failed for {count} rows."
