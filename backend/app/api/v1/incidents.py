"""Authority-only incident, laboratory and report endpoints.

RBAC is enforced on the backend for every route: only an active AUTHORITY
account can read or write incidents, lab contacts or lab results. Public
routes never expose these records.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_authority
from app.core.database import get_db
from app.models.user import User
from app.schemas.incident import (
    IncidentCreate,
    IncidentListItem,
    IncidentResponse,
    LabContactCreate,
    LabContactResponse,
    LabResultCreate,
    NotifyLabRequest,
    ResolveIncidentRequest,
    SampleCollectedRequest,
)
from app.services import incident_service

router = APIRouter(prefix="/authority", tags=["Authority Incidents"])


@router.get("/lab-contacts", response_model=List[LabContactResponse])
def list_lab_contacts(
    include_inactive: bool = Query(False),
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    return incident_service.list_lab_contacts(db, include_inactive=include_inactive)


@router.post(
    "/lab-contacts",
    response_model=LabContactResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_lab_contact(
    payload: LabContactCreate,
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    return incident_service.create_lab_contact(db, payload)


@router.get("/incidents", response_model=List[IncidentListItem])
def list_incidents(
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="raised | lab_notified | sample_collected | result_received | resolved",
    ),
    station_code: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    incidents = incident_service.list_incidents(
        db, status_filter=status_filter, station_code=station_code, limit=limit
    )
    return [incident_service.serialize_list_item(db, row) for row in incidents]


@router.post(
    "/incidents", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED
)
def create_incident(
    payload: IncidentCreate,
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    """Raise an incident for a station (optionally linked to a stored reading)."""

    incident = incident_service.create_incident(db, current_user, payload)
    return incident_service.serialize_incident(db, incident)


@router.get("/incidents/{incident_id}", response_model=IncidentResponse)
def get_incident(
    incident_id: int,
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    incident = incident_service.get_incident(db, incident_id)
    return incident_service.serialize_incident(db, incident)


@router.post("/incidents/{incident_id}/notify-lab", response_model=IncidentResponse)
def notify_lab(
    incident_id: int,
    payload: NotifyLabRequest,
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    """Record the lab notification and email the PDF report when SMTP is set."""

    incident = incident_service.get_incident(db, incident_id)
    incident_service.notify_lab(db, current_user, incident, payload)
    return incident_service.serialize_incident(db, incident)


@router.post(
    "/incidents/{incident_id}/sample-collected", response_model=IncidentResponse
)
def record_sample_collected(
    incident_id: int,
    payload: SampleCollectedRequest,
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    incident = incident_service.get_incident(db, incident_id)
    incident_service.record_sample(db, current_user, incident, payload)
    return incident_service.serialize_incident(db, incident)


@router.post("/incidents/{incident_id}/lab-result", response_model=IncidentResponse)
def record_lab_result(
    incident_id: int,
    payload: LabResultCreate,
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    """Store a laboratory report entered verbatim by an authorised user."""

    incident = incident_service.get_incident(db, incident_id)
    incident_service.record_result(db, current_user, incident, payload)
    return incident_service.serialize_incident(db, incident)


@router.post("/incidents/{incident_id}/resolve", response_model=IncidentResponse)
def resolve_incident(
    incident_id: int,
    payload: ResolveIncidentRequest,
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    incident = incident_service.get_incident(db, incident_id)
    incident_service.resolve_incident(db, current_user, incident, payload)
    return incident_service.serialize_incident(db, incident)


@router.get("/incidents/{incident_id}/report.pdf")
def download_incident_report(
    incident_id: int,
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    """Generated PDF report of the stored incident record."""

    incident = incident_service.get_incident(db, incident_id)
    pdf = incident_service.build_incident_report_pdf(db, incident)
    filename = f"{incident.reference or ('incident-' + str(incident.id))}-report.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
