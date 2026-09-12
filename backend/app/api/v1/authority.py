from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from app.api.deps import get_current_authority
from app.core.database import get_db
from app.models.user import User
from app.models.water import MonitoringStation, SensorReading
from app.schemas.ml_analysis import MLAnalysisResponse, ReadingAnalysisResponse
from app.schemas.user import UserResponse
from app.schemas.water import (
    MonitoringStationAuthorityResponse,
    LatestSensorReadingResponse,
    SensorReadingResponse,
)

router = APIRouter(prefix="/authority", tags=["Authority"])


@router.get("/me", response_model=UserResponse)
def get_authority_profile(
    current_user: User = Depends(get_current_authority)
):
    return current_user


@router.get("/stations", response_model=List[MonitoringStationAuthorityResponse])
def get_all_monitoring_stations(
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db)
):
    stations = (
        db.query(MonitoringStation)
        .options(joinedload(MonitoringStation.water_source))
        .all()
    )
    return stations


@router.get("/stations/{station_code}/readings/latest/analysis", response_model=ReadingAnalysisResponse)
def get_latest_station_reading_analysis(
    station_code: str,
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    """Latest reading for a station plus its ML analysis (authority-only)."""
    station = db.query(MonitoringStation).filter(MonitoringStation.station_code == station_code).first()
    if not station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitoring station with code '{station_code}' not found."
        )

    reading = (
        db.query(SensorReading)
        .filter(SensorReading.station_id == station.id)
        .order_by(SensorReading.timestamp.desc(), SensorReading.id.desc())
        .first()
    )
    if not reading:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No sensor readings found for station '{station_code}'."
        )

    return ReadingAnalysisResponse(
        reading_id=reading.id,
        station_id=reading.station_id,
        station_code=station.station_code,
        device_id=reading.device_id,
        timestamp=reading.timestamp,
        created_at=reading.created_at,
        ph=reading.ph,
        turbidity=reading.turbidity,
        tds=reading.tds,
        temperature=reading.temperature,
        ml=MLAnalysisResponse(
            anomaly_label=reading.anomaly_label,
            anomaly_score=reading.anomaly_score,
            water_quality_label=reading.water_quality_label,
            safe_probability=reading.safe_probability,
            unsafe_probability=reading.unsafe_probability,
            ml_processed_at=reading.ml_processed_at,
        ),
    )


@router.get("/stations/{station_code}/readings/latest", response_model=LatestSensorReadingResponse)
def get_latest_station_reading(
    station_code: str,
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db)
):
    station = db.query(MonitoringStation).filter(MonitoringStation.station_code == station_code).first()
    if not station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitoring station with code '{station_code}' not found."
        )

    reading = (
        db.query(SensorReading)
        .filter(SensorReading.station_id == station.id)
        .order_by(SensorReading.timestamp.desc(), SensorReading.id.desc())
        .first()
    )

    if not reading:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No sensor readings found for station '{station_code}'."
        )

    return LatestSensorReadingResponse(
        station_code=station.station_code,
        device_id=reading.device_id,
        timestamp=reading.timestamp,
        pH=reading.ph,
        turbidity=reading.turbidity,
        tds=reading.tds,
        temperature=reading.temperature,
    )


@router.get("/stations/{station_code}/readings", response_model=List[SensorReadingResponse])
def get_station_readings_history(
    station_code: str,
    limit: int = 100,
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db)
):
    station = db.query(MonitoringStation).filter(MonitoringStation.station_code == station_code).first()
    if not station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitoring station with code '{station_code}' not found."
        )

    readings = (
        db.query(SensorReading)
        .filter(SensorReading.station_id == station.id)
        .order_by(SensorReading.timestamp.desc(), SensorReading.id.desc())
        .limit(limit)
        .all()
    )

    result = []
    for r in readings:
        result.append(
            SensorReadingResponse(
                id=r.id,
                station_id=r.station_id,
                station_code=station.station_code,
                device_id=r.device_id,
                timestamp=r.timestamp,
                pH=r.ph,
                turbidity=r.turbidity,
                tds=r.tds,
                temperature=r.temperature,
                created_at=r.created_at,
            )
        )
    return result


@router.get("/readings/{reading_id}/analysis", response_model=ReadingAnalysisResponse)
def get_reading_ml_analysis(
    reading_id: int,
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    """Return a sensor reading plus its ML analysis (authority-only).

    ML fields are null when the reading has not been processed or inference
    did not run (e.g. ML service unavailable at ingestion time). Internal
    model file paths and model internals are never exposed.
    """
    reading = (
        db.query(SensorReading)
        .options(joinedload(SensorReading.station))
        .filter(SensorReading.id == reading_id)
        .first()
    )
    if not reading:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sensor reading with id '{reading_id}' not found."
        )

    return ReadingAnalysisResponse(
        reading_id=reading.id,
        station_id=reading.station_id,
        station_code=reading.station.station_code,
        device_id=reading.device_id,
        timestamp=reading.timestamp,
        created_at=reading.created_at,
        ph=reading.ph,
        turbidity=reading.turbidity,
        tds=reading.tds,
        temperature=reading.temperature,
        ml=MLAnalysisResponse(
            anomaly_label=reading.anomaly_label,
            anomaly_score=reading.anomaly_score,
            water_quality_label=reading.water_quality_label,
            safe_probability=reading.safe_probability,
            unsafe_probability=reading.unsafe_probability,
            ml_processed_at=reading.ml_processed_at,
        ),
    )

