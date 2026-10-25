"""Schemas for ML transparency (model health + evaluation report)."""
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel


class MLModelStatus(BaseModel):
    """Public, non-sensitive description of one model artifact."""

    key: str
    name: str
    role: str
    file: str                       # file NAME only — never an absolute path
    features: List[str]
    live_inference: bool
    artifact_present: bool
    loaded: bool


class MLStatusResponse(BaseModel):
    """Model availability plus the computed evaluation report (if generated).

    `evaluation` is None when the report has not been generated; consumers must
    render "evaluation unavailable" rather than inventing metrics.
    """

    models: List[MLModelStatus]
    evaluation_available: bool
    evaluation: Optional[dict[str, Any]] = None
    report: Optional[str] = None    # relative label, e.g. ml/reports/evaluation_report.json
    generated_at: Optional[datetime] = None
