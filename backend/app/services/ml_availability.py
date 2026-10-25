"""Honest per-reading ML availability status.

The Phase 6 models are NTU-trained: their validated input contract expects
turbidity in NTU-style units. A relative turbidity INDEX (0–100) is a different
quantity, so it must never be passed to those models as though it were NTU.
Readings taken with the analog index are therefore stored with NULL ML columns
— no prediction is fabricated — and this module explains WHY, so the API and UI
can say "ML prediction unavailable for Turbidity Index readings" instead of a
generic "unavailable".

The separate, index-trained model described in `docs/TURBIDITY_INDEX_ML.md`
does not exist yet (no representative labelled dataset), so the exclusion is
retained until such a model is trained and evaluated.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

TURBIDITY_UNIT_RELATIVE = "relative_index_0_100"

STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"

REASON_TURBIDITY_INDEX = "turbidity_index_not_ntu"
REASON_MISSING_VALUES = "missing_sensor_values"
REASON_NOT_PROCESSED = "not_processed"

MESSAGES = {
    REASON_TURBIDITY_INDEX: (
        "ML prediction unavailable for Turbidity Index readings. The existing "
        "models are trained on NTU measurements; a relative 0–100 index is a "
        "different quantity and is never fed to them as NTU. See "
        "docs/TURBIDITY_INDEX_ML.md for the data requirements of a compatible "
        "index model."
    ),
    REASON_MISSING_VALUES: (
        "ML prediction unavailable: one or more sensor values are missing for "
        "this reading. Missing data is never replaced with a fabricated value."
    ),
    REASON_NOT_PROCESSED: (
        "ML prediction unavailable: this reading was recorded before ML "
        "inference ran, or the model artifacts are not loaded. No result is "
        "fabricated."
    ),
}


def availability_for(reading: Any) -> Dict[str, Optional[str]]:
    """Return ``{status, reason, message}`` for one stored reading."""

    if reading is None:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": REASON_MISSING_VALUES,
            "message": MESSAGES[REASON_MISSING_VALUES],
        }

    unit = getattr(reading, "turbidity_unit", None)
    if unit == TURBIDITY_UNIT_RELATIVE:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": REASON_TURBIDITY_INDEX,
            "message": MESSAGES[REASON_TURBIDITY_INDEX],
        }

    if None in (
        getattr(reading, "ph", None),
        getattr(reading, "turbidity", None),
        getattr(reading, "tds", None),
        getattr(reading, "temperature", None),
    ):
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": REASON_MISSING_VALUES,
            "message": MESSAGES[REASON_MISSING_VALUES],
        }

    if getattr(reading, "ml_processed_at", None) is None:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": REASON_NOT_PROCESSED,
            "message": MESSAGES[REASON_NOT_PROCESSED],
        }

    return {"status": STATUS_OK, "reason": None, "message": None}
