from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ProductDeviceBase(BaseModel):
    product_code: str
    device_id: str
    device_type: str = "PERSONAL_WATER_TESTER"


class ProductDeviceCreate(ProductDeviceBase):
    pass


class ProductDeviceResponse(ProductDeviceBase):
    id: int
    status: str
    device_number: Optional[str] = None
    station_code: Optional[str] = None
    owner_id: Optional[int] = None
    activated_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
