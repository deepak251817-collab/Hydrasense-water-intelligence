from datetime import datetime, timezone
from typing import List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from app.api.deps import get_current_authority
from app.core.database import get_db
from app.models.user import User
from app.models.water import MonitoringStation, SensorReading
from app.schemas.forecast import ForecastResponse
from app.schemas.ml_analysis import MLAnalysisResponse, ReadingAnalysisResponse
from app.schemas.ml_status import MLStatusResponse
from app.schemas.product_test import LiveAssessmentResponse
from app.schemas.suitability import StationSuitabilityResponse
from app.schemas.user import UserResponse
from app.services.forecasting import build_forecast
from app.services.live_assessment_service import build_live_assessment
from app.services.ml_availability import availability_for
from app.services.ml_service import ml_service
from app.services.ml_status_service import build_ml_status
from app.services.water_suitability import (
    RULESET_VERSION,
    assess_reading,
    persist_assessments,
)
from app.schemas.water import (
    MonitoringStationAuthorityResponse,
    LatestSensorReadingResponse,
    SensorReadingResponse,
)

router = APIRouter(prefix="/authority", tags=["Authority"])


def _ml_analysis_or_empty(reading: SensorReading, status: str) -> MLAnalysisResponse:
    """Stored ML results, or an all-null payload when they must not be shown.

    A legacy row can carry a stale label (e.g. written before index readings
    were excluded from the NTU models). Surfacing that label next to an
    "unavailable" status would contradict the honesty guarantee, so the ML
    fields are nulled whenever availability is not OK.
    """
    if status != "ok":
        return MLAnalysisResponse()
    return MLAnalysisResponse(
        anomaly_label=reading.anomaly_label,
        anomaly_score=reading.anomaly_score,
        water_quality_label=reading.water_quality_label,
        safe_probability=reading.safe_probability,
        unsafe_probability=reading.unsafe_probability,
        ml_processed_at=reading.ml_processed_at,
    )


def _reading_analysis(reading: SensorReading, station_code: str) -> ReadingAnalysisResponse:
    """Reading + honest ML availability for the analysis endpoints.

    `ml_status`/`ml_unavailable_*` explain WHY an ML result is absent (for
    example "ML prediction unavailable for Turbidity Index readings."), so the
    UI never has to guess and never fabricates a default verdict.
    """
    availability = availability_for(reading)
    return ReadingAnalysisResponse(
        reading_id=reading.id,
        station_id=reading.station_id,
        station_code=station_code,
        device_id=reading.device_id,
        timestamp=reading.timestamp,
        created_at=reading.created_at,
        ph=reading.ph,
        turbidity=reading.turbidity,
        turbidity_unit=reading.turbidity_unit,
        turbidity_index=reading.turbidity_index,
        turbidity_status=reading.turbidity_status,
        tds=reading.tds,
        temperature=reading.temperature,
        source=reading.source,
        diagnostics=reading.diagnostics,
        ml_status=availability["status"],
        ml_unavailable_reason=availability["reason"],
        ml_unavailable_message=availability["message"],
        ml=_ml_analysis_or_empty(reading, availability["status"]),
    )


@router.get("/me", response_model=UserResponse)
def get_authority_profile(
    current_user: User = Depends(get_current_authority)
):
    return current_user


@router.get("/ml/status", response_model=MLStatusResponse)
def get_ml_status(
    current_user: User = Depends(get_current_authority),
):
    """Model health + evaluation metrics (authority-only, read-only).

    `evaluation` is the report produced by
    `python ml/scripts/build_evaluation_report.py`. If it has not been
    generated, `evaluation_available` is false and `evaluation` is null — the
    API never fabricates model performance numbers.
    """
    return build_ml_status(
        ml_service=ml_service,
        report_path=None,
    )


@router.get("/stations/{station_code}/suitability", response_model=StationSuitabilityResponse)
def get_station_suitability(
    station_code: str,
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    """Standards-based suitability screening for the latest station reading.

    Compares only calibrated, physical, fresh measurements with the documented
    BIS IS 10500 / CPCB limits; everything else is reported as missing. Each
    result is persisted once per (reading, use, ruleset version) so the
    assessment history is auditable without touching the original reading.
    """
    station = (
        db.query(MonitoringStation)
        .filter(MonitoringStation.station_code == station_code)
        .first()
    )
    if not station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitoring station with code '{station_code}' not found.",
        )

    reading = (
        db.query(SensorReading)
        .filter(SensorReading.station_id == station.id)
        .order_by(SensorReading.timestamp.desc(), SensorReading.id.desc())
        .first()
    )

    assessments = assess_reading(
        reading, now=datetime.now(timezone.utc)
    )
    if reading is not None:
        persist_assessments(db, station.id, assessments)

    return StationSuitabilityResponse(
        station_code=station.station_code,
        station_name=station.station_name,
        generated_at=datetime.now(timezone.utc),
        ruleset_version=RULESET_VERSION,
        assessments=assessments,
    )


@router.get("/stations/{station_code}/live-assessment", response_model=LiveAssessmentResponse)
def get_live_water_assessment(
    station_code: str,
    use: Literal[
        "drinking", "domestic", "irrigation", "general", "swimming", "aquaculture"
    ] = Query(
        "drinking", description="Intended use for this assessment"
    ),
    aquaculture_context: Optional[str] = Query(
        None, max_length=200, description="Species/farming context for aquaculture"
    ),
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    """Stable-reading assessment for Live Monitoring (authority-only).

    Uses the same shared screening service as Product User tests. Stability is
    computed from the rolling window of real stored readings; stable readings
    are never treated as calibrated. A stable, persisted assessment receives a
    ``LIVE-######`` test ID.
    """
    station = (
        db.query(MonitoringStation)
        .filter(MonitoringStation.station_code == station_code)
        .first()
    )
    if not station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitoring station with code '{station_code}' not found.",
        )
    return build_live_assessment(
        db, station, use, aquaculture_context=aquaculture_context
    )


@router.get("/stations", response_model=List[MonitoringStationAuthorityResponse])
def get_all_monitoring_stations(
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db)
):
    stations = (
        db.query(MonitoringStation)
        .options(joinedload(MonitoringStation.water_source))
        # Deterministic order so the dashboard's initial station selection is
        # stable across requests and restarts.
        .order_by(MonitoringStation.station_code)
        .all()
    )
    return stations


@router.get("/stations/{station_code}/forecast", response_model=ForecastResponse)
def get_station_forecast(
    station_code: str,
    horizon_hours: int = Query(24, ge=1, le=168),
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    """Honest baseline forecast for one station (authority-only).

    Returns forecast points only for parameters whose model beat a naive
    persistence baseline on a chronological holdout. When history is
    insufficient or evaluation does not support the models, the response
    reports ``status = unavailable`` with an explicit reason instead of
    numbers.
    """
    station = (
        db.query(MonitoringStation)
        .filter(MonitoringStation.station_code == station_code)
        .first()
    )
    if not station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitoring station with code '{station_code}' not found.",
        )
    return build_forecast(db, station, horizon_hours=horizon_hours)


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

    return _reading_analysis(reading, station.station_code)


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
        turbidity_unit=reading.turbidity_unit,
        turbidity_status=reading.turbidity_status,
        tds=reading.tds,
        temperature=reading.temperature,
        source=reading.source,
        diagnostics=reading.diagnostics,
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
            turbidity_unit=r.turbidity_unit,
            turbidity_status=r.turbidity_status,
            tds=r.tds,
            temperature=r.temperature,
            source=r.source,
            diagnostics=r.diagnostics,
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

    return _reading_analysis(reading, reading.station.station_code)

