"""Canonical suitability states — the single vocabulary for every assessment.

Every water-use suitability decision in this project is derived from exactly
four sensor inputs (pH, TDS, temperature, turbidity index / calibrated turbidity)
plus the selected intended use and its configured threshold profile. The two
screening engines historically used different overall-status vocabularies:

- product/live tests (``water_screening.py``):
  ``WITHIN_PROJECT_TARGETS`` / ``REVIEW_RECOMMENDED`` /
  ``NOT_RECOMMENDED_BY_SCREENING`` / ``INCONCLUSIVE``
- station assessments (``water_suitability.py``):
  ``preliminary_suitable`` / ``treatment_required`` / ``outside_limits`` /
  ``lab_confirmation_required`` / ``insufficient_data``

This module maps both onto one canonical four-state vocabulary so the API,
UI and tests always agree:

``within_configured_ranges``  all required readings are valid and every
                              applicable configured screening rule passes
``caution``                   readings are valid but at least one parameter is
                              in a configured caution range
``outside_configured_ranges`` at least one valid reading falls outside the
                              configured acceptable range
``insufficient_data``         one or more required readings are missing, stale,
                              invalid or unavailable — never a positive result

Precedence is fixed: invalid, stale or unstable readings always collapse to
``insufficient_data`` BEFORE any pass/caution/fail rule is considered, so an
invalid or stale reading can never produce a positive suitability result.
"""

from __future__ import annotations

WITHIN = "within_configured_ranges"
CAUTION = "caution"
OUTSIDE = "outside_configured_ranges"
INSUFFICIENT = "insufficient_data"

STATE_LABELS = {
    WITHIN: "Within configured screening ranges",
    CAUTION: "Caution — further testing or treatment may be needed",
    OUTSIDE: "Outside configured screening ranges",
    INSUFFICIENT: "Insufficient data — check readings, calibration or timing",
}

# Order matters: any of these short-circuits to INSUFFICIENT regardless of the
# individual parameter verdicts.
INVALID_STATES = frozenset({INSUFFICIENT})

# Mappings from each engine's legacy overall code.
_SCREENING_MAP = {
    "WITHIN_PROJECT_TARGETS": WITHIN,
    "REVIEW_RECOMMENDED": CAUTION,
    "NOT_RECOMMENDED_BY_SCREENING": OUTSIDE,
    "INCONCLUSIVE": INSUFFICIENT,
}

_STATION_MAP = {
    "preliminary_suitable": WITHIN,
    # All measurable rules pass, but the standard requires laboratory
    # parameters this hardware cannot measure. The four measured indicators
    # DO pass the configured screening rules — this is still reported as
    # within_configured_ranges with the lab caveat attached, never as
    # "confirmed safe".
    "lab_confirmation_required": WITHIN,
    "treatment_required": CAUTION,
    "outside_limits": OUTSIDE,
    "insufficient_data": INSUFFICIENT,
}


def canonical_state(legacy_code: str, *, engine: str = "screening") -> str:
    """Map an engine's overall code to the canonical four-state vocabulary.

    Raises ``ValueError`` for an unknown code rather than guessing — a
    silently-invented state would be dishonest.
    """
    mapping = _SCREENING_MAP if engine == "screening" else _STATION_MAP
    try:
        return mapping[legacy_code]
    except KeyError:
        raise ValueError(
            f"Unknown {engine} result code: {legacy_code!r}. "
            "Extend app/services/screening_states.py deliberately instead of "
            "guessing a canonical state."
        ) from None


def state_label(state: str) -> str:
    return STATE_LABELS.get(state, state)


__all__ = [
    "WITHIN",
    "CAUTION",
    "OUTSIDE",
    "INSUFFICIENT",
    "STATE_LABELS",
    "canonical_state",
    "state_label",
]
