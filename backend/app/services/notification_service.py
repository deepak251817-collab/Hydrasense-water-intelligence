"""User notifications with dedup, severity and a real delivery log.

Email is the only implemented channel (``app.core.config`` SMTP_* settings);
push/SMS would be additional channel adapters and are never pretended to work.

Design points that callers rely on:

- **Never fire on null/stale data.** The service consumes alert dictionaries
  produced by ``app.services.alerting`` — those already refuse to invent
  readings and label "sensor not reporting" staleness as a warning notice
  instead of a measurement alert. Here we only dispatch, re-validating shape.
- **Debounced.** Same ``(user, dedup_key)`` inside
  ``NOTIFICATION_COOLDOWN_SECONDS`` is recorded as ``deduped``; and each user
  receives at most ``NOTIFICATION_MAX_PER_WINDOW`` notifications per cooldown
  window (severity ``critical`` still counted, but never dropped by the cap).
- **Never raise into ingestion/alarming.** Delivery failures are captured in
  the row itself (``status='failed'``), never propagated.
- Credentials are never logged; payloads carry no tokens or secrets.
"""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.notification import Notification, NotificationPreference
from app.models.user import User

logger = logging.getLogger("hydrasense.notifications")

VALID_SEVERITIES = ("info", "warning", "critical")


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _email_enabled() -> bool:
    return bool(settings.SMTP_HOST)


def _send_email(user: User, *, title: str, body: str) -> Tuple[bool, str]:
    """Attempt delivery through SMTP. Returns (ok, detail_or_error_text)."""

    message = EmailMessage()
    message["Subject"] = title
    message["From"] = settings.SMTP_FROM
    message["To"] = user.email
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(message)
        return True, "sent"
    except Exception as exc:  # noqa: BLE001 - delivery must never raise
        # Log the type only — SMTP transcripts can contain credentials.
        logger.warning("Notification email delivery failed: %s", type(exc).__name__)
        return False, f"{type(exc).__name__}"


def category_enabled(db: Session, user_id: int, category: str) -> bool:
    pref = (
        db.query(NotificationPreference)
        .filter(
            NotificationPreference.user_id == user_id,
            NotificationPreference.category == category,
            NotificationPreference.channel == "email",
        )
        .first()
    )
    return bool(pref.enabled) if pref is not None else True


def notify(
    db: Session,
    user: User,
    *,
    category: str,
    severity: str = "warning",
    title: str,
    body: str,
    dedup_key: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Tuple[Optional[Notification], str]:
    """Compose and (attempt to) deliver one notification.

    Returns ``(notification, reason)`` where reason is one of
    ``sent`` / ``skipped_unconfigured`` / ``failed`` / ``suppressed_category`` /
    ``deduped`` / ``capped``. ``notification`` is ``None`` for suppressions.
    """

    now = _as_utc(now) if now else datetime.now(timezone.utc)
    if severity not in VALID_SEVERITIES:
        severity = "warning"

    if not category_enabled(db, user.id, category):
        return None, "suppressed_category"

    cooldown = timedelta(seconds=settings.NOTIFICATION_COOLDOWN_SECONDS)

    # Dedup: identical dedup_key for the user inside the cooldown window.
    if dedup_key:
        recent = (
            db.query(Notification)
            .filter(
                Notification.user_id == user.id,
                Notification.dedup_key == dedup_key,
            )
            .order_by(Notification.created_at.desc())
            .first()
        )
        if recent is not None and _as_utc(recent.created_at) + cooldown > now:
            return None, "deduped"

    # Per-user cap per window (critical always passes the cap).
    if severity != "critical":
        window_start = now - cooldown
        recent_count = (
            db.query(func.count(Notification.id))
            .filter(
                Notification.user_id == user.id,
                Notification.channel == "email",
                Notification.status.in_(("sent", "failed", "skipped_unconfigured")),
                Notification.created_at >= window_start,
            )
            .scalar()
            or 0
        )
        if recent_count >= settings.NOTIFICATION_MAX_PER_WINDOW:
            return None, "capped"

    row = Notification(
        user_id=user.id,
        channel="email",
        category=category,
        severity=severity,
        title=title,
        body=body,
        dedup_key=dedup_key,
        payload_json=str(payload) if payload else None,
        status="skipped_unconfigured",
        created_at=now,
    )

    if not _email_enabled():
        db.add(row)
        db.commit()
        db.refresh(row)
        return row, "skipped_unconfigured"

    ok, detail = _send_email(user, title=title, body=body)
    row.status = "sent" if ok else "failed"
    row.sent_at = now if ok else None
    if payload is not None:
        row.payload_json = str({**payload, "delivery_detail": detail})
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, row.status


def notify_alert(
    db: Session,
    user: User,
    alert: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
) -> Tuple[Optional[Notification], str]:
    """Dispatch one alert dictionary from ``app.services.alerting``.

    Dedup key combines user, parameter, severity and the alert's timestamp
    bucket (the alert text), so repeated requests against the same stored
    reading do not re-notify, while genuinely new readings do.
    """

    parameter = str(alert.get("parameter") or "unknown")
    severity = str(alert.get("severity") or "warning")
    value = alert.get("value")
    message = str(alert.get("message") or "")
    source = str(alert.get("source") or "unknown")
    at = alert.get("timestamp") or ""
    label = str(alert.get("label") or parameter)

    dedup_key = f"alert:{user.id}:{parameter}:{severity}:{at}:{value}"

    body_lines = [
        f"HydraSense {severity.upper()} alert for your device:",
        "",
        label,
        message,
        "",
        f"Reading source: {source}" + (" (simulated)" if alert.get("simulated") else ""),
    ]
    reference = alert.get("reference")
    if reference:
        body_lines += ["", f"Reference: {reference}"]
    next_step = alert.get("next_step")
    if next_step:
        body_lines += ["", f"Next step: {next_step}"]
    body_lines += [
        "",
        "This is an automated screening notice from measured sensor readings — "
        "not a laboratory safety certification.",
        "Manage notification preferences in your HydraSense dashboard.",
    ]

    payload = {
        "parameter": parameter,
        "value": value,
        "unit": alert.get("unit"),
        "source": source,
        "simulated": bool(alert.get("simulated")),
        "threshold_key": alert.get("threshold_key"),
        "threshold_profile_version": alert.get("threshold_profile_version"),
    }

    return notify(
        db,
        user,
        category=f"alert:{parameter}",
        severity=severity,
        title=str(alert.get("title") or f"HydraSense alert: {label}"),
        body="\n".join(body_lines),
        dedup_key=dedup_key,
        payload=payload,
        now=now,
    )


def list_for_user(db: Session, user_id: int, limit: int = 20) -> list[Notification]:
    return (
        db.query(Notification)
        .filter(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .all()
    )


def preferences_for_user(db: Session, user_id: int) -> list[NotificationPreference]:
    return (
        db.query(NotificationPreference)
        .filter(NotificationPreference.user_id == user_id)
        .order_by(NotificationPreference.category.asc())
        .all()
    )
