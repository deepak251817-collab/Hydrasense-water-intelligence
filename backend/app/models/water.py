from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    String, Text, Float, Boolean, DateTime, ForeignKey, Integer, JSON,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class WaterSource(Base):
    __tablename__ = "water_sources"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    source_code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    stations: Mapped[List["MonitoringStation"]] = relationship(
        "MonitoringStation",
        back_populates="water_source",
        cascade="all, delete-orphan"
    )


class MonitoringStation(Base):
    __tablename__ = "monitoring_stations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    station_code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    water_source_id: Mapped[int] = mapped_column(ForeignKey("water_sources.id"), nullable=False, index=True)
    station_name: Mapped[str] = mapped_column(String(255), nullable=False)
    zone: Mapped[str] = mapped_column(String(100), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    public_warning: Mapped[str] = mapped_column(String(100), default="NORMAL", nullable=False)
    public_message: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    water_source: Mapped["WaterSource"] = relationship("WaterSource", back_populates="stations")
    readings: Mapped[List["SensorReading"]] = relationship(
        "SensorReading",
        back_populates="station",
        cascade="all, delete-orphan"
    )


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("monitoring_stations.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(100), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # Nullable: a value is NULL when the device has no honest measurement for
    # it — an uncalibrated analog sensor (pH/turbidity/TDS) or a failed sensor
    # (e.g. DS18B20 disconnected). NULL never means "safe" or "normal"; the
    # UI renders it as "uncalibrated/unavailable". Simulated telemetry always
    # provides full values, so existing rows are unaffected.
    ph: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    turbidity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Turbidity unit for THIS row. "relative_index_0_100" = ESP32 live
    # PROVISIONAL relative index (0-100, higher = cloudier — never NTU);
    # "ntu" = simulated/legacy NTU-style value; NULL = unit unknown (rows
    # predating unit tracking). Consumers must never assume NTU: a row whose
    # unit is NULL or relative_index_0_100 must not be read as NTU.
    turbidity_unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # DEDICATED analog-sensor field: the relative turbidity index on a
    # documented 0-100 scale, higher = cloudier (clearer water reads lower).
    # Populated ONLY for rows whose unit is relative_index_0_100. It is a
    # different quantity from NTU: never labelled NTU, never compared with
    # an NTU limit, and never converted into NTU. NULL for NTU rows and for
    # rows with an unknown unit.
    turbidity_index: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Firmware-reported relative status band (CLEARER / MODERATE / CLOUDIER)
    # for relative-index rows; NULL when not reported or not applicable.
    turbidity_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    # Telemetry provenance: "simulator" (Python simulator / seeded demo data)
    # or "esp32" (physical station hardware). Keeps simulated and physical
    # readings distinguishable in every query.
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="simulator", server_default="simulator")

    # Optional device diagnostics JSON: raw ADC counts, measured voltages,
    # calibration status per sensor, device health (uptime, Wi-Fi RSSI,
    # error list). Stored verbatim; never used for ML inference.
    diagnostics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Phase 6 ML results (nullable: rows predating ML, or where inference
    # failed/skipped, keep NULL — never fabricated values).
    anomaly_label: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1 = anomalous condition, 0 = normal
    anomaly_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Isolation Forest decision function
    water_quality_label: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # predicted class: Safe/Unsafe
    safe_probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unsafe_probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ml_processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    station: Mapped["MonitoringStation"] = relationship("MonitoringStation", back_populates="readings")


class WaterSuitabilityAssessment(Base):
    """Standards-based suitability assessment of ONE reading for ONE intended use.

    Derived data only: the original reading is never modified. One row per
    (reading, use, ruleset version), so recalculating is idempotent and the
    history accumulates as new readings arrive.

    `parameters` stores the per-criterion outcome (value, limit, status, note),
    `missing_parameters` the tests still required, and `data_quality` the
    freshness/provenance that justified the comparison.
    """

    __tablename__ = "water_suitability_assessments"
    __table_args__ = (
        UniqueConstraint(
            "reading_id", "use_code", "standard_version",
            name="uq_suitability_reading_use_version",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    station_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_stations.id"), nullable=False, index=True
    )
    reading_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sensor_readings.id"), nullable=True, index=True
    )

    use_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    standard_code: Mapped[str] = mapped_column(String(60), nullable=False)
    standard_version: Mapped[str] = mapped_column(String(20), nullable=False)

    result_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    result_label: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    parameters: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    missing_parameters: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    measured_values: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    data_quality: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    limitations: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    reading_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    assessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

