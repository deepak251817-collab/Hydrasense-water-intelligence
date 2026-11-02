"""Schemas for the product-user water-test workflow."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.recommendations import RecommendationSet

WaterSourceCode = Literal["tap", "borewell", "well", "tank", "surface", "other"]
IntendedUseCode = Literal["drinking", "domestic", "irrigation", "general"]
ReadingMode = Literal["live", "demo"]


class ProductWaterTestCreate(BaseModel):
    water_source: WaterSourceCode
    intended_use: IntendedUseCode
    reading_mode: ReadingMode = "live"


class ActivateProductRequest(BaseModel):
    product_code: str = Field(min_length=3, max_length=100)

    @field_validator("product_code")
    @classmethod
    def strip_code(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("Product code is required")
        return cleaned


class ReadingAssessment(BaseModel):
    parameter: str
    label: str
    value: Optional[float] = None
    unit: str = ""
    status: str
    status_label: str
    reference: str
    note: Optional[str] = None


class ReasonDetail(BaseModel):
    parameter: str
    label: str
    value: Optional[float] = None
    unit: str = ""
    status: str
    status_label: str
    reference: str
    reason: str
    calibration_limitation: Optional[str] = None
    next_step: str


class OverallAssessment(BaseModel):
    status: str
    # Canonical four-state vocabulary (within_configured_ranges | caution |
    # outside_configured_ranges | insufficient_data) from the central
    # suitability engine; null for assessments stored before it existed.
    state: Optional[str] = None
    state_label: Optional[str] = None
    label: str
    summary: str
    reasons: List[str]
    reason_details: List[ReasonDetail] = []


class AttentionItem(BaseModel):
    parameter: str
    label: str
    value: Optional[float] = None
    unit: str = ""
    status: str
    status_label: str
    message: str


class SuitabilityCriterion(BaseModel):
    parameter: str
    label: str
    value: Optional[float] = None
    unit: str = ""
    status: str
    status_label: str
    reference: str
    note: Optional[str] = None


class SuitabilityAssessment(BaseModel):
    use: str
    use_label: str
    description: str
    standard_code: str
    standard: str
    criteria_version: str
    result: str
    result_label: str
    summary: str
    criteria_available: bool = True
    criteria: List[SuitabilityCriterion]
    limitations: List[str]
    reference_profile: Dict[str, Any] = {}


class DataQuality(BaseModel):
    demo_mode: bool
    reading_mode: str
    freshness: str
    age_seconds: Optional[float] = None
    calibration_status: str
    calibration_verified: bool = False
    stability: Optional[Dict[str, Any]] = None
    errors: List[str] = []
    warnings: List[str] = []


class PredictionStatus(BaseModel):
    available: bool
    message: str
    model_version: Optional[str] = None
    horizon_minutes: Optional[int] = None


class ProductTestAssessment(BaseModel):
    criteria_version: str
    intended_use: str
    intended_use_label: str
    reading_mode: str
    reading_timestamp: Optional[datetime] = None
    readings: Dict[str, ReadingAssessment]
    # Declared engine contract (accepted inputs, exclusions, data source).
    engine: Optional[Dict[str, Any]] = None
    overall: OverallAssessment
    attention: List[AttentionItem]
    suitability: SuitabilityAssessment
    data_quality: DataQuality
    next_steps: List[str]
    prediction: PredictionStatus
    reference_profile: Dict[str, Any] = {}
    # Rule-based advice derived from the triggered rules; empty when the result
    # is within the configured ranges. Older stored assessments without the key
    # simply default to an empty set.
    recommendations: RecommendationSet = RecommendationSet()


class ProductWaterTestResponse(BaseModel):
    id: int
    test_code: str
    water_source: str
    water_source_label: str
    intended_use: str
    intended_use_label: str
    reading_mode: str
    reading_source: str
    device_id: str
    device_name: str
    ph: Optional[float] = None
    tds: Optional[float] = None
    turbidity: Optional[float] = None
    turbidity_unit: Optional[str] = None
    temperature: Optional[float] = None
    reading_timestamp: Optional[datetime] = None
    created_at: datetime
    overall_status: str
    overall_state: Optional[str] = None
    overall_label: str
    criteria_version: str
    assessment: ProductTestAssessment


class ProductWaterTestSummary(BaseModel):
    id: int
    test_code: str
    water_source: str
    water_source_label: str
    intended_use: str
    intended_use_label: str
    reading_mode: str
    overall_status: str
    overall_state: Optional[str] = None
    overall_label: str
    ph: Optional[float] = None
    tds: Optional[float] = None
    turbidity: Optional[float] = None
    turbidity_unit: Optional[str] = None
    temperature: Optional[float] = None
    reading_timestamp: Optional[datetime] = None
    created_at: datetime


class ProductWaterTestList(BaseModel):
    total: int
    items: List[ProductWaterTestSummary]


class DeviceReading(BaseModel):
    ph: Optional[float] = None
    turbidity: Optional[float] = None
    turbidity_unit: Optional[str] = None
    turbidity_status: Optional[str] = None
    tds: Optional[float] = None
    temperature: Optional[float] = None
    timestamp: datetime
    source: str
    calibration: Dict[str, str] = {}


class ProductDeviceStatus(BaseModel):
    device_id: str
    device_name: str
    product_code: str
    status: str
    connected: bool
    last_seen: Optional[datetime] = None
    reading_age_seconds: Optional[float] = None
    reading: Optional[DeviceReading] = None
    note: str


class ProductDeviceSummary(BaseModel):
    id: int
    product_code: str
    device_id: str
    device_number: Optional[str] = None
    station_code: Optional[str] = None
    device_type: str
    device_name: str
    status: str
    owner_id: Optional[int] = None
    activated_at: Optional[datetime] = None
    created_at: datetime


class ProductOverview(BaseModel):
    total_tests: int
    latest_test: Optional[ProductWaterTestSummary] = None
    recent_tests: List[ProductWaterTestSummary] = []
    device: Optional[ProductDeviceStatus] = None


class ProductLiveReadingResponse(BaseModel):
    available: bool
    mode: Literal["live", "demo"]
    reading: DeviceReading
    calibration: Dict[str, str] = {}
    warnings: List[str] = []
    info: Dict[str, Any] = {}


class LiveLatestReading(BaseModel):
    reading_id: Optional[int] = None
    timestamp: Optional[datetime] = None
    ph: Optional[float] = None
    tds: Optional[float] = None
    turbidity: Optional[float] = None
    turbidity_unit: Optional[str] = None
    turbidity_status: Optional[str] = None
    temperature: Optional[float] = None
    source: Optional[str] = None


class LiveAssessmentResponse(BaseModel):
    station_code: str
    station_name: str
    water_source_name: str
    device_id: Optional[str] = None
    device_name: str = "HydraSense station"
    connection: Literal["connected", "connecting", "offline", "error", "no_data"]
    connection_label: str
    last_received: Optional[datetime] = None
    live: bool
    poll_interval_seconds: int
    stability: Dict[str, Any]
    latest: Optional[LiveLatestReading] = None
    assessment: ProductTestAssessment
    test_id: Optional[str] = None
    assessment_id: Optional[int] = None
    assessment_persisted: bool = False
    criteria_version: str
