"""Supervised Water Quality Dataset Preparation & Validation Module.

Handles schema validation, physical range sanity checks, feature mapping,
reproducible stratified train/val/test splitting, and leakage-safe preprocessing
for supervised water-quality classification (Phase 5C-1).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

logger = logging.getLogger(__name__)

# Raw dataset schema expectations
EXPECTED_RAW_COLUMNS = ["pH", "TDS_ppm", "Turbidity_NTU", "Temperature_C", "Label"]
RAW_FEATURE_COLUMNS = ["pH", "TDS_ppm", "Turbidity_NTU", "Temperature_C"]
RAW_TARGET_COLUMN = "Label"

# Standardized project-facing schema mapping
RAW_TO_PROJECT_COLUMN_MAPPING = {
    "pH": "pH",
    "TDS_ppm": "tds",
    "Turbidity_NTU": "turbidity",
    "Temperature_C": "temperature",
    "Label": "label",
}

STANDARDIZED_COLUMNS = ["pH", "tds", "turbidity", "temperature", "label"]
STANDARDIZED_FEATURE_COLUMNS = ["pH", "tds", "turbidity", "temperature"]
STANDARDIZED_TARGET_COLUMN = "label"

EXPECTED_LABELS = {"Safe", "Unsafe"}

# Physical boundary definitions for sanity checks
PHYSICAL_BOUNDS = {
    "pH": (0.0, 14.0),
    "tds": (0.0, 100000.0),  # Non-negative TDS
    "turbidity": (0.0, 5000.0),  # Non-negative Turbidity
    "temperature": (-10.0, 60.0),  # Valid liquid water temperatures
}


def map_features(df: pd.DataFrame) -> pd.DataFrame:
    """Map raw dataset column names to standardized project parameters.

    Does not modify the original DataFrame.
    """
    mapped_df = df.copy()
    mapped_df = mapped_df.rename(columns=RAW_TO_PROJECT_COLUMN_MAPPING)
    return mapped_df


def validate_dataset(df: pd.DataFrame, is_raw: bool = True) -> Dict[str, Any]:
    """Validate dataset structure, types, missing values, duplicates, and physical bounds.

    Parameters
    ----------
    df : pd.DataFrame
        Dataset to validate.
    is_raw : bool
        If True, expects raw column names (pH, TDS_ppm, ...).
        If False, expects standardized names (pH, tds, ...).

    Returns
    -------
    Dict[str, Any]
        Dictionary with validation results and flags.
    """
    expected_cols = EXPECTED_RAW_COLUMNS if is_raw else STANDARDIZED_COLUMNS
    feature_cols = RAW_FEATURE_COLUMNS if is_raw else STANDARDIZED_FEATURE_COLUMNS
    target_col = RAW_TARGET_COLUMN if is_raw else STANDARDIZED_TARGET_COLUMN

    report: Dict[str, Any] = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "checks": {},
    }

    # 1. Column presence check
    missing_cols = [c for c in expected_cols if c not in df.columns]
    unexpected_cols = [c for c in df.columns if c not in expected_cols]
    report["checks"]["column_presence"] = len(missing_cols) == 0
    if missing_cols:
        report["valid"] = False
        report["errors"].append(f"Missing required columns: {missing_cols}")
    if unexpected_cols:
        report["warnings"].append(f"Unexpected extra columns found: {unexpected_cols}")

    # 2. Target presence & labels check
    if target_col in df.columns:
        unique_labels = set(df[target_col].dropna().unique())
        unexpected_labels = unique_labels - EXPECTED_LABELS
        report["checks"]["target_present"] = True
        report["checks"]["unexpected_labels"] = list(unexpected_labels)
        if unexpected_labels:
            report["valid"] = False
            report["errors"].append(f"Unexpected label values found: {unexpected_labels}")
    else:
        report["valid"] = False
        report["checks"]["target_present"] = False
        report["errors"].append(f"Target column '{target_col}' not found.")

    # 3. Numeric feature types check
    non_numeric_features = []
    for col in feature_cols:
        if col in df.columns:
            if not np.issubdtype(df[col].dtype, np.number):
                # Try coercion check
                coerced = pd.to_numeric(df[col], errors="coerce")
                if coerced.isnull().sum() > 0:
                    non_numeric_features.append(col)
    report["checks"]["non_numeric_features"] = non_numeric_features
    if non_numeric_features:
        report["valid"] = False
        report["errors"].append(f"Features with non-numeric values: {non_numeric_features}")

    # 4. Missing values check
    missing_counts = df.isnull().sum().to_dict()
    total_missing = sum(missing_counts.values())
    report["checks"]["missing_counts"] = missing_counts
    report["checks"]["total_missing"] = total_missing
    if total_missing > 0:
        report["valid"] = False
        report["errors"].append(f"Dataset contains {total_missing} missing values: {missing_counts}")

    # 5. Duplicate checks
    exact_duplicates = int(df.duplicated().sum())
    feature_duplicates = int(df.duplicated(subset=[c for c in feature_cols if c in df.columns]).sum())
    report["checks"]["exact_duplicates"] = exact_duplicates
    report["checks"]["feature_duplicates"] = feature_duplicates

    # 6. Physical boundary sanity checks
    col_mapping = {
        "pH": "pH" if "pH" in df.columns else None,
        "tds": "TDS_ppm" if "TDS_ppm" in df.columns else ("tds" if "tds" in df.columns else None),
        "turbidity": "Turbidity_NTU" if "Turbidity_NTU" in df.columns else ("turbidity" if "turbidity" in df.columns else None),
        "temperature": "Temperature_C" if "Temperature_C" in df.columns else ("temperature" if "temperature" in df.columns else None),
    }

    physical_violations: Dict[str, int] = {}

    if col_mapping["pH"]:
        ph_series = pd.to_numeric(df[col_mapping["pH"]], errors="coerce")
        ph_invalid = int(((ph_series < PHYSICAL_BOUNDS["pH"][0]) | (ph_series > PHYSICAL_BOUNDS["pH"][1])).sum())
        physical_violations["invalid_pH"] = ph_invalid

    if col_mapping["tds"]:
        tds_series = pd.to_numeric(df[col_mapping["tds"]], errors="coerce")
        tds_negative = int((tds_series < 0.0).sum())
        physical_violations["negative_tds"] = tds_negative

    if col_mapping["turbidity"]:
        turb_series = pd.to_numeric(df[col_mapping["turbidity"]], errors="coerce")
        turb_negative = int((turb_series < 0.0).sum())
        physical_violations["negative_turbidity"] = turb_negative

    if col_mapping["temperature"]:
        temp_series = pd.to_numeric(df[col_mapping["temperature"]], errors="coerce")
        temp_invalid = int(((temp_series < PHYSICAL_BOUNDS["temperature"][0]) | (temp_series > PHYSICAL_BOUNDS["temperature"][1])).sum())
        physical_violations["unreasonable_temperature"] = temp_invalid

    report["checks"]["physical_violations"] = physical_violations
    for check_name, count in physical_violations.items():
        if count > 0:
            report["valid"] = False
            report["errors"].append(f"Physical range check '{check_name}' failed for {count} rows.")

    return report


def inspect_dataset(df: pd.DataFrame, is_raw: bool = True) -> Dict[str, Any]:
    """Calculate comprehensive dataset inspection metrics, statistics, and class distribution."""
    feature_cols = RAW_FEATURE_COLUMNS if is_raw else STANDARDIZED_FEATURE_COLUMNS
    target_col = RAW_TARGET_COLUMN if is_raw else STANDARDIZED_TARGET_COLUMN

    stats: Dict[str, Any] = {
        "total_rows": int(len(df)),
        "total_columns": int(len(df.columns)),
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "missing_values": {col: int(df[col].isnull().sum()) for col in df.columns},
        "exact_duplicates": int(df.duplicated().sum()),
        "feature_duplicates": int(df.duplicated(subset=[c for c in feature_cols if c in df.columns]).sum()),
        "feature_statistics": {},
        "class_distribution": {},
    }

    # Descriptive statistics for features
    for col in feature_cols:
        if col in df.columns:
            series = pd.to_numeric(df[col], errors="coerce")
            stats["feature_statistics"][col] = {
                "min": float(series.min()),
                "max": float(series.max()),
                "mean": float(series.mean()),
                "median": float(series.median()),
                "std": float(series.std()),
            }

    # Target class distribution
    if target_col in df.columns:
        counts = df[target_col].value_counts().to_dict()
        percentages = (df[target_col].value_counts(normalize=True) * 100.0).to_dict()
        unique_labels = sorted([str(k) for k in counts.keys()])

        safe_count = int(counts.get("Safe", 0))
        unsafe_count = int(counts.get("Unsafe", 0))
        safe_pct = float(percentages.get("Safe", 0.0))
        unsafe_pct = float(percentages.get("Unsafe", 0.0))
        imbalance_ratio = float(unsafe_count / safe_count) if safe_count > 0 else float("inf")

        stats["class_distribution"] = {
            "unique_labels": unique_labels,
            "counts": {k: int(v) for k, v in counts.items()},
            "percentages": {k: round(float(v), 2) for k, v in percentages.items()},
            "safe_count": safe_count,
            "unsafe_count": unsafe_count,
            "safe_percentage": round(safe_pct, 2),
            "unsafe_percentage": round(unsafe_pct, 2),
            "imbalance_ratio": round(imbalance_ratio, 4),
        }

    return stats


def split_supervised_data(
    df: pd.DataFrame,
    test_size: float = 0.30,
    val_ratio_of_test: float = 0.50,
    random_state: int = 42,
    stratify_col: str = "label",
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Generate reproducible, stratified 70% train / 15% validation / 15% test splits.

    Ensures zero row overlap, preserved class proportions, and reproducibility.

    Parameters
    ----------
    df : pd.DataFrame
        The full dataset (with standardized column names).
    test_size : float
        Proportion allocated to combined validation + test (default 0.30 -> 70% train).
    val_ratio_of_test : float
        Fraction of test_size allocated to validation (default 0.50 -> 15% val, 15% test).
    random_state : int
        Seed for deterministic splitting.
    stratify_col : str
        Column to stratify on.

    Returns
    -------
    Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]
        train_df, val_df, test_df
    """
    if stratify_col not in df.columns:
        raise ValueError(f"Stratify column '{stratify_col}' not found in dataframe.")

    # Stage 1: Split 70% train and 30% temp
    train_df, temp_df = train_test_split(
        df,
        test_size=test_size,
        random_state=random_state,
        stratify=df[stratify_col],
    )

    # Stage 2: Split temp into 50% val (15% overall) and 50% test (15% overall)
    val_df, test_df = train_test_split(
        temp_df,
        test_size=val_ratio_of_test,
        random_state=random_state,
        stratify=temp_df[stratify_col],
    )

    # Sanity verify zero overlap
    train_idx = set(train_df.index)
    val_idx = set(val_df.index)
    test_idx = set(test_df.index)

    if len(train_idx.intersection(val_idx)) > 0:
        raise ValueError("Data leakage detected: Train and Validation indices overlap.")
    if len(train_idx.intersection(test_idx)) > 0:
        raise ValueError("Data leakage detected: Train and Test indices overlap.")
    if len(val_idx.intersection(test_idx)) > 0:
        raise ValueError("Data leakage detected: Validation and Test indices overlap.")

    return train_df.copy(), val_df.copy(), test_df.copy()


class SupervisedPreprocessor:
    """Leakage-safe preprocessor for supervised water-quality classification.

    Fits transformations strictly on training features (X_train).
    Validation and test sets are never seen during fitting.
    Guarantees label column is strictly excluded from feature matrix.

    In Phase 5C-1, performs schema validation and identity pass-through,
    establishing an extensible interface for future scalers or encoders.
    """

    def __init__(self, feature_cols: List[str] | None = None) -> None:
        self.feature_cols = feature_cols or list(STANDARDIZED_FEATURE_COLUMNS)
        self.is_fitted: bool = False
        self.feature_names_in_: List[str] = []
        self.n_features_in_: int = 0

    def fit(self, X: pd.DataFrame, y: Any = None) -> "SupervisedPreprocessor":
        """Fit preprocessor strictly on training features X.

        Raises
        ------
        ValueError
            If label/target column is present in feature matrix X.
        """
        # Strict data leakage check: Target must NOT be in X
        if "label" in X.columns or "Label" in X.columns:
            raise ValueError("Target leakage detected: 'label' column present in feature matrix X.")

        missing_cols = [c for c in self.feature_cols if c not in X.columns]
        if missing_cols:
            raise ValueError(f"Missing required feature columns: {missing_cols}")

        self.feature_names_in_ = list(self.feature_cols)
        self.n_features_in_ = len(self.feature_names_in_)
        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Transform feature matrix using fitted parameters."""
        if not self.is_fitted:
            raise RuntimeError("SupervisedPreprocessor must be fitted before transforming data.")

        if "label" in X.columns or "Label" in X.columns:
            raise ValueError("Target leakage detected: 'label' column present in feature matrix X.")

        # Ensure consistent column ordering and presence
        X_out = X[self.feature_names_in_].copy()
        return X_out

    def fit_transform(self, X: pd.DataFrame, y: Any = None) -> pd.DataFrame:
        """Fit on X and return transformed features."""
        return self.fit(X, y).transform(X)
