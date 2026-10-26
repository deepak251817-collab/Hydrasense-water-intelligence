"""Private product-user water tests.

Each row stores exactly what was measured for ONE test, the source/use the user
selected, the reading provenance (live hardware vs. explicitly labelled
simulation), and the complete assessment produced at that time. The assessment
is stored as JSON so a historical result is reproducible even if screening
criteria are edited later; `criteria_version` records which criteria were used.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime, Float, ForeignKey, Index, JSON, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProductWaterTest(Base):
    __tablename__ = "product_water_tests"
    __table_args__ = (
        Index("ix_product_water_tests_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    sensor_reading_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sensor_readings.id"), nullable=True
    )

    water_source: Mapped[str] = mapped_column(String(32), nullable=False)
    intended_use: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reading_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    # "esp32" for hardware, "simulated" for clearly-labelled demo readings.
    reading_source: Mapped[str] = mapped_column(String(20), nullable=False)

    ph: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    turbidity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    turbidity_unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reading_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    overall_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # Canonical four-state suitability vocabulary
    # (within_configured_ranges | caution | outside_configured_ranges |
    #  insufficient_data) derived from the central suitability engine.
    overall_state: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    criteria_version: Mapped[str] = mapped_column(String(40), nullable=False)
    assessment: Mapped[dict] = mapped_column(JSON, nullable=False)
    summary_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LiveWaterAssessment(Base):
    """A persisted stable-reading assessment from the authority Live Monitoring page.

    Keyed by (reading, use, criteria version) so polling the live page does not
    create duplicates. The assessment JSON is immutable for auditability; the
    original sensor reading remains untouched in ``sensor_readings``.
    """

    __tablename__ = "live_water_assessments"
    __table_args__ = (
        UniqueConstraint(
            "reading_id", "use_code", "criteria_version",
            name="uq_live_assessment_reading_use_version",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    station_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_stations.id"), nullable=False, index=True
    )
    reading_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sensor_readings.id"), nullable=True, index=True
    )
    device_id: Mapped[str] = mapped_column(String(100), nullable=False)
    use_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    overall_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # Canonical four-state suitability vocabulary (see services/screening_states.py).
    overall_state: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    criteria_version: Mapped[str] = mapped_column(String(40), nullable=False)
    assessment: Mapped[dict] = mapped_column(JSON, nullable=False)
    reading_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
