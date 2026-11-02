"""Boundary and data-quality tests for the shared four-sensor assessment.

These pin the official BIS/FAO references, the project-only strict TDS demo rule
(drinking profile only), the required overall states, and the rule that a
relative turbidity index is never compared with NTU.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.water_screening import (
    CRITERIA_VERSION,
    FRESH_WITHIN_SECONDS,
    ScreeningCriteria,
    assess,
    validate_readings,
)

NOW = datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)
STRICT_MESSAGE = "Does not meet the project's strict drinking-water TDS target of 200 ppm"

# A fully calibrated sensor set whose turbidity is genuinely NTU — the only
# way turbidity can be validated. With the default relative-index turbidity the
# best possible result for turbidity-rated uses is REVIEW_RECOMMENDED
# (unvalidated-turbidity cap), so tests whose intent is a clean pass use this.
CALIBRATED = {
    "ph": "calibrated", "tds": "calibrated",
    "turbidity": "calibrated", "temperature": "calibrated",
}
NTU_PASS = {"turbidity": 0.5, "unit": "ntu", "calibration": CALIBRATED}


def run(
    *,
    ph=7.2,
    tds=320.0,
    turbidity=18.0,
    temperature=25.0,
    unit="relative_index_0_100",
    use="drinking",
    mode="demo",
    calibration=None,
    timestamp=NOW,
    now=NOW,
    stability=None,
    criteria=None,
):
    return assess(
        {"ph": ph, "tds": tds, "turbidity": turbidity, "temperature": temperature},
        intended_use=use,
        reading_mode=mode,
        reading_timestamp=timestamp,
        turbidity_unit=unit,
        calibration=calibration or {},
        stability=stability,
        now=now,
        criteria=criteria,
    )


def status(result, parameter):
    return result["readings"][parameter]["status"]


def reason_text(result):
    return " ".join(detail["reason"] for detail in result["overall"]["reason_details"])


# ---------------------------------------------------------------------------
# pH boundaries
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ph", [6.5, 7.0, 8.5])
def test_ph_within_reference(ph):
    result = run(ph=ph, tds=320, **NTU_PASS)
    assert status(result, "ph") == "within_range"
    assert result["overall"]["status"] == "WITHIN_PROJECT_TARGETS"


@pytest.mark.parametrize("ph", [6.49, 8.51])
def test_ph_outside_reference(ph):
    result = run(ph=ph, tds=320)
    assert status(result, "ph") in ("below_reference", "above_reference")
    assert result["overall"]["status"] == "NOT_RECOMMENDED_BY_SCREENING"
    assert "pH" in result["overall"]["summary"]


# ---------------------------------------------------------------------------
# Drinking TDS: official BIS limits + project-only strict target
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "tds,tds_status,overall",
    [
        (199.9, "below_project_target", "REVIEW_RECOMMENDED"),
        (200.0, "within_range", "WITHIN_PROJECT_TARGETS"),
        (201.0, "within_range", "WITHIN_PROJECT_TARGETS"),
        (499.0, "within_range", "WITHIN_PROJECT_TARGETS"),
        (499.9, "within_range", "WITHIN_PROJECT_TARGETS"),
        (500.0, "within_range", "WITHIN_PROJECT_TARGETS"),
        (500.1, "above_acceptable", "REVIEW_RECOMMENDED"),
        (501.0, "above_acceptable", "REVIEW_RECOMMENDED"),
        (2000.0, "above_acceptable", "REVIEW_RECOMMENDED"),
        (2000.1, "above_permissible", "NOT_RECOMMENDED_BY_SCREENING"),
        (3000.0, "above_permissible", "NOT_RECOMMENDED_BY_SCREENING"),
    ],
)
def test_drinking_tds_boundaries(tds, tds_status, overall):
    result = run(tds=tds, **NTU_PASS)
    assert status(result, "tds") == tds_status
    assert result["overall"]["status"] == overall


def test_below_strict_target_message_is_explicit_and_not_an_official_unsafe_claim():
    result = run(tds=150)
    assert status(result, "tds") == "below_project_target"
    detail = next(
        item for item in result["overall"]["reason_details"] if item["parameter"] == "tds"
    )
    assert STRICT_MESSAGE in detail["reason"]
    assert "not an official BIS determination" in detail["reason"]
    assert "unsafe" in detail["reason"].lower()
    assert "project" in detail["status_label"].lower()
    assert result["overall"]["status"] == "REVIEW_RECOMMENDED"
    assert result["overall"]["label"] == (
        "Not suitable by the project's strict TDS target"
    )
    assert "not a certification that the water is safe to drink" in (
        result["overall"]["summary"].lower()
    )
    assert result["reference_profile"]["demo_rules"]["DEMO_STRICT_TDS_RULE"]["enabled"] is True
    assert result["reference_profile"]["demo_rules"]["DEMO_STRICT_TDS_RULE"]["is_official_standard"] is False


def test_strict_rule_can_be_disabled_without_changing_official_limits():
    criteria = ScreeningCriteria(demo_strict_tds_rule=False)
    result = run(tds=150, criteria=criteria, **NTU_PASS)
    assert status(result, "tds") == "within_range"
    assert result["overall"]["status"] == "WITHIN_PROJECT_TARGETS"
    assert result["reference_profile"]["demo_rules"]["DEMO_STRICT_TDS_RULE"]["enabled"] is False


def test_500_message_mentions_permissible_limit_condition():
    result = run(tds=800)
    detail = next(
        item for item in result["overall"]["reason_details"] if item["parameter"] == "tds"
    )
    assert "permissible limit applies only in the absence of an alternate source" in detail["reason"]


def test_above_2000_message_is_exact():
    result = run(tds=2100)
    detail = next(
        item for item in result["overall"]["reason_details"] if item["parameter"] == "tds"
    )
    assert detail["reason"] == "Exceeds the cited BIS permissible TDS reference."


# ---------------------------------------------------------------------------
# The strict rule is drinking-only; domestic/irrigation keep their own logic
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("use", ["domestic", "irrigation", "general"])
def test_strict_tds_rule_does_not_apply_to_other_uses(use):
    result = run(tds=150, use=use)
    assert status(result, "tds") != "below_project_target"
    assert STRICT_MESSAGE not in reason_text(result)


def test_domestic_tds_thresholds_are_unchanged():
    within = run(tds=500, use="domestic")
    assert status(within, "tds") == "within_range"
    above = run(tds=501, use="domestic")
    assert status(above, "tds") == "above_acceptable"
    beyond = run(tds=2001, use="domestic")
    assert status(beyond, "tds") == "above_permissible"
    assert beyond["overall"]["status"] == "NOT_RECOMMENDED_BY_SCREENING"


@pytest.mark.parametrize(
    "tds,tds_status,overall",
    [
        (449.0, "no_restriction", "REVIEW_RECOMMENDED"),
        (450.0, "slight_restriction", "REVIEW_RECOMMENDED"),
        (2000.0, "slight_restriction", "REVIEW_RECOMMENDED"),
        (2000.1, "severe_restriction", "NOT_RECOMMENDED_BY_SCREENING"),
    ],
)
def test_irrigation_fao_tds_categories(tds, tds_status, overall):
    result = run(tds=tds, use="irrigation")
    assert status(result, "tds") == tds_status
    assert result["overall"]["status"] == overall
    assert result["suitability"]["standard_code"] == "FAO-TDS-PH"


@pytest.mark.parametrize(
    "ph,ph_status",
    [(6.49, "below_reference"), (6.5, "within_range"), (8.4, "within_range"), (8.41, "above_reference")],
)
def test_irrigation_ph_reference(ph, ph_status):
    result = run(ph=ph, use="irrigation", tds=300)
    assert status(result, "ph") == ph_status


def test_irrigation_never_claims_complete_suitability():
    result = run(use="irrigation", tds=300, ph=7.0)
    suitability = result["suitability"]
    assert suitability["result"] == "REVIEW_RECOMMENDED"
    assert any(item["parameter"] == "ec" and item["status"] == "not_measured"
               for item in suitability["criteria"])
    assert any("not an irrigation suitability certification" in item
               or "cannot certify" in item for item in suitability["limitations"])


# ---------------------------------------------------------------------------
# Turbidity: calibrated NTU only; relative index never converted
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [0.0, 1.0])
def test_calibrated_ntu_within_acceptable(value):
    result = run(
        turbidity=value, unit="ntu",
        calibration={"turbidity": "calibrated", "ph": "calibrated",
                     "tds": "calibrated", "temperature": "calibrated"},
        mode="live",
    )
    assert status(result, "turbidity") == "within_range"


@pytest.mark.parametrize("value", [1.01, 5.0])
def test_calibrated_ntu_above_acceptable(value):
    result = run(turbidity=value, unit="ntu",
                 calibration={"turbidity": "calibrated", "ph": "calibrated",
                              "tds": "calibrated", "temperature": "calibrated"},
                 mode="live")
    assert status(result, "turbidity") == "above_acceptable"
    assert result["overall"]["status"] == "REVIEW_RECOMMENDED"


@pytest.mark.parametrize("value", [5.01, 30.0])
def test_calibrated_ntu_above_permissible(value):
    result = run(turbidity=value, unit="ntu",
                 calibration={"turbidity": "calibrated", "ph": "calibrated",
                              "tds": "calibrated", "temperature": "calibrated"},
                 mode="live")
    assert status(result, "turbidity") == "above_permissible"
    assert result["overall"]["status"] == "NOT_RECOMMENDED_BY_SCREENING"


def test_relative_index_is_never_compared_with_ntu():
    result = run(turbidity=49.0, unit="relative_index_0_100")
    turbidity = result["readings"]["turbidity"]
    assert turbidity["status"] == "not_comparable"
    assert "not NTU" in turbidity["unit"]
    assert "not compared" in turbidity["note"]
    # The verdict must point at a laboratory test instead of an NTU limit.
    assert "cannot be" in turbidity["note"] and "NTU limits" in turbidity["note"]
    assert "laboratory test" in turbidity["note"]
    # The NTU numbers must never appear as this row's own limits.
    for limit in ("1 NTU", "5 NTU"):
        if limit in turbidity["note"]:
            assert "not compared with the 1 NTU" in turbidity["note"]


def test_relative_index_does_not_create_a_green_pass():
    """pH and TDS passing with an unvalidated turbidity index is a CAUTION."""
    result = run(turbidity=80.0, unit="relative_index_0_100", tds=320)
    assert result["overall"]["status"] == "REVIEW_RECOMMENDED"
    assert "not a certification that the water is safe to drink" in (
        result["overall"]["summary"].lower()
    )
    assert any(item["parameter"] == "turbidity"
               for item in result["overall"]["reason_details"])
    # The exact reason must be stated in the warnings.
    assert any("NTU calibration required" in warning
               for warning in result["data_quality"]["warnings"])


def test_uncalibrated_ntu_is_not_compared():
    result = run(turbidity=3.0, unit="ntu", calibration={"turbidity": "pending"})
    assert status(result, "turbidity") == "not_comparable"
    assert "uncalibrated" in result["readings"]["turbidity"]["unit"].lower()


# ---------------------------------------------------------------------------
# Missing / invalid data and calibration
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_ph", [None, float("nan"), float("inf"), -0.1, 14.1])
def test_invalid_ph_is_inconclusive(bad_ph):
    result = run(ph=bad_ph)
    assert result["overall"]["status"] == "INCONCLUSIVE"
    assert result["readings"]["ph"]["value"] in (None, bad_ph)


@pytest.mark.parametrize("bad_tds", [None, float("nan"), -10.0, 6000.0])
def test_invalid_tds_is_inconclusive(bad_tds):
    result = run(tds=bad_tds)
    assert result["overall"]["status"] == "INCONCLUSIVE"


def test_missing_temperature_is_context_only():
    result = run(temperature=None, **NTU_PASS)
    assert status(result, "temperature") == "not_measured"
    assert result["overall"]["status"] == "WITHIN_PROJECT_TARGETS"
    assert any("Temperature" in warning for warning in result["data_quality"]["warnings"])


def test_validate_readings_reports_missing_and_invalid_values():
    check = validate_readings(
        {"ph": None, "tds": -5, "turbidity": None, "temperature": None},
        turbidity_unit=None,
    )
    assert len(check["errors"]) == 2
    assert any("pH" in err for err in check["errors"])
    assert any("TDS" in err for err in check["errors"])
    assert any("Turbidity" in warning for warning in check["warnings"])


def test_live_low_tds_inconclusive_still_says_not_suitable_because_of_tds():
    result = run(
        mode="live",
        tds=150,
        ph=7.2,
        calibration={"ph": "pending", "tds": "pending", "turbidity": "pending",
                     "temperature": "pending"},
        stability={"status": "stable", "stable": True, "message": "Readings stable"},
    )
    assert result["overall"]["status"] == "INCONCLUSIVE"
    assert result["overall"]["label"] == (
        "Not suitable by the project's strict TDS target — more data or "
        "calibration required"
    )
    summary = result["overall"]["summary"].lower()
    assert "not suitable under the project's strict drinking-water tds target" in summary
    assert "tds is below 200 ppm" in summary
    assert "not an official bis determination" in summary
    assert "more data or verified sensor calibration" in summary
    assert result["suitability"]["result_label"] == result["overall"]["label"]


def test_live_unverified_calibration_is_inconclusive_not_green():
    result = run(
        mode="live", tds=320, ph=7.2,
        calibration={"ph": "pending", "tds": "pending", "turbidity": "pending",
                     "temperature": "pending"},
    )
    assert result["data_quality"]["calibration_verified"] is False
    assert result["overall"]["status"] == "INCONCLUSIVE"
    assert "calibration is unverified" in result["overall"]["summary"].lower()
    assert any(detail["parameter"] == "calibration"
               for detail in result["overall"]["reason_details"])


def test_live_calibrated_stable_readings_can_pass():
    result = run(
        mode="live", tds=320, ph=7.2, **NTU_PASS,
        stability={"status": "stable", "stable": True, "message": "Readings stable"},
    )
    assert result["data_quality"]["calibration_verified"] is True
    assert result["overall"]["status"] == "WITHIN_PROJECT_TARGETS"


def test_demo_mode_is_labelled_simulation():
    result = run(mode="demo")
    assert result["data_quality"]["demo_mode"] is True
    assert result["data_quality"]["freshness"] == "simulated"
    assert any("SIMULATION" in warning for warning in result["data_quality"]["warnings"])


# ---------------------------------------------------------------------------
# Stability, staleness and offline
# ---------------------------------------------------------------------------

def test_stable_window_can_pass():
    stability = {"status": "stable", "stable": True, "message": "Readings stable"}
    result = run(stability=stability, **NTU_PASS)
    assert result["overall"]["status"] == "WITHIN_PROJECT_TARGETS"
    assert result["data_quality"]["stability"]["stable"] is True


def test_unstable_window_is_inconclusive():
    stability = {"status": "unstable", "stable": False, "message": "Reading unstable"}
    result = run(stability=stability)
    assert result["overall"]["status"] == "INCONCLUSIVE"


def test_offline_or_stale_window_is_inconclusive():
    for status_name in ("offline", "waiting_for_data", "sensor_error", "collecting", "stabilizing"):
        result = run(stability={"status": status_name, "stable": False,
                                 "message": f"{status_name} message"})
        assert result["overall"]["status"] == "INCONCLUSIVE"
        assert any(detail["parameter"] == "stability"
                   for detail in result["overall"]["reason_details"])


def test_stale_live_reading_is_inconclusive():
    old = NOW - timedelta(seconds=FRESH_WITHIN_SECONDS + 1)
    result = run(timestamp=old, now=NOW, mode="live")
    assert result["data_quality"]["freshness"] == "stale"
    assert result["overall"]["status"] == "INCONCLUSIVE"


# ---------------------------------------------------------------------------
# Intended uses and required messages
# ---------------------------------------------------------------------------

def test_drinking_never_certifies_potability():
    result = run(**NTU_PASS)
    assert result["overall"]["status"] == "WITHIN_PROJECT_TARGETS"
    assert "does not certify" in result["overall"]["summary"]
    assert "Laboratory testing is required" in " ".join(result["next_steps"])
    assert result["suitability"]["standard_code"] == "BIS-IS-10500:2012"


def test_domestic_is_not_universal_suitability():
    result = run(use="domestic", **NTU_PASS)
    assert result["overall"]["status"] == "WITHIN_PROJECT_TARGETS"
    assert "not a potability assessment" in result["overall"]["summary"]
    assert "different requirements" in result["overall"]["summary"]


def test_all_uses_return_a_status_and_reasons():
    for use in ("drinking", "domestic", "irrigation", "general"):
        result = run(use=use, tds=320, ph=7.2)
        assert result["overall"]["status"] in {
            "WITHIN_PROJECT_TARGETS", "REVIEW_RECOMMENDED",
            "NOT_RECOMMENDED_BY_SCREENING", "INCONCLUSIVE",
        }
        assert result["suitability"]["use"] == use


def test_multiple_failures_are_all_reported():
    result = run(ph=9.2, tds=2600, turbidity=8.0, unit="ntu",
                 calibration={"turbidity": "calibrated", "ph": "pending",
                              "tds": "pending", "temperature": "pending"},
                 mode="live")
    params = {detail["parameter"] for detail in result["overall"]["reason_details"]}
    assert {"ph", "tds", "turbidity", "calibration"} <= params


# ---------------------------------------------------------------------------
# Prediction honesty
# ---------------------------------------------------------------------------

def test_no_trained_forecast_is_fabricated():
    result = run()
    assert result["prediction"]["available"] is False
    assert "not configured" in result["prediction"]["message"]
    assert result["criteria_version"] == CRITERIA_VERSION
