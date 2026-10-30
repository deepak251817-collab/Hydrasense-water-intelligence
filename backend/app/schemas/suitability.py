"""Schemas for the standards-based Water Suitability Assessment."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.recommendations import RecommendationSet


class SuitabilityParameter(BaseModel):
    parameter: str
    label: str
    unit: str = ""
    value: Optional[float] = None
    status: str
    status_label: str
    reference: str
    critical: bool = True
    note: Optional[str] = None


class SuitabilityMissingParameter(BaseModel):
    parameter: str
    label: str
    why: str
    required_by: str


class SuitabilityMeasuredValue(BaseModel):
    parameter: str
    label: str
    value: float
    unit: str = ""
    source: str


class SuitabilityExcludedParameter(BaseModel):
    parameter: str
    reason: Optional[str] = None


class SuitabilityDataQuality(BaseModel):
    freshness: str
    age_seconds: Optional[int] = None
    reading_id: Optional[int] = None
    reading_timestamp: Optional[datetime] = None
    device_source: Optional[str] = None
    comparable_parameters: List[str] = Field(default_factory=list)
    excluded_parameters: List[SuitabilityExcludedParameter] = Field(default_factory=list)


class WaterSuitabilityAssessmentResponse(BaseModel):
    use: str
    use_label: str
    description: str
    standard_code: str
    standard: str
    ruleset_version: str
    result: str
    result_label: str
    summary: str
    parameters: List[SuitabilityParameter]
    missing_parameters: List[SuitabilityMissingParameter]
    measured_values: List[SuitabilityMeasuredValue]
    limitations: List[str]
    data_quality: SuitabilityDataQuality
    # Advice derived from the rules this assessment triggered; empty when the
    # result is within the configured ranges.
    recommendations: RecommendationSet = RecommendationSet()


class StationSuitabilityResponse(BaseModel):
    station_code: str
    station_name: str
    generated_at: datetime
    ruleset_version: str
    assessments: List[WaterSuitabilityAssessmentResponse]


class PublicLatestReading(BaseModel):
    """Public-safe reading summary (no diagnostics, no device credentials)."""

    station_code: str
    timestamp: datetime
    pH: Optional[float] = None
    turbidity: Optional[float] = None
    turbidity_unit: Optional[str] = None
    turbidity_status: Optional[str] = None
    tds: Optional[float] = None
    temperature: Optional[float] = None
    source: str = "simulator"


class PublicReadingHistoryRow(PublicLatestReading):
    id: int
