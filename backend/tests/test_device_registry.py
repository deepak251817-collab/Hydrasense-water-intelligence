"""Device-number registry + login tests.

Covers the personal-user flow: an account is bound to exactly one device, a
printed device number can log the bound account in, unknown/unbound numbers
receive generic messages, and the `device-login` endpoint is rate limited.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.security import get_password_hash
from app.models.device import ProductDevice
from app.models.user import User, UserRole


def _make_device(db, device_number="HSD-0001-K7M2Q9", product_code="HS-KIT-000125",
                 device_id="ESP32-HS-001", station_code="ARK-001", owner_id=None):
    device = ProductDevice(
        product_code=product_code,
        device_id=device_id,
        device_number=device_number,
        station_code=station_code,
        device_type="PERSONAL_WATER_TESTER",
        status="PENDING_ACTIVATION" if owner_id is None else "ACTIVE",
        owner_id=owner_id,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def _register_user(client, email="device-owner@example.com"):
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "TestPassword123!",
            "full_name": "Device Owner",
            "role": "PRODUCT_USER",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _login_token(client, email):
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "TestPassword123!"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_unknown_device_number_is_generic_404(client, db_session):
    response = client.post("/api/auth/device-login", json={"device_number": "HSD-9999-XXXXX"})
    assert response.status_code == 404
    body = response.json()["detail"]
    assert "activate this device number first" in body


def test_unbound_device_number_is_generic_404(client, db_session):
    _make_device(db_session, owner_id=None)
    response = client.post("/api/auth/device-login", json={"device_number": "HSD-0001-K7M2Q9"})
    assert response.status_code == 404
    body = response.json()["detail"]
    # Same generic text as the unknown case: no enumeration signal.
    assert "activate this device number first" in body


def test_bound_device_number_logs_the_owner_in(client, db_session):
    user = User(
        email="owner@example.com",
        password_hash=get_password_hash("TestPassword123!"),
        full_name="Owner",
        role=UserRole.PRODUCT_USER,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    _make_device(db_session, owner_id=user.id)
    db_session.expire(user)

    response = client.post("/api/auth/device-login", json={"device_number": " hsd-0001-k7m2q9 "})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["role"] == "PRODUCT_USER"
    assert body["user"]["email"] == "owner@example.com"
    assert body["access_token"]


def test_device_number_lookup_is_case_insensitive(client, db_session):
    user = User(
        email="owner2@example.com",
        password_hash=get_password_hash("TestPassword123!"),
        full_name="Owner Two",
        role=UserRole.PRODUCT_USER,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    _make_device(db_session, owner_id=user.id)
    db_session.expire(user)

    response = client.post("/api/auth/device-login", json={"device_number": "HsD-0001-k7M2q9"})
    assert response.status_code == 200, response.text


def test_inactive_device_account_is_rejected(client, db_session):
    user = User(
        email="inactive@example.com",
        password_hash=get_password_hash("TestPassword123!"),
        full_name="Inactive",
        role=UserRole.PRODUCT_USER,
        is_active=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    _make_device(db_session, owner_id=user.id)

    response = client.post("/api/auth/device-login", json={"device_number": "HSD-0001-K7M2Q9"})
    assert response.status_code == 403


def test_one_device_per_account_limits_activation(client, db_session):
    owner = _register_user(client, email="limit-user@example.com")
    first = _make_device(db_session, device_number="HSD-0001-K7M2Q9")
    second = _make_device(
        db_session,
        device_number="HSD-0003-P2W6L4",
        product_code="HS-KIT-000126",
        device_id="ESP32-PERSONAL-002",
        station_code=None,
    )

    token = _login_token(client, owner["email"])
    headers = {"Authorization": f"Bearer {token}"}

    bind_first = client.post(
        "/api/product/activate", headers=headers, json={"product_code": first.product_code}
    )
    assert bind_first.status_code == 200, bind_first.text
    assert bind_first.json()["device_number"] == first.device_number
    assert bind_first.json()["station_code"] == "ARK-001"

    bind_second = client.post(
        "/api/product/activate", headers=headers, json={"product_code": second.product_code}
    )
    assert bind_second.status_code == 409
    assert bind_second.json()["detail"]["code"] == "account_device_limit"


def test_activate_accepts_device_number_identifier(client, db_session):
    owner = _register_user(client, email="number-user@example.com")
    device = _make_device(db_session)
    token = _login_token(client, owner["email"])
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/api/product/activate",
        headers=headers,
        json={"product_code": device.device_number},
    )
    assert response.status_code == 200, response.text
    assert response.json()["device_number"] == device.device_number
    assert response.json()["station_code"] == "ARK-001"


def test_device_login_rate_limited(client, db_session, monkeypatch):
    import app.core.config as config

    monkeypatch.setattr(config.settings, "RATE_LIMIT_ENABLED", True, raising=False)
    monkeypatch.setattr(config.settings, "RATE_LIMIT_LOGIN_MAX", 3, raising=False)
    monkeypatch.setattr(config.settings, "RATE_LIMIT_LOGIN_WINDOW_SECONDS", 60, raising=False)
    monkeypatch.setattr(config.settings, "RATE_LIMIT_TRUST_PROXY_HEADERS", False, raising=False)

    for _ in range(3):
        response = client.post("/api/auth/device-login", json={"device_number": "HSD-0001-NOPE1"})
        assert response.status_code == 404
    response = client.post("/api/auth/device-login", json={"device_number": "HSD-0001-NOPE1"})
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_seed_demo_is_idempotent_for_first_device(db_session, monkeypatch):
    """Run the seeding logic for the first device exactly as seed_demo does."""
    from scripts.seed_demo import seed_first_personal_device

    seed_first_personal_device(db_session, quiet=True)
    first = (
        db_session.query(ProductDevice)
        .filter(ProductDevice.device_number == "HSD-0001-K7M2Q9")
        .one_or_none()
    )
    assert first is not None
    assert first.device_id == "ESP32-HS-001"
    assert first.station_code == "ARK-001"
    assert first.owner_id is None

    seed_first_personal_device(db_session, quiet=True)
    count = (
        db_session.query(ProductDevice)
        .filter(ProductDevice.device_number == "HSD-0001-K7M2Q9")
        .count()
    )
    assert count == 1
