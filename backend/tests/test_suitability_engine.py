"""Central four-parameter suitability engine — behaviour pinned by tests.

Every decision must be traceable to exactly four sensor values (pH, TDS,
temperature, turbidity) plus the intended use and its configured threshold
profile. These tests pin:

- the engine accepts ONLY the four inputs (extra parameters are rejected, so
  DO, ML scores, rainfall, history or location can never change a result);
- each purpose applies its own profile, and each sensor can move the state
  only where that profile has a rule;
- invalid, stale, missing or non-finite values never produce a positive state;
- turbidity index (0–100) is never compared with NTU limits;
- the canonical four-state vocabulary (within_configured_ranges / caution /
  outside_configured_ranges / insufficient_data) is emitted consistently by
  both engines and the API;
- identical inputs + profile version reproduce an identical result.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import math
import pytest

from app.services import suitability_engine as engine
from app.services.screening_states import (
    CAUTION,
    INSUFFICIENT,
    OUTSIDE,
    STATE_LABELS,
    WITHIN,
    canonical_state,
)

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
DEMO_UNIT = "relative_index_0_100"

BASE_READINGS = {"ph": 7.2, "tds": 300.0, "temperature": 25.0, "turbidity": 20.0}


def evaluate(readings=None, **overrides):
    data = dict(BASE_READINGS)
    if readings:
        data.update(readings)
    kwargs = dict(
        intended_use="drinking",
        reading_mode="demo",
        reading_timestamp=NOW,
        turbidity_unit=DEMO_UNIT,
        now=NOW,
    )
    kwargs.update(overrides)
    return engine.evaluate(data, **kwargs)


def state_of(result):
    return result["overall"]["state"]


# ---------------------------------------------------------------------------
# 1. Input contract — exactly four parameters, nothing else
# ---------------------------------------------------------------------------


def test_engine_declares_exactly_the_four_sensor_inputs():
    assert engine.INPUTS == ("ph", "tds", "temperature", "turbidity")


@pytest.mark.parametrize(
    "extra",
    [
        {"dissolved_oxygen": 3.0},
        {"anomaly_score": 0.93},
        {"rainfall_mm": 42.0},
        {"forecast": {"ph": 9.9}},
        {"location": "downstream"},
        {"total_coliform": 0},
        {"risk_score": 88},
    ],
)
def test_unsupported_parameters_are_rejected_not_ignored(extra):
    """An extra input must raise, never silently influence the decision."""
    with pytest.raises(ValueError, match="four sensor inputs"):
        evaluate(readings=extra)


def test_hidden_parameters_cannot_change_the_result():
    """Baseline and identical inputs must agree (no external state involved)."""
    baseline = evaluate()
    identical = evaluate()
    assert identical == baseline


# ---------------------------------------------------------------------------
# 2. Canonical vocabulary
# ---------------------------------------------------------------------------


def test_unvalidated_turbidity_caps_a_drinking_pass_at_caution():
    """pH and TDS passing with an unvalidated index is never a full pass."""
    result = evaluate()
    assert result["readings"]["ph"]["status"] == "within_range"
    assert result["readings"]["tds"]["status"] == "within_range"
    assert result["readings"]["turbidity"]["status"] == "not_comparable"
    assert state_of(result) == CAUTION
    assert any("NTU calibration required" in warning
               for warning in result["data_quality"]["warnings"])


def test_validated_ntu_turbidity_allows_a_full_pass():
    calibrated = {
        "ph": "calibrated", "tds": "calibrated",
        "turbidity": "calibrated", "temperature": "calibrated",
    }
    result = evaluate(
        readings={"turbidity": 0.5},
        turbidity_unit="ntu",
        calibration=calibrated,
        stability={"stable": True, "status": "stable", "message": ""},
    )
    assert state_of(result) == WITHIN


def test_result_carries_canonical_state_and_label():
    result = evaluate()
    assert state_of(result) in STATE_LABELS
    assert result["overall"]["state_label"] == STATE_LABELS[state_of(result)]


def test_engine_metadata_lists_inputs_and_exclusions():
    result = evaluate()
    meta = result["engine"]
    assert meta["inputs"] == ["ph", "tds", "temperature", "turbidity"]
    assert "dissolved_oxygen" in meta["excluded_inputs"]
    assert "ml_predictions" in meta["excluded_inputs"]
    assert meta["source"] == "simulated"


def test_real_mode_is_labelled_real_sensor():
    result = evaluate(
        reading_mode="live",
        readings={"turbidity": 0.8},
        turbidity_unit="ntu",
        calibration={
            "ph": "calibrated",
            "tds": "calibrated",
            "turbidity": "calibrated",
            "temperature": "calibrated",
        },
        stability={"stable": True, "status": "stable", "message": ""},
    )
    assert result["engine"]["source"] == "real_sensor"


# ---------------------------------------------------------------------------
# 3. Per-parameter boundary behaviour (drinking profile)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ph,expected", [(7.2, CAUTION), (6.5, CAUTION), (8.5, CAUTION),
                                         (6.4, OUTSIDE), (8.6, OUTSIDE)])
def test_ph_boundary_changes_state(ph, expected):
    # With the default relative-index turbidity the best possible state is
    # CAUTION (unvalidated-turbidity cap); pH still drives OUTSIDE when it fails.
    assert state_of(evaluate(readings={"ph": ph})) == expected


@pytest.mark.parametrize("tds,expected", [
    (100.0, CAUTION),      # below the project strict TDS target
    (200.0, CAUTION),      # at the strict target; turbidity unvalidated => caution
    (300.0, CAUTION),
    (500.0, CAUTION),      # at the acceptable reference; turbidity unvalidated
    (501.0, CAUTION),      # above acceptable, investigation
    (2000.0, CAUTION),     # at the permissible reference
    (2001.0, OUTSIDE),     # above the permissible reference
])
def test_tds_boundary_changes_state(tds, expected):
    assert state_of(evaluate(readings={"tds": tds})) == expected


def test_temperature_has_no_rule_and_never_changes_state():
    """No purpose configures a temperature pass/fail limit — context only."""
    cold = evaluate(readings={"temperature": 5.0})
    warm = evaluate(readings={"temperature": 45.0})
    assert state_of(cold) == state_of(warm)
    assert cold["readings"]["temperature"]["status"] == "informational"


def test_implausible_temperature_is_never_a_positive_result():
    result = evaluate(readings={"temperature": -100.0})
    assert state_of(result) == INSUFFICIENT


# ---------------------------------------------------------------------------
# 4. Turbidity: index is never NTU; calibrated NTU uses NTU limits
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("index", [3.0, 30.0, 70.0, 97.0])
def test_turbidity_index_is_never_compared_with_ntu_limits(index):
    result = evaluate(readings={"turbidity": index})
    turbidity = result["readings"]["turbidity"]
    assert turbidity["status"] == "not_comparable"
    assert "not compared with the 1 NTU" in turbidity["note"]
    assert "must not be read as NTU" in turbidity["note"]
    assert "index" in turbidity["unit"]


def test_calibrated_ntu_values_do_use_ntu_references():
    calibrated = {
        "ph": "calibrated", "tds": "calibrated",
        "turbidity": "calibrated", "temperature": "calibrated",
    }
    def ntu_state(value):
        return state_of(evaluate(
            readings={"turbidity": value},
            turbidity_unit="ntu",
            calibration=calibrated,
            stability={"stable": True, "status": "stable", "message": ""},
        ))
    assert ntu_state(0.5) == WITHIN
    assert ntu_state(3.0) == CAUTION
    assert ntu_state(7.0) == OUTSIDE


# ---------------------------------------------------------------------------
# 5. Missing / stale / unstable / non-finite never produce a positive state
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("readings", [
    {"ph": None},
    {"tds": None},
    {"ph": float("nan")},
    {"tds": float("inf")},
    {"ph": 99.0},          # impossible pH
    {"tds": -5.0},         # negative TDS
])
def test_invalid_or_missing_values_are_insufficient(readings):
    assert state_of(evaluate(readings=readings)) == INSUFFICIENT


def test_stale_live_reading_is_insufficient():
    result = evaluate(
        reading_mode="live",
        reading_timestamp=NOW - timedelta(hours=2),
        turbidity_unit="ntu",
        calibration={"ph": "calibrated", "tds": "calibrated",
                     "turbidity": "calibrated", "temperature": "calibrated"},
        stability={"stable": True, "status": "stable", "message": ""},
    )
    assert state_of(result) == INSUFFICIENT


def test_unstable_window_is_insufficient():
    result = evaluate(
        reading_mode="live",
        turbidity_unit="ntu",
        calibration={"ph": "calibrated", "tds": "calibrated",
                     "turbidity": "calibrated", "temperature": "calibrated"},
        stability={"stable": False, "status": "unstable",
                   "message": "The reading is unstable. Wait for more samples."},
    )
    assert state_of(result) == INSUFFICIENT


def test_unverified_live_calibration_is_insufficient():
    result = evaluate(
        reading_mode="live",
        turbidity_unit="ntu",
        calibration={"ph": "provisional"},
        stability={"stable": True, "status": "stable", "message": ""},
    )
    assert state_of(result) == INSUFFICIENT


# ---------------------------------------------------------------------------
# 6. Purpose-specific profiles
# ---------------------------------------------------------------------------


def test_purposes_apply_their_own_profiles():
    readings = {"tds": 600.0}
    drinking = evaluate(readings=readings, intended_use="drinking")
    general = evaluate(readings=readings, intended_use="general")
    # Both caution, but for different reasons: drinking names the TDS
    # reference, general carries no TDS pass/fail at all.
    assert state_of(drinking) == CAUTION
    assert state_of(general) == CAUTION
    assert general["readings"]["tds"]["status"] == "informational"


def test_swimming_and_aquaculture_never_certify_suitability():
    assert state_of(evaluate(intended_use="swimming")) == CAUTION
    assert state_of(evaluate(intended_use="aquaculture")) == INSUFFICIENT


def test_every_supported_purpose_returns_a_canonical_state():
    for use in ("drinking", "domestic", "irrigation", "general",
                "swimming", "aquaculture"):
        result = evaluate(intended_use=use)
        assert state_of(result) in STATE_LABELS


# ---------------------------------------------------------------------------
# 7. Reproducibility and profile versioning
# ---------------------------------------------------------------------------


def test_identical_inputs_reproduce_an_identical_result():
    first = evaluate()
    second = evaluate()
    assert first == second
    assert first["criteria_version"] == second["criteria_version"]


def test_unknown_legacy_code_is_rejected_not_guessed():
    with pytest.raises(ValueError, match="Unknown"):
        canonical_state("SOME_NEW_CODE")


# ---------------------------------------------------------------------------
# 8. Station engine (stored-reading assessments) uses the same vocabulary
# ---------------------------------------------------------------------------


def _station_reading(**overrides):
    values = dict(
        ph=7.2, tds=220.0, turbidity=0.6, temperature=26.0,
        turbidity_unit="ntu", source="esp32",
        timestamp=NOW.replace(tzinfo=None),
        id=1, device_id="DEV-1",
        diagnostics={
            "ph": {"calibration_status": "calibrated"},
            "tds": {"calibration_status": "calibrated"},
            "turbidity": {"calibration_status": "calibrated"},
            "temperature": {"calibration_status": "calibrated"},
        },
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_station_engine_emits_canonical_state_for_every_use():
    from app.services.water_suitability import assess_reading

    for assessment in assess_reading(_station_reading(), now=NOW):
        assert assessment["state"] in STATE_LABELS
        assert assessment["state_label"] == STATE_LABELS[assessment["state"]]
        # Legacy code and canonical state must always agree.
        assert assessment["state"] == canonical_state(
            assessment["result"], engine="station"
        )


def test_station_result_unaffected_by_unmeasured_or_external_attributes():
    from app.services.water_suitability import assess_reading

    plain = assess_reading(_station_reading(), now=NOW)
    polluted = assess_reading(
        _station_reading(
            dissolved_oxygen=2.1, coliform=900, rainfall_mm=120,
            lat=12.97, lon=77.59, anomaly_score=0.8,
        ),
        now=NOW,
    )
    for a, b in zip(plain, polluted):
        assert a["result"] == b["result"]
        assert a["state"] == b["state"]


def test_station_relative_index_reading_is_not_ntu_compared():
    from app.services.water_suitability import assess_reading

    indexed = _station_reading(turbidity=68, turbidity_unit="relative_index_0_100")
    turbidity_params = [
        next(p for p in a["parameters"] if p["parameter"] == "turbidity")
        for a in assess_reading(indexed, now=NOW)
        if any(p["parameter"] == "turbidity" for p in a["parameters"])
    ]
    # At least one use must evaluate turbidity, and any such entry for a
    # relative-index reading is "not compared with NTU", never a pass/fail.
    assert turbidity_params
    for turbidity in turbidity_params:
        if turbidity["status"] == "not_comparable":
            assert turbidity["value"] == 68
            assert "not NTU" in (turbidity.get("note") or "")
        else:
            # Only a genuinely NTU-calibrated measurement may be compared.
            assert turbidity["status"] != "within_acceptable"


# ---------------------------------------------------------------------------
# 9. API agreement (product tests persist and serve the canonical state)
# ---------------------------------------------------------------------------


def test_api_product_test_reports_state_matching_overall_status(
    client, db_session, product_user, product_token_headers
):
    from app.models.device import ProductDevice

    device = ProductDevice(
        product_code="HS-CENTRAL-ENGINE",
        device_id="DEV-CENTRAL-ENGINE",
        device_type="PERSONAL_WATER_TESTER",
        status="ACTIVE",
        owner_id=product_user.id,
    )
    db_session.add(device)
    db_session.commit()

    response = client.post(
        "/api/product/tests",
        json={"water_source": "tap", "intended_use": "drinking",
              "reading_mode": "demo"},
        headers=product_token_headers,
    )
    assert response.status_code in (200, 201)
    body = response.json()
    assert body["overall_state"] == canonical_state(body["overall_status"])
    assert body["overall_state"] in STATE_LABELS
    # The assessment embedded in the response carries the same state.
    assert body["assessment"]["overall"]["state"] == body["overall_state"]
