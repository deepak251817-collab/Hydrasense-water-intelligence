"""Danger-level alerts derived from measured readings.

Every alert is derived from an actual stored reading or a saved test — nothing
is invented. Alerts are plain dictionaries so the same structure can be
returned by the authority and product-user APIs and rendered directly by the
frontend.

Severity rules (project configuration, not a regulatory determination):

- ``critical`` — a measured value is at a danger level for the configured
  screening profile (strongly outside the reference range).
- ``warning``  — a value is outside the configured range, a sensor stopped
  reporting, or the reading is stale.

Turbidity alerts use the analog sensor's documented 0-100 RELATIVE INDEX bands
(CLEARER < 30, MODERATE 30-54, CLOUDIER >= 55, higher = cloudier). The index is
never compared with an NTU limit, and an alert never claims a measurement the
sensor cannot make.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models.water import SensorReading
from app.models.water_test import ProductWaterTest

# Configurable danger levels (project screening configuration).
PH_DANGER_MIN, PH_DANGER_MAX = 6.0, 9.0
PH_RANGE_MIN, PH_RANGE_MAX = 6.5, 8.5
TDS_WATCH_MAX = 500.0
TDS_DANGER_MAX = 2000.0
TURBIDITY_INDEX_WATCH = 55.0   # CLOUDIER band (firmware documentation)
TURBIDITY_INDEX_DANGER = 80.0  # strongly cloudier — demo danger level
TEMPERATURE_UNUSUAL_MIN = 5.0
TEMPERATURE_UNUSUAL_MAX = 40.0

STALE_AFTER_SECONDS = 300  # matches FRESH_WITHIN_SECONDS in water_screening


def _alert(
    parameter: str,
    label: str,
    value: Optional[float],
    unit: str,
    severity: str,
    title: str,
    message: str,
    reference: str,
    next_step: str,
    at: datetime,
    source: str,
    simulated: bool,
) -> Dict[str, Any]:
    return {
        "parameter": parameter,
        "label": label,
        "value": value,
        "unit": unit,
        "severity": severity,
        "title": title,
        "message": message,
        "reference": reference,
        "next_step": next_step,
        "timestamp": at.isoformat(),
        "source": source,
        "simulated": simulated,
    }


def reading_alerts(
    reading: SensorReading,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Build alerts for one stored reading (hardware or labelled simulation)."""

    if reading is None:
        return []

    now = now or datetime.now(timezone.utc)
    at = reading.timestamp if reading.timestamp.tzinfo else reading.timestamp.replace(tzinfo=timezone.utc)
    simulated = reading.source != "esp32"
    source = reading.source
    alerts: List[Dict[str, Any]] = []

    # --- freshness -------------------------------------------------------
    age = (now - at).total_seconds()
    if age > STALE_AFTER_SECONDS:
        alerts.append(_alert(
            "freshness", "Data freshness", round(age / 60.0, 1), "min",
            "warning",
            "Reading is stale",
            f"The last measurement is {int(age // 60)} min old, so it does not "
            "describe current conditions.",
            f"Readings older than {STALE_AFTER_SECONDS // 60} min are treated as stale.",
            "Wait for a new reading before acting on this result.",
            at, source, simulated,
        ))

    # --- pH --------------------------------------------------------------
    ph = reading.ph
    if ph is None:
        alerts.append(_alert(
            "ph", "pH", None, "pH", "warning",
            "pH sensor not reporting",
            "No pH value is available for this measurement.",
            "Configured drinking-water reference: pH 6.5-8.5 (BIS IS 10500:2012).",
            "Check the pH probe connection and calibration, then retest.",
            at, source, simulated,
        ))
    elif ph < PH_DANGER_MIN or ph > PH_DANGER_MAX:
        alerts.append(_alert(
            "ph", "pH", ph, "pH", "critical",
            "Danger level: pH far outside the reference range",
            f"pH is {ph}, well outside the configured 6.5-8.5 range.",
            f"Configured range {PH_RANGE_MIN}-{PH_RANGE_MAX}; danger below "
            f"{PH_DANGER_MIN} or above {PH_DANGER_MAX}.",
            "Do not use this water until the reading is confirmed with a "
            "calibrated meter and, if confirmed, treated or tested in a laboratory.",
            at, source, simulated,
        ))
    elif ph < PH_RANGE_MIN or ph > PH_RANGE_MAX:
        alerts.append(_alert(
            "ph", "pH", ph, "pH", "warning",
            "pH outside the configured range",
            f"pH is {ph}, outside the configured 6.5-8.5 range.",
            "Configured drinking-water reference: pH 6.5-8.5 (BIS IS 10500:2012).",
            "Recheck with a calibrated meter and review the other parameters.",
            at, source, simulated,
        ))

    # --- TDS -------------------------------------------------------------
    tds = reading.tds
    if tds is None:
        alerts.append(_alert(
            "tds", "TDS", None, "mg/L", "warning",
            "TDS sensor not reporting",
            "No TDS value is available for this measurement.",
            "Configured references: 500 mg/L acceptable, 2000 mg/L permissible "
            "(BIS IS 10500:2012).",
            "Check the TDS sensor connection, then retest.",
            at, source, simulated,
        ))
    elif tds > TDS_DANGER_MAX:
        alerts.append(_alert(
            "tds", "TDS", tds, "mg/L", "critical",
            "Danger level: TDS exceeds the permissible reference",
            f"TDS is {tds} mg/L, above the 2000 mg/L permissible reference.",
            "BIS IS 10500:2012 permissible TDS 2000 mg/L (absence of an "
            "alternate source).",
            "Avoid use pending laboratory confirmation and treatment advice.",
            at, source, simulated,
        ))
    elif tds > TDS_WATCH_MAX:
        alerts.append(_alert(
            "tds", "TDS", tds, "mg/L", "warning",
            "TDS above the acceptable reference",
            f"TDS is {tds} mg/L, above the 500 mg/L acceptable reference.",
            "BIS IS 10500:2012 acceptable TDS 500 mg/L.",
            "Investigate the source and confirm with laboratory testing.",
            at, source, simulated,
        ))

    # --- Turbidity index (relative 0-100, NEVER NTU) ---------------------
    index = reading.turbidity_index
    if index is None and reading.turbidity_unit == "relative_index_0_100":
        index = reading.turbidity
    if index is None:
        alerts.append(_alert(
            "turbidity_index", "Turbidity index", None, "0-100 index", "warning",
            "Turbidity sensor not reporting",
            "No turbidity index value is available for this measurement.",
            "Relative index 0-100 (higher = cloudier). Not NTU.",
            "Check the turbidity sensor connection, then retest.",
            at, source, simulated,
        ))
    elif index >= TURBIDITY_INDEX_DANGER:
        alerts.append(_alert(
            "turbidity_index", "Turbidity index", index, "0-100 index", "critical",
            "Danger level: turbidity index strongly cloudier",
            f"The turbidity index is {index} (CLOUDIER band). This is a relative "
            "sensor index, not an NTU measurement.",
            "Documented demo bands: CLEARER < 30, MODERATE 30-54, CLOUDIER >= 55 "
            "(higher = cloudier).",
            "Inspect the water visually, check the sensor for fouling, and confirm "
            "clarity with a calibrated NTU instrument if compliance matters.",
            at, source, simulated,
        ))
    elif index >= TURBIDITY_INDEX_WATCH:
        alerts.append(_alert(
            "turbidity_index", "Turbidity index", index, "0-100 index", "warning",
            "Turbidity index in the CLOUDIER band",
            f"The turbidity index is {index}. This is a relative sensor index, "
            "not an NTU measurement.",
            "Documented demo bands: CLEARER < 30, MODERATE 30-54, CLOUDIER >= 55 "
            "(higher = cloudier).",
            "Review recent changes at the source and retest.",
            at, source, simulated,
        ))

    # --- Temperature (context only) --------------------------------------
    temperature = reading.temperature
    if temperature is None:
        alerts.append(_alert(
            "temperature", "Temperature", None, "°C", "warning",
            "Temperature sensor not reporting",
            "No temperature value is available for this measurement.",
            "Temperature has no single drinking-water pass/fail limit; it provides "
            "context and supports trend analysis.",
            "Check the temperature sensor connection, then retest.",
            at, source, simulated,
        ))
    elif temperature < TEMPERATURE_UNUSUAL_MIN or temperature > TEMPERATURE_UNUSUAL_MAX:
        alerts.append(_alert(
            "temperature", "Temperature", temperature, "°C", "warning",
            "Unusual water temperature",
            f"Temperature is {temperature} °C, unusual for the monitored sources.",
            f"Context band {TEMPERATURE_UNUSUAL_MIN}-{TEMPERATURE_UNUSUAL_MAX} °C "
            "(project configuration, not a safety limit).",
            "Confirm the sensor reading; temperature alone does not establish "
            "water safety.",
            at, source, simulated,
        ))

    return alerts


def test_alerts(test: ProductWaterTest) -> List[Dict[str, Any]]:
    """Build alerts from a saved test's per-parameter screening results."""

    assessment = test.assessment if isinstance(test.assessment, dict) else {}
    at = test.created_at
    if at is None:
        at = datetime.now(timezone.utc)
    elif at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)

    simulated = test.reading_source != "esp32"
    alerts: List[Dict[str, Any]] = []

    # `attention` holds every per-parameter entry whose status is a concern
    # status; `readings` holds all four entries with their references.
    readings = assessment.get("readings", {})
    attention = assessment.get("attention", [])
    next_steps = assessment.get("next_steps", [])

    for entry in attention:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status") or "")
        severity = "critical" if status in (
            "above_permissible", "severe_restriction", "invalid"
        ) else "warning"
        parameter = str(entry.get("parameter") or "parameter")
        full = readings.get(parameter) if isinstance(readings, dict) else None
        reference = full.get("reference") if isinstance(full, dict) else None
        alerts.append({
            "parameter": parameter,
            "label": entry.get("label") or "Parameter",
            "value": entry.get("value"),
            "unit": entry.get("unit") or "",
            "severity": severity,
            "title": f"{entry.get('label') or 'Parameter'} needs attention",
            "message": entry.get("message") or entry.get("status_label") or
                "The measured value is outside the configured screening reference.",
            "reference": reference or "",
            "next_step": (next_steps[0] if next_steps else
                "Confirm with a calibrated instrument and laboratory testing."),
            "timestamp": at.isoformat(),
            "source": test.reading_source,
            "simulated": simulated,
            "test_id": test.id,
            "intended_use": test.intended_use,
        })
    return alerts
