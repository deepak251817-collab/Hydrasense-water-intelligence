"""Central suitability engine — the single entry point for every decision.

Every water-use suitability decision in HydraSense comes from exactly four
sensor inputs plus the selected intended use and its configured threshold
profile:

1. pH (analog pH sensor)
2. TDS in ppm/mg/L (TDS sensor)
3. Temperature in °C (DS18B20)
4. Turbidity — relative index 0–100 (analog sensor) or calibrated NTU when the
   hardware actually reports it

Explicitly NOT inputs (they may exist elsewhere in the product, but can never
change a suitability result):

- dissolved oxygen, microbiology, heavy metals, pesticides, or any parameter
  the hardware does not measure;
- rainfall, weather, traffic, river location or any geographic information;
- historical readings, anomaly scores, ML predictions or forecast outputs;
- simulated values while assessing a real sensor sample (provenance is carried
  through and labelled, never mixed);
- any hidden composite "risk score" or external data source.

The heavy lifting (validation, per-parameter evaluation, explanations, profile
versioning) lives in ``app.services.water_screening.assess``; this module is
the enforced façade: it pins the input set, adds the canonical four-state
result (``app.services.screening_states``), and declares the input contract so
no caller can quietly widen it.

Every result is reproducible: identical four readings + intended use +
criteria (and threshold-profile version) produce an identical assessment.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Optional

from app.services import recommendations, water_screening
from app.services.screening_states import (
    CAUTION,
    INSUFFICIENT,
    OUTSIDE,
    STATE_LABELS,
    WITHIN,
    canonical_state,
    state_label,
)

# The complete, closed set of water-quality inputs the engine accepts.
INPUTS = ("ph", "tds", "temperature", "turbidity")

# Provenance labels surfaced in every result.
SOURCE_REAL = "real_sensor"
SOURCE_SIMULATED = "simulated"


def evaluate(
    readings: Mapping[str, Any],
    *,
    intended_use: str,
    reading_mode: str,
    reading_timestamp: Optional[datetime] = None,
    turbidity_unit: Optional[str] = None,
    calibration: Optional[Mapping[str, str]] = None,
    stability: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
    criteria: Optional[water_screening.ScreeningCriteria] = None,
    aquaculture_context: Optional[str] = None,
) -> dict[str, Any]:
    """Assess exactly the four supported readings for one intended use.

    Raises ``ValueError`` when ``readings`` contains any key outside
    ``INPUTS``: extra parameters (DO, ML scores, rainfall, history…) must not
    be able to influence a suitability decision, and a silent tolerance here
    would hide such an attempt.
    """
    extra = set(readings) - set(INPUTS)
    if extra:
        raise ValueError(
            "The suitability engine accepts only the four sensor inputs "
            f"{INPUTS}; received unsupported input(s): {sorted(extra)}. "
            "Additional parameters can never change a suitability result."
        )

    result = water_screening.assess(
        readings,
        intended_use=intended_use,
        reading_mode=reading_mode,
        reading_timestamp=reading_timestamp,
        turbidity_unit=turbidity_unit,
        calibration=calibration,
        stability=stability,
        now=now,
        criteria=criteria,
        aquaculture_context=aquaculture_context,
    )

    # Pin the canonical state and the engine's declared inputs on the result
    # so every consumer (API, UI, persistence) reads the same vocabulary.
    overall = result["overall"]
    state = canonical_state(overall["status"], engine="screening")
    overall["state"] = state
    overall["state_label"] = state_label(state)

    # Rule-based advice for non-passing results, derived only from the entries
    # this assessment actually triggered (see app/services/recommendations.py).
    result["recommendations"] = recommendations.for_screening(result)
    result["engine"] = {
        "name": "four-parameter screening engine",
        "version": water_screening.CRITERIA_VERSION,
        "inputs": list(INPUTS),
        "excluded_inputs": [
            "dissolved_oxygen",
            "microbiology",
            "chemical_contaminants",
            "weather_or_location",
            "historical_readings",
            "anomaly_scores",
            "ml_predictions",
            "forecasts",
        ],
        "source": SOURCE_SIMULATED if reading_mode == "demo" else SOURCE_REAL,
    }
    return result


__all__ = [
    "INPUTS",
    "evaluate",
    "canonical_state",
    "state_label",
    "STATE_LABELS",
    "WITHIN",
    "CAUTION",
    "OUTSIDE",
    "INSUFFICIENT",
]
