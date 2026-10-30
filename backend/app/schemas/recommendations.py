"""Schemas for rule-based recommendations attached to an assessment."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Urgency = Literal["low", "medium", "high"]


class RecommendationItem(BaseModel):
    """Advice for one triggered (use, parameter, direction) rule.

    ``possible_causes`` are hypotheses worded as possible, never asserted, and
    only ever reference the measured sensors. ``actions`` never claim that
    treatment or re-testing makes water safe. Unmeasured parameters appear only
    in ``RecommendationSet.missing_assessments``.
    """

    parameter: str
    label: str
    direction: str
    status: Optional[str] = None
    value: Optional[float] = None
    unit: str = ""
    reason: Optional[str] = None
    urgency: Urgency
    possible_causes: List[str] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)
    avoid: List[str] = Field(default_factory=list)


class RecommendationSet(BaseModel):
    recommendations: List[RecommendationItem] = Field(default_factory=list)
    missing_assessments: List[str] = Field(default_factory=list)
    urgency: Optional[Urgency] = None
    authority_actions: List[str] = Field(default_factory=list)
