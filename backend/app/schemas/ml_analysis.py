"""ML analysis schemas (Phase 6)."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class MLAnalysisResponse(BaseModel):
    """Structured ML result for a sensor reading.

    Honesty: `anomaly_label` marks an *anomalous condition* identified by the
    Isolation Forest (unusual sensor pattern). `water_quality_label` is the
    Random Forest *predicted water-quality class* on the benchmark dataset.
    Neither is laboratory confirmation, guaranteed safety, guaranteed
    contamination, or causal pollution detection.
    """

    anomaly_label: Optional[int] = None          # 1 = anomalous condition, 0 = normal pattern
    anomaly_score: Optional[float] = None        # Isolation Forest decision function
    water_quality_label: Optional[str] = None    # predicted water-quality class: Safe / Unsafe
    safe_probability: Optional[float] = None     # in [0, 1]
    unsafe_probability: Optional[float] = None   # in [0, 1]
    ml_processed_at: Optional[datetime] = None   # when inference was stored; NULL = not processed


class ReadingAnalysisResponse(BaseModel):
    """Authority endpoint payload: sensor reading information + ML analysis."""

    reading_id: int
    station_id: int
    station_code: str
    device_id: str
    timestamp: datetime
    created_at: datetime

    ph: float
    turbidity: float
    tds: float
    temperature: float

    ml: MLAnalysisResponse
