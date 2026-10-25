"""Persistent simulation run state (shared across API workers).

Exactly ONE row (``id = 1``) holds the current simulation configuration and
status. The row is the single source of truth, so Start / Pause / Generate and
scenario selection stay consistent across API workers and frontend sessions,
and survive an application restart.

Duplicate-loop protection: a worker may only generate samples while it holds an
unexpired ``lease_expires_at`` lease recorded in ``worker_id``. Leases expire
automatically if a worker dies, letting another worker take over without ever
running two generation loops at the same time.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    # Singleton row: id is always 1.
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    station_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    scenario: Mapped[str] = mapped_column(String(40), nullable=False, default="normal")
    seed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    interval_seconds: Mapped[float] = mapped_column(nullable=False, default=5.0)

    # "running" | "paused"
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="paused")

    step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    samples_generated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Generation lease: only the worker named in `worker_id` with an unexpired
    # `lease_expires_at` may produce samples.
    worker_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sample_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )
