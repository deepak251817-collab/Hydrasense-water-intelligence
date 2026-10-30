"""Rule-based recommendation engine tests.

Covers the contract the spec requires:

- one content test per rule in the ``(use, parameter, direction)`` table;
- advice never names an unmeasured parameter as a cause or an action;
- no temperature advice (there is no temperature threshold);
- drinking advice ends with laboratory confirmation and never claims safety;
- recommendations exist only for caution / not-suitable / insufficient results;
- authority incident steps appear only on the authority view;
- the API surfaces (public, authority) return the same advice.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services import recommendations as rec
from app.services import suitability_engine
from app.services.screening_states import WITHIN, canonical_state

# --------------------------------------------------------------------------- #
# Rule-table contract
# --------------------------------------------------------------------------- #

RULE_KEYS = sorted(rec.RULES)


def test_rule_table_is_keyed_by_use_parameter_direction():
    assert RULE_KEYS, "the rule table must not be empty"
    for key in RULE_KEYS:
        use, parameter, direction = key
        assert use in rec.USES, key
        assert parameter in rec.PARAMETERS, key
        assert direction in rec.DIRECTIONS, key


def test_no_rule_exists_for_temperature():
    """Temperature has no configured threshold, so it cannot drive advice."""
    assert not any(parameter == "temperature" for _, parameter, _ in RULE_KEYS)


def test_every_use_covers_its_data_quality_case():
    for use in rec.USES:
        assert (use, "data_quality", "missing") in rec.RULES


@pytest.mark.parametrize("key", RULE_KEYS)
def test_rule_content_is_well_formed(key):
    _, _, _ = key
    rule = rec.RULES[key]
    assert rule["urgency"] in rec.URGENCY_LEVELS
    assert rule["possible_causes"], key
    assert rule["actions"], key
    for text in list(rule["possible_causes"]) + list(rule["actions"]) + list(rule["avoid"]):
        assert isinstance(text, str) and text.strip(), key


@pytest.mark.parametrize("key", RULE_KEYS)
def test_rule_never_names_an_unmeasured_parameter(key):
    """Causes and actions may only reference measured sensors / data quality."""
    rule = rec.RULES[key]
    advice = " ".join(rule["possible_causes"] + rule["actions"] + rule["avoid"]).lower()
    for term in rec.UNMEASURED_TERMS:
        assert term not in advice, f"{key} advice mentions unmeasured '{term}'"


@pytest.mark.parametrize("key", RULE_KEYS)
def test_rule_causes_are_hedged_not_asserted(key):
    """A single reading cannot identify a source: causes must not assert one."""
    rule = rec.RULES[key]
    banned = ("is caused by", "is because", "resulted from", "proves that")
    for cause in rule["possible_causes"]:
        lowered = cause.lower()
        assert not any(phrase in lowered for phrase in banned), (key, cause)


@pytest.mark.parametrize("key", [k for k in RULE_KEYS if k[0] == "drinking"])
def test_drinking_advice_ends_with_laboratory_confirmation(key):
    actions = rec.RULES[key]["actions"]
    assert "laboratory confirmation" in actions[-1].lower(), key


@pytest.mark.parametrize("key", [k for k in RULE_KEYS if k[0] == "drinking"])
def test_drinking_advice_never_claims_safety(key):
    rule = rec.RULES[key]
    advice = " ".join(rule["possible_causes"] + rule["actions"] + rule["avoid"]).lower()
    for claim in (
        "safe to drink",
        "guaranteed",
        "certified safe",
        "confirmed safe",
        "100% safe",
        "treatment makes",
        "makes the water safe",
    ):
        assert claim not in advice, (key, claim)
    # The required closing line is the honest one.
    assert "cannot confirm that the water is safe" in advice


@pytest.mark.parametrize("use", rec.USES)
def test_missing_assessments_name_what_is_not_measured(use):
    items = rec.MISSING_ASSESSMENTS[use]
    assert items, use
    assert any("not measured by these sensors" in item for item in items), use


# --------------------------------------------------------------------------- #
# Behaviour
# --------------------------------------------------------------------------- #


READING_KEYS = ("ph", "tds", "temperature", "turbidity")


def _screening(**overrides):
    readings = {
        "ph": 7.1,
        "tds": 220.0,
        "temperature": 25.0,
        "turbidity": 0.5,
    }
    readings.update(overrides.pop("readings", {}))
    # Scalar reading overrides (``_screening(turbidity=63.0)``) belong to the
    # readings dict, not to ``evaluate()``'s own keyword arguments.
    for key in READING_KEYS:
        if key in overrides:
            readings[key] = overrides.pop(key)
    return suitability_engine.evaluate(
        readings,
        intended_use=overrides.pop("intended_use", "drinking"),
        reading_mode=overrides.pop("reading_mode", "demo"),
        reading_timestamp=overrides.pop(
            "reading_timestamp", datetime.now(timezone.utc)
        ),
        turbidity_unit=overrides.pop("turbidity_unit", "ntu"),
        calibration=overrides.pop(
            "calibration",
            {"ph": "calibrated", "tds": "calibrated",
             "turbidity": "calibrated", "temperature": "calibrated"},
        ),
        stability=overrides.pop("stability", {"stable": True, "valid_samples": 12}),
        **overrides,
    )


def test_within_result_carries_no_recommendations():
    result = _screening()
    assert result["overall"]["state"] == WITHIN
    assert result["recommendations"]["recommendations"] == []
    assert result["recommendations"]["missing_assessments"] == []
    assert result["recommendations"]["authority_actions"] == []


def test_turbidity_index_downgrade_returns_unvalidated_advice():
    result = _screening(turbidity=63.0, turbidity_unit="relative_index_0_100")
    assert result["overall"]["state"] != WITHIN
    advice = result["recommendations"]["recommendations"]
    assert advice, "a caution result must carry advice"
    turbidity = [item for item in advice if item["parameter"] == "turbidity"]
    assert turbidity and turbidity[0]["direction"] == "unvalidated"
    assert "not calibrated NTU" in " ".join(turbidity[0]["possible_causes"])
    assert result["recommendations"]["missing_assessments"]


def test_pH_direction_changes_the_advice():
    high = _screening(readings={"ph": 9.4})
    low = _screening(readings={"ph": 5.2})
    high_advice = [i for i in high["recommendations"]["recommendations"] if i["parameter"] == "ph"]
    low_advice = [i for i in low["recommendations"]["recommendations"] if i["parameter"] == "ph"]
    assert high_advice[0]["direction"] == "above"
    assert low_advice[0]["direction"] == "below"
    assert high_advice[0]["actions"] != low_advice[0]["actions"]


def test_high_tds_is_severe_and_high_urgency():
    result = _screening(readings={"tds": 2400.0})
    tds = [i for i in result["recommendations"]["recommendations"] if i["parameter"] == "tds"]
    assert tds[0]["direction"] == "above_severe"
    assert tds[0]["urgency"] == "high"
    assert result["recommendations"]["urgency"] == "high"


def test_missing_reading_is_insufficient_with_data_quality_advice():
    result = _screening(readings={"ph": None})
    assert canonical_state(result["overall"]["status"]) == "insufficient_data"
    advice = result["recommendations"]["recommendations"]
    assert advice, "insufficient data must still produce guidance"
    assert {item["parameter"] for item in advice} <= {
        "ph", "tds", "turbidity", "data_quality"
    }


def test_advice_only_references_the_four_inputs():
    result = _screening(turbidity=63.0, turbidity_unit="relative_index_0_100",
                        readings={"ph": 9.5})
    parameters = {i["parameter"] for i in result["recommendations"]["recommendations"]}
    assert parameters <= set(rec.PARAMETERS)


def test_authority_actions_require_the_authority_view():
    result = _screening(turbidity=63.0, turbidity_unit="relative_index_0_100")
    assert result["recommendations"]["authority_actions"] == []

    advice = rec.for_screening(result, authority=True)
    steps = advice["authority_actions"]
    assert steps, "authority view must add the incident workflow"
    joined = " ".join(steps).lower()
    assert "grab sample" in joined
    assert "upstream" in joined
    assert "pollution control authority" in joined
    assert "laboratory result" in joined


def test_recommendations_are_reproducible():
    first = _screening(turbidity=63.0, turbidity_unit="relative_index_0_100")
    second = _screening(turbidity=63.0, turbidity_unit="relative_index_0_100")
    assert first["recommendations"] == second["recommendations"]


def test_unmeasured_external_inputs_cannot_shape_advice():
    """Only the four inputs plus data quality can reach a recommendation."""
    result = _screening(readings={"tds": 2400.0}, intended_use="irrigation")
    advice = result["recommendations"]
    text = " ".join(
        " ".join(i["possible_causes"] + i["actions"])
        for i in advice["recommendations"]
    ).lower()
    for term in rec.UNMEASURED_TERMS:
        assert term not in text
    # The irrigation entry points at its missing assessments instead.
    assert any("EC, SAR" in item for item in advice["missing_assessments"])


# --------------------------------------------------------------------------- #
# API surfaces
# --------------------------------------------------------------------------- #


def test_public_suitability_returns_recommendations(client, seeded_water_data):
    response = client.get("/api/public/stations/TEST-STA-01/suitability")
    assert response.status_code == 200, response.text
    assessments = response.json()["assessments"]
    assert assessments
    advice = assessments[0]["recommendations"]
    assert advice["authority_actions"] == [], "public view must not carry incident steps"
    assert isinstance(advice["recommendations"], list)
    assert isinstance(advice["missing_assessments"], list)


def test_authority_suitability_adds_incident_steps(
    client, seeded_water_data, authority_token_headers
):
    response = client.get(
        "/api/authority/stations/TEST-STA-01/suitability",
        headers=authority_token_headers,
    )
    assert response.status_code == 200, response.text
    assessments = response.json()["assessments"]
    assert assessments
    advice = assessments[0]["recommendations"]
    assert advice["authority_actions"], "authority view must carry incident steps"
    assert advice["authority_actions"] == rec.authority_actions(
        use=assessments[0]["use"],
        state=canonical_state(assessments[0]["result"], engine="station"),
    )


def test_authority_endpoint_requires_the_role(
    client, seeded_water_data, product_token_headers
):
    response = client.get(
        "/api/authority/stations/TEST-STA-01/suitability",
        headers=product_token_headers,
    )
    assert response.status_code == 403
