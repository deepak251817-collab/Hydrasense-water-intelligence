"""Request/response schemas for incidents, lab contacts and lab results."""

from datetime import datetime
from math import isfinite
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, EmailStr, field_validator, model_validator

IncidentPriority = Literal["low", "medium", "high", "critical"]
IncidentStatus = Literal[
    "raised", "lab_notified", "sample_collected", "result_received", "resolved"
]


class LabContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    organization: str = Field(min_length=1, max_length=255)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=60)
    address: Optional[str] = Field(default=None, max_length=2000)
    accreditation: Optional[str] = Field(default=None, max_length=120)


class LabContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    organization: str
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None
    accreditation: Optional[str] = None
    is_active: bool
    created_at: datetime


class IncidentCreate(BaseModel):
    station_code: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=5000)
    priority: IncidentPriority = "medium"
    # Optional stored reading that triggered the incident.
    reading_id: Optional[int] = Field(default=None, gt=0)
    alert_reason: Optional[str] = Field(default=None, max_length=5000)
    # Free text the authority wants recorded. ``explanation_source`` in the
    # response states that this text was entered manually.
    explanation: Optional[str] = Field(default=None, max_length=5000)
    time_window_start: Optional[datetime] = None
    time_window_end: Optional[datetime] = None

    @model_validator(mode="after")
    def _window_is_ordered(self):
        if (
            self.time_window_start is not None
            and self.time_window_end is not None
            and self.time_window_end < self.time_window_start
        ):
            raise ValueError("time_window_end must not be before time_window_start")
        return self


class NotifyLabRequest(BaseModel):
    lab_contact_id: int = Field(gt=0)
    note: Optional[str] = Field(default=None, max_length=2000)


class SampleCollectedRequest(BaseModel):
    sample_id: str = Field(min_length=1, max_length=120)
    collected_at: Optional[datetime] = None
    note: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("sample_id")
    @classmethod
    def _sample_id_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("sample_id must not be blank")
        return value


class LabResultEntry(BaseModel):
    """One laboratory measurement, as reported by the laboratory.

    Values are recorded verbatim. They must not be produced from the four
    hardware sensors (pH, TDS, temperature, relative turbidity index); the
    service forces ``source = "laboratory"`` for every entry.
    """

    parameter: str = Field(min_length=1, max_length=80)
    value: float
    unit: str = Field(min_length=1, max_length=30)
    method: Optional[str] = Field(default=None, max_length=120)
    reference: Optional[str] = Field(default=None, max_length=200)
    detection_limit: Optional[str] = Field(default=None, max_length=60)
    note: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("value")
    @classmethod
    def _value_is_finite(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("lab result values must be finite numbers")
        return value


class LabResultCreate(BaseModel):
    sample_id: str = Field(min_length=1, max_length=120)
    summary: Optional[str] = Field(default=None, max_length=5000)
    reported_at: Optional[datetime] = None
    document_reference: Optional[str] = Field(default=None, max_length=255)
    results: List[LabResultEntry] = Field(min_length=1, max_length=200)

    @field_validator("sample_id")
    @classmethod
    def _sample_id_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("sample_id must not be blank")
        return value


class ResolveIncidentRequest(BaseModel):
    resolution_summary: str = Field(min_length=1, max_length=5000)


class IncidentEventResponse(BaseModel):
    id: int
    from_status: Optional[str] = None
    to_status: str
    note: Optional[str] = None
    actor_id: Optional[int] = None
    created_at: datetime


class LabResultResponse(BaseModel):
    id: int
    sample_id: str
    reported_at: Optional[datetime] = None
    summary: Optional[str] = None
    results: List[dict] = []
    document_reference: Optional[str] = None
    received_by_id: Optional[int] = None
    created_at: datetime
    # Fixed provenance: laboratory values are entered by an authorised user
    # and are never derived from the four hardware sensors.
    source: Literal["laboratory"] = "laboratory"
    derived_from_sensors: bool = False


class IncidentReadingSnapshot(BaseModel):
    id: int
    timestamp: datetime
    ph: Optional[float] = None
    tds: Optional[float] = None
    temperature: Optional[float] = None
    turbidity: Optional[float] = None
    turbidity_unit: Optional[str] = None
    turbidity_index: Optional[float] = None
    turbidity_status: Optional[str] = None
    source: Optional[str] = None
    simulated: bool = False


class IncidentListItem(BaseModel):
    id: int
    reference: Optional[str] = None
    station_code: str
    station_name: str
    title: str
    priority: str
    status: str
    origin: str
    is_demo: bool
    raised_at: datetime
    lab_notification_status: str


class IncidentResponse(BaseModel):
    id: int
    reference: Optional[str] = None
    station_code: str
    station_name: str
    title: str
    summary: str
    priority: str
    status: str
    origin: str
    is_demo: bool
    alert_reason: Optional[str] = None
    explanation: Optional[str] = None
    explanation_source: str
    time_window_start: Optional[datetime] = None
    time_window_end: Optional[datetime] = None
    raised_by_id: Optional[int] = None
    raised_at: datetime
    lab_contact: Optional[LabContactResponse] = None
    lab_notification_status: str
    lab_notified_at: Optional[datetime] = None
    sample_id: Optional[str] = None
    sample_collected_at: Optional[datetime] = None
    result_received_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolution_summary: Optional[str] = None
    allowed_transitions: List[str] = []
    events: List[IncidentEventResponse] = []
    lab_results: List[LabResultResponse] = []
    readings: List[IncidentReadingSnapshot] = []
    # The active screening profile the triggering readings were judged with;
    # empty when the incident has no linked reading.
    threshold_profile_version: Optional[str] = None
