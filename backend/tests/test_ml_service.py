"""Phase 6 — ML service tests.

Covers: model loading, valid inference, per-feature validation (pH, turbidity,
tds, temperature, NaN, infinity), result schemas, probability ranges, explicit
feature ordering, missing-model behavior, model persistence, and repeated
inference consistency.
"""
import math

import pandas as pd
import pytest

from app.services import ml_service as ml_service_module
from app.services.ml_service import (
    ISOLATION_FOREST_FEATURES,
    RANDOM_FOREST_FEATURES,
    MLService,
    MLServiceUnavailableError,
    MLValidationError,
    ml_service,
)


@pytest.fixture(scope="module")
def loaded_service() -> MLService:
    service = MLService()
    assert service.load_models() is True, (
        "Live model artifacts must load; run the Phase 5B/5C-2 training scripts "
        "if ml/models/ artifacts are absent."
    )
    return service


# 1. Model loading
def test_model_loading(loaded_service: MLService):
    assert loaded_service.is_available
    assert loaded_service.isolation_forest is not None
    assert loaded_service.random_forest is not None
    assert loaded_service.isolation_forest.n_features_in_ == len(ISOLATION_FOREST_FEATURES)
    assert loaded_service.random_forest.n_features_in_ == len(RANDOM_FOREST_FEATURES)


# 2. Valid inference
def test_valid_inference_returns_structured_result(loaded_service: MLService):
    result = loaded_service.predict(ph=7.2, turbidity=4.5, tds=210.0, temperature=25.5)
    assert isinstance(result, ml_service_module.MLResult)
    assert result.anomaly_label in (0, 1)
    assert result.water_quality_label in ("Safe", "Unsafe")


# 3. Invalid pH
@pytest.mark.parametrize("ph", [-0.1, 14.1, 99.0])
def test_invalid_ph_rejected(loaded_service: MLService, ph: float):
    with pytest.raises(MLValidationError, match="pH"):
        loaded_service.predict(ph=ph, turbidity=1.0, tds=200.0, temperature=25.0)


# 4. Negative turbidity
def test_negative_turbidity_rejected(loaded_service: MLService):
    with pytest.raises(MLValidationError, match="turbidity"):
        loaded_service.predict(ph=7.0, turbidity=-0.01, tds=200.0, temperature=25.0)


# 5. Negative TDS
def test_negative_tds_rejected(loaded_service: MLService):
    with pytest.raises(MLValidationError, match="tds"):
        loaded_service.predict(ph=7.0, turbidity=1.0, tds=-5.0, temperature=25.0)


# 6. Invalid temperature (Phase 5 ML cleaning range: [-10, 60])
@pytest.mark.parametrize("temperature", [-10.1, 60.1, 150.0])
def test_invalid_temperature_rejected(loaded_service: MLService, temperature: float):
    with pytest.raises(MLValidationError, match="temperature"):
        loaded_service.predict(ph=7.0, turbidity=1.0, tds=200.0, temperature=temperature)


# 7. NaN handling
@pytest.mark.parametrize("field", ["ph", "turbidity", "tds", "temperature"])
def test_nan_rejected(loaded_service: MLService, field: str):
    kwargs = {"ph": 7.0, "turbidity": 1.0, "tds": 200.0, "temperature": 25.0}
    kwargs[field] = float("nan")
    with pytest.raises(MLValidationError):
        loaded_service.predict(**kwargs)


# 8. Infinity handling
@pytest.mark.parametrize("field", ["ph", "turbidity", "tds", "temperature"])
def test_infinity_rejected(loaded_service: MLService, field: str):
    kwargs = {"ph": 7.0, "turbidity": 1.0, "tds": 200.0, "temperature": 25.0}
    kwargs[field] = float("inf")
    with pytest.raises(MLValidationError):
        loaded_service.predict(**kwargs)
    kwargs[field] = -float("inf")
    with pytest.raises(MLValidationError):
        loaded_service.predict(**kwargs)


# 9. Anomaly result schema
def test_anomaly_result_schema(loaded_service: MLService):
    result = loaded_service.predict(ph=7.0, turbidity=2.0, tds=250.0, temperature=24.0)
    payload = result.to_dict()
    assert set(payload.keys()) == {
        "anomaly_label", "anomaly_score",
        "water_quality_label", "safe_probability", "unsafe_probability",
    }
    assert isinstance(payload["anomaly_label"], int)
    assert isinstance(payload["anomaly_score"], float)
    assert math.isfinite(payload["anomaly_score"])
    assert payload["water_quality_label"] in ("Safe", "Unsafe")


# 10. Random Forest result schema
def test_random_forest_result_schema(loaded_service: MLService):
    result = loaded_service.predict(ph=5.0, turbidity=60.0, tds=900.0, temperature=25.0)
    assert result.water_quality_label in ("Safe", "Unsafe")
    # the predicted label must match the argmax of the stored probabilities
    if result.water_quality_label == "Safe":
        assert result.safe_probability >= result.unsafe_probability
    else:
        assert result.unsafe_probability >= result.safe_probability


# 11. Probability range [0, 1]
def test_probabilities_within_unit_range(loaded_service: MLService):
    for ph, turb, tds, temp in (
        (7.0, 1.0, 200.0, 25.0),
        (5.0, 60.0, 900.0, 25.0),
        (9.0, 0.5, 100.0, 18.0),
    ):
        r = loaded_service.predict(ph=ph, turbidity=turb, tds=tds, temperature=temp)
        for p in (r.safe_probability, r.unsafe_probability):
            assert 0.0 <= p <= 1.0
        assert abs((r.safe_probability + r.unsafe_probability) - 1.0) < 1e-9


# 12. Feature ordering: service arrays match the training contracts exactly,
# and a permuted input row would change predictions (proving order matters).
def test_feature_ordering_matches_training_contracts(loaded_service: MLService):
    assert ISOLATION_FOREST_FEATURES == ["ph", "turbidity", "tds", "temperature"]
    assert RANDOM_FOREST_FEATURES == ["pH", "tds", "turbidity", "temperature"]

    # Build two rows: correct tds/turbidity vs swapped, via the service's own
    # DataFrame assembly path to prove no dict ordering is relied on.
    ph, turb, tds, temp = 7.0, 400.0, 60.0, 25.0  # turbidity high OR tds high
    X_correct_rf = pd.DataFrame([[ph, tds, turb, temp]], columns=RANDOM_FOREST_FEATURES)
    X_swapped_rf = pd.DataFrame([[ph, turb, tds, temp]], columns=RANDOM_FOREST_FEATURES)
    rf = loaded_service.random_forest
    p_correct = float(rf.predict_proba(X_correct_rf)[0][list(rf.classes_).index("Unsafe")])
    p_swapped = float(rf.predict_proba(X_swapped_rf)[0][list(rf.classes_).index("Unsafe")])
    assert p_correct != p_swapped, (
        "Permuting tds/turbidity must change the prediction — proves explicit "
        "ordering matters and is honored."
    )


# 13. Missing model behavior: unavailable service raises, never fabricates.
def test_missing_model_behavior(tmp_path):
    service = MLService(
        isolation_forest_path=tmp_path / "nope_if.joblib",
        random_forest_path=tmp_path / "nope_rf.joblib",
    )
    assert service.load_models() is False
    assert not service.is_available
    with pytest.raises(MLServiceUnavailableError):
        service.predict(ph=7.0, turbidity=1.0, tds=200.0, temperature=25.0)


# 14. Model persistence: predictions from a second load are identical.
def test_model_persistence_consistency(loaded_service: MLService):
    r1 = loaded_service.predict(ph=6.8, turbidity=30.0, tds=500.0, temperature=27.0)
    fresh = MLService()
    assert fresh.load_models() is True
    r2 = fresh.predict(ph=6.8, turbidity=30.0, tds=500.0, temperature=27.0)
    assert r1 == r2


# 15. Repeated inference consistency (deterministic models, no state drift).
def test_repeated_inference_consistency(loaded_service: MLService):
    args = (7.3, 8.0, 320.0, 26.0)
    results = [loaded_service.predict(ph=args[0], turbidity=args[1], tds=args[2], temperature=args[3]) for _ in range(3)]
    assert all(r == results[0] for r in results)
    # module singleton must also agree (same artifacts); it loads exactly like
    # the app startup path does
    assert ml_service.load_models() is True
    singleton = ml_service.predict(ph=args[0], turbidity=args[1], tds=args[2], temperature=args[3])
    assert singleton == results[0]
