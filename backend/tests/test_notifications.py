"""Notification service tests.

Covers: cooldown dedup, per-user cap, deferred preference opt-out, SMTP
unconfigured/configured/failure outcomes, and the /product API endpoints.
The service is also contractually never raised by delivery failures.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.security import get_password_hash
from app.models.user import User, UserRole
from app.services import notification_service


def _user(db, email="notify@example.com") -> User:
    user = User(
        email=email,
        password_hash=get_password_hash("TestPassword123!"),
        full_name="Notify",
        role=UserRole.PRODUCT_USER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _alert(parameter="ph", severity="critical", value=3.1, **extra):
    base = {
        "parameter": parameter,
        "label": "pH",
        "value": value,
        "unit": "pH",
        "severity": severity,
        "title": "Danger level: pH outside the configured screening range",
        "message": "pH: 3.1 breaches the configured critical level.",
        "reference": "pH screening range - 6.5-8.5 [official standard]",
        "next_step": "Do not use this water until confirmed.",
        "timestamp": "2026-10-30T10:00:00+00:00",
        "source": "esp32",
        "simulated": False,
        "threshold_key": "ph_range",
        "threshold_profile_version": "v1",
    }
    base.update(extra)
    return base


def test_skips_unconfigured_channel_but_logs(db_session):
    user = _user(db_session)
    row, reason = notification_service.notify(
        db_session, user, category="alert:ph", severity="critical",
        title="pH critical", body="body", dedup_key="alert:1",
    )
    assert reason == "skipped_unconfigured"
    assert row.status == "skipped_unconfigured"
    assert row.sent_at is None
    assert row.dedup_key == "alert:1"


def test_cooldown_dedup_suppresses_repeat_from_same_key(db_session):
    user = _user(db_session)
    first, reason1 = notification_service.notify(
        db_session, user, category="alert:ph", severity="warning",
        title="t", body="b", dedup_key="k-1",
    )
    second, reason2 = notification_service.notify(
        db_session, user, category="alert:ph", severity="warning",
        title="t", body="b", dedup_key="k-1",
    )
    assert first is not None and second is None
    assert reason1 == "skipped_unconfigured"
    assert reason2 == "deduped"


def test_new_attempt_after_cooldown_window_passes_dedup(db_session):
    user = _user(db_session)
    now = datetime.now(timezone.utc)
    first, _ = notification_service.notify(
        db_session, user, category="alert:ph", severity="warning",
        title="t", body="b", dedup_key="fresh-1", now=now,
    )
    assert first is not None
    later, reason = notification_service.notify(
        db_session, user, category="alert:ph", severity="warning",
        title="t2", body="b2", dedup_key="fresh-1",
        now=now + timedelta(seconds=1000 + 1),
    )
    assert later is not None
    assert reason == "skipped_unconfigured"


def test_per_user_cap_spares_critical(db_session, monkeypatch):
    import app.core.config as config

    user = _user(db_session)
    monkeypatch.setattr(config.settings, "NOTIFICATION_MAX_PER_WINDOW", 4, raising=False)

    reasons = []
    for i in range(4):
        _, reason = notification_service.notify(
            db_session, user, category="test", severity="warning",
            title=f"t{i}", body="b", dedup_key=f"cap-{i}",
        )
        assert reason == "skipped_unconfigured"
        reasons.append(reason)

    _, capped = notification_service.notify(
        db_session, user, category="test", severity="warning",
        title="t-cap", body="b", dedup_key="cap-99",
    )
    assert capped == "capped"

    # A critical notification bypasses the cap.
    row, reason = notification_service.notify(
        db_session, user, category="test", severity="critical",
        title="critical", body="b", dedup_key="cap-critical",
    )
    assert row is not None
    assert reason == "skipped_unconfigured"


def test_category_opt_out_suppresses(db_session):
    user = _user(db_session)
    pref = notification_service.NotificationPreference(
        user_id=user.id, category="alert:ph", channel="email", enabled=False
    )
    db_session.add(pref)
    db_session.commit()

    row, reason = notification_service.notify(
        db_session, user, category="alert:ph", severity="critical",
        title="t", body="b", dedup_key="opt-1",
    )
    assert row is None
    assert reason == "suppressed_category"


def test_alert_payload_never_fabricates_and_labels_source(db_session):
    user = _user(db_session)
    alert = _alert(source="simulator", simulated=True)
    row, reason = notification_service.notify_alert(db_session, user, alert)
    assert row is not None
    assert reason == "skipped_unconfigured"
    assert "'simulated': True" in row.payload_json

    # A null-value alert ("sensor not reporting" notice) still dispatches as a
    # warning — its recorded payload must show the missing value as null, not 0.
    stale = _alert(parameter="ph", severity="warning", value=None, title="pH sensor not reporting")
    row2, reason2 = notification_service.notify_alert(db_session, user, stale)
    assert row2 is not None
    assert reason2 == "skipped_unconfigured"
    assert "'value': None" in row2.payload_json


def test_delivery_failure_captured_not_raised(db_session, monkeypatch):
    import app.core.config as config

    user = _user(db_session)
    monkeypatch.setattr(config.settings, "SMTP_HOST", "smtp.example.invalid", raising=False)
    row, reason = notification_service.notify(
        db_session, user, category="alert:tds", severity="critical",
        title="t", body="b", dedup_key="fail-1",
    )
    assert row is not None
    assert row.status == "failed"
    assert row.sent_at is None


def test_smtp_success_marks_sent(db_session, monkeypatch):
    import app.core.config as config
    import app.services.notification_service as ns

    sent_messages = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            pass

        def login(self, username, password):
            pass

        def send_message(self, message):
            sent_messages.append(message)

    user = _user(db_session, email="delivered@example.com")
    monkeypatch.setattr(config.settings, "SMTP_HOST", "smtp.example", raising=False)
    monkeypatch.setattr(ns.smtplib, "SMTP", FakeSMTP, raising=False)

    payload = {"parameter": "ph", "value": 3.1}
    row, reason = notification_service.notify(
        db_session, user, category="alert:ph", severity="warning",
        title="Warm reading OK", body="Everything within the configured range.",
        dedup_key="sent-1", payload=payload,
    )
    assert row is not None
    assert row.status == "sent"
    assert row.sent_at is not None
    assert len(sent_messages) == 1
    assert sent_messages[0]["To"] == "delivered@example.com"
    # The stored delivery detail records the attempt, not credentials.
    assert "TestPassword123!" not in row.body


def _auth_headers(user) -> dict:
    from app.core.security import create_access_token

    token = create_access_token(subject=user.id, role=user.role.value, email=user.email)
    return {"Authorization": f"Bearer {token}"}


def test_product_notifications_api_lists_own_only(client, db_session):
    owner = _user(db_session, email="api-owner@example.com")
    other = _user(db_session, email="api-other@example.com")
    notification_service.notify(
        db_session, owner, category="alert:ph", severity="warning",
        title="owner note", body="x", dedup_key="api-1",
    )
    notification_service.notify(
        db_session, other, category="alert:ph", severity="warning",
        title="other note", body="y", dedup_key="api-2",
    )

    response = client.get("/api/product/notifications", headers=_auth_headers(owner))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["channel"] == "email"
    titles = [item["title"] for item in body["items"]]
    assert titles == ["owner note"]


def test_notification_preferences_roundtrip(client, db_session):
    user = _user(db_session, email="prefs@example.com")
    headers = _auth_headers(user)

    # Missing category defaults to enabled.
    response = client.get("/api/product/notification-preferences", headers=headers)
    assert response.status_code == 200 and response.json()["items"] == []

    response = client.put(
        "/api/product/notification-preferences/alert:ph?enabled=false", headers=headers
    )
    assert response.status_code == 200
    assert response.json() == {
        "category": "alert:ph", "channel": "email", "enabled": False
    }

    # The backend honours the opt-out: an alert for the suppressed category is
    # recorded as suppressed and never composed.
    row, reason = notification_service.notify(
        db_session, user, category="alert:ph", severity="critical",
        title="t", body="b", dedup_key="pref-1",
    )
    assert row is None and reason == "suppressed_category"


# The alerts endpoint dispatch: a GET of /alerts composes (debounced)
# notifications from real stored data and reports the breakdown.
def test_alerts_endpoint_response_shape(client, db_session):
    user = _user(db_session, email="dispatch@example.com")
    headers = _auth_headers(user)

    first = client.get("/api/product/alerts", headers=headers)
    assert first.status_code == 200, first.text
    dispatch = first.json()["notification_dispatch"]
    assert dispatch["channel"] == "email"
    assert dispatch["attempted"] == len(first.json().get("alerts", []))
    assert set(dispatch["by_reason"]) <= {
        "sent", "failed", "skipped_unconfigured", "suppressed_category",
        "deduped", "capped", "error",
    }
