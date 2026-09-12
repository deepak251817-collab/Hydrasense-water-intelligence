"""Pytest Test Suite for Random Forest Water-Quality Classification (Phase 5C-2).

Verifies all Phase 5C-2 specifications:
1. Training succeeds
2. Model file is created
3. Model can be loaded via joblib
4. Correct feature set is used (pH, tds, turbidity, temperature)
5. Target label is excluded from features (data leakage protection)
6. Prediction generation works
7. Probability output works
8. Predictions contain expected classes ('Safe', 'Unsafe')
9. Probabilities are numeric and strictly bounded in [0, 1]
10. Feature importance contains all 4 features and sums to 1.0
11. Model persistence yields identical predictions between memory and disk
12. Reproducibility with random_state=42
13. Training does not use validation or test rows
14. Prediction output schema contains all 8 required columns
"""

from __future__ import annotations

from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier

from ml.preprocessing.prepare_supervised import (
    STANDARDIZED_FEATURE_COLUMNS,
    STANDARDIZED_TARGET_COLUMN,
)
from ml.scripts.predict_water_quality import predict_water_quality
from ml.scripts.train_random_forest import train_random_forest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODEL_PATH = PROJECT_ROOT / "ml" / "models" / "random_forest_classifier.joblib"
TRAIN_PATH = PROJECT_ROOT / "ml" / "data" / "processed" / "supervised_train.csv"
VAL_PATH = PROJECT_ROOT / "ml" / "data" / "processed" / "supervised_validation.csv"
TEST_PATH = PROJECT_ROOT / "ml" / "data" / "processed" / "supervised_test.csv"
IMPORTANCE_PATH = PROJECT_ROOT / "ml" / "data" / "processed" / "random_forest_feature_importance.csv"
PREDICTIONS_PATH = PROJECT_ROOT / "ml" / "data" / "processed" / "random_forest_predictions.csv"


@pytest.fixture(scope="module")
def loaded_model() -> RandomForestClassifier:
    """Load the persisted Random Forest model."""
    assert MODEL_PATH.exists(), f"Model file missing at {MODEL_PATH}"
    model = joblib.load(MODEL_PATH)
    assert isinstance(model, RandomForestClassifier)
    return model


@pytest.fixture(scope="module")
def test_data() -> pd.DataFrame:
    """Load the test split dataset."""
    assert TEST_PATH.exists(), f"Test split missing at {TEST_PATH}"
    return pd.read_csv(TEST_PATH)


def test_training_succeeds_and_creates_model(tmp_path: Path):
    """Verify that training pipeline runs and outputs model and importance CSV."""
    tmp_model = tmp_path / "rf_test.joblib"
    tmp_importance = tmp_path / "rf_importance.csv"
    tmp_plot = tmp_path / "rf_plot.png"

    model, imp_df = train_random_forest(
        train_path=TRAIN_PATH,
        model_output=tmp_model,
        importance_output=tmp_importance,
        plot_output=tmp_plot,
        n_estimators=10,  # fast test run
        random_state=42,
    )

    assert tmp_model.is_file()
    assert tmp_model.stat().st_size > 0
    assert tmp_importance.is_file()
    assert tmp_plot.is_file()
    assert isinstance(model, RandomForestClassifier)
    assert len(imp_df) == 4

    # Persistence round-trip: the model immediately after training and the model
    # loaded from disk must produce consistent predictions for the same input
    # (spec 5C-2 section 7).
    sample = pd.read_csv(TRAIN_PATH, nrows=100)[STANDARDIZED_FEATURE_COLUMNS]
    reloaded = joblib.load(tmp_model)
    np.testing.assert_array_equal(model.predict(sample), reloaded.predict(sample))
    np.testing.assert_allclose(model.predict_proba(sample), reloaded.predict_proba(sample))


def test_model_file_exists():
    """Verify standard model artifact exists at ml/models/random_forest_classifier.joblib."""
    assert MODEL_PATH.is_file()
    assert MODEL_PATH.stat().st_size > 0


def test_model_can_be_loaded(loaded_model: RandomForestClassifier):
    """Verify model can be deserialized and is a fitted RandomForestClassifier."""
    assert hasattr(loaded_model, "estimators_")
    assert len(loaded_model.estimators_) == 100
    assert hasattr(loaded_model, "classes_")
    assert set(loaded_model.classes_) == {"Safe", "Unsafe"}


def test_correct_feature_set_used(loaded_model: RandomForestClassifier):
    """Verify model was trained on exactly the 4 standardized water quality features."""
    assert loaded_model.n_features_in_ == 4
    if hasattr(loaded_model, "feature_names_in_"):
        assert list(loaded_model.feature_names_in_) == STANDARDIZED_FEATURE_COLUMNS


def test_label_excluded_from_features(loaded_model: RandomForestClassifier):
    """Verify label is not present in model feature names."""
    if hasattr(loaded_model, "feature_names_in_"):
        assert "label" not in loaded_model.feature_names_in_
        assert "Label" not in loaded_model.feature_names_in_


def test_prediction_works(loaded_model: RandomForestClassifier, test_data: pd.DataFrame):
    """Verify predict produces array of expected length and classes."""
    X = test_data[STANDARDIZED_FEATURE_COLUMNS].iloc[:50]
    preds = loaded_model.predict(X)

    assert len(preds) == 50
    assert all(p in {"Safe", "Unsafe"} for p in preds)


def test_probability_output_works(loaded_model: RandomForestClassifier, test_data: pd.DataFrame):
    """Verify predict_proba produces valid (N, 2) probability array."""
    X = test_data[STANDARDIZED_FEATURE_COLUMNS].iloc[:50]
    probs = loaded_model.predict_proba(X)

    assert probs.shape == (50, 2)
    assert np.all(probs >= 0.0)
    assert np.all(probs <= 1.0)
    assert np.allclose(probs.sum(axis=1), 1.0)


def test_predictions_contain_expected_classes(loaded_model: RandomForestClassifier, test_data: pd.DataFrame):
    """Verify predictions on test set contain both 'Safe' and 'Unsafe' labels."""
    X = test_data[STANDARDIZED_FEATURE_COLUMNS]
    preds = loaded_model.predict(X)
    unique_preds = set(preds)

    assert unique_preds == {"Safe", "Unsafe"}


def test_probabilities_within_zero_one(loaded_model: RandomForestClassifier, test_data: pd.DataFrame):
    """Verify full test set probabilities are strictly in [0, 1] and sum to 1."""
    X = test_data[STANDARDIZED_FEATURE_COLUMNS]
    probs = loaded_model.predict_proba(X)

    assert np.all(probs >= 0.0)
    assert np.all(probs <= 1.0)
    assert np.allclose(probs.sum(axis=1), 1.0)


def test_feature_importance_contains_all_features():
    """Verify random_forest_feature_importance.csv has all 4 features and valid importances."""
    assert IMPORTANCE_PATH.is_file()
    df = pd.read_csv(IMPORTANCE_PATH)

    assert list(df.columns) == ["feature", "importance"]
    assert set(df["feature"]) == set(STANDARDIZED_FEATURE_COLUMNS)
    assert len(df) == 4
    # Importance sum should be ~1.0
    assert pytest.approx(df["importance"].sum(), abs=1e-4) == 1.0
    # Must be sorted descending
    assert df["importance"].is_monotonic_decreasing


def test_model_persistence_consistency(loaded_model: RandomForestClassifier, test_data: pd.DataFrame, tmp_path: Path):
    """Verify memory model and loaded model produce identical predictions."""
    X = test_data[STANDARDIZED_FEATURE_COLUMNS].iloc[:100]

    preds_original = loaded_model.predict(X)
    probs_original = loaded_model.predict_proba(X)

    tmp_file = tmp_path / "reloaded.joblib"
    joblib.dump(loaded_model, tmp_file)
    reloaded = joblib.load(tmp_file)

    preds_reloaded = reloaded.predict(X)
    probs_reloaded = reloaded.predict_proba(X)

    np.testing.assert_array_equal(preds_original, preds_reloaded)
    np.testing.assert_allclose(probs_original, probs_reloaded)


def test_reproducibility_with_random_state():
    """Verify two models trained with random_state=42 generate identical predictions."""
    train_df = pd.read_csv(TRAIN_PATH).iloc[:2000]  # subset for fast testing
    X = train_df[STANDARDIZED_FEATURE_COLUMNS]
    y = train_df[STANDARDIZED_TARGET_COLUMN]

    rf1 = RandomForestClassifier(n_estimators=10, random_state=42)
    rf1.fit(X, y)

    rf2 = RandomForestClassifier(n_estimators=10, random_state=42)
    rf2.fit(X, y)

    val_df = pd.read_csv(VAL_PATH).iloc[:100]
    X_val = val_df[STANDARDIZED_FEATURE_COLUMNS]

    preds1 = rf1.predict(X_val)
    preds2 = rf2.predict(X_val)
    np.testing.assert_array_equal(preds1, preds2)

    probs1 = rf1.predict_proba(X_val)
    probs2 = rf2.predict_proba(X_val)
    np.testing.assert_allclose(probs1, probs2)


def test_training_does_not_use_val_or_test():
    """Verify that training set size matches 70,560 and does not include val or test data."""
    train_df = pd.read_csv(TRAIN_PATH)
    val_df = pd.read_csv(VAL_PATH)
    test_df = pd.read_csv(TEST_PATH)

    assert len(train_df) == 70_560
    assert len(val_df) == 15_120
    assert len(test_df) == 15_120
    assert len(train_df) + len(val_df) + len(test_df) == 100_800

    # Verify that in-memory splitting indices across train, val, and test are completely disjoint
    from ml.preprocessing.prepare_supervised import map_features, split_supervised_data
    raw_df = pd.read_csv(PROJECT_ROOT / "ml" / "data" / "external" / "water_quality_dataset1.csv")
    s_train, s_val, s_test = split_supervised_data(map_features(raw_df), random_state=42)

    assert len(set(s_train.index).intersection(set(s_val.index))) == 0
    assert len(set(s_train.index).intersection(set(s_test.index))) == 0
    assert len(set(s_val.index).intersection(set(s_test.index))) == 0


def test_prediction_output_schema():
    """Verify random_forest_predictions.csv exists with the required 8 columns."""
    assert PREDICTIONS_PATH.is_file()
    df = pd.read_csv(PREDICTIONS_PATH)

    expected_cols = [
        "pH",
        "tds",
        "turbidity",
        "temperature",
        "actual_label",
        "predicted_label",
        "probability_safe",
        "probability_unsafe",
    ]
    assert list(df.columns) == expected_cols
    assert len(df) == 15_120
    assert set(df["predicted_label"].unique()) == {"Safe", "Unsafe"}
    assert np.all(df["probability_safe"] >= 0.0)
    assert np.all(df["probability_safe"] <= 1.0)
    assert np.all(df["probability_unsafe"] >= 0.0)
    assert np.all(df["probability_unsafe"] <= 1.0)
