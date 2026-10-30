"""Incident, laboratory and audit-trail models.

An incident is an operational record created by an authorised authority user
(or explicitly labelled demo data). Nothing here is derived from a sensor
reading except the optional reference to the stored reading that triggered it;
laboratory results are entered verbatim by an authorised user and are never
computed from the four hardware sensors.

Workflow (forward-only, with an explicit close-early path):

    raised -> lab_notified -> sample_collected -> result_received -> resolved

Every status change is appended to ``incident_events`` as an audit trail.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


INCIDENT_STATUSES = (
    "raised",
    "lab_notified",
    "sample_collected",
    "result_received",
    "resolved",
)

INCIDENT_PRIORITIES = ("low", "medium", "high", "critical")


class LabContact(Base):
    """A laboratory the authority can notify about an incident."""

    __tablename__ = "lab_contacts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    organization: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Accreditation / reference number, when the authority has verified one.
    accreditation: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Incident(Base):
    """One water-quality incident with its workflow state and audit trail."""

    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    # Human-facing reference, e.g. INC-000001; assigned when the row gets an id.
    reference: Mapped[Optional[str]] = mapped_column(
        String(30), unique=True, index=True, nullable=True
    )
    station_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_stations.id"), nullable=False, index=True
    )
    # Optional triggering reading. Validated to belong to the same station.
    reading_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sensor_readings.id"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="raised", index=True
    )
    # "manual" = created by an authorised user; "demo" = seeded demonstration
    # data, clearly labelled as such everywhere it is returned.
    origin: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual", server_default="manual"
    )

    # Reasoning captured with the incident. ``explanation`` is text supplied by
    # the authority (or a rule summary); ``explanation_source`` records which,
    # so an automated explanation is never mistaken for a human statement.
    alert_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    explanation_source: Mapped[str] = mapped_column(
        String(40), nullable=False, default="none", server_default="none"
    )

    # Window of readings that the incident/report covers (both optional).
    time_window_start: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    time_window_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    raised_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    raised_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # --- laboratory workflow ------------------------------------------------
    lab_contact_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("lab_contacts.id"), nullable=True
    )
    # Delivery outcome of the lab notification email, recorded honestly:
    # "sent" / "smtp_unconfigured" / "failed" / "not_notified".
    lab_notification_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="not_notified", server_default="not_notified"
    )
    lab_notified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sample_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    sample_collected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result_received_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    station: Mapped["MonitoringStation"] = relationship("MonitoringStation")  # noqa: F821
    lab_contact: Mapped[Optional["LabContact"]] = relationship("LabContact")
    events: Mapped[List["IncidentEvent"]] = relationship(
        "IncidentEvent",
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="IncidentEvent.created_at, IncidentEvent.id",
    )
    lab_results: Mapped[List["LabResult"]] = relationship(
        "LabResult",
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="LabResult.created_at, LabResult.id",
    )


class IncidentEvent(Base):
    """Append-only audit trail entry for an incident status change."""

    __tablename__ = "incident_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actor_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    incident: Mapped["Incident"] = relationship("Incident", back_populates="events")


class LabResult(Base):
    """A laboratory report entered by an authorised user, verbatim.

    ``results`` is a JSON list of measurement objects. Every object is stored
    as entered; the API forces ``source = "laboratory"`` so a laboratory value
    can never be confused with, or derived from, a hardware sensor reading.
    """

    __tablename__ = "lab_results"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lab_contact_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("lab_contacts.id"), nullable=True
    )
    received_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    sample_id: Mapped[str] = mapped_column(String(120), nullable=False)
    reported_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    results: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Reference to the lab's own document (filename, LIMS id, ...). No binary
    # upload is implemented; this is a pointer recorded by the authority.
    document_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    incident: Mapped["Incident"] = relationship("Incident", back_populates="lab_results")
