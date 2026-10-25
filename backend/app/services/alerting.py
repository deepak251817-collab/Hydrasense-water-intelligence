"""Danger-level alerts derived from measured readings.

Every alert is derived from an actual stored reading or a saved test — nothing
is invented. Alerts are plain dictionaries so the same structure can be
returned by the authority and product-user APIs and rendered directly by the
frontend.

All numeric triggers come from ``app.services.alert_thresholds`` — the single,
versioned threshold profile. Each alert carries the threshold it fired on, its
classification (``official_standard`` vs ``project_configured``), the source of
that threshold and its rationale, plus the profile version, so the UI can show
the active profile and never present a project setting as a regulatory limit.

Severity:

- ``critical`` — a measured value breached a critical condition of the profile;
- ``warning``  — a value breached a warning condition, a sensor stopped
  reporting, or the reading is stale.

Turbidity alerts use the analog sensor's documented 0–100 RELATIVE INDEX bands
(CLEARER < 30, MODERATE 30–54, CLOUDIER ≥ 55, higher = cloudier). The index is
never compared with an NTU limit, and an alert never claims a measurement the
sensor cannot make.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models.water import SensorReading
from app.models.water_test import ProductWaterTest
from app.services.alert_thresholds import (
    BY_KEY,
    PROFILE_VERSION,
    Threshold,
    profile_payload,
)

# Parameter labels/units for the four sensors + freshness.
_UNITS = {
    "ph": "pH",
    "tds": "mg/L",
    "turbidity_index": "0-100 index",
    "temperature": "°C",
    "freshness": "min",
}
_LABELS = {
    "ph": "pH",
    "tds": "TDS",
    "turbidity_index": "Turbidity index",
    "temperature": "Temperature",
    "freshness": "Data freshness",
}


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _alert(
    *,
    parameter: str,
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
    threshold: Optional[Threshold] = None,
) -> Dict[str, Any]:
    return {
        "parameter": parameter,
        "label": _LABELS.get(parameter, parameter),
        "value": value,
        "unit": unit,
        "severity": severity,
        "title": title,
        "message": message,
        "reference": reference,
        "next_step": next_step,
        "timestamp": _as_utc(at).isoformat(),
        "source": source,
        "simulated": simulated,
        # Threshold provenance: which configured threshold fired, whether it is
        # an official standard or a project setting, and where it comes from.
        "threshold_key": threshold.key if threshold else None,
        "threshold_classification": threshold.classification if threshold else None,
        "threshold_source": threshold.source if threshold else None,
        "threshold_rationale": threshold.rationale if threshold else None,
        "threshold_profile_version": PROFILE_VERSION if threshold else None,
    }


def _condition_text(threshold: Threshold, severity: str) -> str:
    conditions = threshold.critical if severity == "critical" else threshold.warning
    return " or ".join(condition.describe() for condition in conditions)


def _zone_description(threshold: Threshold) -> str:
    """Full configured zones: warning level and critical level."""
    parts = []
    if threshold.warning:
        parts.append(
            "alert when " + " or ".join(c.describe() for c in threshold.warning)
        )
    if threshold.critical:
        parts.append(
            "critical when " + " or ".join(c.describe() for c in threshold.critical)
        )
    return "; ".join(parts) or "informational only"


def _threshold_alert(
    threshold: Threshold,
    value: Optional[float],
    *,
    at: datetime,
    source: str,
    simulated: bool,
    severity: Optional[str] = None,
    message_suffix: str = "",
    next_step: str = "",
) -> Optional[Dict[str, Any]]:
    """Build one alert for a threshold breach (None when the value is fine).

    ``severity`` overrides the zone-derived severity when a separate threshold
    entry documents the critical band (so a critical pH alert is classified as
    the project choice it is, not as the official reference).
    """

    if value is None:
        return None
    zone = threshold.zone(value)
    if zone == "ok":
        return None
    severity = severity or zone
    if severity not in ("warning", "critical"):
        return None
    unit = _UNITS.get(threshold.parameter, threshold.unit)
    condition = _condition_text(threshold, severity)
    message = (
        f"{threshold.label}: {value:g} {unit} breaches the configured "
        f"{'critical level' if severity == 'critical' else 'screening level'} "
        f"({condition})."
    )
    if message_suffix:
        message = f"{message} {message_suffix}"

    return _alert(
        parameter=threshold.parameter,
        value=value,
        unit=unit,
        severity=severity,
        title=(
            f"{'Danger' if severity == 'critical' else 'Warning'} level: "
            f"{threshold.label.lower()} outside the configured screening range"
        ),
        message=message,
        reference=(
            f"{threshold.label} — {_zone_description(threshold)}. "
            f"{threshold.source} "
            f"[{threshold.classification.replace('_', ' ')}; profile {PROFILE_VERSION}]"
        ),
        next_step=next_step or (
            "Confirm the value with a calibrated instrument before relying on it, "
            "and review the other parameters."
        ),
        at=at,
        source=source,
        simulated=simulated,
        threshold=threshold,
    )


def reading_alerts(
    reading: SensorReading,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Build alerts for one stored reading (hardware or labelled simulation)."""

    if reading is None:
        return []

    now = now or datetime.now(timezone.utc)
    at = reading.timestamp
    simulated = reading.source != "esp32"
    source = reading.source
    alerts: List[Dict[str, Any]] = []

    # --- freshness (stale readings must never read as live) ---------------
    age_seconds = (now - _as_utc(at)).total_seconds()
    freshness_threshold = BY_KEY["freshness_stale"]
    if freshness_threshold.zone(age_seconds) in ("warning", "critical"):
        alerts.append(_alert(
            parameter="freshness",
            value=round(age_seconds / 60.0, 1),
            unit="min",
            severity="warning",
            title="Reading is stale",
            message=(
                f"The last measurement is {int(age_seconds // 60)} min old, so it "
                "does not describe current conditions."
            ),
            reference=(
                f"Stale-reading policy — {freshness_threshold.warning[0].describe()}. "
                f"{freshness_threshold.source} "
                f"[project configured; profile {PROFILE_VERSION}]"
            ),
            next_step="Wait for a new reading before acting on this result.",
            at=at,
            source=source,
            simulated=simulated,
            threshold=freshness_threshold,
        ))

    # --- pH ----------------------------------------------------------------
    if reading.ph is None:
        alerts.append(_alert(
            parameter="ph", value=None, unit=_UNITS["ph"], severity="warning",
            title="pH sensor not reporting",
            message="No pH value is available for this measurement.",
            reference=(
                f"pH screening range — 6.5–8.5. {BY_KEY['ph_range'].source} "
                "[official standard]"
            ),
            next_step="Check the pH probe connection and calibration, then retest.",
            at=at, source=source, simulated=simulated,
            threshold=BY_KEY["ph_range"],
        ))
    else:
        danger_zone = BY_KEY["ph_danger"].zone(reading.ph)
        if danger_zone != "ok":
            # Critical band is a project-configured choice — classified as such.
            alert = _threshold_alert(
                BY_KEY["ph_danger"], reading.ph, at=at, source=source,
                simulated=simulated, severity="critical",
                next_step=(
                    "Do not use this water until the reading is confirmed with a "
                    "calibrated meter and, if confirmed, treated or tested in a "
                    "laboratory."
                ),
            )
        else:
            alert = _threshold_alert(
                BY_KEY["ph_range"], reading.ph, at=at, source=source,
                simulated=simulated, severity="warning",
            )
        if alert:
            alerts.append(alert)

    # --- TDS ----------------------------------------------------------------
    if reading.tds is None:
        alerts.append(_alert(
            parameter="tds", value=None, unit=_UNITS["tds"], severity="warning",
            title="TDS sensor not reporting",
            message="No TDS value is available for this measurement.",
            reference=(
                f"TDS acceptable reference — 500 mg/L acceptable / 2000 mg/L "
                f"permissible. {BY_KEY['tds_acceptable'].source} [official standard]"
            ),
            next_step="Check the TDS sensor connection, then retest.",
            at=at, source=source, simulated=simulated,
            threshold=BY_KEY["tds_acceptable"],
        ))
    else:
        alert = _threshold_alert(
            BY_KEY["tds_acceptable"], reading.tds, at=at, source=source,
            simulated=simulated,
            next_step=(
                "Avoid use pending laboratory confirmation and treatment advice."
            ) if BY_KEY["tds_acceptable"].zone(reading.tds) == "critical" else "",
        )
        if alert:
            alerts.append(alert)

    # --- Turbidity index (relative 0–100, NEVER NTU) -----------------------
    index = reading.turbidity_index
    if index is None and reading.turbidity_unit == "relative_index_0_100":
        index = reading.turbidity
    index_threshold = BY_KEY["turbidity_index_bands"]
    if index is None:
        alerts.append(_alert(
            parameter="turbidity_index", value=None, unit=_UNITS["turbidity_index"],
            severity="warning",
            title="Turbidity sensor not reporting",
            message="No turbidity index value is available for this measurement.",
            reference=(
                "Relative index 0–100 (higher = cloudier). Not NTU. "
                f"{index_threshold.source} [project configured]"
            ),
            next_step="Check the turbidity sensor connection, then retest.",
            at=at, source=source, simulated=simulated,
            threshold=index_threshold,
        ))
    else:
        alert = _threshold_alert(
            index_threshold, index, at=at, source=source, simulated=simulated,
            message_suffix=(
                "This is a relative sensor index, not an NTU measurement, and it "
                "is never compared with NTU limits."
            ),
            next_step=(
                "Inspect the water visually, check the sensor for fouling, and "
                "confirm clarity with a calibrated NTU instrument if compliance "
                "matters."
            ),
        )
        if alert:
            alerts.append(alert)

    # --- Temperature (context only) -----------------------------------------
    if reading.temperature is None:
        alerts.append(_alert(
            parameter="temperature", value=None, unit=_UNITS["temperature"],
            severity="warning",
            title="Temperature sensor not reporting",
            message="No temperature value is available for this measurement.",
            reference=(
                "Temperature has no single drinking-water pass/fail limit; it "
                "provides context and supports trend analysis. "
                "[project configured]"
            ),
            next_step="Check the temperature sensor connection, then retest.",
            at=at, source=source, simulated=simulated,
            threshold=BY_KEY["temperature_unusual"],
        ))
    else:
        alert = _threshold_alert(
            BY_KEY["temperature_unusual"], reading.temperature, at=at, source=source,
            simulated=simulated,
            message_suffix=(
                "Temperature alone does not establish water safety — this is a "
                "context flag, not a safety limit."
            ),
            next_step="Confirm the sensor reading and review the trend.",
        )
        if alert:
            alerts.append(alert)

    return alerts


# Screening-reference classifications used by saved-test alerts.
_OFFICIAL_MARKERS = ("BIS", "CPCB", "FAO", "WHO")


def _classification_for(reference: str) -> str:
    upper = (reference or "").upper()
    return (
        "official_standard"
        if any(marker in upper for marker in _OFFICIAL_MARKERS)
        else "project_configured"
    )


def test_alerts(test: ProductWaterTest) -> List[Dict[str, Any]]:
    """Build alerts from a saved test's per-parameter screening results."""

    assessment = test.assessment if isinstance(test.assessment, dict) else {}
    at = test.created_at or datetime.now(timezone.utc)
    simulated = test.reading_source != "esp32"
    alerts: List[Dict[str, Any]] = []

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
        reference = reference or ""
        alerts.append({
            "parameter": parameter,
            "label": entry.get("label") or "Parameter",
            "value": entry.get("value"),
            "unit": entry.get("unit") or "",
            "severity": severity,
            "title": f"{entry.get('label') or 'Parameter'} needs attention",
            "message": entry.get("message") or entry.get("status_label") or
                "The measured value is outside the configured screening reference.",
            "reference": reference,
            "next_step": (next_steps[0] if next_steps else
                "Confirm with a calibrated instrument and laboratory testing."),
            "timestamp": _as_utc(at).isoformat(),
            "source": test.reading_source,
            "simulated": simulated,
            "test_id": test.id,
            "intended_use": test.intended_use,
            # Provenance of the screening reference cited by this entry.
            "threshold_classification": _classification_for(reference),
            "threshold_source": reference,
            "threshold_profile_version": PROFILE_VERSION,
        })
    return alerts


def alert_response(items: List[Dict[str, Any]], limit: int) -> Dict[str, Any]:
    """Standard alert-list payload, including the active threshold profile."""

    items.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
    return {
        "total": len(items),
        "items": items[:limit],
        "critical_count": sum(1 for i in items if i.get("severity") == "critical"),
        "warning_count": sum(1 for i in items if i.get("severity") == "warning"),
        "threshold_profile": profile_payload(),
    }
