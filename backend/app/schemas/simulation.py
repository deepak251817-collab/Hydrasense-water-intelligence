"""Schemas for the three-river simulation controls.

All generated samples are SIMULATED — the API labels them as such in every
response so a client can never present them as live sensor data.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SimulationStartRequest(BaseModel):
    station_code: str = Field(min_length=1, max_length=100)
    scenario: str = Field(default="normal")
    seed: Optional[int] = Field(default=None, description="Reproducible RNG seed")
    interval_seconds: float = Field(default=5.0, gt=0, le=300)


class SimulationGenerateRequest(BaseModel):
    station_code: Optional[str] = Field(
        default=None,
        description="Defaults to the station of the running/last simulation",
    )
    scenario: str = Field(default="normal")
    seed: Optional[int] = None
    count: int = Field(default=1, ge=1, le=20)


class SimulationSample(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    station_code: Optional[str] = None
    source_code: Optional[str] = None
    timestamp: Optional[str] = None
    scenario: Optional[str] = None
    step: int = 0
    ph: Optional[float] = None
    tds: Optional[float] = None
    temperature: Optional[float] = None
    turbidity_index: Optional[float] = None
    turbidity_status: Optional[str] = None
    fault_sensor: Optional[str] = None
    source: str = "simulator"
    simulated: bool = True


class SimulationStateResponse(BaseModel):
    running: bool
    station_code: Optional[str] = None
    source_code: Optional[str] = None
    scenario: str = "normal"
    seed: Optional[int] = None
    interval_seconds: float = 5.0
    step: int = 0
    samples_generated: int = 0
    started_at: Optional[str] = None
    last_sample_at: Optional[str] = None
    simulated: bool = True
    label: str = "SIMULATED DATA — NOT LIVE SENSOR DATA"
    scenarios: List[str]
    scenario_labels: Dict[str, str] = Field(default_factory=dict)
    # Persistence / duplicate-loop visibility: state lives in PostgreSQL and
    # only the lease-holding worker generates samples.
    persistent: bool = True
    worker_holding_lease: bool = False
    recent_samples: List[SimulationSample]
