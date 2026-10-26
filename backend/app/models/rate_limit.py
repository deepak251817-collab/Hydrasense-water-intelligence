"""Database-backed rate-limit counters.

Counters live in PostgreSQL so that every API worker (and every application
restart) observes the same limits. Process-local dictionaries would reset on
restart and diverge between workers.
"""

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, func
from app.core.database import Base


class RateLimitCounter(Base):
    __tablename__ = "rate_limit_counters"

    id = Column(Integer, primary_key=True, index=True)
    bucket_key = Column(String(255), nullable=False, index=True)
    # Epoch seconds of the start of the fixed window for this bucket.
    window_start = Column(Integer, nullable=False)
    hits = Column(Integer, nullable=False, default=0)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("bucket_key", "window_start", name="uq_rate_limit_bucket_window"),
    )
