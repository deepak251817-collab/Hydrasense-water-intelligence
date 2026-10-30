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

import subprocess
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


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent.parent

# Real secret files that must never be tracked by git. Templates are allowed.
SENSITIVE_TRACKED_PATHS = {
    "backend/.env",
    "frontend/.env",
    "firmware/hydrasense_esp32/config.h",
}


def _is_production(cfg: Settings) -> bool:
    return cfg.APP_ENV.strip().lower() in {"production", "prod", "staging", "live"}


def _tracked_secret_files() -> tuple[list[str] | None, str]:
    """List tracked real-secret files; None when git cannot be inspected."""
    try:
        result = subprocess.run(
            ["git", "-C", str(REPOSITORY_ROOT), "ls-files"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as err:  # pragma: no cover - env specific
        return None, f"git unavailable ({err.__class__.__name__})"
    if result.returncode != 0:
        return None, "git ls-files failed"
    flagged = [
        path
        for path in result.stdout.splitlines()
        if path in SENSITIVE_TRACKED_PATHS
        or Path(path).name in {".env", ".env.local", ".env.production"}
    ]
    return flagged, f"{len(result.stdout.splitlines())} tracked files scanned"


def _ingestion_bounds() -> dict[str, float]:
    """Read the real ingestion bounds from the telemetry validator."""
    from app.services.mqtt_service import (
        TDS_MAX_PPM,
        TURBIDITY_INDEX_MAX,
        TURBIDITY_MAX_NTU,
    )

    return {
        "tds_ppm": TDS_MAX_PPM,
        "turbidity_ntu": TURBIDITY_MAX_NTU,
        "turbidity_index": TURBIDITY_INDEX_MAX,
    }


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

    # 8. MQTT broker authentication: anonymous publishing is never acceptable.
    if cfg.MQTT_ALLOW_ANONYMOUS:
        results.append((
            "MQTT authentication configured",
            FAIL,
            "MQTT_ALLOW_ANONYMOUS=true: anyone who can reach the broker could publish telemetry",
        ))
    elif cfg.MQTT_USERNAME.strip() and cfg.MQTT_PASSWORD:
        results.append((
            "MQTT authentication configured",
            PASS,
            "broker username/password supplied from the environment (values never printed)",
        ))
    else:
        results.append((
            "MQTT authentication configured",
            FAIL,
            "MQTT_USERNAME/MQTT_PASSWORD are missing; the subscriber would connect anonymously",
        ))

    # 9. Broker TLS: mandatory as soon as the broker leaves the host.
    broker_is_local = cfg.MQTT_BROKER_HOST.strip().lower() in {
        "localhost", "127.0.0.1", "::1",
    }
    if cfg.MQTT_USE_TLS:
        results.append((
            "MQTT transport encrypted",
            PASS,
            "MQTT_USE_TLS=true"
            + (" with a configured CA bundle" if cfg.MQTT_CA_CERT_PATH else " (system trust store)"),
        ))
    elif broker_is_local:
        results.append((
            "MQTT transport encrypted",
            REVIEW,
            "broker is loopback (TLS optional inside one host); set MQTT_USE_TLS before it leaves the host",
        ))
    else:
        results.append((
            "MQTT transport encrypted",
            FAIL,
            f"remote broker {cfg.MQTT_BROKER_HOST!r} configured without TLS",
        ))

    # 10. QR / public-page base URL must be the real HTTPS origin.
    base = cfg.PUBLIC_BASE_URL.strip()
    if base.startswith("https://"):
        results.append(("PUBLIC_BASE_URL uses HTTPS", PASS, base + " (printed QR links)"))
    elif base.startswith("http://localhost") or base.startswith("http://127.0.0.1"):
        results.append((
            "PUBLIC_BASE_URL uses HTTPS",
            REVIEW,
            "still points at the local dev server; QR codes would be unscannable off this machine",
        ))
    else:
        results.append((
            "PUBLIC_BASE_URL uses HTTPS",
            FAIL,
            "PUBLIC_BASE_URL must be the real public HTTPS origin before printing QR codes",
        ))

    # 11. Telemetry ingestion bounds are finite and documented.
    bounds = _ingestion_bounds()
    bounds_ok = all(
        isinstance(value, (int, float)) and 0 < value < float("inf")
        for value in bounds.values()
    )
    results.append((
        "Telemetry ingestion bounds",
        PASS if bounds_ok else FAIL,
        ", ".join(f"{name}<={value:g}" for name, value in bounds.items()),
    ))

    # 12. No real secret file is tracked by git (templates are fine).
    tracked, detail = _tracked_secret_files()
    if tracked is None:
        results.append(("No secrets committed", REVIEW, detail))
    else:
        results.append((
            "No secrets committed",
            FAIL if tracked else PASS,
            f"tracked secret files: {tracked}" if tracked else detail,
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
