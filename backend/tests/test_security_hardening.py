"""Security hardening regression tests: CORS allowlist, JWT secret, rate limits.

Covers the three fixes in this pass:
1. Explicit CORS origins (no wildcard + credentials), fail-closed in production.
2. JWT signing secret required from the environment; insecure defaults refuse
   to boot in production and never silently regenerate.
3. Database-backed rate limiting on the authentication endpoints with 429 +
   Retry-After once the configured limit is exceeded.

Rate limiting is enabled here explicitly because conftest disables it for the
rest of the suite (shared counters would otherwise throttle unrelated tests).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.cors import DEV_ORIGINS, configure_cors, resolve_cors
from app.core.config import (
    INSECURE_JWT_SECRETS,
    MIN_JWT_SECRET_LENGTH,
    Settings,
    settings,
)
from app.core.rate_limit import consume
from app.main import app as main_app
from app.models.rate_limit import RateLimitCounter

VALID_SECRET = "hydrasense-tests-only-signing-key-0123456789abcdef"


# --------------------------------------------------------------------------
# 1. CORS
# --------------------------------------------------------------------------


def test_cors_explicit_allowlist_is_used_verbatim():
    cfg = Settings(
        APP_ENV="production",
        CORS_ALLOW_ORIGINS="https://app.example.com, https://admin.example.com",
    )
    config = resolve_cors(cfg)
    assert config["allow_origins"] == [
        "https://app.example.com",
        "https://admin.example.com",
    ]
    assert "*" not in config["allow_origins"]


def test_cors_production_fails_closed_when_unset():
    config = resolve_cors(Settings(APP_ENV="production", CORS_ALLOW_ORIGINS=""))
    assert config["allow_origins"] == []


def test_cors_development_defaults_to_local_origins_only():
    config = resolve_cors(Settings(APP_ENV="development", CORS_ALLOW_ORIGINS=""))
    assert config["allow_origins"] == list(DEV_ORIGINS)
    assert "*" not in config["allow_origins"]


def test_cors_rejects_wildcard_with_credentials():
    cfg = Settings(APP_ENV="development", CORS_ALLOW_ORIGINS="*")
    with pytest.raises(RuntimeError, match="CORS_ALLOW_ORIGINS"):
        resolve_cors(cfg)


def test_cors_rejects_wildcard_in_production():
    cfg = Settings(
        APP_ENV="production",
        CORS_ALLOW_ORIGINS="*",
        CORS_ALLOW_CREDENTIALS=False,
    )
    with pytest.raises(RuntimeError, match="production"):
        resolve_cors(cfg)


def _mini_app(cfg: Settings) -> FastAPI:
    app = FastAPI()

    @app.get("/")
    def index():
        return {"ok": True}

    configure_cors(app, cfg)
    return app


def test_cors_trusted_origin_is_allowed_by_middleware():
    cfg = Settings(
        APP_ENV="production",
        CORS_ALLOW_ORIGINS="https://app.example.com",
    )
    client = TestClient(_mini_app(cfg))
    response = client.get(
        "/", headers={"Origin": "https://app.example.com"}
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.example.com"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_untrusted_origin_is_rejected_by_middleware():
    cfg = Settings(
        APP_ENV="production",
        CORS_ALLOW_ORIGINS="https://app.example.com",
    )
    client = TestClient(_mini_app(cfg))

    # Simple request: no CORS headers are emitted, so a browser blocks it.
    simple = client.get("/", headers={"Origin": "https://evil.example.com"})
    assert simple.status_code == 200
    assert "access-control-allow-origin" not in simple.headers

    # Preflight: explicitly refused.
    preflight = client.options(
        "/",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers


def test_cors_preflight_succeeds_for_trusted_origin():
    cfg = Settings(
        APP_ENV="production",
        CORS_ALLOW_ORIGINS="https://app.example.com",
    )
    client = TestClient(_mini_app(cfg))
    response = client.options(
        "/",
        headers={
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.example.com"


def test_wired_application_uses_allowlist_not_wildcard():
    config = resolve_cors(settings)
    assert "*" not in config["allow_origins"]


# --------------------------------------------------------------------------
# 2. JWT secret
# --------------------------------------------------------------------------


def test_missing_jwt_secret_fails_validation():
    cfg = Settings(JWT_SECRET_KEY=None, APP_ENV="development")
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY is not configured"):
        cfg.validate_security()


def test_empty_jwt_secret_fails_validation():
    cfg = Settings(JWT_SECRET_KEY="   ", APP_ENV="development")
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY is not configured"):
        cfg.validate_security()


@pytest.mark.parametrize("insecure", sorted(INSECURE_JWT_SECRETS))
def test_insecure_defaults_fail_in_production(insecure):
    cfg = Settings(JWT_SECRET_KEY=insecure, APP_ENV="production")
    with pytest.raises(RuntimeError, match="known insecure default"):
        cfg.validate_security()


def test_insecure_default_only_warns_in_development():
    cfg = Settings(
        JWT_SECRET_KEY=sorted(INSECURE_JWT_SECRETS)[0], APP_ENV="development"
    )
    cfg.validate_security()  # no exception outside production


def test_short_secret_fails_in_production_but_not_development():
    short = "a" * (MIN_JWT_SECRET_LENGTH - 1)
    with pytest.raises(RuntimeError, match="shorter than"):
        Settings(JWT_SECRET_KEY=short, APP_ENV="production").validate_security()
    Settings(JWT_SECRET_KEY=short, APP_ENV="development").validate_security()


def test_valid_secret_passes_in_every_environment():
    Settings(JWT_SECRET_KEY=VALID_SECRET, APP_ENV="production").validate_security()
    Settings(JWT_SECRET_KEY=VALID_SECRET, APP_ENV="development").validate_security()


def test_app_startup_fails_when_secret_missing(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", None)
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        with TestClient(main_app):
            pass  # pragma: no cover - startup must raise first


def test_app_startup_fails_with_insecure_default_in_production(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", sorted(INSECURE_JWT_SECRETS)[0])
    monkeypatch.setattr(settings, "APP_ENV", "production")
    with pytest.raises(RuntimeError, match="known insecure default"):
        with TestClient(main_app):
            pass  # pragma: no cover - startup must raise first


def test_app_startup_succeeds_with_configured_secret(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", VALID_SECRET)
    monkeypatch.setattr(settings, "APP_ENV", "development")
    with TestClient(main_app) as client:
        assert client.get("/").json()["status"] == "online"


# --------------------------------------------------------------------------
# 3. Rate limiting
# --------------------------------------------------------------------------


@pytest.fixture
def rate_limited_settings(monkeypatch):
    """Enable rate limiting with small, per-test limits."""
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_LOGIN_MAX", 3)
    monkeypatch.setattr(settings, "RATE_LIMIT_LOGIN_WINDOW_SECONDS", 60)
    monkeypatch.setattr(settings, "RATE_LIMIT_REGISTER_MAX", 3)
    monkeypatch.setattr(settings, "RATE_LIMIT_REGISTER_WINDOW_SECONDS", 60)
    monkeypatch.setattr(settings, "RATE_LIMIT_TRUST_PROXY_HEADERS", False)
    return settings


def test_login_within_limit_succeeds(client, db_session, rate_limited_settings):
    from app.core.security import get_password_hash
    from app.models.user import User, UserRole

    db_session.add(
        User(
            email="rl_user@example.com",
            password_hash=get_password_hash("CorrectPassword123!"),
            full_name="Rate Limit User",
            role=UserRole.PRODUCT_USER,
            is_active=True,
        )
    )
    db_session.commit()

    payload = {
        "email": "rl_user@example.com",
        "password": "CorrectPassword123!",
    }
    for _ in range(rate_limited_settings.RATE_LIMIT_LOGIN_MAX):
        response = client.post("/api/auth/login", json=payload)
        assert response.status_code == 200


def test_login_beyond_limit_returns_429_with_retry_after(
    client, db_session, rate_limited_settings
):
    from app.core.security import get_password_hash
    from app.models.user import User, UserRole

    db_session.add(
        User(
            email="rl_brute@example.com",
            password_hash=get_password_hash("CorrectPassword123!"),
            full_name="Brute Force User",
            role=UserRole.PRODUCT_USER,
            is_active=True,
        )
    )
    db_session.commit()

    payload = {"email": "rl_brute@example.com", "password": "CorrectPassword123!"}
    limit = rate_limited_settings.RATE_LIMIT_LOGIN_MAX
    for _ in range(limit):
        assert client.post("/api/auth/login", json=payload).status_code == 200

    blocked = client.post("/api/auth/login", json=payload)
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Too many requests. Please wait before trying again."
    assert int(blocked.headers["Retry-After"]) >= 1


def test_register_beyond_limit_returns_429(client, rate_limited_settings):
    limit = rate_limited_settings.RATE_LIMIT_REGISTER_MAX
    for index in range(limit):
        response = client.post(
            "/api/auth/register",
            json={
                "email": f"rl_reg_{index}@example.com",
                "password": "Password123!",
                "full_name": f"RL {index}",
                "role": "PRODUCT_USER",
            },
        )
        assert response.status_code == 201

    blocked = client.post(
        "/api/auth/register",
        json={
            "email": "rl_reg_blocked@example.com",
            "password": "Password123!",
            "full_name": "Blocked",
            "role": "PRODUCT_USER",
        },
    )
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_rate_limiting_disabled_never_blocks(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "RATE_LIMIT_LOGIN_MAX", 1)
    for index in range(5):
        response = client.post(
            "/api/auth/login",
            json={"email": f"disabled_{index}@example.com", "password": "x"},
        )
        assert response.status_code == 401  # throttled nowhere, just unknown user


def test_counters_are_shared_database_rows_not_memory(client, db_session, rate_limited_settings):
    """Counters persist in the database, so any worker/restart sees them."""
    allowed, _ = consume(db_session, "auth:login:testclient", limit=5, window_seconds=60)
    assert allowed is True
    rows = db_session.query(RateLimitCounter).filter_by(
        bucket_key="auth:login:testclient"
    ).all()
    assert len(rows) == 1
    assert rows[0].hits == 1


def test_consume_counts_concurrently_across_sessions(db_session):
    """Every hit on the same bucket is counted in the shared row."""
    for _ in range(5):
        allowed, _ = consume(db_session, "auth:register:shared", 10, 60)
        assert allowed is True
    row = (
        db_session.query(RateLimitCounter)
        .filter_by(bucket_key="auth:register:shared")
        .one()
    )
    assert row.hits == 5

    # Exceeding the limit reports "not allowed" with a retry hint.
    for _ in range(6):
        allowed, retry_after = consume(db_session, "auth:register:shared", 10, 60)
    assert allowed is False
    assert retry_after >= 1


def test_registration_cannot_escalate_to_authority(client):
    """Regression: the privilege-escalation fix must stay in place."""
    response = client.post(
        "/api/auth/register",
        json={
            "email": "escalation_harden@hydrasense.local",
            "password": "TestPassword123!",
            "full_name": "Escalation Attempt",
            "role": "AUTHORITY",
        },
    )
    assert response.status_code == 403