"""Explicit-origin CORS configuration.

Replaces the historical ``allow_origins=["*"]`` + ``allow_credentials=True``
combination (which any origin can exploit) with an allowlist driven by the
``CORS_ALLOW_ORIGINS`` environment variable.

Resolution rules:
- ``CORS_ALLOW_ORIGINS`` set  -> exactly those origins, comma separated.
- unset, non-production       -> local dev/preview origins only.
- unset, production           -> empty allowlist (fail closed); the API logs a
  warning because cross-origin browser access stays disabled until the real
  frontend origin is configured.
- ``*``                        -> rejected when credentials are enabled, and
  rejected outright in production.
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import Settings, settings

logger = logging.getLogger("hydrasense.cors")

# Vite dev/preview servers used by the local frontend.
DEV_ORIGINS: tuple[str, ...] = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


def _split(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def resolve_cors(cfg: Settings) -> dict:
    """Translate settings into CORSMiddleware keyword arguments.

    Raises RuntimeError for configurations that must never be shipped.
    """
    raw = cfg.CORS_ALLOW_ORIGINS.strip()
    if raw:
        origins = _split(raw)
    elif cfg.is_production:
        origins = []
    else:
        origins = list(DEV_ORIGINS)

    allow_credentials = cfg.CORS_ALLOW_CREDENTIALS

    if "*" in origins:
        if allow_credentials:
            raise RuntimeError(
                "CORS_ALLOW_ORIGINS contains '*' while CORS_ALLOW_CREDENTIALS "
                "is enabled. Wildcard origins with credentials let any site "
                "make authenticated requests; list explicit origins instead."
            )
        if cfg.is_production:
            raise RuntimeError(
                "CORS_ALLOW_ORIGINS may not contain '*' in production "
                f"(APP_ENV={cfg.APP_ENV}); configure explicit frontend origins."
            )
        logger.warning(
            "CORS wildcard origin requested without credentials; browser "
            "responses will be readable by any site."
        )

    if cfg.is_production and not origins:
        logger.warning(
            "CORS_ALLOW_ORIGINS is empty in production: cross-origin browser "
            "requests will be rejected (same-origin access still works)."
        )

    return {
        "allow_origins": origins,
        "allow_credentials": allow_credentials,
        "allow_methods": _split(cfg.CORS_ALLOW_METHODS),
        "allow_headers": _split(cfg.CORS_ALLOW_HEADERS),
    }


def configure_cors(app: FastAPI, cfg: Settings | None = None) -> dict:
    """Attach the CORSMiddleware and return the resolved configuration."""
    config = resolve_cors(cfg or settings)
    app.add_middleware(CORSMiddleware, **config)
    return config
