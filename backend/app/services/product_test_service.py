"""Product-user water-test orchestration.

Resolves the authenticated user's own device, obtains a live reading from that
device (or an explicitly requested, clearly labelled simulation), validates it,
runs the rule-based screening service, and persists the private test.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.device import ProductDevice
from app.models.water import SensorReading
from app.models.water_test import ProductWaterTest
from app.schemas.product_test import ProductWaterTestCreate
from app.services.sensor_stability import compute_stability
from app.services.water_screening import (
    CRITERIA_VERSION,
    FRESH_WITHIN_SECONDS,
    SOURCE_LABELS,
    USE_LABELS,
    assess,
    validate_readings,
)

DEVICE_NAME = "HydraSense Personal Tester"

# Deterministic demo profiles, cycled by the user's demo-test count so the demo
# can show different screening outcomes. Every demo value is labelled
# ``reading_source = "simulated"`` in the API and UI.
_DEMO_PROFILES: Tuple[Dict[str, Any], ...] = (
    {
        "ph": 7.2,
        "tds": 320.0,
        "turbidity": 18.0,
        "temperature": 24.5,
        "turbidity_status": "CLEARER",
    },
    {
        "ph": 8.9,
        "tds": 780.0,
        "turbidity": 46.0,
        "temperature": 27.0,
        "turbidity_status": "MODERATE",
    },
    {
        "ph": 6.2,
        "tds": 2350.0,
        "turbidity": 62.0,
        "temperature": 31.0,
        "turbidity_status": "CLOUDIER",
    },
)


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _sensor_calibration(reading: Optional[SensorReading]) -> Dict[str, str]:
    """Read per-sensor calibration status from device diagnostics (if any)."""

    if reading is None:
        return {}
    diagnostics = reading.diagnostics if isinstance(reading.diagnostics, dict) else {}
    result: Dict[str, str] = {}
    for sensor in ("ph", "tds", "turbidity", "temperature"):
        entry = diagnostics.get(sensor)
        if isinstance(entry, dict) and entry.get("calibration_status"):
            result[sensor] = str(entry["calibration_status"])
    return result


def get_owned_device(
    db: Session,
    user_id: int,
    device_id: Optional[str] = None,
) -> ProductDevice:
    query = db.query(ProductDevice).filter(ProductDevice.owner_id == user_id)
    if device_id:
        query = query.filter(ProductDevice.device_id == device_id)
    else:
        query = query.order_by(ProductDevice.activated_at.desc(), ProductDevice.id.asc())
    device = query.first()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "no_device",
                "message": (
                    "No HydraSense product is linked to this account. Activate a "
                    "product code before starting a water test."
                ),
            },
        )
    if device.status not in ("ACTIVE",):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "device_inactive",
                "message": f"Device {device.device_id} is not active.",
            },
        )
    return device


def latest_reading(db: Session, device_id: str) -> Optional[SensorReading]:
    return (
        db.query(SensorReading)
        .filter(SensorReading.device_id == device_id)
        .order_by(SensorReading.timestamp.desc(), SensorReading.id.desc())
        .first()
    )


def _reading_payload(reading: SensorReading) -> Dict[str, Any]:
    return {
        "ph": reading.ph,
        "tds": reading.tds,
        "turbidity": reading.turbidity,
        "temperature": reading.temperature,
    }


def _age_seconds(timestamp: Optional[datetime], now: datetime) -> Optional[float]:
    stamp = _as_utc(timestamp)
    if stamp is None:
        return None
    return max((now - stamp).total_seconds(), 0.0)


def device_status(db: Session, device: ProductDevice, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    reading = latest_reading(db, device.device_id)
    age = _age_seconds(reading.timestamp, now) if reading else None
    connected = bool(reading and age is not None and age <= FRESH_WITHIN_SECONDS)

    if reading is None:
        note = "No live reading received from this device yet."
    elif connected:
        note = f"Connected - last reading {int(age or 0)} s ago."
    else:
        minutes = int((age or 0) // 60)
        note = (
            f"Device not sending current data - last reading {minutes} min ago. "
            "Live testing is unavailable until a new reading arrives."
        )

    return {
        "device_id": device.device_id,
        "device_name": DEVICE_NAME,
        "product_code": device.product_code,
        "status": device.status,
        "connected": connected,
        "last_seen": reading.timestamp if reading else None,
        "reading_age_seconds": age,
        "reading": (
            {
                "ph": reading.ph,
                "tds": reading.tds,
                "turbidity": reading.turbidity,
                "turbidity_unit": reading.turbidity_unit,
                "turbidity_index": reading.turbidity_index,
                "turbidity_status": reading.turbidity_status,
                "temperature": reading.temperature,
                "timestamp": reading.timestamp,
                "source": reading.source,
                "calibration": _sensor_calibration(reading),
            }
            if reading else None
        ),
        "note": note,
    }


def _demo_reading(db: Session, user_id: int) -> Dict[str, Any]:
    count = (
        db.query(func.count(ProductWaterTest.id))
        .filter(
            ProductWaterTest.user_id == user_id,
            ProductWaterTest.reading_mode == "demo",
        )
        .scalar()
        or 0
    )
    profile = _DEMO_PROFILES[int(count) % len(_DEMO_PROFILES)]
    return {
        "ph": profile["ph"],
        "tds": profile["tds"],
        "turbidity": profile["turbidity"],
        "temperature": profile["temperature"],
        "turbidity_unit": "relative_index_0_100",
        "turbidity_status": profile["turbidity_status"],
        "reading_source": "simulated",
        "sensor_reading_id": None,
        "reading_timestamp": datetime.now(timezone.utc),
        "calibration": {key: "simulated" for key in ("ph", "tds", "turbidity", "temperature")},
    }


def _live_reading(db: Session, device: ProductDevice) -> Dict[str, Any]:
    readings = (
        db.query(SensorReading)
        .filter(SensorReading.device_id == device.device_id)
        .order_by(SensorReading.timestamp.desc(), SensorReading.id.desc())
        .limit(40)
        .all()
    )
    reading = readings[0] if readings else None
    if reading is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "device_offline",
                "message": (
                    f"Device {device.device_id} has not sent any readings yet. "
                    "Connect the ESP32, or use clearly labelled demo readings."
                ),
            },
        )

    age = _age_seconds(reading.timestamp, datetime.now(timezone.utc))
    if age is None or age > FRESH_WITHIN_SECONDS:
        minutes = int((age or 0) // 60)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "stale_reading",
                "message": (
                    f"The latest reading from {device.device_id} is {minutes} min old; "
                    f"a live test needs a reading from the last "
                    f"{FRESH_WITHIN_SECONDS // 60} min. Retry once the device is "
                    "sending data, or use clearly labelled demo readings."
                ),
            },
        )

    # Report unusable sensor data as such before asking the user to wait for
    # stability: a missing/invalid value will never stabilise.
    validation = validate_readings(
        _reading_payload(reading),
        turbidity_unit=reading.turbidity_unit,
    )
    if validation["errors"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_reading",
                "message": "The latest sensor reading contains no valid value for a required parameter.",
                "errors": validation["errors"],
            },
        )

    stability = compute_stability(readings)
    if not stability["stable"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "unstable_reading",
                "message": (
                    f"Sensor readings from {device.device_id} are not stable yet. "
                    f"{stability['message']} Keep the probe submerged and retry, "
                    "or use clearly labelled demo readings."
                ),
                "stability": stability,
            },
        )

    return {
        "ph": reading.ph,
        "tds": reading.tds,
        "turbidity": reading.turbidity,
        "temperature": reading.temperature,
        "turbidity_unit": reading.turbidity_unit,
        "turbidity_status": reading.turbidity_status,
        "reading_source": reading.source or "unknown",
        "sensor_reading_id": reading.id,
        "reading_timestamp": reading.timestamp,
        "calibration": stability.get("calibration") or _sensor_calibration(reading),
        "stability": stability,
    }


def create_test(
    db: Session,
    user_id: int,
    payload: ProductWaterTestCreate,
) -> ProductWaterTest:
    device = get_owned_device(db, user_id)

    if payload.reading_mode == "demo":
        reading = _demo_reading(db, user_id)
    else:
        reading = _live_reading(db, device)

    values = {
        "ph": reading["ph"],
        "tds": reading["tds"],
        "turbidity": reading["turbidity"],
        "temperature": reading["temperature"],
    }
    validation = validate_readings(
        values,
        turbidity_unit=reading["turbidity_unit"],
        max_age_seconds=(
            _age_seconds(reading["reading_timestamp"], datetime.now(timezone.utc))
            if payload.reading_mode == "live" else None
        ),
    )
    if validation["errors"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_reading",
                "message": "The sensor reading is not valid enough for an assessment.",
                "errors": validation["errors"],
            },
        )

    result = assess(
        values,
        intended_use=payload.intended_use,
        reading_mode=payload.reading_mode,
        reading_timestamp=reading["reading_timestamp"],
        turbidity_unit=reading["turbidity_unit"],
        calibration=reading["calibration"],
        stability=reading.get("stability"),
        aquaculture_context=payload.aquaculture_context,
    )

    test = ProductWaterTest(
        user_id=user_id,
        device_id=device.device_id,
        sensor_reading_id=reading["sensor_reading_id"],
        water_source=payload.water_source,
        intended_use=payload.intended_use,
        reading_mode=payload.reading_mode,
        reading_source=(
            "simulated" if payload.reading_mode == "demo" else reading["reading_source"]
        ),
        ph=reading["ph"],
        tds=reading["tds"],
        turbidity=reading["turbidity"],
        turbidity_unit=reading["turbidity_unit"],
        temperature=reading["temperature"],
        reading_timestamp=_as_utc(reading["reading_timestamp"]),
        overall_status=result["overall"]["status"],
        criteria_version=CRITERIA_VERSION,
        assessment=result,
        summary_text=result["overall"]["summary"],
    )
    db.add(test)
    db.commit()
    db.refresh(test)
    return test


def _test_code(test_id: int) -> str:
    return f"WT-{test_id:06d}"


def serialize_test(db: Session, test: ProductWaterTest) -> Dict[str, Any]:
    assessment = test.assessment or {}
    overall = assessment.get("overall", {})
    return {
        "id": test.id,
        "test_code": _test_code(test.id),
        "water_source": test.water_source,
        "water_source_label": SOURCE_LABELS.get(test.water_source, test.water_source),
        "intended_use": test.intended_use,
        "intended_use_label": USE_LABELS.get(test.intended_use, test.intended_use),
        "reading_mode": test.reading_mode,
        "reading_source": test.reading_source,
        "device_id": test.device_id,
        "device_name": DEVICE_NAME,
        "ph": test.ph,
        "tds": test.tds,
        "turbidity": test.turbidity,
        "turbidity_unit": test.turbidity_unit,
        "temperature": test.temperature,
        "reading_timestamp": test.reading_timestamp,
        "created_at": test.created_at,
        "overall_status": test.overall_status,
        "overall_label": overall.get("label", test.overall_status),
        "criteria_version": test.criteria_version,
        "assessment": assessment,
    }


def serialize_summary(test: ProductWaterTest) -> Dict[str, Any]:
    overall = (test.assessment or {}).get("overall", {})
    return {
        "id": test.id,
        "test_code": _test_code(test.id),
        "water_source": test.water_source,
        "water_source_label": SOURCE_LABELS.get(test.water_source, test.water_source),
        "intended_use": test.intended_use,
        "intended_use_label": USE_LABELS.get(test.intended_use, test.intended_use),
        "reading_mode": test.reading_mode,
        "overall_status": test.overall_status,
        "overall_label": overall.get("label", test.overall_status),
        "ph": test.ph,
        "tds": test.tds,
        "turbidity": test.turbidity,
        "turbidity_unit": test.turbidity_unit,
        "temperature": test.temperature,
        "reading_timestamp": test.reading_timestamp,
        "created_at": test.created_at,
    }


def query_tests(
    db: Session,
    user_id: int,
    *,
    limit: int = 25,
    offset: int = 0,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> Tuple[int, List[ProductWaterTest]]:
    query = db.query(ProductWaterTest).filter(ProductWaterTest.user_id == user_id)
    if date_from is not None:
        query = query.filter(ProductWaterTest.created_at >= date_from)
    if date_to is not None:
        query = query.filter(ProductWaterTest.created_at <= date_to)
    total = query.count()
    items = (
        query.order_by(ProductWaterTest.created_at.desc(), ProductWaterTest.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return total, items


def get_user_test(db: Session, user_id: int, test_id: int) -> ProductWaterTest:
    test = (
        db.query(ProductWaterTest)
        .filter(
            ProductWaterTest.id == test_id,
            ProductWaterTest.user_id == user_id,
        )
        .first()
    )
    if not test:
        # Do not reveal whether another user's test exists.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "test_not_found", "message": "Water test not found."},
        )
    return test


def activate_product(db: Session, user_id: int, product_code: str) -> ProductDevice:
    """Bind a product code to the authenticated user atomically.

    ``SELECT ... FOR UPDATE`` (where the database supports it) serialises two
    concurrent claims of the same code. PostgreSQL is the production database;
    SQLite ignores the row lock, which is acceptable for local tests.
    """

    code = product_code.strip().upper()
    query = db.query(ProductDevice).filter(func.upper(ProductDevice.product_code) == code)
    try:
        device = query.with_for_update().first()
    except Exception:  # pragma: no cover - dialect without row locking
        device = query.first()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_product_code",
                "message": "Invalid product code: no HydraSense product has this code.",
            },
        )

    if device.owner_id is not None:
        if device.owner_id == user_id:
            return device
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "product_already_claimed",
                "message": "This product code is already linked to another account.",
            },
        )

    device.owner_id = user_id
    device.status = "ACTIVE"
    device.activated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(device)
    return device


def overview(db: Session, user: Any) -> Dict[str, Any]:
    device_row = (
        db.query(ProductDevice)
        .filter(ProductDevice.owner_id == user.id)
        .order_by(ProductDevice.activated_at.desc(), ProductDevice.id.asc())
        .first()
    )
    total = (
        db.query(func.count(ProductWaterTest.id))
        .filter(ProductWaterTest.user_id == user.id)
        .scalar()
        or 0
    )
    recent = (
        db.query(ProductWaterTest)
        .filter(ProductWaterTest.user_id == user.id)
        .order_by(ProductWaterTest.created_at.desc(), ProductWaterTest.id.desc())
        .limit(5)
        .all()
    )
    return {
        "total_tests": int(total),
        "latest_test": serialize_summary(recent[0]) if recent else None,
        "recent_tests": [serialize_summary(item) for item in recent],
        "device": device_status(db, device_row) if device_row else None,
    }
