from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class WaterSourceResponse(BaseModel):
    id: int
    source_code: str
    name: str
    source_type: str
    description: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MonitoringStationPublicResponse(BaseModel):
    id: int
    station_code: str
    station_name: str
    zone: str
    location: str
    latitude: float
    longitude: float
    public_warning: str
    public_message: str
    is_active: bool
    created_at: datetime
    water_source: WaterSourceResponse

    model_config = ConfigDict(from_attributes=True)


class MonitoringStationAuthorityResponse(BaseModel):
    id: int
    station_code: str
    water_source_id: int
    station_name: str
    zone: str
    location: str
    latitude: float
    longitude: float
    public_warning: str
    public_message: str
    is_active: bool
    created_at: datetime
    water_source: WaterSourceResponse

    model_config = ConfigDict(from_attributes=True)


class LatestSensorReadingResponse(BaseModel):
    station_code: str
    device_id: str
    timestamp: datetime
    # NULL = no honest measurement yet (uncalibrated sensor or sensor fault),
    # never "safe"/"normal". Hardware raw data travels in `diagnostics`.
    pH: Optional[float] = None
    turbidity: Optional[float] = None
    tds: Optional[float] = None
    temperature: Optional[float] = None
    source: str = "simulator"
    diagnostics: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SensorReadingResponse(BaseModel):
    id: int
    station_id: int
    station_code: Optional[str] = None
    device_id: str
    timestamp: datetime
    # NULL = no honest measurement yet (uncalibrated sensor or sensor fault).
    pH: Optional[float] = None
    turbidity: Optional[float] = None
    tds: Optional[float] = None
    temperature: Optional[float] = None
    source: str = "simulator"
    diagnostics: Optional[dict] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

