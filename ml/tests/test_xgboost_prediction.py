"""Pytest Test Suite for XGBoost Deterioration Prediction (Phase 5D-2).

Covers the Phase 5D-2 specification:
1.  Model trains successfully
2.  Model artifact is created
3.  Model loads successfully (joblib)
4.  Correct target is used (deterioration_target)
5.  Target is not included in input features (leakage protection)
6.  Validation prediction works
7.  Test prediction works
8.  Probability values are valid (numeric, within [0, 1])
9.  Prediction output schema is correct
10. Feature importance contains all model features
11. Model save/load predictions are consistent
12. Reproducibility (same data/params/seed => identical predictions)
13. Training uses only forecast_train.csv
14. No validation/test leakage into training
15. Chronological ordering remains valid

The suite builds a SYNTHETIC chronological dataset (two stations, hourly,
learnable deterioration pattern) strictly inside tmp directories and runs the
real Phase 5D-1 preparation + Phase 5D-2 pipeline on it. No project forecast
CSVs are fabricated: additional guardrail tests assert that the real Phase
5D-1 STOP state (no suitable dataset) still holds and that the 5D-2 scripts
fail loudly - with clear instructions - when real inputs are missing.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
import xgboost as xgb

from ml.preprocessing.forecasting import (
    CORE_PARAMETERS,
    STATION_COLUMN,
    TARGET_COLUMN,
    TIMESTAMP_COLUMN,
    build_forecasting_dataset,
    chronological_split,
    resolve_feature_columns,
)
from ml.scripts.evaluate_xgboost import evaluate_split
from ml.scripts.predict_deterioration import PREDICTION_COLUMNS, predict_deterioration
from ml.scripts.train_xgboost import train_xgboost

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = PROJECT_ROOT / "ml" / "data" / "processed"
REAL_TRAIN = PROCESSED_DIR / "forecast_train.csv"
REAL_VAL = PROCESSED_DIR / "forecast_validation.csv"
REAL_TEST = PROCESSED_DIR / "forecast_test.csv"


# ---------------------------------------------------------------------------
# Synthetic chronological dataset with a LEARNABLE deterioration pattern:
# when turbidity exceeds 3.0 NTU the next observation deteriorates (turbidity
# +25%) with probability 0.8, otherwise turbidity mean-reverts. The target at
# time t therefore depends on the CURRENT turbidity (a legitimate Phase 5D-1
# feature), never on future rows. Other parameters never trigger the rule.
# ---------------------------------------------------------------------------
def make_synthetic_series(n_per_station: int = 200, seed: int = 42) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    frames = []
    for station in ("SITE-1", "SITE-2"):
        base = pd.Timestamp("2023-01-01", tz="UTC")
        turb = 2.0
        rows = []
        for i in range(n_per_station):
            rows.append({
                "site": station,
                "observed_at": base + pd.Timedelta(hours=i),
                "pH": 7.0 + rng.uniform(-0.1, 0.1),        # never triggers pH rule
                "turbidity": turb,
                "tds": 200.0 + rng.uniform(-5, 5),          # never triggers tds rule
                "temperature": 25.0 + rng.uniform(-1, 1),   # excluded from rule
            })
            # Mean-reverting level with a deterministic spike every 25th hour;
            # after a spike the level deteriorates (+25%) with p=0.8 or recovers.
            if i % 25 == 10:
                turb = 3.5
            elif turb > 3.0 and rng.uniform() < 0.8:
                turb = turb * 1.25
            else:
                turb = 2.0 + rng.uniform(-0.2, 0.2)
        frames.append(pd.DataFrame(rows))
    return pd.concat(frames, ignore_index=True)


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    """Build synthetic 5D-1 splits, then run the real 5D-2 pipeline once:
    train -> evaluate (validation) -> evaluate (test) -> predict (test)."""
    workdir = tmp_path_factory.mktemp("xgb_pipeline")
    train_csv = workdir / "forecast_train.csv"
    val_csv = workdir / "forecast_validation.csv"
    test_csv = workdir / "forecast_test.csv"

    df = make_synthetic_series()
    built, _ = build_forecasting_dataset(df, "site", "observed_at",
                                         {"pH": "pH", "turbidity": "turbidity",
                                          "tds": "tds", "temperature": "temperature"},
                                         lags=(1, 2), windows=(3,), horizon=1)
    train_df, val_df, test_df, _ = chronological_split(built)
    assert set(train_df[TARGET_COLUMN].dropna().unique()) == {0.0, 1.0}
    assert set(val_df[TARGET_COLUMN].dropna().unique()) == {0.0, 1.0}
    assert set(test_df[TARGET_COLUMN].dropna().unique()) == {0.0, 1.0}
    train_df.to_csv(train_csv, index=False)
    val_df.to_csv(val_csv, index=False)
    test_df.to_csv(test_csv, index=False)

    model_path = workdir / "xgboost_deterioration.joblib"
    importance_csv = workdir / "xgboost_feature_importance.csv"
    importance_png = workdir / "xgboost_feature_importance.png"
    cm_png = workdir / "xgboost_confusion_matrix.png"
    predictions_csv = workdir / "xgboost_predictions.csv"

    feature_list = workdir / "xgboost_feature_list.txt"
    error_csv = workdir / "xgboost_error_analysis.csv"

    model, feature_cols, importance_df = train_xgboost(
        train_path=train_csv, model_output=model_path,
        importance_output=importance_csv, importance_plot_output=importance_png,
        feature_list_output=feature_list,
        random_state=42,
    )
    val_metrics = evaluate_split(val_csv, model_path=model_path, plot_output=cm_png,
                                 split_name="Validation", threshold=0.2)
    test_metrics = evaluate_split(test_csv, model_path=model_path, plot_output=None,
                                  split_name="Test", threshold=0.2)
    predictions = predict_deterioration(input_path=test_csv, model_path=model_path,
                                        output_path=predictions_csv, error_analysis_path=error_csv,
                                        threshold=0.2)

    return {
        "workdir": workdir,
        "train_csv": train_csv, "val_csv": val_csv, "test_csv": test_csv,
        "model": model, "model_path": model_path,
        "feature_cols": feature_cols, "importance_df": importance_df,
        "importance_csv": importance_csv, "importance_png": importance_png,
        "feature_list": feature_list, "error_csv": error_csv,
        "cm_png": cm_png, "predictions": predictions, "predictions_csv": predictions_csv,
        "val_metrics": val_metrics, "test_metrics": test_metrics,
        "built": built,
    }


# ---------------------------------------------------------------------------
# 1-3. Training, artifact creation, loading
# ---------------------------------------------------------------------------
def test_model_trains_successfully(pipeline):
    assert isinstance(pipeline["model"], xgb.XGBClassifier)
    assert hasattr(pipeline["model"], "classes_")


def test_model_artifact_created(pipeline):
    assert pipeline["model_path"].is_file()
    assert pipeline["model_path"].stat().st_size > 0
    assert pipeline["importance_csv"].is_file()
    assert pipeline["importance_png"].is_file()
    assert pipeline["feature_list"].is_file()
    assert pipeline["error_csv"].is_file()


def test_feature_list_file_content(pipeline):
    """The saved feature list must contain exactly the resolved feature
    columns, one per line (spec section 4)."""
    lines = [ln.strip() for ln in pipeline["feature_list"].read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines == pipeline["feature_cols"]
    assert TARGET_COLUMN not in lines and STATION_COLUMN not in lines and TIMESTAMP_COLUMN not in lines


def test_scale_pos_weight_documented_and_training_only(pipeline):
    """Class-imbalance handling (spec section 6): with the default 'auto',
    scale_pos_weight must equal n_negative/n_positive of the TRAINING split."""
    train_df = pd.read_csv(pipeline["train_csv"]).dropna(subset=[TARGET_COLUMN])
    n_neg = int((train_df[TARGET_COLUMN] == 0).sum())
    n_pos = int((train_df[TARGET_COLUMN] == 1).sum())
    expected_spw = n_neg / n_pos
    model_spw = pipeline["model"].get_params()["scale_pos_weight"]
    assert model_spw == pytest.approx(expected_spw)
    assert model_spw > 1.0  # positive class is rarer, so it is up-weighted


def test_thresholded_labels_match_frozen_threshold(pipeline):
    """Predictions must apply the frozen threshold to probabilities, not the
    model's internal decision rule."""
    preds = pipeline["predictions"]
    ev = preds[preds["predicted_deterioration"].isin([0, 1])]
    expected = (ev["prediction_probability"] >= 0.2).astype(int)
    assert (ev["predicted_deterioration"] == expected).all()


def test_error_analysis_schema_and_consistency(pipeline):
    """Error-analysis CSV must contain only incorrect predictions and match
    the prediction output exactly (spec section 16)."""
    errors = pd.read_csv(pipeline["error_csv"])
    preds = pd.read_csv(pipeline["predictions_csv"])
    assert {"station", "timestamp", "actual_deterioration", "predicted_deterioration",
            "prediction_probability", "error_type"}.issubset(errors.columns)
    # Errors are counted among EVALUABLE rows only (not-predictable rows,
    # predicted = -1 with NaN actual, are excluded by design).
    evaluable = preds["predicted_deterioration"].isin([0, 1])
    mask = evaluable & (preds["actual_deterioration"] != preds["predicted_deterioration"])
    assert len(errors) == int(mask.sum())
    assert set(errors["error_type"].unique()) <= {"false_positive", "false_negative"}
    fp = ((preds["actual_deterioration"] == 0) & (preds["predicted_deterioration"] == 1)).sum()
    fn = ((preds["actual_deterioration"] == 1) & (preds["predicted_deterioration"] == 0)).sum()
    assert (errors["error_type"] == "false_positive").sum() == fp
    assert (errors["error_type"] == "false_negative").sum() == fn


def test_model_loads_with_joblib(pipeline):
    loaded = joblib.load(pipeline["model_path"])
    assert isinstance(loaded, xgb.XGBClassifier)
    assert list(loaded.classes_) == [0, 1]


# ---------------------------------------------------------------------------
# 4-5. Correct target / target never a feature
# ---------------------------------------------------------------------------
def test_correct_target_used(pipeline):
    # The model's input features are exactly the resolved 5D-1 feature schema,
    # which by construction excludes the target and identifier columns.
    model_features = list(pipeline["model"].get_booster().feature_names)
    assert model_features == pipeline["feature_cols"]
    assert TARGET_COLUMN not in model_features
    assert STATION_COLUMN not in model_features and TIMESTAMP_COLUMN not in model_features


def test_target_not_included_in_input_features():
    df = pd.DataFrame({
        STATION_COLUMN: ["S"] * 3,
        TIMESTAMP_COLUMN: pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-03"], utc=True),
        **{p: [1.0, 2.0, 3.0] for p in CORE_PARAMETERS},
        "pH_lag_1": [np.nan, 1.0, 2.0],
        TARGET_COLUMN: [0.0, 1.0, 0.0],
    })
    features = resolve_feature_columns(df)
    assert TARGET_COLUMN not in features
    assert STATION_COLUMN not in features and TIMESTAMP_COLUMN not in features


def test_target_derived_columns_are_rejected_as_features():
    df = pd.DataFrame({
        STATION_COLUMN: ["S"],
        TIMESTAMP_COLUMN: pd.to_datetime(["2023-01-01"], utc=True),
        **{p: [1.0] for p in CORE_PARAMETERS},
        "actual_deterioration": [1.0],
        TARGET_COLUMN: [1.0],
    })
    with pytest.raises(ValueError, match="leakage"):
        resolve_feature_columns(df)


def test_unknown_extra_columns_are_rejected():
    df = pd.DataFrame({
        STATION_COLUMN: ["S"],
        TIMESTAMP_COLUMN: pd.to_datetime(["2023-01-01"], utc=True),
        **{p: [1.0] for p in CORE_PARAMETERS},
        "suspicious_future_value": [42.0],
        TARGET_COLUMN: [0.0],
    })
    with pytest.raises(ValueError, match="feature contract"):
        resolve_feature_columns(df)


# ---------------------------------------------------------------------------
# 6-8. Validation/test prediction works, probabilities valid
# ---------------------------------------------------------------------------
def test_validation_prediction_works(pipeline):
    m = pipeline["val_metrics"]
    assert m["evaluable_rows"] > 0
    for key in ("accuracy", "precision", "recall", "f1", "balanced_accuracy"):
        assert 0.0 <= m[key] <= 1.0
    cm = m["confusion_matrix"]
    assert cm["tn"] + cm["fp"] + cm["fn"] + cm["tp"] == m["evaluable_rows"]
    assert pipeline["cm_png"].is_file()


def test_test_prediction_works(pipeline):
    m = pipeline["test_metrics"]
    assert m["evaluable_rows"] > 0
    assert m["split_name"] == "Test"
    for key in ("accuracy", "precision", "recall", "f1"):
        assert 0.0 <= m[key] <= 1.0
    assert set(m["confusion_matrix"].values()) and sum(m["confusion_matrix"].values()) == m["evaluable_rows"]


def test_model_learns_the_pattern(pipeline):
    """Sanity check on the synthetic pattern: the model must beat the
    trivial all-zero baseline on validation (the target depends on the
    current turbidity, a legitimate feature)."""
    m = pipeline["val_metrics"]
    assert m["accuracy"] > 0.5
    assert m["recall"] > 0.0


def test_probability_values_valid(pipeline):
    preds = pipeline["predictions"]
    probs = preds["prediction_probability"].dropna()
    assert len(probs) > 0
    assert np.issubdtype(probs.dtype, np.floating)
    assert ((probs >= 0.0) & (probs <= 1.0)).all()
    # predicted labels valid; non-predictable rows marked -1 with NaN probability
    assert set(preds["predicted_deterioration"].unique()).issubset({0, 1, -1})
    not_predictable = preds["predicted_deterioration"] == -1
    assert preds.loc[not_predictable, "prediction_probability"].isna().all()
    assert preds.loc[~not_predictable, "prediction_probability"].notna().all()


# ---------------------------------------------------------------------------
# 9. Prediction output schema
# ---------------------------------------------------------------------------
def test_prediction_output_schema(pipeline):
    preds = pd.read_csv(pipeline["predictions_csv"])
    # Schema follows the input frame's parameters (fixture uses tds; the USGS
    # dataset uses specific_conductance): identifiers + parameters + labels.
    assert list(preds.columns)[:2] == ["station", "timestamp"]
    assert list(preds.columns)[-3:] == ["actual_deterioration", "predicted_deterioration",
                                        "prediction_probability"]
    assert len(preds) > 0
    assert preds["actual_deterioration"].dropna().isin([0.0, 1.0]).all()


# ---------------------------------------------------------------------------
# 10. Feature importance contains all model features
# ---------------------------------------------------------------------------
def test_feature_importance_contains_all_model_features(pipeline):
    imp = pipeline["importance_df"]
    assert list(imp.columns) == ["feature", "importance"]
    assert set(imp["feature"]) == set(pipeline["feature_cols"])
    assert len(imp) == len(pipeline["feature_cols"])
    assert imp["importance"].is_monotonic_decreasing  # sorted descending
    assert imp["importance"].sum() == pytest.approx(1.0, abs=1e-6)
    assert (imp["importance"] >= 0).all()


# ---------------------------------------------------------------------------
# 11. Model save/load predictions are consistent
# ---------------------------------------------------------------------------
def test_model_save_load_predictions_consistent(pipeline):
    val_df = pd.read_csv(pipeline["val_csv"]).dropna(subset=[TARGET_COLUMN])
    X = val_df[pipeline["feature_cols"]]
    in_memory = pipeline["model"].predict(X)
    reloaded = joblib.load(pipeline["model_path"]).predict(X)
    np.testing.assert_array_equal(in_memory, reloaded)
    np.testing.assert_allclose(
        pipeline["model"].predict_proba(X), joblib.load(pipeline["model_path"]).predict_proba(X)
    )


# ---------------------------------------------------------------------------
# 12. Reproducibility
# ---------------------------------------------------------------------------
def test_reproducibility_same_seed(pipeline):
    """Two trainings with identical data, hyperparameters, seed=42, and n_jobs
    must produce identical predictions and feature importances."""
    m1, feats, imp1 = train_xgboost(train_path=pipeline["train_csv"], model_output=None,
                                    importance_output=None, importance_plot_output=None,
                                    random_state=42)
    m2, _, imp2 = train_xgboost(train_path=pipeline["train_csv"], model_output=None,
                                importance_output=None, importance_plot_output=None,
                                random_state=42)
    val_df = pd.read_csv(pipeline["val_csv"]).dropna(subset=[TARGET_COLUMN])
    X = val_df[feats]
    np.testing.assert_array_equal(m1.predict(X), m2.predict(X))
    np.testing.assert_allclose(m1.predict_proba(X), m2.predict_proba(X))
    assert list(imp1["importance"]) == list(imp2["importance"])


# ---------------------------------------------------------------------------
# 13-14. Training uses only forecast_train.csv; no val/test leakage
# ---------------------------------------------------------------------------
def test_training_script_references_only_train_split():
    """The training script must read ONLY forecast_train.csv: its source must
    not reference the validation or test split paths at all."""
    import ml.scripts.train_xgboost as train_module
    source = inspect.getsource(train_module)
    assert "forecast_validation" not in source
    assert "forecast_test" not in source
    signature = inspect.signature(train_xgboost)
    assert "train_path" in signature.parameters
    assert not any(p in signature.parameters for p in ("val_path", "test_path"))


def test_training_succeeds_without_val_test_present(tmp_path):
    """Training requires ONLY the training split: it must succeed in a directory
    where validation/test splits do not exist (they are never read)."""
    df = make_synthetic_series(n_per_station=120, seed=7)
    built, _ = build_forecasting_dataset(df, "site", "observed_at",
                                         {"pH": "pH", "turbidity": "turbidity",
                                          "tds": "tds", "temperature": "temperature"},
                                         lags=(1,), windows=(3,), horizon=1)
    train_df, _, _, _ = chronological_split(built)
    train_csv = tmp_path / "forecast_train.csv"
    train_df.to_csv(train_csv, index=False)
    assert not (tmp_path / "forecast_validation.csv").exists()
    assert not (tmp_path / "forecast_test.csv").exists()

    model, feats, _ = train_xgboost(train_path=train_csv, model_output=None,
                                    importance_output=None, importance_plot_output=None,
                                    n_estimators=20, random_state=42)
    assert len(feats) > 0


def test_no_validation_or_test_rows_in_training(pipeline):
    """Rows of the validation and test splits must not appear in the training
    split (chronological disjointness by (station, timestamp) key)."""
    train_df = pd.read_csv(pipeline["train_csv"])
    val_df = pd.read_csv(pipeline["val_csv"])
    test_df = pd.read_csv(pipeline["test_csv"])
    train_keys = set(zip(train_df[STATION_COLUMN], train_df[TIMESTAMP_COLUMN]))
    val_keys = set(zip(val_df[STATION_COLUMN], val_df[TIMESTAMP_COLUMN]))
    test_keys = set(zip(test_df[STATION_COLUMN], test_df[TIMESTAMP_COLUMN]))
    assert not (train_keys & val_keys)
    assert not (train_keys & test_keys)


def test_no_future_information_in_features(pipeline):
    """Truncating the training data after time t must not change features at t
    (all 5D-1 features are past-only; nothing here re-creates features)."""
    built = pipeline["built"].sort_values([STATION_COLUMN, TIMESTAMP_COLUMN]).reset_index(drop=True)
    feature_cols = [c for c in built.columns
                    if c not in (STATION_COLUMN, TIMESTAMP_COLUMN, TARGET_COLUMN)]
    t = 250  # a row in the second station's series
    ts_t = built.loc[t, TIMESTAMP_COLUMN]
    truncated = built[built[TIMESTAMP_COLUMN] <= ts_t]
    for col in feature_cols:
        a, b = built.loc[t, col], truncated.loc[truncated.index[-1], col]
        if pd.isna(a) and pd.isna(b):
            continue
        assert a == pytest.approx(b), f"feature '{col}' changed when later rows were removed"


# ---------------------------------------------------------------------------
# 15. Chronological ordering remains valid
# ---------------------------------------------------------------------------
def test_chronological_ordering_remains_valid(pipeline):
    for key in ("train_csv", "val_csv", "test_csv"):
        part = pd.read_csv(pipeline[key])
        for _, group in part.groupby(STATION_COLUMN):
            ts = pd.to_datetime(group[TIMESTAMP_COLUMN], utc=True).tolist()
            assert ts == sorted(ts), f"{key} must remain chronologically sorted per station"
    train_df = pd.read_csv(pipeline["train_csv"])
    test_df = pd.read_csv(pipeline["test_csv"])
    assert pd.to_datetime(train_df[TIMESTAMP_COLUMN], utc=True).max() <= \
           pd.to_datetime(test_df[TIMESTAMP_COLUMN], utc=True).min()


def test_predictions_csv_chronological_per_station(pipeline):
    preds = pd.read_csv(pipeline["predictions_csv"])
    for _, group in preds.groupby(STATION_COLUMN):
        ts = pd.to_datetime(group[TIMESTAMP_COLUMN], utc=True).tolist()
        assert ts == sorted(ts)


# ---------------------------------------------------------------------------
# Guardrails: real Phase 5D-1 STOP state and loud failures on missing inputs
# ---------------------------------------------------------------------------
def test_real_forecast_inputs_exist_from_usgs_data():
    """Phase 5D-1 (USGS edition) has produced REAL chronological forecast
    splits from station USGS-01649190: they must exist, be non-empty, and use
    specific_conductance as a distinct measurement (never renamed to tds)."""
    for path in (REAL_TRAIN, REAL_VAL, REAL_TEST):
        assert path.is_file(), f"{path.name} missing - run ml/scripts/prepare_usgs_forecast_dataset.py"
        assert path.stat().st_size > 0
    df = pd.read_csv(REAL_TRAIN, nrows=5)
    assert "specific_conductance" in df.columns and "tds" not in df.columns


def test_training_fails_loudly_without_real_train_split(tmp_path, capsys):
    """With the real training split absent, training must raise a clear error
    that explains the Phase 5D-1 STOP state (never fabricate data)."""
    fake = tmp_path / "forecast_train.csv"
    with pytest.raises(FileNotFoundError, match="Phase 5D-1"):
        train_xgboost(train_path=fake, model_output=None, importance_output=None,
                      importance_plot_output=None)


def test_evaluation_fails_loudly_without_real_split(tmp_path):
    # Provide an existing model file so the check reaches the missing-SPLIT
    # branch, whose message documents the Phase 5D-1 STOP state.
    dummy_model = tmp_path / "model.joblib"
    joblib.dump({}, dummy_model)
    with pytest.raises(FileNotFoundError, match="STOP"):
        evaluate_split(tmp_path / "forecast_validation.csv",
                       model_path=dummy_model, plot_output=None,
                       split_name="Validation")


def test_predict_fails_loudly_without_real_split(tmp_path):
    from ml.scripts.predict_deterioration import DEFAULT_MODEL_PATH
    with pytest.raises(FileNotFoundError, match="STOP|STOP state|not found"):
        predict_deterioration(input_path=tmp_path / "forecast_test.csv",
                              model_path=DEFAULT_MODEL_PATH,
                              output_path=tmp_path / "out.csv")
