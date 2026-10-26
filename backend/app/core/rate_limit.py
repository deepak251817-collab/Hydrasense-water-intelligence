"""Fixed-window API rate limiting backed by PostgreSQL.

Why the database: uvicorn/gunicorn deployments run several workers and can be
restarted at any moment, so process-local counters would both diverge between
workers and reset on restart. The ``rate_limit_counters`` table is shared
through the existing PostgreSQL instance, giving every worker the same view
with no new infrastructure.

Usage::

    @router.post("/login", dependencies=[Depends(rate_limit("login", "RATE_LIMIT_LOGIN_MAX", "RATE_LIMIT_LOGIN_WINDOW_SECONDS"))])

The dependency raises ``429 Too Many Requests`` with a ``Retry-After`` header
once the configured limit is exceeded. Request bodies are never logged.
"""

import time
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.rate_limit import RateLimitCounter

# Keep this many old windows around before pruning, so concurrent workers that
# still hold a reference to an old window row are not surprised.
_WINDOW_RETENTION = 6


def client_key(request: Request) -> str:
    """Best-effort client identity for limit buckets.

    Only consults ``X-Forwarded-For`` when explicitly trusted
    (``RATE_LIMIT_TRUST_PROXY_HEADERS``), otherwise the direct peer address is
    used so a client cannot spoof its way out of a limit.
    """
    if settings.RATE_LIMIT_TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _window_start(window_seconds: int, now: float) -> int:
    return int(now // window_seconds) * window_seconds


def consume(
    db: Session, bucket_key: str, limit: int, window_seconds: int
) -> tuple[bool, int]:
    """Register one hit against ``bucket_key``.

    Returns ``(allowed, retry_after_seconds)``. The row lock
    (``SELECT ... FOR UPDATE``) serialises concurrent hits on PostgreSQL so
    two workers cannot both slip past the limit; the unique constraint is the
    fallback for databases that ignore row locks.
    """
    now = time.time()
    window_start = _window_start(window_seconds, now)
    retry_after = max(1, int(window_start + window_seconds - now))

    # Prune windows that no in-flight request can still reference.
    db.query(RateLimitCounter).filter(
        RateLimitCounter.window_start < window_start - _WINDOW_RETENTION * window_seconds
    ).delete(synchronize_session=False)

    row = (
        db.query(RateLimitCounter)
        .filter(
            RateLimitCounter.bucket_key == bucket_key,
            RateLimitCounter.window_start == window_start,
        )
        .with_for_update()
        .first()
    )

    if row is None:
        row = RateLimitCounter(bucket_key=bucket_key, window_start=window_start, hits=1)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            # Another worker inserted the same bucket concurrently; fall back
            # to the existing row and increment it.
            db.rollback()
            row = (
                db.query(RateLimitCounter)
                .filter(
                    RateLimitCounter.bucket_key == bucket_key,
                    RateLimitCounter.window_start == window_start,
                )
                .with_for_update()
                .first()
            )
            if row is None:  # pragma: no cover - defensive
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Rate limiter state unavailable",
                )
            row.hits = (row.hits or 0) + 1
            db.commit()
    else:
        row.hits = (row.hits or 0) + 1
        db.commit()

    return row.hits <= limit, retry_after


def rate_limit(bucket: str, limit_setting: str, window_setting: str):
    """FastAPI dependency factory enforcing a configured limit per client.

    ``bucket`` namespaces the counter (e.g. ``auth:login``), the two setting
    names read their values from ``settings`` on every request so limits stay
    configurable without restarting.
    """

    def dependency(request: Request, db: Session = Depends(get_db)) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return

        limit: int = getattr(settings, limit_setting)
        window: int = getattr(settings, window_setting)
        bucket_key = f"{bucket}:{client_key(request)}"

        allowed, retry_after = consume(db, bucket_key, limit, window)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please wait before trying again.",
                headers={"Retry-After": str(retry_after)},
            )

    return dependency


__all__ = ["rate_limit", "consume", "client_key"]
