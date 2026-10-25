"""Rolling-window sensor stability detection.

Stability is NOT calibration. This module answers one question only: are the
last valid readings consistent enough to screen? A stable window can still come
from provisional/uncalibrated sensors; calibration is reported separately.

Central development settings:
  window          at least 10 valid samples spanning at least 20 s
  pH              window range <= 0.10
  TDS             window range <= max(10 mg/L, 5% of median)
  relative index  window range <= 5 index points
  NTU             window range <= max(0.2 NTU, 10% of median)
  temperature     window range <= 0.5 °C
  fresh sample    latest reading <= 30 s old (firmware publishes every 3 s)
  offline         latest reading > 120 s old

The station's actual stored readings are used; no synthetic values are added.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, List, Optional, Sequence

REQUIRED_SAMPLES = 10
MIN_SPAN_SECONDS = 20.0
WINDOW_SECONDS = 300.0
STALE_AFTER_SECONDS = 30.0
OFFLINE_AFTER_SECONDS = 120.0
FIRMWARE_PUBLISH_INTERVAL_SECONDS = 3.0

TOLERANCE_PH = 0.10
TOLERANCE_TDS_ABS = 10.0
TOLERANCE_TDS_REL = 0.05
TOLERANCE_RELATIVE_INDEX = 5.0
TOLERANCE_NTU_ABS = 0.2
TOLERANCE_NTU_REL = 0.10
TOLERANCE_TEMPERATURE = 0.5

STATUS_LABELS = {
    "waiting_for_data": "Waiting for sensor data",
    "collecting": "Collecting readings",
    "stabilizing": "Stabilizing sensors",
    "stable": "Readings stable",
    "unstable": "Reading unstable",
    "offline": "Device offline",
    "sensor_error": "Sensor error",
}


def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _diagnostics(reading: Any) -> Dict[str, Any]:
    diagnostics = getattr(reading, "diagnostics", None)
    return diagnostics if isinstance(diagnostics, dict) else {}


def sensor_errors(reading: Any) -> List[str]:
    """Device/sensor faults reported with the latest reading."""

    diagnostics = _diagnostics(reading)
    errors: List[str] = []
    for key in ("ph", "tds", "turbidity", "temperature"):
        entry = diagnostics.get(key)
        if not isinstance(entry, dict):
            continue
        if entry.get("valid") is False:
            label = entry.get("sensor") or key
            errors.append(f"{label}: {entry.get('error') or 'sensor reported invalid data'}")
        elif entry.get("error"):
            errors.append(f"{key}: {entry['error']}")
    device = diagnostics.get("device")
    if isinstance(device, dict) and isinstance(device.get("errors"), list):
        errors.extend(str(item) for item in device["errors"])
    return errors


def calibration_status(reading: Any) -> Dict[str, str]:
    diagnostics = _diagnostics(reading)
    result: Dict[str, str] = {}
    for key in ("ph", "tds", "turbidity", "temperature"):
        entry = diagnostics.get(key)
        if isinstance(entry, dict) and entry.get("calibration_status"):
            result[key] = str(entry["calibration_status"])
    return result


def _readings_ascending(readings: Sequence[Any]) -> List[Any]:
    return sorted(
        readings,
        key=lambda row: (_as_utc(getattr(row, "timestamp", None)) or datetime.min.replace(tzinfo=timezone.utc),
                         getattr(row, "id", 0)),
    )


def _valid_sample(reading: Any) -> Optional[Dict[str, Any]]:
    values = {
        "ph": _finite(getattr(reading, "ph", None)),
        "tds": _finite(getattr(reading, "tds", None)),
        "turbidity": _finite(getattr(reading, "turbidity", None)),
        "temperature": _finite(getattr(reading, "temperature", None)),
    }
    if any(value is None for value in values.values()):
        return None
    values["timestamp"] = _as_utc(getattr(reading, "timestamp", None))
    values["id"] = getattr(reading, "id", None)
    values["turbidity_unit"] = getattr(reading, "turbidity_unit", None)
    return values


def _tolerance(key: str, values: List[float], unit: Optional[str]) -> float:
    med = abs(median(values))
    if key == "ph":
        return TOLERANCE_PH
    if key == "tds":
        return max(TOLERANCE_TDS_ABS, TOLERANCE_TDS_REL * med)
    if key == "temperature":
        return TOLERANCE_TEMPERATURE
    if unit == "ntu":
        return max(TOLERANCE_NTU_ABS, TOLERANCE_NTU_REL * med)
    return TOLERANCE_RELATIVE_INDEX


def compute_stability(
    readings: Sequence[Any],
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Compute stability from recent stored readings (any order)."""

    now = now or datetime.now(timezone.utc)
    rows = _readings_ascending(readings)
    latest = rows[-1] if rows else None
    last_timestamp = _as_utc(getattr(latest, "timestamp", None)) if latest else None
    age = (now - last_timestamp).total_seconds() if last_timestamp else None

    errors = sensor_errors(latest) if latest else []
    calibration = calibration_status(latest) if latest else {}

    base: Dict[str, Any] = {
        "required_samples": REQUIRED_SAMPLES,
        "required_span_seconds": MIN_SPAN_SECONDS,
        "window_seconds": WINDOW_SECONDS,
        "firmware_publish_interval_seconds": FIRMWARE_PUBLISH_INTERVAL_SECONDS,
        "stale_after_seconds": STALE_AFTER_SECONDS,
        "offline_after_seconds": OFFLINE_AFTER_SECONDS,
        "valid_samples": 0,
        "span_seconds": 0.0,
        "progress": 0,
        "stable": False,
        "stale": False,
        "sensor_errors": errors,
        "calibration": calibration,
        "latest_timestamp": last_timestamp.isoformat() if last_timestamp else None,
        "age_seconds": age,
        "latest_reading_id": getattr(latest, "id", None) if latest else None,
        "per_parameter": {},
    }

    def result(status: str, message: str, **updates: Any) -> Dict[str, Any]:
        payload = {
            **base,
            **updates,
            "status": status,
            "status_label": STATUS_LABELS[status],
            "message": message,
            "connection": updates.pop("connection", "connected"),
        }
        payload["stable"] = status == "stable"
        return payload

    if latest is None:
        return result(
            "waiting_for_data",
            "Waiting for sensor data. No readings have been received for this device.",
            connection="no_data",
            progress=0,
        )

    if age is not None and age > OFFLINE_AFTER_SECONDS:
        return result(
            "offline",
            f"Device offline — last reading was {int(age // 60)} min ago.",
            connection="offline",
            stale=True,
            progress=0,
        )

    if errors:
        return result(
            "sensor_error",
            "Sensor error reported by the device: " + "; ".join(errors),
            connection="error",
            stale=bool(age is not None and age > STALE_AFTER_SECONDS),
            progress=0,
        )

    if age is not None and age > STALE_AFTER_SECONDS:
        return result(
            "collecting",
            f"Waiting for a fresh reading — the latest sample is {int(age)} s old.",
            connection="connecting",
            stale=True,
            progress=0,
        )

    cutoff = now.timestamp() - WINDOW_SECONDS
    valid: List[Dict[str, Any]] = []
    for row in reversed(rows):
        sample = _valid_sample(row)
        if sample is None:
            continue
        stamp = sample["timestamp"]
        if stamp is None or stamp.timestamp() < cutoff:
            continue
        valid.append(sample)
        if len(valid) == REQUIRED_SAMPLES:
            break

    valid_count = len(valid)
    if valid_count >= 2:
        span = (valid[0]["timestamp"] - valid[-1]["timestamp"]).total_seconds()
    else:
        span = 0.0

    # valid is newest-first after the loop.
    span = max(span, 0.0)
    progress = min(100, int((valid_count / REQUIRED_SAMPLES) * 100))

    base.update(
        valid_samples=valid_count,
        span_seconds=span,
        progress=progress,
    )

    if valid_count < REQUIRED_SAMPLES:
        return result(
            "collecting" if valid_count > 0 else "waiting_for_data",
            f"Collecting readings — {valid_count} of {REQUIRED_SAMPLES} valid samples.",
            valid_samples=valid_count,
            span_seconds=span,
            progress=progress,
        )

    if span < MIN_SPAN_SECONDS:
        return result(
            "stabilizing",
            f"Stabilizing sensors — {valid_count} valid samples span {span:.1f} s "
            f"(need {MIN_SPAN_SECONDS:.0f} s).",
            valid_samples=valid_count,
            span_seconds=span,
            progress=progress,
        )

    per_parameter: Dict[str, Any] = {}
    unstable: List[str] = []
    for key, label in (
        ("ph", "pH"),
        ("tds", "TDS"),
        ("turbidity", "Turbidity"),
        ("temperature", "Temperature"),
    ):
        values = [float(sample[key]) for sample in valid]
        low, high = min(values), max(values)
        spread = high - low
        tolerance = _tolerance(key, values, valid[0].get("turbidity_unit"))
        passed = spread <= tolerance + 1e-9
        if not passed:
            unstable.append(label)
        per_parameter[key] = {
            "label": label,
            "min": round(low, 3),
            "max": round(high, 3),
            "median": round(median(values), 3),
            "range": round(spread, 3),
            "tolerance": round(tolerance, 3),
            "stable": passed,
        }

    if unstable:
        return result(
            "unstable",
            "Reading unstable — variation exceeds the configured tolerance for: "
            + ", ".join(unstable) + ".",
            valid_samples=valid_count,
            span_seconds=span,
            progress=100,
            per_parameter=per_parameter,
        )

    return result(
        "stable",
        f"Readings stable — {valid_count} valid samples over {span:.0f} s.",
        valid_samples=valid_count,
        span_seconds=span,
        progress=100,
        per_parameter=per_parameter,
    )
