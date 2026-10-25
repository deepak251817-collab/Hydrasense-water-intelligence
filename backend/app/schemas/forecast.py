"""Forecast response schemas.

Honesty contract: a forecast block is present only when the model was
trained and evaluated against a naive persistence baseline on a time-aware
holdout split, and beat it. Otherwise the parameter (or the whole station)
carries an explicit ``unavailable`` status and reason instead of numbers.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ForecastPoint(BaseModel):
    """One forecast step. ``value`` is a MODEL OUTPUT, never a measurement."""

    timestamp: datetime
    value: float
    # Constant-width empirical band from the holdout MAE (see UncertaintyInfo).
    lower: float
    upper: float


class UncertaintyInfo(BaseModel):
    method: str = "holdout_mae"
    width: float = Field(..., description="± width in the parameter's unit")
    note: str


class ForecastModelInfo(BaseModel):
    name: str
    evaluation: str = "chronological train/test split (last 20% held out)"
    train_size: int
    test_size: int
    mae: float
    rmse: float
    baseline_mae: float = Field(..., description="naive persistence on the same holdout")
    baseline_rmse: float


class ForecastParameterResult(BaseModel):
    """Forecast for one parameter, or an honest explanation of its absence."""

    parameter: str
    label: str
    unit: str
    status: str = Field(..., pattern="^(ready|unavailable)$")
    reason: Optional[str] = None
    message: Optional[str] = None
    last_observed: Optional[float] = None
    last_observed_at: Optional[datetime] = None
    model: Optional[ForecastModelInfo] = None
    uncertainty: Optional[UncertaintyInfo] = None
    points: List[ForecastPoint] = Field(default_factory=list)


class ForecastReadinessParameter(BaseModel):
    parameter: str
    valid_samples: int
    span_days: float = 0.0
    sufficient: bool


class ForecastReadiness(BaseModel):
    """How close the stored history is to being forecastable (data pipeline)."""

    min_samples_required: int
    min_span_days_required: int
    observed_span_days: float
    parameters: List[ForecastReadinessParameter]


class ForecastResponse(BaseModel):
    station_code: str
    generated_at: datetime
    horizon_hours: int
    status: str = Field(..., pattern="^(ready|unavailable)$")
    unavailable_reason: Optional[str] = None
    message: str
    # Traceability: what the forecast history is actually made of.
    data_sources: dict = Field(default_factory=dict)
    trained_on_simulated: bool = False
    readiness: ForecastReadiness
    parameters: List[ForecastParameterResult] = Field(default_factory=list)
