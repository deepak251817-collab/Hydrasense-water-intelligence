from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models.water import MonitoringStation, SensorReading
from app.schemas.suitability import (
    PublicLatestReading,
    PublicReadingHistoryRow,
    StationSuitabilityResponse,
)
from app.schemas.water import MonitoringStationPublicResponse
from app.services.water_suitability import (
    RULESET_VERSION,
    assess_reading,
    persist_assessments,
)

router = APIRouter(prefix="/public", tags=["Public"])


def _get_station_or_404(station_code: str, db: Session) -> MonitoringStation:
    station = (
        db.query(MonitoringStation)
        .options(joinedload(MonitoringStation.water_source))
        .filter(MonitoringStation.station_code == station_code)
        .first()
    )
    if not station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitoring station with code '{station_code}' not found",
        )
    return station


def _latest_reading(db: Session, station: MonitoringStation) -> Optional[SensorReading]:
    return (
        db.query(SensorReading)
        .filter(SensorReading.station_id == station.id)
        .order_by(SensorReading.timestamp.desc(), SensorReading.id.desc())
        .first()
    )


@router.get("/stations/{station_code}", response_model=MonitoringStationPublicResponse)
def get_public_station(station_code: str, db: Session = Depends(get_db)):
    return _get_station_or_404(station_code, db)


@router.get("/stations/{station_code}/readings/latest", response_model=PublicLatestReading)
def get_public_latest_reading(station_code: str, db: Session = Depends(get_db)):
    """Latest reading for the public QR page (no diagnostics or credentials)."""
    station = _get_station_or_404(station_code, db)
    reading = _latest_reading(db, station)
    if not reading:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No sensor readings found for station '{station_code}'.",
        )
    return PublicLatestReading(
        station_code=station.station_code,
        timestamp=reading.timestamp,
        pH=reading.ph,
        turbidity=reading.turbidity,
        turbidity_unit=reading.turbidity_unit,
        turbidity_status=reading.turbidity_status,
        tds=reading.tds,
        temperature=reading.temperature,
        source=reading.source,
    )


@router.get("/stations/{station_code}/readings", response_model=List[PublicReadingHistoryRow])
def get_public_reading_history(
    station_code: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Recent readings for the public trend chart (newest first, public-safe)."""
    station = _get_station_or_404(station_code, db)
    readings = (
        db.query(SensorReading)
        .filter(SensorReading.station_id == station.id)
        .order_by(SensorReading.timestamp.desc(), SensorReading.id.desc())
        .limit(limit)
        .all()
    )
    return [
        PublicReadingHistoryRow(
            id=reading.id,
            station_code=station.station_code,
            timestamp=reading.timestamp,
            pH=reading.ph,
            turbidity=reading.turbidity,
            turbidity_unit=reading.turbidity_unit,
            turbidity_status=reading.turbidity_status,
            tds=reading.tds,
            temperature=reading.temperature,
            source=reading.source,
        )
        for reading in readings
    ]


@router.get("/stations/{station_code}/suitability", response_model=StationSuitabilityResponse)
def get_public_suitability(station_code: str, db: Session = Depends(get_db)):
    """Public suitability assessment for the latest reading of a station.

    Public-safe by construction: it exposes per-parameter outcomes, missing
    tests, freshness and provenance — never diagnostics, device credentials or
    private records.
    """
    station = _get_station_or_404(station_code, db)
    reading = _latest_reading(db, station)

    assessments = assess_reading(reading, now=datetime.now(timezone.utc))
    if reading is not None:
        persist_assessments(db, station.id, assessments)

    return StationSuitabilityResponse(
        station_code=station.station_code,
        station_name=station.station_name,
        generated_at=datetime.now(timezone.utc),
        ruleset_version=RULESET_VERSION,
        assessments=assessments,
    )
