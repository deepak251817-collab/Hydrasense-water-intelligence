"""Live Monitoring assessment built on the shared four-sensor screening service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.water import MonitoringStation, SensorReading
from app.models.water_test import LiveWaterAssessment
from app.services.sensor_stability import compute_stability
from app.services.water_screening import CRITERIA_VERSION, USE_LABELS, assess

POLL_INTERVAL_SECONDS = 5
READING_WINDOW_LIMIT = 40

CONNECTION_LABELS = {
    "connected": "Connected",
    "connecting": "Connecting",
    "offline": "Offline",
    "error": "Error",
    "no_data": "Waiting for data",
}


def recent_readings(db: Session, station_id: int, limit: int = READING_WINDOW_LIMIT):
    return (
        db.query(SensorReading)
        .filter(SensorReading.station_id == station_id)
        .order_by(SensorReading.timestamp.desc(), SensorReading.id.desc())
        .limit(limit)
        .all()
    )


def _persist(
    db: Session,
    station: MonitoringStation,
    reading: SensorReading,
    use: str,
    assessment: Dict[str, Any],
) -> Optional[LiveWaterAssessment]:
    existing = (
        db.query(LiveWaterAssessment)
        .filter(
            LiveWaterAssessment.reading_id == reading.id,
            LiveWaterAssessment.use_code == use,
            LiveWaterAssessment.criteria_version == CRITERIA_VERSION,
        )
        .first()
    )
    if existing:
        return existing
    if not assessment.get("data_quality", {}).get("stability", {}).get("stable"):
        return None

    record = LiveWaterAssessment(
        station_id=station.id,
        reading_id=reading.id,
        device_id=reading.device_id,
        use_code=use,
        overall_status=assessment["overall"]["status"],
        criteria_version=CRITERIA_VERSION,
        assessment=assessment,
        reading_timestamp=reading.timestamp,
    )
    db.add(record)
    try:
        db.commit()
        db.refresh(record)
        return record
    except IntegrityError:
        # A concurrent poll already stored this exact assessment.
        db.rollback()
        return (
            db.query(LiveWaterAssessment)
            .filter(
                LiveWaterAssessment.reading_id == reading.id,
                LiveWaterAssessment.use_code == use,
                LiveWaterAssessment.criteria_version == CRITERIA_VERSION,
            )
            .first()
        )


def build_live_assessment(
    db: Session,
    station: MonitoringStation,
    use: str,
    *,
    aquaculture_context: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    readings = recent_readings(db, station.id)
    latest = readings[0] if readings else None
    stability = compute_stability(readings, now=now)

    values = {
        "ph": latest.ph if latest else None,
        "tds": latest.tds if latest else None,
        "turbidity": latest.turbidity if latest else None,
        "temperature": latest.temperature if latest else None,
    }
    assessment = assess(
        values,
        intended_use=use,
        reading_mode="live",
        reading_timestamp=latest.timestamp if latest else None,
        turbidity_unit=latest.turbidity_unit if latest else None,
        calibration=stability.get("calibration") or {},
        stability=stability,
        now=now,
        aquaculture_context=aquaculture_context,
    )

    persisted = _persist(db, station, latest, use, assessment) if latest else None

    return {
        "station_code": station.station_code,
        "station_name": station.station_name,
        "water_source_name": (
            station.water_source.name if station.water_source else "Unknown source"
        ),
        "device_id": latest.device_id if latest else None,
        "device_name": "HydraSense ESP32 monitoring station",
        "connection": stability.get("connection") or "no_data",
        "connection_label": CONNECTION_LABELS.get(
            stability.get("connection") or "no_data", "Unknown"
        ),
        "last_received": latest.timestamp if latest else None,
        "live": bool(stability.get("connection") == "connected"),
        "poll_interval_seconds": POLL_INTERVAL_SECONDS,
        "stability": stability,
        "latest": (
            {
                "reading_id": latest.id,
                "timestamp": latest.timestamp,
                "ph": latest.ph,
                "tds": latest.tds,
                "turbidity": latest.turbidity,
                "turbidity_unit": latest.turbidity_unit,
                "turbidity_index": latest.turbidity_index,
                "turbidity_status": latest.turbidity_status,
                "temperature": latest.temperature,
                "source": latest.source,
            }
            if latest else None
        ),
        "assessment": assessment,
        "test_id": f"LIVE-{persisted.id:06d}" if persisted else None,
        "assessment_id": persisted.id if persisted else None,
        "assessment_persisted": persisted is not None,
        "criteria_version": CRITERIA_VERSION,
    }
