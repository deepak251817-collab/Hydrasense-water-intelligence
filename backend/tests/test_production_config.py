"""Production-configuration verification checks — pinned by tests.

These run the same static checks as ``scripts/verify_production_config.py``
against synthetic production-like Settings objects. They verify the checker
itself; they are NOT a deployment verification (that stays unverified until
the real environment is exercised).
"""

import pytest

from app.core.config import Settings
from scripts.verify_production_config import FAIL, PASS, REVIEW, run_checks

GOOD = dict(
    APP_ENV="production",
    JWT_SECRET_KEY="a" * 48,
    CORS_ALLOW_ORIGINS="https://app.example.com",
    RATE_LIMIT_ENABLED=True,
    DATABASE_URL="postgresql+psycopg2://hydrasense:STRONG@db.example.com/hydrasense",
)


def statuses(cfg: Settings) -> dict[str, str]:
    return {check: status for check, status, _detail in run_checks(cfg)}


def test_good_production_config_passes_everything():
    result = statuses(Settings(**GOOD))
    assert FAIL not in result.values(), result
    assert REVIEW not in result.values(), result


def test_missing_secret_fails():
    cfg = Settings(**{**GOOD, "JWT_SECRET_KEY": None})
    assert statuses(cfg)["JWT secret configured"] == FAIL


def test_insecure_default_secret_fails():
    from app.core.config import INSECURE_JWT_SECRETS

    cfg = Settings(**{**GOOD, "JWT_SECRET_KEY": sorted(INSECURE_JWT_SECRETS)[0]})
    assert statuses(cfg)["JWT secret configured"] == FAIL


def test_short_secret_fails():
    cfg = Settings(**{**GOOD, "JWT_SECRET_KEY": "b" * 20})
    assert statuses(cfg)["JWT secret strength"] == FAIL


def test_empty_cors_allowlist_fails():
    cfg = Settings(**{**GOOD, "CORS_ALLOW_ORIGINS": ""})
    assert statuses(cfg)["CORS allowlist configured"] == FAIL


def test_wildcard_cors_fails():
    cfg = Settings(**{**GOOD, "CORS_ALLOW_ORIGINS": "*"})
    assert statuses(cfg)["CORS allowlist configured"] == FAIL


def test_disabled_rate_limiting_fails():
    cfg = Settings(**{**GOOD, "RATE_LIMIT_ENABLED": False})
    assert statuses(cfg)["Rate limiting enabled"] == FAIL


def test_non_production_environment_fails_the_gate():
    cfg = Settings(**{**GOOD, "APP_ENV": "development"})
    assert statuses(cfg)["APP_ENV is production-like"] == FAIL


def test_dev_database_url_needs_review():
    cfg = Settings(**{**GOOD})  # GOOD already uses a custom URL
    assert statuses(cfg)["DATABASE_URL is not the dev default"] == PASS
    dev = Settings(**{**GOOD, "DATABASE_URL": "postgresql+psycopg2://postgres:postgres@localhost:5432/hydrasense"})
    assert statuses(dev)["DATABASE_URL is not the dev default"] == REVIEW


def test_proxy_trust_and_long_token_lifetime_need_review():
    cfg = Settings(**{**GOOD, "RATE_LIMIT_TRUST_PROXY_HEADERS": True,
                      "ACCESS_TOKEN_EXPIRE_MINUTES": 2000})
    result = statuses(cfg)
    assert result["Proxy header trust"] == REVIEW
    assert result["Token lifetime"] == REVIEW
