"""Incident + laboratory workflow.

Rules enforced here (not just in the UI):

- Only authorised authority users reach these functions; the API applies RBAC.
- Status transitions are forward-only along
  ``raised -> lab_notified -> sample_collected -> result_received -> resolved``
  with an explicit close-early path to ``resolved`` (recorded in the audit
  trail as closing before a laboratory result).
- A laboratory value can only be *entered*, never computed: results are stored
  verbatim with ``source = "laboratory"`` and ``derived_from_sensors = false``.
- Lab notification delivery is reported honestly: ``sent`` /
  ``smtp_unconfigured`` / ``failed``. When email is not configured the report
  is still generated and the workflow advances, but the incident records that
  no email was delivered so the UI can tell the user to send it manually.
- Demo records are impossible to create through the API: ``origin`` defaults
  to ``manual`` and is not a client-settable field.
"""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Dict, List, Optional, Sequence

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.incident import (
    INCIDENT_PRIORITIES,
    Incident,
    IncidentEvent,
    LabContact,
    LabResult,
)
from app.models.user import User
from app.models.water import MonitoringStation, SensorReading
from app.schemas.incident import (
    IncidentCreate,
    LabContactCreate,
    LabResultCreate,
    NotifyLabRequest,
    ResolveIncidentRequest,
    SampleCollectedRequest,
)
from app.services.alert_thresholds import PROFILE_VERSION
from app.services.incident_pdf import render_pdf

logger = logging.getLogger("hydrasense.incidents")

ALLOWED_TRANSITIONS: Dict[str, Sequence[str]] = {
    "raised": ("lab_notified", "resolved"),
    "lab_notified": ("sample_collected", "resolved"),
    "sample_collected": ("result_received", "resolved"),
    "result_received": ("resolved",),
    "resolved": (),
}

_WORKFLOW_ORDER = (
    "raised",
    "lab_notified",
    "sample_collected",
    "result_received",
    "resolved",
)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message}
    )


# --- lab contacts -----------------------------------------------------------


def create_lab_contact(db: Session, payload: LabContactCreate) -> LabContact:
    contact = LabContact(**payload.model_dump())
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


def list_lab_contacts(db: Session, include_inactive: bool = False) -> List[LabContact]:
    query = db.query(LabContact)
    if not include_inactive:
        query = query.filter(LabContact.is_active.is_(True))
    return query.order_by(LabContact.organization.asc(), LabContact.id.asc()).all()


def _get_lab_contact(db: Session, contact_id: int) -> LabContact:
    contact = db.query(LabContact).filter(LabContact.id == contact_id).first()
    if contact is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "lab_contact_not_found",
            "Laboratory contact not found.",
        )
    if not contact.is_active:
        raise _error(
            status.HTTP_409_CONFLICT,
            "lab_contact_inactive",
            "This laboratory contact is inactive; choose an active contact.",
        )
    return contact


# --- incidents --------------------------------------------------------------


def get_station(db: Session, station_code: str) -> MonitoringStation:
    station = (
        db.query(MonitoringStation)
        .filter(MonitoringStation.station_code == station_code)
        .first()
    )
    if station is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "station_not_found",
            f"Monitoring station with code '{station_code}' not found.",
        )
    return station


def create_incident(db: Session, actor: User, payload: IncidentCreate) -> Incident:
    station = get_station(db, payload.station_code)

    reading: Optional[SensorReading] = None
    if payload.reading_id is not None:
        reading = (
            db.query(SensorReading)
            .filter(SensorReading.id == payload.reading_id)
            .first()
        )
        if reading is None:
            raise _error(
                status.HTTP_404_NOT_FOUND,
                "reading_not_found",
                f"Sensor reading with id '{payload.reading_id}' not found.",
            )
        if reading.station_id != station.id:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "reading_station_mismatch",
                "The triggering reading does not belong to this station.",
            )

    if payload.priority not in INCIDENT_PRIORITIES:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_priority",
            "priority must be low, medium, high or critical.",
        )

    incident = Incident(
        station_id=station.id,
        reading_id=reading.id if reading else None,
        title=payload.title.strip(),
        summary=payload.summary.strip(),
        priority=payload.priority,
        status="raised",
        origin="manual",
        alert_reason=payload.alert_reason.strip() if payload.alert_reason else None,
        explanation=payload.explanation.strip() if payload.explanation else None,
        explanation_source="authority_manual" if payload.explanation else "none",
        time_window_start=payload.time_window_start,
        time_window_end=payload.time_window_end,
        raised_by_id=actor.id,
        raised_at=datetime.now(timezone.utc),
        lab_notification_status="not_notified",
    )
    db.add(incident)
    db.flush()  # assign the id used for the human-facing reference
    incident.reference = f"INC-{incident.id:06d}"

    db.add(
        IncidentEvent(
            incident_id=incident.id,
            from_status=None,
            to_status="raised",
            note="Incident raised by an authorised authority user.",
            actor_id=actor.id,
            created_at=incident.raised_at,
        )
    )
    db.commit()
    db.refresh(incident)
    return incident


def get_incident(db: Session, incident_id: int) -> Incident:
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if incident is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "incident_not_found",
            f"Incident with id '{incident_id}' not found.",
        )
    return incident


def list_incidents(
    db: Session,
    *,
    status_filter: Optional[str] = None,
    station_code: Optional[str] = None,
    limit: int = 50,
) -> List[Incident]:
    query = db.query(Incident)
    if status_filter:
        if status_filter not in _WORKFLOW_ORDER:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "invalid_status",
                "status must be one of: " + ", ".join(_WORKFLOW_ORDER),
            )
        query = query.filter(Incident.status == status_filter)
    if station_code:
        station = (
            db.query(MonitoringStation)
            .filter(MonitoringStation.station_code == station_code)
            .first()
        )
        if station is None:
            raise _error(
                status.HTTP_404_NOT_FOUND,
                "station_not_found",
                f"Monitoring station with code '{station_code}' not found.",
            )
        query = query.filter(Incident.station_id == station.id)
    return (
        query.order_by(Incident.raised_at.desc(), Incident.id.desc())
        .limit(limit)
        .all()
    )


def allowed_transitions(incident_status: str) -> List[str]:
    return [step for step in ALLOWED_TRANSITIONS.get(incident_status, ())]


def _transition(
    db: Session,
    incident: Incident,
    actor: User,
    to_status: str,
    *,
    note: Optional[str] = None,
    at: Optional[datetime] = None,
) -> None:
    current = incident.status
    if to_status not in ALLOWED_TRANSITIONS.get(current, ()):
        raise _error(
            status.HTTP_409_CONFLICT,
            "invalid_transition",
            f"Cannot move an incident from '{current}' to '{to_status}'. "
            f"Allowed: {', '.join(allowed_transitions(current)) or 'none'}.",
        )
    incident.status = to_status
    db.add(
        IncidentEvent(
            incident_id=incident.id,
            from_status=current,
            to_status=to_status,
            note=note,
            actor_id=actor.id,
            created_at=at or datetime.now(timezone.utc),
        )
    )


def _compose_report_email(
    contact: LabContact,
    incident: Incident,
    station: MonitoringStation,
    pdf: bytes,
    note: Optional[str] = None,
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = (
        f"[HydraSense] Lab request {incident.reference or incident.id}: "
        f"{station.station_code} — {incident.title}"
    )
    message["From"] = settings.SMTP_FROM
    message["To"] = contact.email
    lines = [
        f"Dear {contact.name},",
        "",
        "A water-quality incident has been raised and this laboratory is "
        "requested to perform confirmatory analysis.",
        "",
        f"Incident: {incident.reference or incident.id}",
        f"Station: {station.station_code} — {station.station_name}",
        f"Priority: {incident.priority}",
        f"Sample reference: {incident.sample_id or 'not yet collected'}",
        "",
        "The attached PDF contains the stored sensor readings, the alert "
        "reason and the current workflow timeline. The four hardware "
        "sensors measure pH, TDS, temperature and a relative turbidity "
        "index only; nothing in the report is a laboratory measurement.",
        "",
        "This is a preliminary screening report, not a safety certification.",
        "",
    ]
    if note and note.strip():
        lines.extend(
            [
                "Message from the reporting authority:",
                note.strip(),
                "",
            ]
        )
    lines.append("HydraSense")
    message.set_content("\n".join(lines))
    message.add_attachment(
        pdf, maintype="application", subtype="pdf",
        filename=f"{incident.reference or 'incident'}-report.pdf",
    )
    return message


def _deliver_report_email(
    contact: LabContact,
    incident: Incident,
    station: MonitoringStation,
    pdf: bytes,
    note: Optional[str] = None,
) -> str:
    """Return the honest delivery outcome; never raise into the workflow."""

    if not settings.SMTP_HOST:
        return "smtp_unconfigured"
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(
                _compose_report_email(contact, incident, station, pdf, note=note)
            )
        return "sent"
    except Exception as exc:  # noqa: BLE001 - delivery must never break the workflow
        logger.warning("Lab notification email failed: %s", type(exc).__name__)
        return "failed"


def notify_lab(
    db: Session, actor: User, incident: Incident, payload: NotifyLabRequest
) -> str:
    """Record the lab notification, deliver the report when possible.

    Returns the delivery outcome (``sent`` / ``smtp_unconfigured`` / ``failed``).
    """

    if incident.status not in ("raised", "lab_notified"):
        raise _error(
            status.HTTP_409_CONFLICT,
            "invalid_transition",
            "A laboratory can only be notified while the incident is "
            "'raised' or 'lab_notified'.",
        )
    contact = _get_lab_contact(db, payload.lab_contact_id)
    station = get_station(db, incident.station.station_code)

    now = datetime.now(timezone.utc)
    pdf = build_incident_report_pdf(db, incident)
    outcome = _deliver_report_email(
        contact, incident, station, pdf, note=payload.note
    )

    incident.lab_contact_id = contact.id
    incident.lab_notification_status = outcome
    incident.lab_notified_at = now if outcome == "sent" else None
    incident.sample_id = incident.sample_id or None

    notes = [
        f"Laboratory '{contact.organization}' recorded for notification.",
        f"Report delivery: {outcome}.",
    ]
    if payload.note:
        notes.append(payload.note.strip())
    if outcome == "smtp_unconfigured":
        notes.append(
            "Email is not configured on this server; deliver the generated "
            "report manually."
        )
    if incident.status == "raised":
        _transition(
            db, incident, actor, "lab_notified",
            note=" ".join(notes), at=now,
        )
    else:
        # Already lab_notified: this is a re-send (typically after a failed
        # delivery). Keep the status and log the attempt in the audit trail.
        db.add(
            IncidentEvent(
                incident_id=incident.id,
                from_status="lab_notified",
                to_status="lab_notified",
                note="Re-notification: " + " ".join(notes),
                actor_id=actor.id,
                created_at=now,
            )
        )
    db.commit()
    db.refresh(incident)
    return outcome


def record_sample(
    db: Session, actor: User, incident: Incident, payload: SampleCollectedRequest
) -> Incident:
    if incident.status != "lab_notified":
        raise _error(
            status.HTTP_409_CONFLICT,
            "invalid_transition",
            "A sample can only be recorded after the laboratory has been notified.",
        )

    collected_at = _as_utc(payload.collected_at) if payload.collected_at else datetime.now(
        timezone.utc
    )
    if collected_at > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "future_timestamp",
            "collected_at cannot be in the future.",
        )

    incident.sample_id = payload.sample_id
    incident.sample_collected_at = collected_at
    notes = [f"Sample '{payload.sample_id}' recorded as collected."]
    if payload.note:
        notes.append(payload.note.strip())
    _transition(
        db, incident, actor, "sample_collected", note=" ".join(notes), at=collected_at
    )
    db.commit()
    db.refresh(incident)
    return incident


def record_result(
    db: Session, actor: User, incident: Incident, payload: LabResultCreate
) -> LabResult:
    if incident.status != "sample_collected":
        raise _error(
            status.HTTP_409_CONFLICT,
            "invalid_transition",
            "A laboratory result can only be recorded after a sample was collected.",
        )

    expected = (incident.sample_id or "").strip().upper()
    if expected and payload.sample_id.strip().upper() != expected:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "sample_mismatch",
            "The result's sample_id does not match the sample recorded on the "
            "incident.",
        )

    now = datetime.now(timezone.utc)
    reported_at = _as_utc(payload.reported_at) if payload.reported_at else now
    if reported_at > now + timedelta(minutes=5):
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "future_timestamp",
            "reported_at cannot be in the future.",
        )

    # Values are stored verbatim; provenance is fixed and never derived from
    # the four hardware sensors.
    entries = []
    for entry in payload.results:
        stored = entry.model_dump()
        stored["source"] = "laboratory"
        stored["derived_from_sensors"] = False
        entries.append(stored)

    result = LabResult(
        incident_id=incident.id,
        lab_contact_id=incident.lab_contact_id,
        received_by_id=actor.id,
        sample_id=payload.sample_id.strip(),
        reported_at=reported_at,
        summary=payload.summary.strip() if payload.summary else None,
        results=entries,
        document_reference=payload.document_reference,
    )
    db.add(result)

    incident.result_received_at = now
    _transition(
        db,
        incident,
        actor,
        "result_received",
        note=(
            f"Laboratory result received for sample '{payload.sample_id.strip()}' "
            f"({len(entries)} reported measurement(s)); values entered by an "
            "authorised user, not derived from the sensors."
        ),
        at=now,
    )
    db.commit()
    db.refresh(result)
    db.refresh(incident)
    return result


def resolve_incident(
    db: Session, actor: User, incident: Incident, payload: ResolveIncidentRequest
) -> Incident:
    if incident.status not in ALLOWED_TRANSITIONS or incident.status == "resolved":
        raise _error(
            status.HTTP_409_CONFLICT,
            "invalid_transition",
            "This incident is already resolved.",
        )
    if incident.status != "result_received":
        # Closing before a laboratory result is allowed, but the audit trail
        # must say so explicitly.
        note = (
            "Incident resolved before a laboratory result was received. "
            f"Reason: {payload.resolution_summary.strip()}"
        )
    else:
        note = f"Incident resolved: {payload.resolution_summary.strip()}"

    now = datetime.now(timezone.utc)
    incident.resolution_summary = payload.resolution_summary.strip()
    incident.resolved_at = now
    _transition(db, incident, actor, "resolved", note=note, at=now)
    db.commit()
    db.refresh(incident)
    return incident


# --- serialisation ----------------------------------------------------------


def _reading_snapshot(reading: SensorReading) -> Dict[str, Any]:
    return {
        "id": reading.id,
        "timestamp": reading.timestamp,
        "ph": reading.ph,
        "tds": reading.tds,
        "temperature": reading.temperature,
        "turbidity": reading.turbidity,
        "turbidity_unit": reading.turbidity_unit,
        "turbidity_index": reading.turbidity_index,
        "turbidity_status": reading.turbidity_status,
        "source": reading.source,
        "simulated": reading.source != "esp32",
    }


def readings_for_incident(
    db: Session, incident: Incident, limit: int = 50
) -> List[SensorReading]:
    if incident.time_window_start and incident.time_window_end:
        start = _as_utc(incident.time_window_start)
        end = _as_utc(incident.time_window_end)
        return (
            db.query(SensorReading)
            .filter(
                SensorReading.station_id == incident.station_id,
                SensorReading.timestamp >= start,
                SensorReading.timestamp <= end,
            )
            .order_by(SensorReading.timestamp.asc(), SensorReading.id.asc())
            .limit(limit)
            .all()
        )
    if incident.reading_id is not None:
        reading = (
            db.query(SensorReading)
            .filter(SensorReading.id == incident.reading_id)
            .first()
        )
        return [reading] if reading is not None else []
    return []


def _lab_result_payload(result: LabResult) -> Dict[str, Any]:
    entries = result.results if isinstance(result.results, list) else []
    return {
        "id": result.id,
        "sample_id": result.sample_id,
        "reported_at": result.reported_at,
        "summary": result.summary,
        "results": entries,
        "document_reference": result.document_reference,
        "received_by_id": result.received_by_id,
        "created_at": result.created_at,
        "source": "laboratory",
        "derived_from_sensors": False,
    }


def serialize_incident(db: Session, incident: Incident) -> Dict[str, Any]:
    station = (
        db.query(MonitoringStation)
        .filter(MonitoringStation.id == incident.station_id)
        .first()
    )
    contact = (
        db.query(LabContact).filter(LabContact.id == incident.lab_contact_id).first()
        if incident.lab_contact_id
        else None
    )
    events = sorted(
        incident.events, key=lambda event: (_as_utc(event.created_at), event.id)
    )
    readings = readings_for_incident(db, incident)

    return {
        "id": incident.id,
        "reference": incident.reference,
        "station_code": station.station_code if station else "",
        "station_name": station.station_name if station else "",
        "title": incident.title,
        "summary": incident.summary,
        "priority": incident.priority,
        "status": incident.status,
        "origin": incident.origin,
        "is_demo": incident.origin == "demo",
        "alert_reason": incident.alert_reason,
        "explanation": incident.explanation,
        "explanation_source": incident.explanation_source,
        "time_window_start": incident.time_window_start,
        "time_window_end": incident.time_window_end,
        "raised_by_id": incident.raised_by_id,
        "raised_at": incident.raised_at,
        "lab_contact": {
            "id": contact.id,
            "name": contact.name,
            "organization": contact.organization,
            "email": contact.email,
            "phone": contact.phone,
            "address": contact.address,
            "accreditation": contact.accreditation,
            "is_active": contact.is_active,
            "created_at": contact.created_at,
        } if contact else None,
        "lab_notification_status": incident.lab_notification_status,
        "lab_notified_at": incident.lab_notified_at,
        "sample_id": incident.sample_id,
        "sample_collected_at": incident.sample_collected_at,
        "result_received_at": incident.result_received_at,
        "resolved_at": incident.resolved_at,
        "resolution_summary": incident.resolution_summary,
        "allowed_transitions": allowed_transitions(incident.status),
        "events": [
            {
                "id": event.id,
                "from_status": event.from_status,
                "to_status": event.to_status,
                "note": event.note,
                "actor_id": event.actor_id,
                "created_at": event.created_at,
            }
            for event in events
        ],
        "lab_results": [_lab_result_payload(result) for result in incident.lab_results],
        "readings": [_reading_snapshot(reading) for reading in readings],
        "threshold_profile_version": PROFILE_VERSION,
    }


def serialize_list_item(db: Session, incident: Incident) -> Dict[str, Any]:
    station = (
        db.query(MonitoringStation)
        .filter(MonitoringStation.id == incident.station_id)
        .first()
    )
    return {
        "id": incident.id,
        "reference": incident.reference,
        "station_code": station.station_code if station else "",
        "station_name": station.station_name if station else "",
        "title": incident.title,
        "priority": incident.priority,
        "status": incident.status,
        "origin": incident.origin,
        "is_demo": incident.origin == "demo",
        "raised_at": incident.raised_at,
        "lab_notification_status": incident.lab_notification_status,
    }


# --- report -----------------------------------------------------------------


def _format_value(value: Optional[float], unit: str) -> str:
    if value is None:
        return "no reading"
    return f"{value:g} {unit}".strip()


def _reading_line(reading: SensorReading) -> str:
    turbidity_unit = reading.turbidity_unit or "unit unknown"
    if reading.turbidity_unit == "relative_index_0_100" or reading.turbidity_index is not None:
        turbidity = (
            f"{_format_value(reading.turbidity_index, '')} "
            "(relative index 0-100, NOT NTU)"
        )
    else:
        turbidity = f"{_format_value(reading.turbidity, '')} ({turbidity_unit}, not validated NTU)"

    return (
        f"{_as_utc(reading.timestamp).strftime('%Y-%m-%d %H:%M UTC')} | "
        f"pH {_format_value(reading.ph, 'pH')} | "
        f"TDS {_format_value(reading.tds, 'mg/L')} | "
        f"Temp {_format_value(reading.temperature, '°C')} | "
        f"Turbidity {turbidity} | "
        f"source {reading.source}, id {reading.id}"
    )


def build_incident_report_pdf(db: Session, incident: Incident) -> bytes:
    station = (
        db.query(MonitoringStation)
        .filter(MonitoringStation.id == incident.station_id)
        .first()
    )
    contact = (
        db.query(LabContact).filter(LabContact.id == incident.lab_contact_id).first()
        if incident.lab_contact_id
        else None
    )
    readings = readings_for_incident(db, incident)

    paragraphs: List[tuple[str, str]] = []
    paragraphs.append(("HydraSense — Water Quality Incident Report", "title"))
    paragraphs.append(
        (f"Incident reference: {incident.reference or incident.id}", "heading")
    )
    paragraphs.append(
        (
            f"Status: {incident.status}    Priority: {incident.priority}    "
            f"Raised: {_as_utc(incident.raised_at).strftime('%Y-%m-%d %H:%M UTC')}",
            "body",
        )
    )
    paragraphs.append(
        (
            f"Station: {(station.station_code + ' — ' + station.station_name) if station else 'unknown'}",
            "body",
        )
    )
    paragraphs.append((f"Title: {incident.title}", "heading"))
    paragraphs.append((incident.summary, "body"))
    paragraphs.append(("Alert reason", "heading"))
    paragraphs.append((incident.alert_reason or "No alert reason was recorded.", "body"))
    paragraphs.append(("Explanation", "heading"))
    paragraphs.append(
        (
            incident.explanation or "No explanation was recorded for this incident.",
            "body",
        )
    )
    paragraphs.append(
        (
            "Explanation provenance: "
            + (
                "entered manually by an authorised authority user"
                if incident.explanation_source == "authority_manual"
                else "no explanation recorded; automated explanations are not generated by this system"
            ),
            "small",
        )
    )

    window = "not specified"
    if incident.time_window_start and incident.time_window_end:
        window = "%s to %s" % (
            _as_utc(incident.time_window_start).strftime("%Y-%m-%d %H:%M UTC"),
            _as_utc(incident.time_window_end).strftime("%Y-%m-%d %H:%M UTC"),
        )
    paragraphs.append((f"Measurement window: {window}", "body"))

    paragraphs.append(("Stored sensor readings in this window", "heading"))
    paragraphs.append(
        (
            "Only pH, TDS, temperature and a relative turbidity index are measured. "
            "The turbidity index is on a project-defined 0-100 scale and is not NTU.",
            "small",
        )
    )
    if readings:
        for reading in readings:
            paragraphs.append((_reading_line(reading), "small"))
    else:
        paragraphs.append(
            ("No stored readings fall inside this incident's window.", "body")
        )

    paragraphs.append(("Laboratory", "heading"))
    if contact:
        paragraphs.append(
            (
                f"{contact.name} — {contact.organization} | {contact.email}"
                + (f" | {contact.phone}" if contact.phone else ""),
                "body",
            )
        )
        if contact.accreditation:
            paragraphs.append(
                (f"Accreditation/reference: {contact.accreditation}", "small")
            )
    else:
        paragraphs.append(("No laboratory contact is associated yet.", "body"))
    paragraphs.append(
        (
            f"Notification status: {incident.lab_notification_status} | "
            f"Notified: "
            + (
                _as_utc(incident.lab_notified_at).strftime("%Y-%m-%d %H:%M UTC")
                if incident.lab_notified_at
                else "not delivered"
            ),
            "body",
        )
    )
    paragraphs.append((f"Sample reference: {incident.sample_id or 'not collected'}", "body"))
    if incident.sample_collected_at:
        paragraphs.append(
            (
                "Sample collected: "
                + _as_utc(incident.sample_collected_at).strftime("%Y-%m-%d %H:%M UTC"),
                "body",
            )
        )

    paragraphs.append(("Laboratory results (entered verbatim)", "heading"))
    if incident.lab_results:
        for result in incident.lab_results:
            paragraphs.append(
                (
                    f"Result {result.id} | sample {result.sample_id} | reported "
                    + (
                        _as_utc(result.reported_at).strftime("%Y-%m-%d %H:%M UTC")
                        if result.reported_at
                        else "date not recorded"
                    ),
                    "body",
                )
            )
            if result.summary:
                paragraphs.append((result.summary, "small"))
            entries = result.results if isinstance(result.results, list) else []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                paragraphs.append(
                    (
                        "  • %s: %s %s%s%s"
                        % (
                            entry.get("parameter", "parameter"),
                            entry.get("value", ""),
                            entry.get("unit", ""),
                            f" | method {entry['method']}" if entry.get("method") else "",
                            f" | reference {entry['reference']}"
                            if entry.get("reference")
                            else "",
                        ),
                        "small",
                    )
                )
    else:
        paragraphs.append(
            ("No laboratory results have been recorded for this incident.", "body")
        )

    paragraphs.append(("Workflow timeline", "heading"))
    for event in sorted(
        incident.events, key=lambda item: (_as_utc(item.created_at), item.id)
    ):
        paragraphs.append(
            (
                "%s | %s -> %s | %s"
                % (
                    _as_utc(event.created_at).strftime("%Y-%m-%d %H:%M UTC"),
                    event.from_status or "start",
                    event.to_status,
                    event.note or "no note",
                ),
                "small",
            )
        )

    paragraphs.append(("Limitations", "heading"))
    paragraphs.append(
        (
            "HydraSense measures four parameters only: pH, TDS, temperature and a "
            "relative turbidity index from an uncalibrated analog sensor. This "
            "report is a preliminary screening of stored readings, not a "
            "laboratory safety certification. Laboratory results are entered by "
            "an authorised user from the laboratory's own report and are never "
            "derived from the four hardware sensors. Microbiological, heavy-metal "
            "and other chemical hazards are not measured by this hardware.",
            "body",
        )
    )
    paragraphs.append(
        (f"Threshold/screening profile version: {PROFILE_VERSION}", "small")
    )

    return render_pdf(
        paragraphs,
        title=f"{incident.reference or 'Incident'} — HydraSense incident report",
        footer=(
            "HydraSense — preliminary screening, not a laboratory safety "
            "certification."
        ),
    )
