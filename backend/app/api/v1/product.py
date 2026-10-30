from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_product_user
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.models.device import ProductDevice
from app.models.user import User
from app.models.water_test import ProductWaterTest
from app.schemas.device import ProductDeviceResponse
from app.schemas.product_test import (
    ActivateProductRequest,
    ProductDeviceStatus,
    ProductDeviceSummary,
    ProductOverview,
    ProductWaterTestCreate,
    ProductWaterTestList,
    ProductWaterTestResponse,
)
from app.schemas.user import UserResponse
from app.services import product_test_service
from app.services.product_test_service import DEVICE_NAME

router = APIRouter(prefix="/product", tags=["Product User"])

# Device activation is a state change on a printed code: throttle it per client
# so activation codes cannot be enumerated at API speed.
activation_rate_limit = rate_limit(
    "product:activate",
    "RATE_LIMIT_ACTIVATE_MAX",
    "RATE_LIMIT_ACTIVATE_WINDOW_SECONDS",
)


@router.get("/me", response_model=UserResponse)
def get_my_profile(current_user: User = Depends(get_current_product_user)):
    return current_user


@router.get("/devices", response_model=List[ProductDeviceResponse])
def get_my_devices(
    current_user: User = Depends(get_current_product_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(ProductDevice)
        .filter(ProductDevice.owner_id == current_user.id)
        .order_by(ProductDevice.id.asc())
        .all()
    )


@router.post(
    "/activate",
    response_model=ProductDeviceSummary,
    dependencies=[Depends(activation_rate_limit)],
)
def activate_my_product(
    payload: ActivateProductRequest,
    current_user: User = Depends(get_current_product_user),
    db: Session = Depends(get_db),
):
    """Claim an unowned product code for the signed-in account."""

    device = product_test_service.activate_product(
        db, current_user.id, payload.product_code
    )
    return {
        "id": device.id,
        "product_code": device.product_code,
        "device_id": device.device_id,
        "device_number": device.device_number,
        "station_code": device.station_code,
        "device_type": device.device_type,
        "device_name": DEVICE_NAME,
        "status": device.status,
        "owner_id": device.owner_id,
        "activated_at": device.activated_at,
        "created_at": device.created_at,
    }


@router.get("/device-status", response_model=ProductDeviceStatus)
def get_my_device_status(
    current_user: User = Depends(get_current_product_user),
    db: Session = Depends(get_db),
):
    device = product_test_service.get_owned_device(db, current_user.id)
    return product_test_service.device_status(db, device)


@router.get("/overview", response_model=ProductOverview)
def get_my_overview(
    current_user: User = Depends(get_current_product_user),
    db: Session = Depends(get_db),
):
    """Dashboard summary: private totals, latest tests and live device state."""

    return product_test_service.overview(db, current_user)


@router.get("/tests", response_model=ProductWaterTestList)
def list_my_tests(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    date_from: Optional[date] = Query(None, description="Inclusive start date"),
    date_to: Optional[date] = Query(None, description="Inclusive end date"),
    current_user: User = Depends(get_current_product_user),
    db: Session = Depends(get_db),
):
    start = (
        datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        if date_from else None
    )
    end = (
        datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
        if date_to else None
    )
    total, tests = product_test_service.query_tests(
        db,
        current_user.id,
        limit=limit,
        offset=offset,
        date_from=start,
        date_to=end,
    )
    return {
        "total": total,
        "items": [product_test_service.serialize_summary(t) for t in tests],
    }


@router.get("/alerts")

def list_my_alerts(
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_product_user),
    db: Session = Depends(get_db),
):
    """Danger-level alerts for this account's water.

    Derived from (a) the latest live reading of the user's own device and
    (b) the user's most recent saved tests. Nothing is invented: every entry
    carries the measured value, its configured reference and the source
    (live hardware vs. labelled simulation).
    """

    from app.services.alerting import alert_response, reading_alerts, test_alerts

    items: list = []

    device = (
        db.query(ProductDevice)
        .filter(ProductDevice.owner_id == current_user.id)
        .order_by(ProductDevice.activated_at.desc(), ProductDevice.id.asc())
        .first()
    )
    if device is not None:
        reading = product_test_service.latest_reading(db, device.device_id)
        if reading is not None:
            items.extend(reading_alerts(reading))

    tests = (
        db.query(ProductWaterTest)
        .filter(ProductWaterTest.user_id == current_user.id)
        .order_by(ProductWaterTest.created_at.desc())
        .limit(10)
        .all()
    )
    for test in tests:
        items.extend(test_alerts(test))

    # Dispatch: whatever alerts were derived from real stored data become
    # (debounced) notifications for this account. The service never fires on
    # suppressed categories / cooldowns and never crashes the endpoint.
    from app.services import notification_service

    dispatch_results = []
    for alert in items:
        try:
            _, reason = notification_service.notify_alert(db, current_user, alert)
            dispatch_results.append(reason)
        except Exception:  # pragma: no cover - delivery must never 500
            dispatch_results.append("error")

    # Most recent first, capped by the requested limit; the response also
    # carries the active threshold profile (official vs project-configured).
    response = alert_response(items, limit)
    response["notification_dispatch"] = {
        "attempted": len(items),
        "by_reason": {r: dispatch_results.count(r) for r in set(dispatch_results)},
        "channel": "email",
    }
    return response


@router.get("/alerts/profile")
def get_alert_threshold_profile(
    current_user: User = Depends(get_current_product_user),
):
    """The active, versioned alert threshold profile.

    Clearly separates thresholds verified against official standards from
    project-configured screening values, with unit, source and rationale for
    each — so the UI can display what is configured without implying that a
    project setting is a regulatory limit.
    """
    from app.services.alert_thresholds import profile_payload

    return profile_payload()


@router.get("/notifications")
def get_my_notifications(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_product_user),
    db: Session = Depends(get_db),
):
    """This account's notification history (the delivery log)."""

    from app.services import notification_service

    rows = notification_service.list_for_user(db, current_user.id, limit=limit)
    return {
        "total": len(rows),
        "channel": "email",
        "items": [
            {
                "id": row.id,
                "category": row.category,
                "severity": row.severity,
                "title": row.title,
                "body": row.body,
                "status": row.status,
                "dedup_key": row.dedup_key,
                "created_at": row.created_at,
                "sent_at": row.sent_at,
            }
            for row in rows
        ],
    }


@router.get("/notification-preferences")
def get_my_notification_preferences(
    current_user: User = Depends(get_current_product_user),
    db: Session = Depends(get_db),
):
    """Per-category email opt-out rows (missing category = enabled)."""

    from app.services import notification_service

    rows = notification_service.preferences_for_user(db, current_user.id)
    return {
        "channel": "email",
        "items": [
            {
                "category": row.category,
                "channel": row.channel,
                "enabled": row.enabled,
            }
            for row in rows
        ],
    }


@router.put("/notification-preferences/{category}")
def set_my_notification_preference(
    category: str,
    enabled: bool = Query(...),
    current_user: User = Depends(get_current_product_user),
    db: Session = Depends(get_db),
):
    """Enable/disable email notifications for one alert category."""

    from app.models.notification import NotificationPreference

    pref = (
        db.query(NotificationPreference)
        .filter(
            NotificationPreference.user_id == current_user.id,
            NotificationPreference.category == category,
            NotificationPreference.channel == "email",
        )
        .first()
    )
    if pref is None:
        pref = NotificationPreference(
            user_id=current_user.id, category=category, channel="email", enabled=enabled
        )
        db.add(pref)
    else:
        pref.enabled = enabled
    db.commit()
    db.refresh(pref)
    return {
        "category": pref.category,
        "channel": pref.channel,
        "enabled": pref.enabled,
    }


@router.post(
    "/tests",
    response_model=ProductWaterTestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_my_test(
    payload: ProductWaterTestCreate,
    current_user: User = Depends(get_current_product_user),
    db: Session = Depends(get_db),
):
    """Run a screening on a live reading from the user's device (or labelled demo)."""

    test = product_test_service.create_test(db, current_user.id, payload)
    return product_test_service.serialize_test(db, test)


@router.get("/tests/{test_id}", response_model=ProductWaterTestResponse)
def get_my_test(
    test_id: int,
    current_user: User = Depends(get_current_product_user),
    db: Session = Depends(get_db),
):
    test = product_test_service.get_user_test(db, current_user.id, test_id)
    return product_test_service.serialize_test(db, test)
