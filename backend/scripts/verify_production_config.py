"""Production-configuration verification checklist (local, static checks).

Runs the application's own fail-fast checks plus a few static ones against a
production-like configuration and prints a PASS / FAIL / REVIEW checklist.
Exits non-zero when any required check FAILS.

    cd backend && python scripts/verify_production_config.py

This is NOT a deployment verification. It cannot reach, probe or exercise the
target environment, so deployment security stays UNVERIFIED until the
"Deployment verification checklist" in README.md has been run against the real
environment (real DNS name, real reverse proxy, real browser CORS request,
real login round-trip, real rate-limit observation).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a plain script from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import (  # noqa: E402
    INSECURE_JWT_SECRETS,
    MIN_JWT_SECRET_LENGTH,
    Settings,
)

PASS, FAIL, REVIEW = "PASS", "FAIL", "REVIEW"


def _is_production(cfg: Settings) -> bool:
    return cfg.APP_ENV.strip().lower() in {"production", "prod", "staging", "live"}


def run_checks(cfg: Settings) -> list[tuple[str, str, str]]:
    """Return [(check, status, detail), ...] for the given settings."""
    results: list[tuple[str, str, str]] = []

    # 1. Environment is explicitly production-like.
    results.append((
        "APP_ENV is production-like",
        PASS if _is_production(cfg) else FAIL,
        f"APP_ENV={cfg.APP_ENV!r}",
    ))

    # 2. JWT signing secret: present, strong, not a known placeholder.
    secret = cfg.jwt_secret
    if not secret:
        results.append(("JWT secret configured", FAIL, "JWT_SECRET_KEY is missing or empty"))
    elif secret in INSECURE_JWT_SECRETS:
        results.append(("JWT secret configured", FAIL, "JWT_SECRET_KEY is a known insecure default"))
    elif len(secret) < MIN_JWT_SECRET_LENGTH:
        results.append((
            "JWT secret strength",
            FAIL,
            f"JWT_SECRET_KEY is {len(secret)} chars; minimum is {MIN_JWT_SECRET_LENGTH}",
        ))
    else:
        results.append((
            "JWT secret configured",
            PASS,
            f"{len(secret)}-char secret from the environment (value never printed)",
        ))

    # 3. CORS: explicit allowlist, no wildcards.
    raw = cfg.CORS_ALLOW_ORIGINS.strip()
    if not raw:
        results.append((
            "CORS allowlist configured",
            FAIL,
            "CORS_ALLOW_ORIGINS is empty; production would silently block the real frontend",
        ))
    elif "*" in raw:
        results.append(("CORS allowlist configured", FAIL, "wildcard origin is never allowed in production"))
    else:
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        bad = [o for o in origins if not o.startswith("https://")]
        if bad:
            results.append((
                "CORS origins use HTTPS",
                REVIEW,
                f"non-HTTPS origins configured: {bad}",
            ))
        results.append((
            "CORS allowlist configured",
            PASS,
            f"{len(origins)} explicit origin(s)",
        ))
    if cfg.CORS_ALLOW_CREDENTIALS and "*" in raw:
        results.append(("CORS credentials safe", FAIL, "wildcard + credentials"))

    # 4. Rate limiting on authentication endpoints.
    if not cfg.RATE_LIMIT_ENABLED:
        results.append(("Rate limiting enabled", FAIL, "RATE_LIMIT_ENABLED is false"))
    else:
        ok = cfg.RATE_LIMIT_LOGIN_MAX > 0 and cfg.RATE_LIMIT_REGISTER_MAX > 0
        results.append((
            "Rate limiting configured",
            PASS if ok else FAIL,
            f"login={cfg.RATE_LIMIT_LOGIN_MAX}/{cfg.RATE_LIMIT_LOGIN_WINDOW_SECONDS}s, "
            f"register={cfg.RATE_LIMIT_REGISTER_MAX}/{cfg.RATE_LIMIT_REGISTER_WINDOW_SECONDS}s",
        ))

    # 5. Proxy-header trust is an explicit deployment decision.
    results.append((
        "Proxy header trust",
        PASS if not cfg.RATE_LIMIT_TRUST_PROXY_HEADERS else REVIEW,
        "RATE_LIMIT_TRUST_PROXY_HEADERS="
        f"{cfg.RATE_LIMIT_TRUST_PROXY_HEADERS} (only enable behind a proxy you control)",
    ))

    # 6. Token algorithm and lifetime.
    results.append((
        "JWT algorithm",
        PASS if cfg.JWT_ALGORITHM == "HS256" else REVIEW,
        f"JWT_ALGORITHM={cfg.JWT_ALGORITHM}",
    ))
    results.append((
        "Token lifetime",
        PASS if cfg.ACCESS_TOKEN_EXPIRE_MINUTES <= 480 else REVIEW,
        f"ACCESS_TOKEN_EXPIRE_MINUTES={cfg.ACCESS_TOKEN_EXPIRE_MINUTES}",
    ))

    # 7. Database URL is not the shipped development default.
    defaultish = "postgres:postgres@" in cfg.DATABASE_URL
    results.append((
        "DATABASE_URL is not the dev default",
        REVIEW if defaultish else PASS,
        "still uses postgres:postgres — change it for production"
        if defaultish else "custom connection string (value never printed)",
    ))

    return results


def main() -> int:
    cfg = Settings()
    results = run_checks(cfg)

    print("HydraSense production-configuration checks")
    print("=" * 72)
    for check, status, detail in results:
        print(f"[{status:6}] {check} — {detail}")
    print("=" * 72)

    failed = [r for r in results if r[1] == FAIL]
    review = [r for r in results if r[1] == REVIEW]
    if failed:
        print(f"RESULT: {len(failed)} check(s) FAILED — fix before any deployment.")
    elif review:
        print(f"RESULT: no failures; {len(review)} item(s) need human review.")
    else:
        print("RESULT: all checks passed.")
    print(
        "NOTE: these are local static checks only. Deployment security remains\n"
        "UNVERIFIED until README.md's deployment verification checklist has been\n"
        "exercised against the real environment."
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
