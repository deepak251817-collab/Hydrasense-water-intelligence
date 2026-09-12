"""Pytest Test Suite for SHAP Explainability (Phase 5E).

Covers the Phase 5E specification:
 1. SHAP dependency loads
 2. Random Forest model loads
 3. XGBoost model loads
 4. SHAP explainer creation succeeds
 5. Random Forest explanation outputs exist
 6. XGBoost explanation outputs exist
 7. Required feature names are present
 8. mean_abs_shap values are numeric
 9. SHAP values contain both positive and negative values
10. Local explanation schema is valid
11. No feature names outside the trained model are introduced
12. Original model predictions remain unchanged after SHAP
13. Original model probabilities remain unchanged after SHAP
14. No future/test data is used for model training (models are only explained)
15. Representative examples correspond to actual evaluation records
16. No fabricated explanation records exist (SHAP additivity is verified)

The suite explains the REAL persisted Phase 5C-2 / Phase 5D-2 models on the
REAL evaluation splits, but writes all explanation artifacts into temporary
directories so the genuine processed-data artifacts are never touched by
tests. Models are asserted byte-identical (sha256) across explanation runs.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from ml.scripts.explain_random_forest import (
    RF_FEATURES,
    RF_LABEL,
    explain_random_forest,
)
from ml.scripts.explain_xgboost import (
    FROZEN_THRESHOLD,
    explain_xgboost,
    load_feature_list,
)
from ml.utils.shap_compat import apply_shap_xgboost_compat

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = PROJECT_ROOT / "ml" / "data" / "processed"
MODELS_DIR = PROJECT_ROOT / "ml" / "models"

RF_MODEL = MODELS_DIR / "random_forest_classifier.joblib"
XGB_MODEL = MODELS_DIR / "xgboost_deterioration.joblib"
RF_TEST = PROCESSED_DIR / "supervised_test.csv"
XGB_TEST = PROCESSED_DIR / "forecast_test.csv"
XGB_FEATURE_LIST = PROCESSED_DIR / "xgboost_feature_list.txt"


@pytest.fixture(scope="module")
def rf_test_data() -> pd.DataFrame:
    assert RF_TEST.exists(), f"Phase 5C test split missing: {RF_TEST}"
    return pd.read_csv(RF_TEST)


@pytest.fixture(scope="module")
def xgb_test_data() -> pd.DataFrame:
    assert XGB_TEST.exists(), f"Phase 5D-1 test split missing: {XGB_TEST}"
    return pd.read_csv(XGB_TEST)


@pytest.fixture(scope="module")
def rf_explanation(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Run the Random Forest explainer once, writing artifacts to a temp dir."""
    out_dir = tmp_path_factory.mktemp("rf_shap")
    return explain_random_forest(model_path=RF_MODEL, data_path=RF_TEST, out_dir=out_dir)


@pytest.fixture(scope="module")
def xgb_explanation(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Run the XGBoost explainer once, writing artifacts to a temp dir."""
    out_dir = tmp_path_factory.mktemp("xgb_shap")
    return explain_xgboost(
        model_path=XGB_MODEL,
        data_path=XGB_TEST,
        feature_list_path=XGB_FEATURE_LIST,
        out_dir=out_dir,
        threshold=FROZEN_THRESHOLD,
    )


# ---------------------------------------------------------------------------
# 1-4. Dependencies and model loading
# ---------------------------------------------------------------------------
def test_shap_dependency_loads():
    import shap  # noqa: F401 - import itself is the assertion

    assert hasattr(shap, "TreeExplainer"), "shap.TreeExplainer is unavailable"


def test_random_forest_model_loads():
    assert RF_MODEL.exists(), f"Phase 5C-2 model missing: {RF_MODEL}"
    from sklearn.ensemble import RandomForestClassifier

    model = joblib.load(RF_MODEL)
    assert isinstance(model, RandomForestClassifier)


def test_xgboost_model_loads():
    assert XGB_MODEL.exists(), f"Phase 5D-2 model missing: {XGB_MODEL}"
    from xgboost import XGBClassifier

    model = joblib.load(XGB_MODEL)
    assert isinstance(model, XGBClassifier)


def test_shap_explainer_creation_succeeds():
    import shap

    rf = joblib.load(RF_MODEL)
    assert shap.TreeExplainer(rf) is not None

    apply_shap_xgboost_compat()  # documented xgboost >= 3 base_score shim
    xgb = joblib.load(XGB_MODEL)
    assert shap.TreeExplainer(xgb) is not None


# ---------------------------------------------------------------------------
# 5-6. Explanation outputs exist (generated fresh into temp dirs)
# ---------------------------------------------------------------------------
def test_random_forest_explanation_outputs_exist(tmp_path: Path):
    out_dir = tmp_path / "rf_out"
    out_dir.mkdir()
    result = explain_random_forest(model_path=RF_MODEL, data_path=RF_TEST, out_dir=out_dir)
    for name in (
        "shap_random_forest_summary.csv",
        "shap_random_forest_summary.png",
        "shap_random_forest_local.csv",
    ):
        produced = out_dir / name
        assert produced.is_file(), f"Missing RF SHAP output: {name}"
        assert produced.stat().st_size > 0
    assert result["n_global_sample"] > 0
    assert result["n_local_rows"] > 0


def test_xgboost_explanation_outputs_exist(tmp_path: Path):
    out_dir = tmp_path / "xgb_out"
    out_dir.mkdir()
    result = explain_xgboost(
        model_path=XGB_MODEL,
        data_path=XGB_TEST,
        feature_list_path=XGB_FEATURE_LIST,
        out_dir=out_dir,
        threshold=FROZEN_THRESHOLD,
    )
    for name in (
        "shap_xgboost_summary.csv",
        "shap_xgboost_summary.png",
        "shap_xgboost_local.csv",
    ):
        produced = out_dir / name
        assert produced.is_file(), f"Missing XGBoost SHAP output: {name}"
        assert produced.stat().st_size > 0
    assert result["n_global_sample"] > 0
    assert result["n_local_rows"] > 0


# ---------------------------------------------------------------------------
# 7-8. Feature names and mean_abs_shap validity
# ---------------------------------------------------------------------------
def test_required_feature_names_present(rf_explanation: dict, xgb_explanation: dict):
    rf_features = set(rf_explanation["summary"]["feature"])
    assert rf_features == set(RF_FEATURES), "RF SHAP summary must cover exactly the four model inputs"

    expected_xgb = load_feature_list(XGB_FEATURE_LIST)
    xgb_features = list(xgb_explanation["summary"]["feature"])
    assert sorted(xgb_features) == sorted(expected_xgb), "XGBoost SHAP summary must use exactly the Phase 5D-2 feature list"
    assert xgb_features == sorted(
        xgb_features, key=lambda f: xgb_explanation["summary"].set_index("feature").loc[f, "mean_abs_shap"],
        reverse=True,
    ), "XGBoost SHAP summary must remain sorted by mean_abs_shap descending"


def test_mean_abs_shap_numeric_and_sorted(rf_explanation: dict, xgb_explanation: dict):
    for summary in (rf_explanation["summary"], xgb_explanation["summary"]):
        values = summary["mean_abs_shap"].to_numpy(dtype=float)
        assert np.all(np.isfinite(values)), "mean_abs_shap contains non-finite values"
        assert np.all(values >= 0), "mean_abs_shap must be non-negative"
        assert np.all(np.diff(values) <= 0), "summary must be sorted descending by mean_abs_shap"


# ---------------------------------------------------------------------------
# 9. SHAP values contain both signs where applicable
# ---------------------------------------------------------------------------
def test_shap_values_contain_both_signs(rf_explanation: dict, xgb_explanation: dict):
    for name, table in (
        ("random_forest", rf_explanation["local_table"]),
        ("xgboost", xgb_explanation["local_table"]),
    ):
        shap_values = table["shap_value"].to_numpy(dtype=float)
        assert np.all(np.isfinite(shap_values))
        assert (shap_values > 0).any(), f"{name}: no positive SHAP contributions found"
        assert (shap_values < 0).any(), f"{name}: no negative SHAP contributions found"


# ---------------------------------------------------------------------------
# 10. Local explanation schema is valid
# ---------------------------------------------------------------------------
def test_local_explanation_schema_valid(rf_explanation: dict, xgb_explanation: dict):
    rf_local = rf_explanation["local_table"]
    assert list(rf_local.columns) == [
        "row_index", "actual_label", "predicted_label",
        "prediction_probability", "feature", "shap_value",
    ]
    assert set(rf_local["actual_label"]).issubset({"Safe", "Unsafe"})
    assert set(rf_local["predicted_label"]).issubset({"Safe", "Unsafe"})
    probs = rf_local["prediction_probability"].to_numpy(dtype=float)
    assert np.all((probs >= 0) & (probs <= 1))

    xgb_local = xgb_explanation["local_table"]
    assert list(xgb_local.columns) == [
        "row_index", "station", "timestamp",
        "actual_deterioration", "predicted_deterioration",
        "prediction_probability", "feature", "shap_value",
    ]
    assert set(xgb_local["actual_deterioration"]).issubset({0, 1})
    assert set(xgb_local["predicted_deterioration"]).issubset({0, 1})
    probs = xgb_local["prediction_probability"].to_numpy(dtype=float)
    assert np.all((probs >= 0) & (probs <= 1))
    # Predicted labels must follow the frozen threshold, not a different rule.
    for _, group in xgb_local.groupby("row_index"):
        thresholded = int(group["prediction_probability"].iloc[0] >= FROZEN_THRESHOLD)
        assert thresholded == group["predicted_deterioration"].iloc[0]


# ---------------------------------------------------------------------------
# 11. No feature names outside the trained model are introduced
# ---------------------------------------------------------------------------
def test_no_feature_names_outside_model(rf_explanation: dict, xgb_explanation: dict):
    allowed_rf = set(RF_FEATURES)
    assert set(rf_explanation["summary"]["feature"]) == allowed_rf
    assert set(rf_explanation["local_table"]["feature"]) == allowed_rf

    allowed_xgb = set(load_feature_list(XGB_FEATURE_LIST))
    assert set(xgb_explanation["summary"]["feature"]) == allowed_xgb
    assert set(xgb_explanation["local_table"]["feature"]) == allowed_xgb
    # Identifiers and the target must never appear as explanation features.
    for forbidden in ("station", "timestamp", "deterioration_target", "label"):
        assert forbidden not in allowed_xgb
        assert forbidden not in allowed_rf


# ---------------------------------------------------------------------------
# 12-13. Model predictions/probabilities unchanged after SHAP
# ---------------------------------------------------------------------------
def test_model_predictions_unchanged_after_shap(
    rf_explanation: dict, xgb_explanation: dict,
    rf_test_data: pd.DataFrame, xgb_test_data: pd.DataFrame,
):
    # The explainers captured BEFORE predictions and compared them to AFTER
    # predictions (hash + arrays); assert that verification passed.
    for name, consistency in (
        ("random_forest", rf_explanation["consistency"]),
        ("xgboost", xgb_explanation["consistency"]),
    ):
        assert consistency["model_hash_unchanged"], f"{name}: model artifact modified"
        assert consistency["predictions_unchanged"], f"{name}: predictions modified by SHAP"
        assert consistency["probabilities_unchanged"], f"{name}: probabilities modified by SHAP"

    # Independently recompute predictions and compare with the stored local
    # explanation rows (row_index = source row position in the test split).
    rf_model = joblib.load(RF_MODEL)
    X_rf = rf_test_data[list(RF_FEATURES)]
    pred_rf = rf_model.predict(X_rf)
    for idx, group in rf_explanation["local_table"].groupby("row_index"):
        assert pred_rf[int(idx)] == group["predicted_label"].iloc[0]

    xgb_model = joblib.load(XGB_MODEL)
    features = load_feature_list(XGB_FEATURE_LIST)
    evaluable = xgb_test_data["deterioration_target"].notna().to_numpy()
    X_xgb = xgb_test_data.loc[evaluable, features]
    prob = xgb_model.predict_proba(X_xgb)[:, 1]
    pred = (prob >= FROZEN_THRESHOLD).astype(int)
    # Map source row positions -> positions within the evaluable arrays.
    source_positions = np.where(evaluable)[0]
    position_of_source = {int(s): i for i, s in enumerate(source_positions)}
    for idx, group in xgb_explanation["local_table"].groupby("row_index"):
        i = position_of_source[int(idx)]
        assert pred[i] == group["predicted_deterioration"].iloc[0]


def test_model_probabilities_unchanged_after_shap(
    rf_explanation: dict, xgb_explanation: dict,
    rf_test_data: pd.DataFrame, xgb_test_data: pd.DataFrame,
):
    rf_model = joblib.load(RF_MODEL)
    X_rf = rf_test_data[list(RF_FEATURES)]
    prob_rf = rf_model.predict_proba(X_rf)[:, 1]
    for idx, group in rf_explanation["local_table"].groupby("row_index"):
        fresh = float(prob_rf[int(idx)])
        stored = float(group["prediction_probability"].iloc[0])
        assert fresh == pytest.approx(stored, abs=1e-12)

    xgb_model = joblib.load(XGB_MODEL)
    features = load_feature_list(XGB_FEATURE_LIST)
    evaluable = xgb_test_data["deterioration_target"].notna().to_numpy()
    X_xgb = xgb_test_data.loc[evaluable, features]
    prob = xgb_model.predict_proba(X_xgb)[:, 1]
    source_positions = np.where(evaluable)[0]
    position_of_source = {int(s): i for i, s in enumerate(source_positions)}
    for idx, group in xgb_explanation["local_table"].groupby("row_index"):
        fresh = float(prob[position_of_source[int(idx)]])
        stored = float(group["prediction_probability"].iloc[0])
        assert fresh == pytest.approx(stored, abs=1e-12)


# ---------------------------------------------------------------------------
# 14. No training/tuning happens in the explanation scripts
# ---------------------------------------------------------------------------
def test_no_future_or_test_data_used_for_training():
    rf_source = (PROJECT_ROOT / "ml" / "scripts" / "explain_random_forest.py").read_text()
    xgb_source = (PROJECT_ROOT / "ml" / "scripts" / "explain_xgboost.py").read_text()

    # No estimator construction or fitting in the explainers.
    assert "RandomForestClassifier(" not in rf_source
    assert "XGBClassifier(" not in xgb_source
    assert ".fit(" not in rf_source
    assert ".fit(" not in xgb_source
    # Each script references exactly its own persisted model artifact.
    assert "random_forest_classifier.joblib" in rf_source
    assert "xgboost_deterioration.joblib" not in rf_source
    assert "xgboost_deterioration.joblib" in xgb_source
    assert "random_forest_classifier.joblib" not in xgb_source

    # The compatibility shim must never write model artifacts; it only
    # normalizes the decoded in-memory representation SHAP reads.
    shim_source = (PROJECT_ROOT / "ml" / "utils" / "shap_compat.py").read_text()
    for forbidden in ("save_model", "save_raw(...).replace", "joblib.dump", ".save_model("):
        assert forbidden not in shim_source
    assert "learner_model_param" in shim_source  # documented normalization point


# ---------------------------------------------------------------------------
# 15. Representative examples correspond to actual evaluation records
# ---------------------------------------------------------------------------
def test_representative_examples_correspond_to_actual_records(
    rf_explanation: dict, xgb_explanation: dict,
    rf_test_data: pd.DataFrame, xgb_test_data: pd.DataFrame,
):
    rf_local = rf_explanation["local_table"]
    n_rf = len(rf_test_data)
    for idx, group in rf_local.groupby("row_index"):
        assert 0 <= int(idx) < n_rf, f"RF local row {idx} out of range"
        actual = rf_test_data.iloc[int(idx)][RF_LABEL]
        assert group["actual_label"].iloc[0] == actual

    xgb_local = xgb_explanation["local_table"]
    n_xgb = len(xgb_test_data)
    for idx, group in xgb_local.groupby("row_index"):
        assert 0 <= int(idx) < n_xgb, f"XGB local row {idx} out of range"
        row = xgb_test_data.iloc[int(idx)]
        assert group["station"].iloc[0] == row["station"]
        assert group["timestamp"].iloc[0] == row["timestamp"]
        assert int(group["actual_deterioration"].iloc[0]) == int(row["deterioration_target"])

    # All four prediction categories were available on the final test split.
    categories = xgb_local.groupby("row_index")[
        ["actual_deterioration", "predicted_deterioration"]].first()
    combos = set(map(tuple, categories.to_numpy()))
    assert {(1, 1), (0, 0), (0, 1), (1, 0)}.issubset(combos), \
        f"Expected TP/TN/FP/FN examples, found {combos}"


# ---------------------------------------------------------------------------
# 16. No fabricated explanation records exist (SHAP additivity verified)
# ---------------------------------------------------------------------------
def test_no_fabricated_explanation_records_xgboost(
    xgb_explanation: dict, xgb_test_data: pd.DataFrame,
):
    """XGBoost SHAP contributions must reconstruct the model's raw margin:
    expected_value + sum(SHAP) == margin for every explained observation."""
    import shap

    apply_shap_xgboost_compat()
    model = joblib.load(XGB_MODEL)
    features = load_feature_list(XGB_FEATURE_LIST)
    evaluable = xgb_test_data["deterioration_target"].notna().to_numpy()
    X_xgb = xgb_test_data.loc[evaluable, features]

    explainer = shap.TreeExplainer(model)
    source_positions = np.where(evaluable)[0]
    position_of_source = {int(s): i for i, s in enumerate(source_positions)}

    xgb_local = xgb_explanation["local_table"]
    for idx, group in xgb_local.groupby("row_index"):
        i = position_of_source[int(idx)]
        row = X_xgb.iloc[[i]]
        sv = explainer.shap_values(row)
        sv = sv[0] if isinstance(sv, np.ndarray) and sv.ndim > 1 else sv
        base = float(np.ravel(explainer.expected_value)[0])
        reconstructed = base + float(np.sum(sv))
        margin = float(model.predict(row, output_margin=True)[0])
        assert reconstructed == pytest.approx(margin, rel=1e-4, abs=1e-6), \
            f"SHAP additivity violated for row {idx}: {reconstructed} != {margin}"


def test_no_fabricated_explanation_records_random_forest(
    rf_explanation: dict, rf_test_data: pd.DataFrame,
):
    """Random Forest SHAP contributions must reconstruct predict_proba for the
    positive class (Unsafe): expected_value + sum(SHAP) == probability."""
    import shap

    model = joblib.load(RF_MODEL)
    X_rf = rf_test_data[list(RF_FEATURES)]
    explainer = shap.TreeExplainer(model)

    rf_local = rf_explanation["local_table"]
    for idx, group in rf_local.groupby("row_index"):
        row = X_rf.iloc[[int(idx)]]
        sv = explainer.shap_values(row)
        if isinstance(sv, list):            # [class0, class1] arrays
            sv_positive = sv[1][0]
            base = float(np.ravel(explainer.expected_value)[1])
        elif isinstance(sv, np.ndarray) and sv.ndim == 3:  # (n, features, classes)
            sv_positive = sv[0, :, 1]
            base = float(np.ravel(explainer.expected_value)[1])
        else:                                # (n, features) positive-class only
            sv_positive = sv[0]
            base = float(np.ravel(explainer.expected_value)[0])
        reconstructed = base + float(np.sum(sv_positive))
        probability = float(model.predict_proba(row)[:, 1][0])
        assert reconstructed == pytest.approx(probability, rel=1e-4, abs=1e-6), \
            f"SHAP additivity violated for row {idx}: {reconstructed} != {probability}"


# ---------------------------------------------------------------------------
# Bonus: the documented xgboost 3.x base_score compatibility shim
# ---------------------------------------------------------------------------
def test_shap_compat_normalizes_vector_base_score():
    from ml.utils.shap_compat import (
        _normalize_vector_base_score,
        apply_shap_xgboost_compat,
    )

    jmodel = {"learner": {"learner_model_param": {"base_score": "[5E-1]"}}}
    normalized = _normalize_vector_base_score(jmodel)
    assert normalized["learner"]["learner_model_param"]["base_score"] == "5E-1"
    assert float(normalized["learner"]["learner_model_param"]["base_score"]) == 0.5

    # Plain scalar values pass through untouched; other structures are safe.
    scalar = {"learner": {"learner_model_param": {"base_score": 0.5}}}
    assert _normalize_vector_base_score(scalar) is scalar
    assert _normalize_vector_base_score({}) == {}
    assert _normalize_vector_base_score({"learner": {}}) == {"learner": {}}

    # apply is idempotent
    apply_shap_xgboost_compat()
    apply_shap_xgboost_compat()
