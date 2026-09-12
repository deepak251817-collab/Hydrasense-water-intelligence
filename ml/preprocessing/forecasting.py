"""Chronological forecasting dataset preparation utilities (Phase 5D-1).

This module provides the pure, deterministic building blocks that Phase 5D-1
defines for future water-quality deterioration forecasting:

- chronological frame preparation (timestamp parsing, station-aware sorting)
- past-only lag / rolling / recent-change feature construction
- a documented rule-based FUTURE deterioration target
- a chronological 70/15/15 train/validation/test split

LEAKAGE CONTRACT (mandatory, enforced by tests in ml/tests/test_forecasting_dataset.py):
- Input features use ONLY observations available at or before prediction time.
  Lag and rolling features are computed with shift()/shift(1)+rolling() so the
  current row's own future values (and any later row) can never contribute.
- The deterioration target MAY use future observations (shift(-horizon)) for
  label creation ONLY. Future-shifted values are never written to feature
  columns and the target column is never part of the feature set.
- Splits are chronological: earlier observations never enter a later split.

SCOPE NOTE (Phase 5D-1): No suitable real chronological dataset exists in the
project yet (see ml/scripts/inspect_forecasting_dataset.py). These utilities
are therefore validated on synthetic in-test series only, and NO forecast_*.csv
artifacts are produced in this phase. No timestamps, stations, or measurements
are fabricated anywhere in the shipped pipeline.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Schema constants (Phase 5D-1 output contract)
# ---------------------------------------------------------------------------
STATION_COLUMN = "station"
TIMESTAMP_COLUMN = "timestamp"

CORE_PARAMETERS = ["pH", "turbidity", "tds", "temperature"]

# All parameter names the pipeline recognizes (specific_conductance is a
# DISTINCT measurement - it is never renamed to or conflated with tds).
KNOWN_PARAMETERS = ["pH", "turbidity", "tds", "temperature", "specific_conductance"]

TARGET_COLUMN = "deterioration_target"

# Default future horizon: deterioration is evaluated against the NEXT
# observation of the same station (horizon=1).
DEFAULT_HORIZON = 1

# Default deterioration thresholds (documented rule, see make_deterioration_target):
# - turbidity / tds: relative increase greater than this fraction
# - pH: increase in distance from neutral (pH 7) greater than this many pH units
DEFAULT_RELATIVE_THRESHOLD = 0.10
DEFAULT_PH_ABSOLUTE_THRESHOLD = 0.20

# Chronological split fractions (spec Phase 5D-1 section 9)
TRAIN_FRACTION = 0.70
VALIDATION_FRACTION = 0.15
TEST_FRACTION = 0.15

SPLIT_COLUMN = "split"

# Every engineered feature is documented here (spec section 6).
FEATURE_DEFINITIONS: Dict[str, str] = {
    "pH": "Current pH measurement (available at prediction time).",
    "turbidity": "Current turbidity measurement in NTU (available at prediction time).",
    "tds": "Current total dissolved solids measurement in ppm (available at prediction time).",
    "temperature": "Current temperature measurement in degrees Celsius (available at prediction time).",
    "{param}_lag_{k}": "Value of {param} exactly k observations earlier at the same station "
                       "(past only; NaN when no such observation exists).",
    "{param}_roll_mean_{w}": "Mean of the w observations strictly BEFORE the current one at the same "
                             "station (current value excluded via shift(1); past only).",
    "{param}_roll_std_{w}": "Sample standard deviation of the w observations strictly BEFORE the "
                            "current one at the same station (past only).",
    "{param}_change_1": "Difference between the current and the previous observation of {param} "
                        "at the same station (recent change; past only).",
}


def prepare_chronological_frame(
    df: pd.DataFrame,
    station_col: str,
    timestamp_col: str,
    param_mapping: Dict[str, str],
    required_parameters: List[str] | None = None,
) -> tuple[pd.DataFrame, Dict[str, Any]]:
    """Validate, standardize, and chronologically sort a raw sensor dataset.

    Parameters
    ----------
    df : pd.DataFrame
        Raw dataset with station, timestamp, and parameter columns.
    station_col : str
        Name of the station/site identifier column in ``df``.
    timestamp_col : str
        Name of the timestamp column in ``df``.
    param_mapping : Dict[str, str]
        Mapping from standardized parameter name to the source column name.
        Only supported, explicit aliases may be mapped; no conductivity-to-TDS
        conversion is performed anywhere in this module (specific conductance
        is retained as its own distinct measurement).
    required_parameters : List[str] | None
        Parameters this dataset must provide (defaults to CORE_PARAMETERS).
        A genuinely missing parameter must be REPORTED, never fabricated.

    Returns
    -------
    (prepared_df, meta)
        prepared_df has standardized columns [station, timestamp, *parameters],
        parseable timestamps, sorted by (station, timestamp) with a reset index.
        meta reports dropped unparseable-timestamp rows, removed duplicate
        (station, timestamp) records (first kept), and missing-value counts
        (missing values are NEVER imputed or fabricated in this phase).
    """
    meta: Dict[str, Any] = {}
    parameters = list(required_parameters) if required_parameters else list(CORE_PARAMETERS)

    missing_cols = [c for c in [station_col, timestamp_col, *param_mapping.values()] if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required source columns: {missing_cols}")
    missing_params = [p for p in parameters if p not in param_mapping]
    if missing_params:
        # A genuinely missing parameter must be REPORTED, never fabricated.
        raise ValueError(f"Core parameters missing from mapping (must not be fabricated): {missing_params}")

    out = df[[station_col, timestamp_col, *param_mapping.values()]].copy()
    out.columns = [STATION_COLUMN, TIMESTAMP_COLUMN, *parameters]

    # 1. Consistent timestamp parsing (UTC-normalized).
    ts = pd.to_datetime(out[TIMESTAMP_COLUMN], errors="coerce", utc=True)
    unparseable = int(ts.isna().sum())
    meta["unparseable_timestamp_rows_dropped"] = unparseable
    out[TIMESTAMP_COLUMN] = ts
    out = out.dropna(subset=[TIMESTAMP_COLUMN])

    # 2. Duplicate (station, timestamp) records: keep the first occurrence so
    #    lag/rolling windows have well-defined ordering. Count is reported.
    before = len(out)
    out = out.drop_duplicates(subset=[STATION_COLUMN, TIMESTAMP_COLUMN], keep="first")
    meta["duplicate_station_timestamp_rows_removed"] = int(before - len(out))

    # 3. Missing values: reported, NOT imputed (no synthetic fill values).
    meta["missing_values_per_parameter"] = {
        p: int(out[p].isna().sum()) for p in parameters
    }

    # 4. Strict chronological ordering per station.
    out = out.sort_values([STATION_COLUMN, TIMESTAMP_COLUMN], kind="mergesort").reset_index(drop=True)

    # 5. Verify ordering (guarantee, not assumption).
    sorted_check = out.sort_values([STATION_COLUMN, TIMESTAMP_COLUMN], kind="mergesort")
    if not sorted_check.index.equals(out.index):
        raise RuntimeError("Internal error: chronological ordering verification failed.")

    meta["rows"] = int(len(out))
    meta["stations"] = int(out[STATION_COLUMN].nunique())
    meta["parameters"] = list(parameters)
    meta["date_range"] = {
        "min": str(out[TIMESTAMP_COLUMN].min()),
        "max": str(out[TIMESTAMP_COLUMN].max()),
    }
    return out, meta


def add_lag_features(
    df: pd.DataFrame,
    lags: tuple[int, ...] = (1,),
    parameters: List[str] | None = None,
) -> pd.DataFrame:
    """Add past-only lag features per station.

    For each parameter p and lag k, adds ``p_lag_k`` = value of p exactly k
    observations earlier at the same station (pandas shift(k) inside each
    station group). Uses ONLY past observations; NaN at the start of each
    station series where no such past observation exists. Never uses future
    values (negative shifts are never applied to feature columns).
    """
    params = list(parameters) if parameters else [c for c in df.columns if c in KNOWN_PARAMETERS]
    out = df.copy()
    for p in params:
        if p not in out.columns:
            raise ValueError(f"Parameter column '{p}' not found.")
        grouped = out.groupby(STATION_COLUMN, sort=False)[p]
        for k in lags:
            if k < 1:
                raise ValueError(f"Lag must be >= 1 (past only); got {k}.")
            out[f"{p}_lag_{k}"] = grouped.shift(k)
    return out


def add_rolling_features(
    df: pd.DataFrame,
    windows: tuple[int, ...] = (3,),
    parameters: List[str] | None = None,
) -> pd.DataFrame:
    """Add past-only rolling mean and standard deviation features per station.

    For each parameter p and window w:
    - ``p_roll_mean_w``: mean of the w observations strictly BEFORE the current
      row (computed as shift(1).rolling(w) so the current value is excluded).
    - ``p_roll_std_w``: sample standard deviation (ddof=1) of the same window.
    ``min_periods=w`` guarantees a complete past-only window; otherwise NaN.
    """
    params = list(parameters) if parameters else [c for c in df.columns if c in KNOWN_PARAMETERS]
    out = df.copy()
    for p in params:
        if p not in out.columns:
            raise ValueError(f"Parameter column '{p}' not found.")
        for w in windows:
            if w < 2:
                raise ValueError(f"Rolling window must be >= 2; got {w}.")

            # Past-only window: shift(1) excludes the current value, so the
            # rolling statistic sees only the w observations BEFORE this row.
            past = out.groupby(STATION_COLUMN, sort=False)[p].shift(1)
            grp = past.groupby(out[STATION_COLUMN], sort=False)
            out[f"{p}_roll_mean_{w}"] = grp.transform(lambda s: s.rolling(w, min_periods=w).mean())
            out[f"{p}_roll_std_{w}"] = grp.transform(lambda s: s.rolling(w, min_periods=w).std(ddof=1))
    return out


def add_recent_change_features(df: pd.DataFrame, parameters: List[str] | None = None) -> pd.DataFrame:
    """Add recent-change features per station.

    ``p_change_1`` = current value minus previous value (diff(1) within each
    station series). Uses the current measurement (available at prediction
    time) and the immediately preceding observation (past only).
    """
    params = list(parameters) if parameters else [c for c in df.columns if c in KNOWN_PARAMETERS]
    out = df.copy()
    for p in params:
        if p not in out.columns:
            raise ValueError(f"Parameter column '{p}' not found.")
        out[f"{p}_change_1"] = out.groupby(STATION_COLUMN, sort=False)[p].diff(1)
    return out


def get_feature_columns(lags: tuple[int, ...] = (1,), windows: tuple[int, ...] = (3,)) -> List[str]:
    """Return the exact feature column contract (target is NEVER included)."""
    cols = list(CORE_PARAMETERS)
    for p in CORE_PARAMETERS:
        cols.extend(f"{p}_lag_{k}" for k in lags)
        cols.extend(f"{p}_roll_mean_{w}" for w in windows)
        cols.extend(f"{p}_roll_std_{w}" for w in windows)
        cols.append(f"{p}_change_1")
    return cols


# Columns that must never be used as model inputs (target-derived data)
FORBIDDEN_FEATURE_PATTERNS = (TARGET_COLUMN, "actual_deterioration", "predicted_deterioration", "prediction_probability")


def resolve_feature_columns(
    df: pd.DataFrame,
    target_col: str = TARGET_COLUMN,
    parameters: List[str] | None = None,
) -> List[str]:
    """Resolve the Phase 5D-1 feature schema present in a forecast split CSV.

    Accepts the 5D-1 contract columns (station, timestamp, parameter columns,
    their lag/rolling/change features) and returns model input columns, enforcing:
    - identifier columns (station, timestamp) are metadata, NOT model inputs;
    - the deterioration target is NEVER a feature (leakage rule);
    - no unknown extra columns are silently consumed (contract integrity).

    ``parameters`` selects the expected parameter set; by default it is
    inferred from the KNOWN_PARAMETERS present in the frame (e.g. the USGS
    dataset provides specific_conductance instead of tds). Raises ValueError
    when required 5D-1 columns are missing, when no known parameter exists,
    when the target column (or any target-derived column) appears among
    candidate features, or when a column is not a 5D-1 current-parameter or
    engineered derivative.
    """
    required_meta = [STATION_COLUMN, TIMESTAMP_COLUMN]
    missing_meta = [c for c in required_meta if c not in df.columns]
    if missing_meta:
        raise ValueError(f"Missing Phase 5D-1 identifier columns: {missing_meta}")
    if target_col not in df.columns:
        raise ValueError(f"Target column '{target_col}' missing (Phase 5D-1 output required).")

    params = list(parameters) if parameters else [p for p in KNOWN_PARAMETERS if p in df.columns]
    if not params:
        raise ValueError(f"No known parameter columns found (expected one of: {KNOWN_PARAMETERS}).")
    missing_params = [p for p in params if p not in df.columns]
    if missing_params:
        raise ValueError(f"Missing core parameter columns: {missing_params}")

    feature_cols = [c for c in df.columns if c not in required_meta + [target_col]]

    # Reject target-derived columns outright (data-leakage protection).
    lower = {c.lower() for c in feature_cols}
    for pattern in FORBIDDEN_FEATURE_PATTERNS:
        if pattern.lower() in lower:
            raise ValueError(
                f"Target-derived column '{pattern}' cannot be a model input (data leakage)."
            )

    # Contract integrity: every feature must be a current parameter or an
    # engineered derivative built by Phase 5D-1 from exactly one parameter.
    allowed_derivations = ("_lag_", "_roll_mean_", "_roll_std_", "_change_")
    for col in feature_cols:
        if col in KNOWN_PARAMETERS:
            continue
        if not any(col.startswith(p + "_") and any(d in col for d in allowed_derivations) for p in KNOWN_PARAMETERS):
            raise ValueError(
                f"Column '{col}' is not part of the Phase 5D-1 feature contract "
                "(current parameters, lag, rolling, or recent-change features)."
            )
    return feature_cols


def make_deterioration_target(
    df: pd.DataFrame,
    horizon: int = DEFAULT_HORIZON,
    relative_threshold: float = DEFAULT_RELATIVE_THRESHOLD,
    ph_absolute_threshold: float = DEFAULT_PH_ABSOLUTE_THRESHOLD,
    conductance_column: str = "tds",
) -> pd.DataFrame:
    """Create the FUTURE deterioration target (label-only use of future data).

    Documented target-generation rule (Phase 5D-1):
    For each station and each row t, let t+h be the observation exactly
    ``horizon`` steps later at the SAME station. The target is 1 (deterioration
    indicator) if ANY of the following holds between t and t+h; otherwise 0:

    - turbidity increases by at least ``relative_threshold`` (relative):
          turbidity[t+h] >= turbidity[t] * (1 + relative_threshold)
    - the conductance-type column increases by at least ``relative_threshold``
      (relative). ``conductance_column`` selects which measurement plays this
      role: "tds" in the original Phase 5D-1 design, or "specific_conductance"
      for the USGS dataset (specific conductance is used AS-IS in uS/cm - it is
      NEVER converted to or labeled as TDS):
          <conductance_column>[t+h] >= <conductance_column>[t] * (1 + relative_threshold)
    - pH moves FURTHER from neutral (pH 7) by more than
      ``ph_absolute_threshold`` pH units (absolute):
          |pH[t+h] - 7| > |pH[t] - 7| + ph_absolute_threshold
    - temperature is deliberately EXCLUDED from the rule: warmer or cooler is
      not inherently worse, so no deterioration direction is invented.

    The result is a rule-based "future water-quality condition" indicator for
    THIS dataset's labeling rule. It is NOT a validated contamination,
    pollution, or potability measure.

    Leakage guarantee: future observations are read with shift(-horizon) for
    LABEL CREATION ONLY. No future-shifted value is ever written to a feature
    column. The target is NaN when the future observation does not exist
    (end of a station series - never filled with 0), crosses no station
    boundary (grouped), or when any value needed by the rule is missing -
    missing values are never fabricated.
    """
    if horizon < 1:
        raise ValueError(f"Horizon must be >= 1; got {horizon}.")
    if conductance_column not in df.columns:
        raise ValueError(
            f"Conductance-type column '{conductance_column}' not found (it triggers the "
            "relative-increase rule; specific_conductance is used as-is, never converted to TDS)."
        )

    out = df.copy()
    g = out.groupby(STATION_COLUMN, sort=False)

    turb_now, turb_next = out["turbidity"], g["turbidity"].shift(-horizon)
    cond_now = out[conductance_column]
    cond_next = g[conductance_column].shift(-horizon)
    ph_now, ph_next = out["pH"], g["pH"].shift(-horizon)

    needed = pd.concat([turb_now, turb_next, cond_now, cond_next, ph_now, ph_next], axis=1)
    valid = needed.notna().all(axis=1)

    turb_worse = turb_next >= turb_now * (1.0 + relative_threshold)
    cond_worse = cond_next >= cond_now * (1.0 + relative_threshold)
    ph_worse = (ph_next - 7.0).abs() > (ph_now - 7.0).abs() + ph_absolute_threshold

    deteriorates = (turb_worse | cond_worse | ph_worse).astype(float)
    deteriorates = deteriorates.where(valid)  # NaN where the rule cannot be evaluated

    out[TARGET_COLUMN] = deteriorates
    return out


def chronological_split(
    df: pd.DataFrame,
    train_fraction: float = TRAIN_FRACTION,
    validation_fraction: float = VALIDATION_FRACTION,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Split chronologically into train/validation/test (70/15/15 default).

    Global timestamp boundaries are computed as quantiles of the sorted unique
    timestamps, so ALL rows sharing a boundary timestamp land in the same
    split (no overlap, no random shuffling):

    - train:      timestamp <= train_boundary        (earliest ~70%)
    - validation: train_boundary < ts <= val_boundary (next ~15%)
    - test:       timestamp > val_boundary           (latest ~15%)

    Station identity is preserved: the station column stays in every split and
    each split remains sortable by (station, timestamp). Later observations
    can never enter training for earlier prediction points.

    Returns (train_df, val_df, test_df, meta) where meta documents the exact
    boundary timestamps and resulting row counts.
    """
    if not (0.0 < train_fraction < 1.0 and 0.0 < validation_fraction
            and train_fraction + validation_fraction < 1.0):
        raise ValueError(
            "Fractions must satisfy 0 < train, 0 < validation, and "
            "train + validation < 1.0 (test is the remainder)."
        )

    ts = df[TIMESTAMP_COLUMN]
    unique_sorted = np.sort(ts.unique())
    train_boundary = pd.Timestamp(unique_sorted[int(len(unique_sorted) * train_fraction)])
    val_boundary = pd.Timestamp(
        unique_sorted[int(len(unique_sorted) * (train_fraction + validation_fraction))]
    )

    train_df = df[ts <= train_boundary].copy()
    val_df = df[(ts > train_boundary) & (ts <= val_boundary)].copy()
    test_df = df[ts > val_boundary].copy()

    for part in (train_df, val_df, test_df):
        part.sort_values([STATION_COLUMN, TIMESTAMP_COLUMN], kind="mergesort", inplace=True)
        part.reset_index(drop=True, inplace=True)

    meta = {
        "train_boundary": str(train_boundary),
        "validation_boundary": str(val_boundary),
        "train_rows": int(len(train_df)),
        "validation_rows": int(len(val_df)),
        "test_rows": int(len(test_df)),
    }
    return train_df, val_df, test_df, meta


def target_distribution(df: pd.DataFrame) -> Dict[str, Any]:
    """Report deterioration target counts/percentages (spec section 11)."""
    counts = df[TARGET_COLUMN].value_counts(dropna=True).to_dict()
    total = int(sum(counts.values()))
    return {
        "counts": {str(k): int(v) for k, v in sorted(counts.items())},
        "percentages": {
            str(k): (round(100.0 * v / total, 2) if total else 0.0) for k, v in sorted(counts.items())
        },
        "evaluable_rows": total,
        "not_evaluable_rows_nan": int(df[TARGET_COLUMN].isna().sum()),
    }


def build_forecasting_dataset(
    df: pd.DataFrame,
    station_col: str,
    timestamp_col: str,
    param_mapping: Dict[str, str],
    lags: tuple[int, ...] = (1,),
    windows: tuple[int, ...] = (3,),
    horizon: int = DEFAULT_HORIZON,
    required_parameters: List[str] | None = None,
    conductance_column: str = "tds",
) -> tuple[pd.DataFrame, Dict[str, Any]]:
    """End-to-end chronological dataset assembly (deterministic, no shuffling).

    Order of operations guarantees the leakage contract: features are built
    from past observations first; the target is added last using future
    observations for label creation only.

    ``required_parameters`` selects the dataset's parameter set (defaults to
    the four original CORE_PARAMETERS). ``conductance_column`` selects the
    measurement that triggers the relative-increase deterioration rule ("tds"
    for the original design, "specific_conductance" for the USGS dataset).
    """
    prepared, meta = prepare_chronological_frame(
        df, station_col, timestamp_col, param_mapping, required_parameters=required_parameters
    )
    params = meta["parameters"]
    prepared = add_lag_features(prepared, lags=lags, parameters=params)
    prepared = add_rolling_features(prepared, windows=windows, parameters=params)
    prepared = add_recent_change_features(prepared, parameters=params)
    prepared = make_deterioration_target(prepared, horizon=horizon, conductance_column=conductance_column)
    meta["lags"] = list(lags)
    meta["rolling_windows"] = list(windows)
    meta["horizon"] = horizon
    return prepared, meta
