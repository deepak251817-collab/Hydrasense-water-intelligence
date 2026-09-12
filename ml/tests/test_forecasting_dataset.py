"""Pytest Test Suite for Forecasting Dataset Preparation (Phase 5D-1).

Covers the Phase 5D-1 specification:
1.  Timestamp parsing (consistent, UTC-normalized, unparseable rows handled)
2.  Chronological sorting (station, timestamp; never shuffled)
3.  Station handling (per-station series, no cross-station windows)
4.  Required feature mapping (pH, turbidity, tds, temperature; no fabrication;
    conductivity is NOT converted to TDS)
5.  Lag correctness (past-only, per-station)
6.  Rolling feature correctness (strictly BEFORE the current row)
7.  No future leakage into features (future values never influence inputs)
8.  Target generation (documented rule; label-only use of future data)
9.  Train/validation/test chronology (global timestamp boundaries)
10. No overlap between splits
11. Target excluded from input feature columns
12. Reproducibility (identical outputs across runs; no randomness)
13. Missing-value handling (reported, never imputed/fabricated)
14. Output schema contract (columns and target rules)
15. STOP-state guardrails: no suitable real dataset exists, therefore no
    forecast_*.csv artifacts must exist and the Phase 5C benchmark must not
    gain fabricated time columns.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.preprocessing.forecasting import (
    CORE_PARAMETERS,
    DEFAULT_HORIZON,
    FEATURE_DEFINITIONS,
    STATION_COLUMN,
    TARGET_COLUMN,
    TIMESTAMP_COLUMN,
    add_lag_features,
    add_recent_change_features,
    add_rolling_features,
    build_forecasting_dataset,
    chronological_split,
    get_feature_columns,
    make_deterioration_target,
    prepare_chronological_frame,
    target_distribution,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = PROJECT_ROOT / "ml" / "data" / "processed"
BENCHMARK_PATH = PROJECT_ROOT / "ml" / "data" / "external" / "water_quality_dataset1.csv"

FORECAST_OUTPUTS = [
    PROCESSED_DIR / "forecast_train.csv",
    PROCESSED_DIR / "forecast_validation.csv",
    PROCESSED_DIR / "forecast_test.csv",
]


# ---------------------------------------------------------------------------
# Helpers: synthetic series (used ONLY inside tests; never shipped as data)
# ---------------------------------------------------------------------------
def make_station_frame(n: int = 12, station: str = "ST-A", seed: int = 0) -> pd.DataFrame:
    """Build a small deterministic per-station series with real timestamps."""
    rng = np.random.RandomState(seed)
    base = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
    return pd.DataFrame({
        "site": [station] * n,
        "measured_at": [base + pd.Timedelta(hours=i) for i in range(n)],
        "pH": 7.0 + rng.uniform(-0.3, 0.3, n),
        "turbidity": 2.0 + rng.uniform(-0.5, 0.5, n),
        "tds": 200.0 + rng.uniform(-20, 20, n),
        "temperature": 25.0 + rng.uniform(-2, 2, n),
    })


@pytest.fixture(scope="module")
def param_mapping() -> dict[str, str]:
    return {"pH": "pH", "turbidity": "turbidity", "tds": "tds", "temperature": "temperature"}


@pytest.fixture(scope="module")
def prepared_two_stations(param_mapping) -> pd.DataFrame:
    df = pd.concat([
        make_station_frame(n=12, station="ST-A", seed=0),
        make_station_frame(n=12, station="ST-B", seed=1),
    ], ignore_index=True)
    out, _ = prepare_chronological_frame(df, "site", "measured_at", param_mapping)
    return out


# ---------------------------------------------------------------------------
# 1. Timestamp parsing
# ---------------------------------------------------------------------------
def test_timestamp_parsing_and_utc_normalization(param_mapping):
    df = pd.DataFrame({
        "site": ["S"] * 3,
        "measured_at": ["2024-01-01 05:00:00+02:00", "2024-01-01 06:00:00+02:00", "not a date"],
        "pH": [7.0, 7.1, 7.2],
        "turbidity": [1.0, 1.1, 1.2],
        "tds": [100.0, 110.0, 120.0],
        "temperature": [20.0, 21.0, 22.0],
    })
    out, meta = prepare_chronological_frame(df, "site", "measured_at", param_mapping)
    assert pd.api.types.is_datetime64_any_dtype(out[TIMESTAMP_COLUMN])
    # +02:00 times normalized to UTC (03:00Z, 04:00Z); unparseable row dropped and reported
    assert out[TIMESTAMP_COLUMN].dt.tz is not None
    assert meta["unparseable_timestamp_rows_dropped"] == 1
    assert len(out) == 2


# ---------------------------------------------------------------------------
# 2. Chronological sorting
# ---------------------------------------------------------------------------
def test_chronological_sorting_by_station_and_timestamp(param_mapping):
    df = pd.concat([make_station_frame(8, "ST-B"), make_station_frame(8, "ST-A")], ignore_index=True)
    df = df.sample(frac=1.0, random_state=7).reset_index(drop=True)  # shuffle input on purpose
    out, _ = prepare_chronological_frame(df, "site", "measured_at", param_mapping)
    for _, group in out.groupby(STATION_COLUMN):
        ts = group[TIMESTAMP_COLUMN].tolist()
        assert ts == sorted(ts), "each station series must be in chronological order"
    # input shuffle must not leak into output ordering (first row = earliest of first station)
    first_station = out[STATION_COLUMN].iloc[0]
    assert out[TIMESTAMP_COLUMN].iloc[0] == out.loc[out[STATION_COLUMN] == first_station, TIMESTAMP_COLUMN].min()


# ---------------------------------------------------------------------------
# 3. Station handling
# ---------------------------------------------------------------------------
def test_station_series_independent_no_cross_station_windows(prepared_two_stations):
    df = add_lag_features(prepared_two_stations, lags=(1,))
    # The first row of each station must have NaN lag (no value borrowed from the other station)
    for station in ("ST-A", "ST-B"):
        first_idx = df.index[df[STATION_COLUMN] == station][0]
        assert pd.isna(df.loc[first_idx, "pH_lag_1"])
        assert pd.isna(df.loc[first_idx, "tds_lag_1"])
    # Second row of each station must lag within the same station
    for station in ("ST-A", "ST-B"):
        rows = df[df[STATION_COLUMN] == station]
        assert rows["pH_lag_1"].iloc[1] == pytest.approx(rows["pH"].iloc[0])


def test_station_count_and_observations_reported(param_mapping):
    df = pd.concat([make_station_frame(10, "S1"), make_station_frame(5, "S2")], ignore_index=True)
    out, meta = prepare_chronological_frame(df, "site", "measured_at", param_mapping)
    assert meta["stations"] == 2
    assert out.groupby(STATION_COLUMN).size().to_dict() == {"S1": 10, "S2": 5}


# ---------------------------------------------------------------------------
# 4. Required feature mapping (no fabrication, no EC->TDS conversion)
# ---------------------------------------------------------------------------
def test_core_parameters_mapped_and_standardized(param_mapping):
    df = make_station_frame(6)
    out, _ = prepare_chronological_frame(df, "site", "measured_at", param_mapping)
    for p in CORE_PARAMETERS:
        assert p in out.columns
    assert set(out.columns) == {STATION_COLUMN, TIMESTAMP_COLUMN, *CORE_PARAMETERS}


def test_missing_core_parameter_raises_instead_of_fabricating(param_mapping):
    df = make_station_frame(6).drop(columns=["temperature"])
    with pytest.raises(ValueError, match="temperature"):
        prepare_chronological_frame(df, "site", "measured_at", param_mapping)


def test_conductivity_is_not_silently_converted_to_tds():
    # A mapping that names a conductivity column for tds must be rejected:
    # Phase 5D-1 forbids unsupported unit conversions.
    df = make_station_frame(6)
    bad_mapping = {"pH": "pH", "turbidity": "turbidity", "tds": "conductivity", "temperature": "temperature"}
    with pytest.raises(ValueError, match="conductivity"):
        prepare_chronological_frame(df, "site", "measured_at", bad_mapping)


# ---------------------------------------------------------------------------
# 5. Lag correctness
# ---------------------------------------------------------------------------
def test_lag_correctness_past_only_per_station(prepared_two_stations):
    df = add_lag_features(prepared_two_stations, lags=(1, 2))
    for station in ("ST-A", "ST-B"):
        rows = df[df[STATION_COLUMN] == station].reset_index(drop=True)
        assert rows["pH_lag_1"].iloc[1] == pytest.approx(rows["pH"].iloc[0])
        assert rows["pH_lag_2"].iloc[2] == pytest.approx(rows["pH"].iloc[0])
        assert rows["tds_lag_1"].iloc[5] == pytest.approx(rows["tds"].iloc[4])
        assert pd.isna(rows["pH_lag_1"].iloc[0]) and pd.isna(rows["pH_lag_2"].iloc[1])


def test_negative_lag_is_rejected(prepared_two_stations):
    with pytest.raises(ValueError, match="past only"):
        add_lag_features(prepared_two_stations, lags=(-1,))


# ---------------------------------------------------------------------------
# 6. Rolling feature correctness
# ---------------------------------------------------------------------------
def test_rolling_mean_excludes_current_value(prepared_two_stations):
    w = 3
    df = add_rolling_features(prepared_two_stations, windows=(w,))
    for station in ("ST-A", "ST-B"):
        rows = df[df[STATION_COLUMN] == station].reset_index(drop=True)
        for i in range(w, len(rows)):  # complete past-only windows start at index w
            expected = rows["turbidity"].iloc[i - w:i].mean()  # strictly BEFORE i
            assert rows[f"turbidity_roll_mean_{w}"].iloc[i] == pytest.approx(expected)
        # incomplete windows are NaN, not partially filled with current values
        assert rows[f"turbidity_roll_mean_{w}"].iloc[:w].isna().all()


def test_rolling_std_matches_manual_window(prepared_two_stations):
    w = 3
    df = add_rolling_features(prepared_two_stations, windows=(w,))
    for station in ("ST-A", "ST-B"):
        rows = df[df[STATION_COLUMN] == station].reset_index(drop=True)
        for i in range(w, len(rows)):
            expected = rows["tds"].iloc[i - w:i].std(ddof=1)
            assert rows[f"tds_roll_std_{w}"].iloc[i] == pytest.approx(expected)


def test_recent_change_feature(prepared_two_stations):
    df = add_recent_change_features(prepared_two_stations)
    for station in ("ST-A", "ST-B"):
        rows = df[df[STATION_COLUMN] == station].reset_index(drop=True)
        assert rows["temperature_change_1"].iloc[3] == pytest.approx(
            rows["temperature"].iloc[3] - rows["temperature"].iloc[2]
        )
        assert pd.isna(rows["temperature_change_1"].iloc[0])


# ---------------------------------------------------------------------------
# 7. No future leakage into features
# ---------------------------------------------------------------------------
def test_features_invariant_to_future_values(param_mapping):
    """Changing ALL FUTURE observations (after time t) must not change any
    feature at time t. This is the core leakage test."""
    df = pd.concat([make_station_frame(20, "ST-X", seed=3)], ignore_index=True)
    base, _ = prepare_chronological_frame(df, "site", "measured_at", param_mapping)
    base = add_lag_features(base, lags=(1, 2))
    base = add_rolling_features(base, windows=(3,))
    base = add_recent_change_features(base)

    t = 10
    mutated = base.copy()
    feature_cols = get_feature_columns(lags=(1, 2), windows=(3,))
    future_rows = mutated.index[mutated[TIMESTAMP_COLUMN] > mutated[TIMESTAMP_COLUMN].iloc[t]]
    for col in CORE_PARAMETERS:
        mutated.loc[future_rows, col] = 9999.0  # extreme future corruption

    for col in feature_cols:
        # features at row t must not depend on values strictly after t
        a = base.loc[t, col]
        b = mutated.loc[t, col]
        if pd.isna(a) and pd.isna(b):
            continue
        assert a == pytest.approx(b), f"feature '{col}' at time t changed when future values changed"


def test_features_only_use_observations_up_to_prediction_time(param_mapping):
    """Truncating the dataset AFTER time t must not change features at t."""
    df = make_station_frame(20, "ST-Y", seed=5)
    full, _ = prepare_chronological_frame(df, "site", "measured_at", param_mapping)
    full = add_lag_features(full, lags=(1,))
    full = add_rolling_features(full, windows=(3,))
    full = add_recent_change_features(full)

    t = 12
    truncated = full[full[TIMESTAMP_COLUMN] <= full[TIMESTAMP_COLUMN].iloc[t]].copy()
    feature_cols = get_feature_columns(lags=(1,), windows=(3,))
    for col in feature_cols:
        a, b = full.loc[t, col], truncated.iloc[-1][col]
        if pd.isna(a) and pd.isna(b):
            continue
        assert a == pytest.approx(b), f"feature '{col}' at t changed when later rows were removed"


# ---------------------------------------------------------------------------
# 8. Target generation
# ---------------------------------------------------------------------------
def test_target_rule_turbidity_spike_within_horizon(param_mapping):
    df = make_station_frame(6, "S", seed=0)
    df.loc[3, "turbidity"] = 2.0
    df.loc[4, "turbidity"] = 5.0  # > +10% relative increase from t=3
    out, _ = prepare_chronological_frame(df, "site", "measured_at", param_mapping)
    labeled = make_deterioration_target(out, horizon=1)
    assert labeled[TARGET_COLUMN].iloc[3] == 1.0
    # stable window: no >10% turb/tds jump, no >0.2 pH shift away from 7
    stable = labeled[(labeled[TARGET_COLUMN] == 0.0)]
    assert len(stable) >= 1


def test_target_rule_pH_moves_further_from_neutral(param_mapping):
    df = make_station_frame(4, "S", seed=1)
    df["pH"] = [7.0, 7.5, 7.5, 7.5]  # t=0 -> t=1: |0.5| > |0.0| + 0.2
    df["turbidity"] = [2.0] * 4
    df["tds"] = [200.0] * 4
    out, _ = prepare_chronological_frame(df, "site", "measured_at", param_mapping)
    labeled = make_deterioration_target(out, horizon=1)
    assert labeled[TARGET_COLUMN].iloc[0] == 1.0


def test_target_is_nan_when_no_future_observation(param_mapping):
    df = make_station_frame(5, "S", seed=2)
    out, _ = prepare_chronological_frame(df, "site", "measured_at", param_mapping)
    labeled = make_deterioration_target(out, horizon=1)
    last_idx = labeled.index[labeled[STATION_COLUMN] == "S"][-1]
    assert pd.isna(labeled.loc[last_idx, TARGET_COLUMN])
    assert labeled.loc[:last_idx - 1, TARGET_COLUMN].notna().all()


def test_target_never_crosses_station_boundary(prepared_two_stations):
    labeled = make_deterioration_target(prepared_two_stations, horizon=1)
    for station in ("ST-A", "ST-B"):
        last_idx = labeled.index[labeled[STATION_COLUMN] == station][-1]
        assert pd.isna(labeled.loc[last_idx, TARGET_COLUMN])


def test_future_observations_only_used_for_labels_not_features(param_mapping):
    """The target exists where future data exists, but no future-shifted value
    is present in any feature column: dropping all rows after t leaves the
    target at t computable only from data already recorded, and every feature
    at t is unchanged when future rows are deleted (covered above). Here we
    additionally assert the target column is absent from the feature contract."""
    assert TARGET_COLUMN not in get_feature_columns(lags=(1, 2), windows=(3,))


def test_temperature_is_not_part_of_deterioration_rule(param_mapping):
    """Temperature must not create deterioration labels (no invented direction)."""
    df = make_station_frame(4, "S", seed=4)
    df["pH"] = [7.0] * 4
    df["turbidity"] = [2.0] * 4
    df["tds"] = [200.0] * 4
    df["temperature"] = [25.0, 60.0, 25.0, 25.0]  # extreme jump must be ignored by the rule
    out, _ = prepare_chronological_frame(df, "site", "measured_at", param_mapping)
    labeled = make_deterioration_target(out, horizon=1)
    assert (labeled[TARGET_COLUMN].dropna() == 0.0).all()


# ---------------------------------------------------------------------------
# 9-10. Chronological split and no overlap
# ---------------------------------------------------------------------------
def test_chronological_split_boundaries_and_no_shuffle(param_mapping):
    n = 100
    df = pd.concat([make_station_frame(n // 2, "A", seed=6), make_station_frame(n // 2, "B", seed=7)],
                   ignore_index=True)
    built, meta = build_forecasting_dataset(df, "site", "measured_at", param_mapping)
    train, val, test, split_meta = chronological_split(built)

    assert len(train) + len(val) + len(test) == len(built)
    # Global time ordering of the splits
    assert train[TIMESTAMP_COLUMN].max() <= val[TIMESTAMP_COLUMN].min()
    assert val[TIMESTAMP_COLUMN].max() <= test[TIMESTAMP_COLUMN].min()
    # Documented boundaries are reported
    assert split_meta["train_boundary"] and split_meta["validation_boundary"]
    # Sizes approximate the 70/15/15 design. Tolerance accommodates timestamp
    # granularity: rows sharing a boundary timestamp must stay in one split.
    assert abs(len(train) / len(built) - 0.70) < 0.05
    assert abs(len(val) / len(built) - 0.15) < 0.05


def test_no_row_overlap_between_splits(param_mapping):
    df = pd.concat([make_station_frame(50, "A", seed=8), make_station_frame(50, "B", seed=9)],
                   ignore_index=True)
    built, _ = build_forecasting_dataset(df, "site", "measured_at", param_mapping)
    train, val, test, _ = chronological_split(built)
    train_keys = set(zip(train[STATION_COLUMN], train[TIMESTAMP_COLUMN]))
    val_keys = set(zip(val[STATION_COLUMN], val[TIMESTAMP_COLUMN]))
    test_keys = set(zip(test[STATION_COLUMN], test[TIMESTAMP_COLUMN]))
    assert not (train_keys & val_keys)
    assert not (train_keys & test_keys)
    assert not (val_keys & test_keys)
    # station identity preserved in every split
    for part in (train, val, test):
        assert {"A", "B"}.issubset(set(part[STATION_COLUMN]))


def test_later_observations_never_enter_training(param_mapping):
    """Every training timestamp must be <= every test timestamp (per station)."""
    df = pd.concat([make_station_frame(40, "A", seed=10), make_station_frame(40, "B", seed=11)],
                   ignore_index=True)
    built, _ = build_forecasting_dataset(df, "site", "measured_at", param_mapping)
    train, _, test, _ = chronological_split(built)
    assert train[TIMESTAMP_COLUMN].max() <= test[TIMESTAMP_COLUMN].min()


# ---------------------------------------------------------------------------
# 11. Target excluded from features
# ---------------------------------------------------------------------------
def test_target_column_excluded_from_feature_columns():
    feature_cols = get_feature_columns()
    assert TARGET_COLUMN not in feature_cols
    assert all(col != TARGET_COLUMN for col in feature_cols)


# ---------------------------------------------------------------------------
# 12. Reproducibility
# ---------------------------------------------------------------------------
def test_build_is_fully_reproducible(param_mapping):
    df = pd.concat([make_station_frame(30, "R1", seed=12), make_station_frame(30, "R2", seed=13)],
                   ignore_index=True)
    built1, _ = build_forecasting_dataset(df, "site", "measured_at", param_mapping)
    built2, _ = build_forecasting_dataset(df, "site", "measured_at", param_mapping)
    pd.testing.assert_frame_equal(built1, built2)


# ---------------------------------------------------------------------------
# 13. Missing-value handling
# ---------------------------------------------------------------------------
def test_missing_values_reported_not_imputed(param_mapping):
    df = make_station_frame(6, "S", seed=14)
    df.loc[2, "tds"] = np.nan
    out, meta = prepare_chronological_frame(df, "site", "measured_at", param_mapping)
    assert meta["missing_values_per_parameter"]["tds"] == 1
    assert out["tds"].isna().sum() == 1  # still NaN: never fabricated
    # downstream: the deterioration rule is NaN where inputs are missing
    labeled = make_deterioration_target(out, horizon=1)
    assert pd.isna(labeled[TARGET_COLUMN].iloc[1])  # t=1 -> t=2 window needs tds[2]
    assert labeled[TARGET_COLUMN].dropna().isin([0.0, 1.0]).all()


def test_duplicate_station_timestamp_removed_and_reported(param_mapping):
    df = make_station_frame(6, "S", seed=15)
    duplicate = df.iloc[[3]].copy()
    duplicate["pH"] = 99.0  # conflicting duplicate: first occurrence must win
    df = pd.concat([df, duplicate], ignore_index=True)
    out, meta = prepare_chronological_frame(df, "site", "measured_at", param_mapping)
    assert meta["duplicate_station_timestamp_rows_removed"] == 1
    assert len(out) == 6
    assert out["pH"].iloc[3] != 99.0


# ---------------------------------------------------------------------------
# 14. Output schema contract
# ---------------------------------------------------------------------------
def test_feature_documentation_exists():
    # Every engineered feature family is documented (spec section 6)
    assert FEATURE_DEFINITIONS["pH"].startswith("Current pH")
    assert "past only" in FEATURE_DEFINITIONS["{param}_lag_{k}"]
    assert "BEFORE" in FEATURE_DEFINITIONS["{param}_roll_mean_{w}"]
    assert "recent change" in FEATURE_DEFINITIONS["{param}_change_1"]


def test_forecast_output_schema(param_mapping):
    """The full pipeline emits exactly the documented columns (plus target),
    in a deterministic order, on the synthetic validation series."""
    df = pd.concat([make_station_frame(30, "A", seed=16), make_station_frame(30, "B", seed=17)],
                   ignore_index=True)
    built, meta = build_forecasting_dataset(df, "site", "measured_at", param_mapping,
                                            lags=(1,), windows=(3,), horizon=DEFAULT_HORIZON)
    expected = [STATION_COLUMN, TIMESTAMP_COLUMN, *CORE_PARAMETERS]
    # Build order: all lags (per param), then per param (roll_mean, roll_std),
    # then all recent changes (per param).
    expected += [f"{p}_lag_1" for p in CORE_PARAMETERS]
    for p in CORE_PARAMETERS:
        expected += [f"{p}_roll_mean_3", f"{p}_roll_std_3"]
    expected += [f"{p}_change_1" for p in CORE_PARAMETERS]
    expected.append(TARGET_COLUMN)
    assert list(built.columns) == expected
    assert meta["horizon"] == DEFAULT_HORIZON
    # target binary where evaluable
    assert built[TARGET_COLUMN].dropna().isin([0.0, 1.0]).all()


def test_target_distribution_report_shape(param_mapping):
    df = make_station_frame(20, "S", seed=18)
    built, _ = build_forecasting_dataset(df, "site", "measured_at", param_mapping)
    dist = target_distribution(built)
    assert set(dist["counts"].keys()) <= {"0.0", "1.0"}
    assert dist["evaluable_rows"] + dist["not_evaluable_rows_nan"] == len(built)
    for pct in dist["percentages"].values():
        assert 0.0 <= pct <= 100.0


# ---------------------------------------------------------------------------
# 15. Dataset-state guardrails (USGS edition: a real dataset NOW exists)
# ---------------------------------------------------------------------------
USGS_COMBINED = PROCESSED_DIR / "usgs_timeseries_combined.csv"
USGS_STATION = "USGS-01649190"


def test_usgs_forecast_artifacts_exist_from_real_data():
    """A real chronological dataset (USGS station USGS-01649190) has been
    prepared: the combined dataset and the three chronological forecast splits
    must exist and be non-empty."""
    for path in [*FORECAST_OUTPUTS, USGS_COMBINED]:
        assert path.is_file(), f"{path.name} missing - run ml/scripts/prepare_usgs_forecast_dataset.py"
        assert path.stat().st_size > 0


def test_usgs_forecast_splits_have_consistent_schema():
    """Split files must carry the 5D-1 contract: station, timestamp, the four
    USGS measurements (specific_conductance as a DISTINCT measurement, NOT
    tds), engineered features, and the deterioration target."""
    required = {"station", "timestamp", "pH", "turbidity", "temperature",
                "specific_conductance", TARGET_COLUMN}
    for path in FORECAST_OUTPUTS:
        df = pd.read_csv(path, nrows=5)
        assert required.issubset(df.columns), f"{path.name} missing columns: {required - set(df.columns)}"
        assert "tds" not in df.columns, "specific_conductance must not be renamed to tds"


def test_usgs_combined_is_synchronized_and_chronological():
    """The combined file must contain only synchronized (station, timestamp)
    rows present in ALL FOUR source files, sorted by (station, timestamp)."""
    combined = pd.read_csv(USGS_COMBINED)
    assert list(combined.columns) == ["station", "timestamp", "pH", "turbidity",
                                      "temperature", "specific_conductance"]
    # chronological order
    ts = pd.to_datetime(combined["timestamp"], utc=True)
    ordered = combined.assign(_ts=ts).sort_values(["station", "_ts"], kind="mergesort")
    assert ordered.index.tolist() == list(range(len(combined)))
    # every row synchronized across all four parameters (inner join => no NaN)
    assert combined[["pH", "turbidity", "temperature", "specific_conductance"]].notna().all().all()
    # matches source timestamps: spot-check first/last against the pH file
    ph = pd.read_csv(PROJECT_ROOT / "ml" / "data" / "external" / "usgs_ph_2024.csv", usecols=["time"])
    ph_ts = set(pd.to_datetime(ph["time"], utc=True))
    temp = pd.read_csv(PROJECT_ROOT / "ml" / "data" / "external" / "usgs_temperature_2024.csv", usecols=["time"])
    temp_ts = set(pd.to_datetime(temp["time"], utc=True))
    combined_ts = set(ts)
    assert combined_ts <= (ph_ts & temp_ts), "combined timestamps must exist in BOTH source files"
    assert combined["station"].nunique() == 1 and combined["station"].iloc[0] == USGS_STATION


def test_usgs_no_synthetic_gap_filling():
    """Gaps must remain gaps: the row count must match the exact count of
    synchronized source timestamps (no synthetic observations inserted)."""
    combined = pd.read_csv(USGS_COMBINED)
    ph = pd.read_csv(PROJECT_ROOT / "ml" / "data" / "external" / "usgs_ph_2024.csv", usecols=["time"])
    turb = pd.read_csv(PROJECT_ROOT / "ml" / "data" / "external" / "usgs_turbidity_2024.csv", usecols=["time"])
    cond = pd.read_csv(PROJECT_ROOT / "ml" / "data" / "external" / "usgs_conductance_2024.csv", usecols=["time"])
    temp = pd.read_csv(PROJECT_ROOT / "ml" / "data" / "external" / "usgs_temperature_2024.csv", usecols=["time"])
    shared = set(pd.to_datetime(ph["time"], utc=True)) \
        & set(pd.to_datetime(turb["time"], utc=True)) \
        & set(pd.to_datetime(cond["time"], utc=True)) \
        & set(pd.to_datetime(temp["time"], utc=True))
    assert len(combined) == len(shared), (
        "combined row count must equal the exact synchronized timestamp intersection; "
        "synthetic gap-filling is forbidden"
    )


def test_usgs_merge_pairs_values_from_the_same_timestamp():
    """Multi-parameter alignment (spec section 17): for sampled synchronized
    timestamps, each measurement in the combined file must equal the source
    file value at THAT timestamp - proving no cross-timestamp pairing."""
    combined = pd.read_csv(USGS_COMBINED)
    sample = combined.sample(n=25, random_state=42)
    sources = {
        "pH": ("usgs_ph_2024.csv", "00400"),
        "turbidity": ("usgs_turbidity_2024.csv", "63680"),
        "temperature": ("usgs_temperature_2024.csv", "00010"),
        "specific_conductance": ("usgs_conductance_2024.csv", "00095"),
    }
    for param, (fname, _code) in sources.items():
        src = pd.read_csv(PROJECT_ROOT / "ml" / "data" / "external" / fname, dtype=str)
        src_ts = pd.to_datetime(src["time"], utc=True)
        src_val = pd.to_numeric(src["value"], errors="coerce")
        lookup = dict(zip(src_ts, src_val))
        for _, row in sample.iterrows():
            row_ts = pd.Timestamp(row["timestamp"])
            assert param in row and pd.notna(row[param])
            assert row[param] == pytest.approx(lookup[row_ts]), (
                f"{param} at {row_ts} in combined does not match the source file value"
            )


def test_usgs_specific_conductance_retained_as_distinct_measurement():
    """Specific conductance is NOT TDS: the outputs keep the
    specific_conductance column with raw uS/cm source values, and no tds
    column or conversion exists anywhere in the artifacts."""
    combined = pd.read_csv(USGS_COMBINED, nrows=50)
    assert "specific_conductance" in combined.columns
    assert "tds" not in combined.columns
    # raw values preserved (compare against the source file, incl. decimals)
    src = pd.read_csv(PROJECT_ROOT / "ml" / "data" / "external" / "usgs_conductance_2024.csv", dtype=str)
    lookup = dict(zip(pd.to_datetime(src["time"], utc=True), src["value"]))
    full = pd.read_csv(USGS_COMBINED)
    for _, row in full.head(20).iterrows():
        row_ts = pd.Timestamp(row["timestamp"])
        assert float(lookup[row_ts]) == pytest.approx(row["specific_conductance"])


def test_usgs_target_reconstructs_from_combined_dataset():
    """The split target must be exactly reproducible from the combined
    dataset with the documented rule (specific conductance triggers the
    relative-increase rule; temperature never does)."""
    combined = pd.read_csv(USGS_COMBINED)
    combined[TIMESTAMP_COLUMN] = pd.to_datetime(combined[TIMESTAMP_COLUMN], utc=True)
    rebuilt = make_deterioration_target(combined, horizon=1, conductance_column="specific_conductance")
    lookup = dict(zip(
        zip(rebuilt[STATION_COLUMN], rebuilt[TIMESTAMP_COLUMN]),
        rebuilt[TARGET_COLUMN],
    ))
    split = pd.read_csv(PROCESSED_DIR / "forecast_test.csv")
    split[TIMESTAMP_COLUMN] = pd.to_datetime(split[TIMESTAMP_COLUMN], utc=True)
    for _, row in split.head(200).iterrows():
        key = (row[STATION_COLUMN], pd.Timestamp(row[TIMESTAMP_COLUMN]))
        assert float(row[TARGET_COLUMN]) == pytest.approx(lookup[key])


def test_inspection_script_reports_stop_when_nothing_suitable(tmp_path: Path):
    """The original inspection script must still conclude STOP (exit 1) when
    shown ONLY unsuitable candidates (proven with a static no-timestamp CSV in
    an isolated directory - the real external dir now contains the USGS files)."""
    import subprocess
    import sys

    static = pd.DataFrame({"pH": [7.0, 7.1], "tds": [100.0, 101.0]})
    static.to_csv(tmp_path / "static_dataset.csv", index=False)
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "ml" / "scripts" / "inspect_forecasting_dataset.py"),
         "--external-dir", str(tmp_path)],
        capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 1, "expected STOP (exit 1) for unsuitable candidates"
    assert "STOP" in result.stdout
    assert "NO SUITABLE FORECASTING DATASET" in result.stdout
    assert "static_dataset.csv" in result.stdout  # candidate was assessed, not skipped


def test_inspection_script_flags_suitable_synthetic_dataset(tmp_path: Path):
    """A genuinely chronological dataset (timestamps + stations + >=50 obs/station)
    IS recognized as suitable - proving the criteria work and were not rigged
    to always return STOP."""
    import subprocess
    import sys

    rng = np.random.RandomState(42)
    rows = []
    for station in ("SITE-1", "SITE-2"):
        base = pd.Timestamp("2023-01-01", tz="UTC")
        n = 60
        rows.append(pd.DataFrame({
            "station_id": [station] * n,
            "observed_at": [base + pd.Timedelta(days=i) for i in range(n)],
            "pH": 7 + rng.uniform(-0.2, 0.2, n),
            "turbidity": 2 + rng.uniform(-0.3, 0.3, n),
            "tds": 200 + rng.uniform(-10, 10, n),
            "temperature": 25 + rng.uniform(-1, 1, n),
        }))
    synthetic = pd.concat(rows, ignore_index=True)
    csv_path = tmp_path / "synthetic_realtime_like.csv"
    synthetic.to_csv(csv_path, index=False)

    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "ml" / "scripts" / "inspect_forecasting_dataset.py"),
         "--external-dir", str(tmp_path)],
        capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, f"expected PROCEED for a suitable dataset; stderr={result.stderr[-500:]}"
    assert "SUITABLE - meets Phase 5D-1" in result.stdout
    assert "60 days" in result.stdout or "dominant=1.0 days" in result.stdout
