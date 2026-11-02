"""Active alert threshold profile — versioned, sourced, and honestly classified.

Two classifications are kept strictly apart:

``official_standard``
    A value verified against a published standard (BIS IS 10500:2012 with
    Amendment 4, in this profile). The citation travels with the threshold.

``project_configured``
    An illustrative project setting for early warning. It is NOT a BIS, WHO or
    government-approved limit, it requires local validation, and the UI says so
    wherever the profile is shown.

Turbidity entries here are RELATIVE INDEX (0–100) bands only. They are never
expressed in NTU and are never compared against NTU limits — the current analog
sensor cannot produce an NTU measurement.

This module is the single source of truth for alert numbers and their trigger
conditions: ``app.services.alerting`` evaluates its conditions here, the API
serves ``profile_payload()``, and the UI renders the active profile with it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

PROFILE_VERSION = "alert-thresholds-2026.10.2"
PROFILE_NAME = "HydraSense alert screening profile"

OFFICIAL = "official_standard"
PROJECT = "project_configured"

BIS_SOURCE = "BIS IS 10500:2012 (Amd. 4), Table 1 — Drinking Water Specification, India"
BIS_URL = "https://standards.bis.gov.in/website/standard-details"
PROJECT_SOURCE = "Project configuration (backend/app/services/alert_thresholds.py)"

DISCLAIMER = (
    "Project-configured screening thresholds for early warning. Values classified "
    "as 'official_standard' are verified against the cited published standard; "
    "values classified as 'project_configured' are illustrative project settings "
    "that require local validation and must never be presented as BIS, WHO or "
    "government-approved limits. The turbidity index (0–100) is compared only "
    "with index bands, never with NTU limits."
)

_OPS = {
    "lt": lambda value, bound: value < bound,
    "lte": lambda value, bound: value <= bound,
    "gt": lambda value, bound: value > bound,
    "gte": lambda value, bound: value >= bound,
}
_SYMBOLS = {"lt": "<", "lte": "≤", "gt": ">", "gte": "≥"}


@dataclass(frozen=True)
class Condition:
    """One numeric trigger: which comparison against which bound."""

    op: str    # lt | lte | gt | gte
    value: float

    def breached(self, value: float) -> bool:
        return _OPS[self.op](value, self.value)

    def describe(self) -> str:
        # pH-style bounds keep a decimal (6.0, 9.0); larger whole numbers stay
        # plain (500, 2000, 55, 300).
        if float(self.value).is_integer() and abs(self.value) < 20:
            rendered = f"{self.value:.1f}"
        else:
            rendered = f"{self.value:g}"
        return f"value {_SYMBOLS[self.op]} {rendered}"


@dataclass(frozen=True)
class Threshold:
    key: str
    parameter: str
    label: str
    unit: str
    classification: str          # OFFICIAL | PROJECT
    source: str
    rationale: str
    warning: Tuple[Condition, ...] = ()
    critical: Tuple[Condition, ...] = ()
    source_url: Optional[str] = None

    @property
    def is_official(self) -> bool:
        return self.classification == OFFICIAL

    @property
    def normal_description(self) -> str:
        """Plain-text description of the non-alert zone, for the UI."""
        if not self.warning:
            return "informational only — no pass/fail limit"
        parts = [condition.describe() for condition in self.warning]
        return "alert when " + " or ".join(parts)

    def zone(self, value: Optional[float]) -> str:
        """Classify one measured value: 'ok' | 'warning' | 'critical' | 'unknown'."""
        if value is None:
            return "unknown"
        if any(condition.breached(value) for condition in self.critical):
            return "critical"
        if any(condition.breached(value) for condition in self.warning):
            return "warning"
        return "ok"


THRESHOLDS: Tuple[Threshold, ...] = (
    Threshold(
        key="ph_range",
        parameter="ph",
        label="pH screening range",
        unit="pH",
        classification=OFFICIAL,
        source=BIS_SOURCE,
        source_url=BIS_URL,
        rationale=(
            "Verified drinking-water reference: warnings fire outside 6.5–8.5. "
            "BIS allows no relaxation for pH."
        ),
        warning=(Condition("lt", 6.5), Condition("gt", 8.5)),
        critical=(Condition("lt", 6.0), Condition("gt", 9.0)),
    ),
    Threshold(
        # Critical band for pH lives on ph_range; this entry documents WHY the
        # critical band exists (an illustrative project choice, not BIS).
        key="ph_danger",
        parameter="ph",
        label="pH danger band (project choice)",
        unit="pH",
        classification=PROJECT,
        source=PROJECT_SOURCE,
        rationale=(
            "Illustrative early-warning level set well outside the reference "
            "range (below 6.0 or above 9.0). Requires local validation; it is "
            "not a BIS or WHO limit."
        ),
        warning=(Condition("lt", 6.0), Condition("gt", 9.0)),
    ),
    Threshold(
        key="tds_acceptable",
        parameter="tds",
        label="TDS acceptable reference",
        unit="mg/L",
        classification=OFFICIAL,
        source=BIS_SOURCE,
        source_url=BIS_URL,
        rationale=(
            "Verified BIS acceptable limit (500 mg/L); readings above it raise a "
            "warning. 1 mg/L ≈ 1 ppm for typical dilute water."
        ),
        warning=(Condition("gt", 500.0),),
        critical=(Condition("gt", 2000.0),),
    ),
    Threshold(
        key="tds_permissible",
        parameter="tds",
        label="TDS permissible reference",
        unit="mg/L",
        classification=OFFICIAL,
        source=BIS_SOURCE,
        source_url=BIS_URL,
        rationale=(
            "Verified BIS permissible limit (2000 mg/L), which applies only in "
            "the absence of an alternate source; readings above it raise a "
            "critical alert."
        ),
        critical=(Condition("gt", 2000.0),),
    ),
    Threshold(
        key="turbidity_index_bands",
        parameter="turbidity_index",
        label="Turbidity index bands (relative 0–100)",
        unit="index points (0–100)",
        classification=PROJECT,
        source="ESP32 firmware band documentation + project configuration",
        rationale=(
            "Relative index ≥ 55 sits in the firmware's CLOUDIER band "
            "(CLEARER < 30, MODERATE 30–54, CLOUDIER ≥ 55; higher = cloudier) "
            "and ≥ 85 is the configured critical level for a very cloudier sample. "
            "Index points only — never compared with the 1 NTU / 5 NTU limits, "
            "because the analog sensor does not measure NTU."
        ),
        warning=(Condition("gte", 55.0),),
        critical=(Condition("gte", 85.0),),
    ),
    Threshold(
        key="temperature_unusual",
        parameter="temperature",
        label="Unusual temperature context band",
        unit="°C",
        classification=PROJECT,
        source=PROJECT_SOURCE,
        rationale=(
            "Context band (below 5 °C or above 40 °C) for flagging unusual "
            "readings at the monitored rivers. There is no universal "
            "temperature safety limit; this is not a drinking-water criterion."
        ),
        warning=(Condition("lt", 5.0), Condition("gt", 40.0)),
    ),
    Threshold(
        key="freshness_stale",
        parameter="freshness",
        label="Stale-reading policy",
        unit="seconds",
        classification=PROJECT,
        source="Project configuration — mirrors FRESH_WITHIN_SECONDS in water_screening",
        rationale=(
            "A reading older than 300 s does not describe current conditions and "
            "raises a warning so old data is never presented as live."
        ),
        warning=(Condition("gt", 300.0),),
    ),
)

BY_KEY = {threshold.key: threshold for threshold in THRESHOLDS}


def profile_payload() -> Dict[str, Any]:
    """The active profile, as served to clients and rendered in the UI."""

    def conditions(items: Tuple[Condition, ...]) -> list:
        return [{"op": c.op, "value": c.value, "description": c.describe()} for c in items]

    return {
        "profile_version": PROFILE_VERSION,
        "profile_name": PROFILE_NAME,
        "disclaimer": DISCLAIMER,
        "thresholds": [
            {
                "key": t.key,
                "parameter": t.parameter,
                "label": t.label,
                "unit": t.unit,
                "classification": t.classification,
                "is_official_standard": t.is_official,
                "source": t.source,
                "source_url": t.source_url,
                "rationale": t.rationale,
                "normal_description": t.normal_description,
                "warning_conditions": conditions(t.warning),
                "critical_conditions": conditions(t.critical),
            }
            for t in THRESHOLDS
        ],
        "official_count": sum(1 for t in THRESHOLDS if t.is_official),
        "project_configured_count": sum(1 for t in THRESHOLDS if not t.is_official),
    }
