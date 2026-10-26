"""Shared four-sensor water assessment for Live Monitoring and Product Users.

One deterministic, explainable rule-based service used by both workflows. It
does not require a trained model: pH, TDS, turbidity and temperature from the
existing ESP32/MQTT pipeline are enough for an initial screening.

Reference profile
-----------------
India, BIS IS 10500:2012 (Drinking Water — Specification, Amendment 4):
  pH            6.5–8.5 (acceptable; no relaxation)
  TDS           500 mg/L acceptable / 2000 mg/L permissible (absence of an
                alternate source)
  Turbidity     1 NTU acceptable / 5 NTU permissible
                (applied only to a calibrated NTU measurement)
  Temperature   no universal pass/fail limit — context and trend only

The ESP32's turbidity value is a provisional relative 0–100 index, not NTU, so
it is never compared with the NTU limits. Relative-index categories below are
project demo bands, not a standard.

Project demo preference (drinking profile only)
-----------------------------------------------
``DEMO_STRICT_TDS_RULE`` (env var, default enabled) adds a project-specific
target of 200 mg/L. A value below 200 is flagged as *below the project target*,
NOT as unsafe drinking water. This preference does not change the official BIS
limits and is never applied to domestic, irrigation, swimming or aquaculture
assessments.

Irrigation uses FAO-style TDS salinity categories (<450 no restriction,
450–2000 slight-to-moderate, >2000 severe) and a pH reference of 6.5–8.4.
Those are screening aids only: crop, soil, EC, SAR, chloride and boron are not
measured by this hardware.

Result states
-------------
WITHIN_PROJECT_TARGETS / REVIEW_RECOMMENDED /
NOT_RECOMMENDED_BY_SCREENING / INCONCLUSIVE

No state certifies potability, and a low-risk result is never described as
"safe to drink".
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

CRITERIA_VERSION = "live-screening-2026.10.3"

BIS_CODE = "BIS-IS-10500:2012"
BIS_NAME = "BIS IS 10500:2012 Drinking Water — Specification (Amd. 4), India"
IRRIGATION_NAME = "FAO irrigation water salinity categories (TDS proxy) + pH reference 6.5–8.4"
CPCB_B_NAME = "CPCB Designated Best Use Class B (outdoor bathing), India"
CPCB_D_NAME = "CPCB Designated Best Use Class D (wildlife & fisheries), India"

FRESH_WITHIN_SECONDS = 300  # backend-wide limit for a saved/live test
TDS_PLAUSIBLE_MAX = 5000.0
PH_VALID_MIN, PH_VALID_MAX = 0.0, 14.0
TEMPERATURE_PLAUSIBLE_MIN, TEMPERATURE_PLAUSIBLE_MAX = -5.0, 60.0
TURBIDITY_INDEX_MIN, TURBIDITY_INDEX_MAX = 0.0, 100.0

SOURCE_LABELS = {
    "tap": "Tap water",
    "borewell": "Borewell water",
    "well": "Well water",
    "tank": "Tank water",
    "surface": "River / lake / pond water",
    "other": "Other source",
}

USE_LABELS = {
    "drinking": "Drinking Water",
    "domestic": "Domestic Use",
    "irrigation": "Irrigation",
    "general": "General Non-Potable Use",
    "swimming": "Swimming / Recreation",
    "aquaculture": "Aquaculture",
}

STATUS_LABELS = {
    "within_range": "Within configured range",
    "below_project_target": "Below project strict target",
    "above_acceptable": "Above acceptable reference",
    "above_permissible": "Exceeds permissible reference",
    "below_reference": "Below configured range",
    "above_reference": "Above configured range",
    "not_comparable": "Not comparable to a standard",
    "not_measured": "Not measured",
    "invalid": "Invalid reading",
    "informational": "Information only — no configured limit",
    "no_restriction": "No restriction indicated",
    "slight_restriction": "Slight-to-moderate restriction",
    "severe_restriction": "Severe restriction",
}

OVERALL_LABELS = {
    "WITHIN_PROJECT_TARGETS": "Within project screening targets",
    "REVIEW_RECOMMENDED": "Review recommended",
    "NOT_RECOMMENDED_BY_SCREENING": "Not recommended by this screening",
    "INCONCLUSIVE": "Inconclusive — more data or calibration required",
}

CONCERN_STATUSES = {
    "below_project_target",
    "above_acceptable",
    "above_permissible",
    "below_reference",
    "above_reference",
    "invalid",
    "slight_restriction",
    "severe_restriction",
    "not_comparable",
}

_LIMITATION_NOT_CERTIFIED = (
    "This screening uses four sensors only. Microbiological, heavy-metal and "
    "pesticide parameters are not measured; no result certifies potability."
)


@dataclass(frozen=True)
class ScreeningCriteria:
    """Editable screening limits and project preferences."""

    ph_min: float = 6.5
    ph_max: float = 8.5
    tds_acceptable_max: float = 500.0
    tds_permissible_max: float = 2000.0
    turbidity_ntu_acceptable_max: float = 1.0
    turbidity_ntu_permissible_max: float = 5.0
    irrigation_ph_min: float = 6.5
    irrigation_ph_max: float = 8.4
    irrigation_tds_no_restriction_max: float = 450.0
    irrigation_tds_severe_min: float = 2000.0
    swimming_ph_min: float = 6.5
    swimming_ph_max: float = 8.5
    aquaculture_ph_min: float = 6.5
    aquaculture_ph_max: float = 8.5
    # Project-specific display preference for the Drinking profile only.
    demo_strict_tds_rule: bool = True
    strict_tds_target: float = 200.0


def default_criteria() -> ScreeningCriteria:
    """Criteria from module defaults, with the demo rule controlled by env.

    Set ``DEMO_STRICT_TDS_RULE=false`` in the backend environment to disable
    the project-specific <200 mg/L drinking-water TDS target. No other use is
    affected.
    """

    raw = os.getenv("DEMO_STRICT_TDS_RULE", "true").strip().lower()
    return ScreeningCriteria(
        demo_strict_tds_rule=raw not in ("0", "false", "no", "off")
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def validate_readings(
    readings: Mapping[str, Any],
    *,
    turbidity_unit: Optional[str],
    max_age_seconds: Optional[float] = None,
) -> Dict[str, List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    ph = _finite(readings.get("ph"))
    if ph is None:
        errors.append("pH reading is missing or not a finite number.")
    elif ph < PH_VALID_MIN or ph > PH_VALID_MAX:
        errors.append(f"pH {ph:g} is outside the valid 0–14 scale.")

    tds = _finite(readings.get("tds"))
    if tds is None:
        errors.append("TDS reading is missing or not a finite number.")
    elif tds < 0:
        errors.append(f"TDS {tds:g} mg/L is negative and cannot be valid.")
    elif tds > TDS_PLAUSIBLE_MAX:
        errors.append(
            f"TDS {tds:g} mg/L is above the configured {TDS_PLAUSIBLE_MAX:g} mg/L "
            "plausibility bound."
        )

    turbidity = _finite(readings.get("turbidity"))
    if turbidity is None:
        warnings.append("Turbidity reading is missing; it is not assessed.")
    elif turbidity_unit == "ntu":
        if turbidity < 0:
            errors.append(f"Turbidity {turbidity:g} NTU is negative.")
    elif turbidity_unit == "relative_index_0_100":
        if turbidity < TURBIDITY_INDEX_MIN or turbidity > TURBIDITY_INDEX_MAX:
            warnings.append(
                f"Relative turbidity index {turbidity:g} is outside the 0–100 "
                "range reported by the sensor."
            )
    else:
        warnings.append(
            "Turbidity unit is unknown, so the value cannot be compared with any limit."
        )

    temperature = _finite(readings.get("temperature"))
    if temperature is None:
        warnings.append("Temperature reading is missing; it is context only.")
    elif (
        temperature < TEMPERATURE_PLAUSIBLE_MIN
        or temperature > TEMPERATURE_PLAUSIBLE_MAX
    ):
        warnings.append(
            f"Temperature {temperature:g} °C is outside the configured "
            f"{TEMPERATURE_PLAUSIBLE_MIN:g}–{TEMPERATURE_PLAUSIBLE_MAX:g} °C "
            "plausibility range."
        )

    if max_age_seconds is not None and max_age_seconds > FRESH_WITHIN_SECONDS:
        warnings.append(
            f"The measurement is {int(max_age_seconds // 60)} min old; a current "
            "assessment requires a reading from the last 5 min."
        )

    return {"errors": errors, "warnings": warnings}


# ---------------------------------------------------------------------------
# Parameter evaluation
# ---------------------------------------------------------------------------

def _entry(
    parameter: str,
    label: str,
    value: Optional[float],
    unit: str,
    status: str,
    reference: str,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "parameter": parameter,
        "label": label,
        "value": value,
        "unit": unit,
        "status": status,
        "status_label": STATUS_LABELS[status],
        "reference": reference,
        "note": note,
    }


def _ph_reference(low: float, high: float, standard: str) -> str:
    return f"{standard}: pH {low:g}–{high:g}"


def _evaluate_ph(
    ph: Optional[float], low: float, high: float, standard: str
) -> Dict[str, Any]:
    reference = _ph_reference(low, high, standard)
    if ph is None:
        return _entry("ph", "pH", None, "", "not_measured", reference)
    if ph < PH_VALID_MIN or ph > PH_VALID_MAX:
        return _entry(
            "ph", "pH", ph, "", "invalid", reference,
            "Value is outside the valid 0–14 pH scale.",
        )
    if ph < low:
        return _entry(
            "ph", "pH", ph, "", "below_reference", reference,
            f"pH is below the configured {low:g} lower reference value.",
        )
    if ph > high:
        return _entry(
            "ph", "pH", ph, "", "above_reference", reference,
            f"pH is above the configured {high:g} upper reference value.",
        )
    return _entry("ph", "pH", ph, "", "within_range", reference)


def _evaluate_drinking_tds(
    tds: Optional[float], criteria: ScreeningCriteria
) -> Dict[str, Any]:
    reference = (
        f"{BIS_CODE}: TDS {criteria.tds_acceptable_max:g} mg/L acceptable, "
        f"{criteria.tds_permissible_max:g} mg/L permissible. "
        "1 mg/L ≈ 1 ppm for typical dilute water."
    )
    if tds is None:
        return _entry("tds", "TDS", None, "mg/L", "not_measured", reference)
    if tds < 0 or tds > TDS_PLAUSIBLE_MAX:
        return _entry(
            "tds", "TDS", tds, "mg/L", "invalid", reference,
            "Value is outside the configured plausibility bounds.",
        )

    if criteria.demo_strict_tds_rule and tds < criteria.strict_tds_target:
        return _entry(
            "tds", "TDS", tds, "mg/L", "below_project_target", reference,
            "Does not meet the project's strict drinking-water TDS target of 200 ppm. "
            "This is a project-specific screening flag, not an official BIS "
            "determination that the water is unsafe. Low TDS alone is not a safety "
            "determination; review the other parameters and perform appropriate "
            "water-quality testing.",
        )
    if criteria.demo_strict_tds_rule and tds < criteria.tds_acceptable_max:
        return _entry(
            "tds", "TDS", tds, "mg/L", "within_range", reference,
            "Meets the project's preferred TDS target (200 to below 500 ppm) and is "
            "within the BIS acceptable reference.",
        )
    if tds <= criteria.tds_acceptable_max:
        return _entry(
            "tds", "TDS", tds, "mg/L", "within_range", reference,
            "Within the BIS acceptable TDS reference. Low TDS does not prove safety "
            "and does not identify which contaminants are present.",
        )
    if tds <= criteria.tds_permissible_max:
        return _entry(
            "tds", "TDS", tds, "mg/L", "above_acceptable", reference,
            "Above the BIS acceptable TDS reference; the permissible limit applies "
            "only in the absence of an alternate source.",
        )
    return _entry(
        "tds", "TDS", tds, "mg/L", "above_permissible", reference,
        "Exceeds the cited BIS permissible TDS reference.",
    )


def _evaluate_domestic_tds(
    tds: Optional[float], criteria: ScreeningCriteria
) -> Dict[str, Any]:
    reference = (
        f"{BIS_CODE}: TDS {criteria.tds_acceptable_max:g} mg/L acceptable, "
        f"{criteria.tds_permissible_max:g} mg/L permissible (domestic profile; the "
        "project-specific strict drinking target is not applied)."
    )
    if tds is None:
        return _entry("tds", "TDS", None, "mg/L", "not_measured", reference)
    if tds < 0 or tds > TDS_PLAUSIBLE_MAX:
        return _entry("tds", "TDS", tds, "mg/L", "invalid", reference,
                      "Value is outside the configured plausibility bounds.")
    if tds <= criteria.tds_acceptable_max:
        return _entry("tds", "TDS", tds, "mg/L", "within_range", reference,
                      "Within the BIS acceptable TDS reference.")
    if tds <= criteria.tds_permissible_max:
        return _entry("tds", "TDS", tds, "mg/L", "above_acceptable", reference,
                      "Within the BIS permissible range but above the acceptable "
                      "value; use the permissible value only when no alternate "
                      "source is available.")
    return _entry("tds", "TDS", tds, "mg/L", "above_permissible", reference,
                  "Exceeds the BIS permissible TDS reference.")


def _evaluate_irrigation_tds(
    tds: Optional[float], criteria: ScreeningCriteria
) -> Dict[str, Any]:
    reference = (
        f"{IRRIGATION_NAME}: TDS <{criteria.irrigation_tds_no_restriction_max:g} mg/L "
        "no restriction indicated; "
        f"{criteria.irrigation_tds_no_restriction_max:g}–"
        f"{criteria.irrigation_tds_severe_min:g} mg/L slight-to-moderate; "
        f">{criteria.irrigation_tds_severe_min:g} mg/L severe."
    )
    if tds is None:
        return _entry("tds", "TDS (salinity proxy)", None, "mg/L",
                      "not_measured", reference)
    if tds < 0 or tds > TDS_PLAUSIBLE_MAX:
        return _entry("tds", "TDS (salinity proxy)", tds, "mg/L", "invalid",
                      reference, "Value is outside the configured plausibility bounds.")
    if tds < criteria.irrigation_tds_no_restriction_max:
        return _entry(
            "tds", "TDS (salinity proxy)", tds, "mg/L", "no_restriction", reference,
            "No salinity-use restriction is indicated by this TDS criterion. TDS is "
            "not electrical conductivity; EC, SAR, chloride and boron still need "
            "testing.",
        )
    if tds <= criteria.irrigation_tds_severe_min:
        return _entry(
            "tds", "TDS (salinity proxy)", tds, "mg/L", "slight_restriction",
            reference,
            "Slight-to-moderate salinity-use restriction indicated. Confirm with "
            "electrical conductivity (EC), SAR and crop-specific guidance.",
        )
    return _entry(
        "tds", "TDS (salinity proxy)", tds, "mg/L", "severe_restriction", reference,
        "Severe salinity-use restriction indicated. Confirm with a laboratory EC/SAR "
        "analysis before irrigating sensitive crops.",
    )


def _evaluate_informational_tds(tds: Optional[float], use: str) -> Dict[str, Any]:
    reference = f"No TDS pass/fail threshold configured for {USE_LABELS[use].lower()}."
    if tds is None:
        return _entry("tds", "TDS", None, "mg/L", "not_measured", reference)
    return _entry(
        "tds", "TDS", tds, "mg/L", "informational", reference,
        "No TDS limit is configured for this use; the value is displayed for context "
        "only and carries no suitability verdict.",
    )


def _evaluate_turbidity(
    turbidity: Optional[float],
    turbidity_unit: Optional[str],
    *,
    turbidity_calibrated: bool,
    criteria: ScreeningCriteria,
) -> Dict[str, Any]:
    ntu_reference = (
        f"{BIS_CODE}: turbidity {criteria.turbidity_ntu_acceptable_max:g} NTU "
        f"acceptable, {criteria.turbidity_ntu_permissible_max:g} NTU permissible"
    )
    if turbidity is None:
        return _entry("turbidity", "Turbidity", None, "", "not_measured",
                      ntu_reference, "No turbidity value is available.")
    if turbidity_unit != "ntu":
        unit = (
            "relative index 0–100 (not NTU)"
            if turbidity_unit == "relative_index_0_100"
            else (turbidity_unit or "unit unknown")
        )
        return _entry(
            "turbidity", "Turbidity", turbidity, unit, "not_comparable",
            "No validated NTU calibration available",
            "Relative turbidity index — not calibrated NTU. It is not compared with "
            "the 1 NTU or 5 NTU limits and must not be read as NTU.",
        )
    if not turbidity_calibrated:
        return _entry(
            "turbidity", "Turbidity", turbidity, "NTU (uncalibrated)",
            "not_comparable", ntu_reference,
            "The NTU value was reported without a verified calibration, so it is not "
            "compared with the standard.",
        )
    if turbidity < 0:
        return _entry("turbidity", "Turbidity", turbidity, "NTU", "invalid",
                      ntu_reference, "A negative NTU value cannot be valid.")
    if turbidity <= criteria.turbidity_ntu_acceptable_max:
        return _entry("turbidity", "Turbidity", turbidity, "NTU", "within_range",
                      ntu_reference)
    if turbidity <= criteria.turbidity_ntu_permissible_max:
        return _entry(
            "turbidity", "Turbidity", turbidity, "NTU", "above_acceptable",
            ntu_reference,
            "Above the acceptable turbidity reference; the higher permissible limit "
            "applies only in the absence of an alternate source.",
        )
    return _entry(
        "turbidity", "Turbidity", turbidity, "NTU", "above_permissible",
        ntu_reference, "Exceeds the cited permissible turbidity reference.",
    )


def _evaluate_temperature(temperature: Optional[float], use: str) -> Dict[str, Any]:
    reference = (
        "No universal temperature pass/fail limit is configured for "
        f"{USE_LABELS[use].lower()}; temperature is context and trend only."
    )
    if temperature is None:
        return _entry("temperature", "Temperature", None, "°C", "not_measured",
                      reference)
    if (
        temperature < TEMPERATURE_PLAUSIBLE_MIN
        or temperature > TEMPERATURE_PLAUSIBLE_MAX
    ):
        return _entry("temperature", "Temperature", temperature, "°C", "invalid",
                      reference,
                      "Value is outside the configured water-temperature "
                      "plausibility range.")
    return _entry(
        "temperature", "Temperature", temperature, "°C", "informational", reference,
        "Temperature alone does not establish water-quality suitability.",
    )


# ---------------------------------------------------------------------------
# Overall state
# ---------------------------------------------------------------------------

def _inconclusive_reason(
    errors: Sequence[str],
    stale: bool,
    stability: Optional[Mapping[str, Any]],
) -> Optional[str]:
    if errors:
        return "Required readings are missing or invalid."
    if stale:
        return "The measurement is stale."
    if stability and not stability.get("stable", False):
        status = stability.get("status")
        if status in ("offline", "waiting_for_data", "sensor_error", "unstable",
                      "collecting", "stabilizing"):
            return str(stability.get("message") or "Sensor readings are not stable yet.")
    return None


def _overall_status(
    intended_use: str,
    *,
    ph: Dict[str, Any],
    tds: Dict[str, Any],
    turbidity: Dict[str, Any],
    temperature: Dict[str, Any],
    errors: Sequence[str],
    stale: bool,
    stability: Optional[Mapping[str, Any]],
    calibration_verified: bool,
    reading_mode: str,
) -> str:
    if _inconclusive_reason(errors, stale, stability):
        return "INCONCLUSIVE"

    # A live reading with unverified/provisional calibration is insufficient for
    # any screening conclusion, including a green pass. Demo values stay labelled
    # SIMULATION and are handled separately.
    if reading_mode == "live" and not calibration_verified:
        return "INCONCLUSIVE"

    if intended_use == "aquaculture":
        # No species-specific criteria are configured, so a suitability result
        # cannot be produced from these four readings.
        return "INCONCLUSIVE"

    # An invalid reading of ANY of the four sensors can never ride along with a
    # positive result: implausible pH/TDS/temperature/turbidity collapses the
    # whole assessment to inconclusive.
    if any(
        entry["status"] == "invalid"
        for entry in (ph, tds, turbidity, temperature)
    ):
        return "INCONCLUSIVE"

    if intended_use == "drinking":
        if (
            tds["status"] == "above_permissible"
            or turbidity["status"] == "above_permissible"
            or ph["status"] in ("below_reference", "above_reference")
        ):
            return "NOT_RECOMMENDED_BY_SCREENING"
        if (
            tds["status"] in ("above_acceptable", "below_project_target")
            or turbidity["status"] == "above_acceptable"
        ):
            return "REVIEW_RECOMMENDED"
        return "WITHIN_PROJECT_TARGETS"

    if intended_use == "domestic":
        if (
            tds["status"] == "above_permissible"
            or turbidity["status"] == "above_permissible"
            or ph["status"] in ("below_reference", "above_reference")
        ):
            return "NOT_RECOMMENDED_BY_SCREENING"
        if (
            tds["status"] == "above_acceptable"
            or turbidity["status"] == "above_acceptable"
        ):
            return "REVIEW_RECOMMENDED"
        return "WITHIN_PROJECT_TARGETS"

    if intended_use == "irrigation":
        if tds["status"] == "severe_restriction":
            return "NOT_RECOMMENDED_BY_SCREENING"
        # Other required irrigation criteria (EC, SAR, boron) are not measured,
        # so even a favourable TDS/pH result can only recommend review.
        return "REVIEW_RECOMMENDED"

    if intended_use == "swimming":
        if (
            ph["status"] in ("below_reference", "above_reference")
            or turbidity["status"] in ("above_acceptable", "above_permissible")
        ):
            return "NOT_RECOMMENDED_BY_SCREENING"
        # Microbiology/oxygen demand are not measured; safe swimming cannot be
        # certified, so the best possible state is review.
        return "REVIEW_RECOMMENDED"

    if intended_use == "general":
        # General non-potable use (cleaning, gardening, cooling, construction):
        # only the measured four are screened, and TDS carries no pass/fail for
        # this use, so a concern in pH or turbidity drives the result.
        if (
            ph["status"] in ("below_reference", "above_reference")
            or turbidity["status"] in ("above_acceptable", "above_permissible")
        ):
            return "NOT_RECOMMENDED_BY_SCREENING"
        return "WITHIN_PROJECT_TARGETS"

    return "INCONCLUSIVE"


def _summary(
    intended_use: str,
    status: str,
    *,
    ph: Dict[str, Any],
    tds: Dict[str, Any],
    turbidity: Dict[str, Any],
    calibration_verified: bool,
    reading_mode: str,
) -> str:
    concern_parts: List[str] = []
    for item, label in ((ph, "pH"), (tds, "TDS"), (turbidity, "Turbidity")):
        if item["status"] in CONCERN_STATUSES and item["value"] is not None:
            value = f"{item['value']:g} {item['unit']}".strip()
            concern_parts.append(f"{label} {value} ({item['status_label'].lower()})")
    concerns = "; ".join(concern_parts)

    if status == "INCONCLUSIVE":
        if intended_use == "aquaculture":
            return (
                "Insufficient parameters for a reliable aquaculture suitability "
                "assessment. Dissolved oxygen, ammonia, nitrite, salinity and "
                "species-specific criteria are not measured by this hardware."
            )
        if intended_use == "drinking" and tds["status"] == "below_project_target":
            return (
                "Not suitable under the project's strict drinking-water TDS target: "
                "TDS is below 200 ppm. This is a project-specific screening preference, "
                "not an official BIS determination that the water is unsafe. The overall "
                "assessment remains inconclusive because more data or verified sensor "
                "calibration is required."
            )
        if reading_mode == "live" and not calibration_verified:
            return (
                "Sensor calibration is unverified, so no reliable screening "
                "conclusion is drawn. Stability does not imply calibration; "
                "calibrate the probes and retry."
            )
        return (
            "Unable to assess reliably — required readings are missing, stale or "
            "unstable. No screening conclusion is drawn."
        )

    if intended_use == "drinking":
        if status == "WITHIN_PROJECT_TARGETS":
            return (
                "No monitored concern was detected by this screening. This result "
                "does not certify that the water is safe to drink."
            )
        if status == "REVIEW_RECOMMENDED":
            return (
                "Review recommended. "
                + (concerns + ". " if concerns else "")
                + "The screening found items that need attention or verification; "
                "this is not a certification that the water is safe to drink."
            )
        return (
            "Not recommended by this screening: "
            + (concerns or "one or more monitored parameters exceed the configured references")
            + ". This is not a laboratory determination that the water is unsafe; "
            "obtain confirmatory testing."
        )

    if intended_use == "domestic":
        if status == "WITHIN_PROJECT_TARGETS":
            return (
                "No monitored parameter exceeded the configured BIS screening values "
                "for domestic water. Bathing, washing, cleaning and gardening can have "
                "different requirements; this is not a potability assessment."
            )
        return (
            "Domestic-use screening requires review: "
            + (concerns or "configured references were not fully assessed")
            + ". Do not assume the water is suitable for every domestic purpose."
        )

    if intended_use == "irrigation":
        tds_note = {
            "no_restriction": "No salinity-use restriction is indicated by this TDS criterion.",
            "slight_restriction": "Slight-to-moderate salinity-use restriction is indicated.",
            "severe_restriction": "Severe salinity-use restriction is indicated.",
        }.get(tds["status"], "The TDS salinity criterion could not be evaluated.")
        return (
            tds_note + " "
            + ("pH is also outside the 6.5–8.4 screening range. " if ph["status"] in
               ("below_reference", "above_reference") else "")
            + "EC, SAR, chloride and boron are not measured, so this is not an "
              "irrigation suitability certification."
        )

    if intended_use == "swimming":
        base = (
            "Recreational water cannot be certified from pH, TDS, turbidity and "
            "temperature alone. Microbiological testing and site-specific criteria "
            "are required."
        )
        if status == "NOT_RECOMMENDED_BY_SCREENING":
            return (
                "One or more monitored parameters are outside the configured "
                "swimming/recreation references: " + (concerns or "see parameters") + ". "
                + base
            )
        return "No pH or turbidity concern was detected by this screening. " + base

    if intended_use == "aquaculture":
        return (
            "Insufficient parameters for a reliable aquaculture suitability "
            "assessment. Dissolved oxygen, ammonia, nitrite, salinity and "
            "species-specific criteria are not measured by this hardware."
        )

    if intended_use == "general":
        if status == "WITHIN_PROJECT_TARGETS":
            return (
                "Measured indicators are within the configured general "
                "(non-potable) screening ranges. This covers uses such as cleaning "
                "and gardening only; it is not a safety certification, and "
                "microbiological contamination is not measured."
            )
        if status == "REVIEW_RECOMMENDED":
            return (
                "Caution — further testing or treatment may be needed: "
                + (concerns or "one or more readings need verification") + "."
            )
        return (
            "Unfavourable measured indicators — investigation recommended: "
            + (concerns or "one or more measured values are outside the configured "
               "general-use references")
            + "."
        )

    return "Unable to assess."


def _reason_details(
    intended_use: str,
    *,
    evaluated: Sequence[Dict[str, Any]],
    ph: Dict[str, Any],
    tds: Dict[str, Any],
    turbidity: Dict[str, Any],
    calibration: Mapping[str, str],
    calibration_status: str,
    reading_mode: str,
    stability: Optional[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    details: List[Dict[str, Any]] = []

    for item in evaluated:
        if item["parameter"] == "temperature":
            continue
        status = item["status"]
        if status in ("within_range", "informational", "no_restriction"):
            continue

        if status == "not_comparable":
            reason = item.get("note") or "Not comparable to a configured reference."
        elif status == "not_measured":
            reason = "No measurement is available for this parameter."
        elif status == "invalid":
            reason = item.get("note") or "The reading is not valid."
        elif status == "below_project_target":
            reason = item.get("note")
        elif item["parameter"] == "ph":
            reason = (
                f"pH is {'above' if status == 'above_reference' else 'below'} the "
                f"configured reference range."
            )
        elif item["parameter"] == "tds":
            reason = item.get("note") or (
                "TDS is above the configured reference."
                if status in ("above_acceptable", "above_permissible")
                else "TDS is outside the configured irrigation salinity category."
            )
        elif item["parameter"] == "turbidity":
            reason = item.get("note") or "Turbidity is above the configured reference."
        else:
            reason = item.get("note") or item["status_label"]

        calibration_note = None
        if reading_mode == "demo":
            calibration_note = "Simulated value — not a physical sensor measurement."
        elif calibration.get(item["parameter"]) not in (None, "calibrated"):
            calibration_note = (
                f"Sensor calibration status is "
                f"{calibration.get(item['parameter'])}; the value is not "
                "laboratory-calibrated."
            )
        elif calibration.get(item["parameter"]) is None:
            calibration_note = "No calibration status was reported for this sensor."

        next_step = {
            "drinking": "Review the parameter and obtain laboratory confirmation before relying on the water.",
            "domestic": "Review the parameter before using the water for domestic purposes.",
            "irrigation": "Confirm EC, SAR, chloride and boron before irrigating, and review crop tolerance.",
            "swimming": "Perform microbiological testing and check site-specific recreational criteria.",
            "general": "Confirm the water's intended non-potable use; treat it separately from any potable use.",
            "aquaculture": "Measure dissolved oxygen, ammonia, nitrite and salinity, and apply species-specific criteria.",
        }[intended_use]

        details.append(
            {
                "parameter": item["parameter"],
                "label": item["label"],
                "value": item["value"],
                "unit": item["unit"],
                "status": status,
                "status_label": item["status_label"],
                "reference": item["reference"],
                "reason": reason,
                "calibration_limitation": calibration_note,
                "next_step": next_step,
            }
        )

    if reading_mode == "live" and calibration_status in ("provisional", "unknown"):
        details.append(
            {
                "parameter": "calibration",
                "label": "Sensor calibration",
                "value": None,
                "unit": "",
                "status": "not_comparable",
                "status_label": "Calibration unverified",
                "reference": "Calibration must be confirmed separately from sensor stability.",
                "reason": (
                    "The sensor calibration is unverified; confirm the measurement "
                    "before relying on the result."
                ),
                "calibration_limitation": (
                    f"Overall calibration status: {calibration_status}."
                ),
                "next_step": "Calibrate the probes with reference solutions and record the calibration date.",
            }
        )

    if stability and not stability.get("stable", False):
        details.append(
            {
                "parameter": "stability",
                "label": "Reading stability",
                "value": stability.get("valid_samples"),
                "unit": "valid samples",
                "status": "not_comparable",
                "status_label": "Not stable",
                "reference": (
                    f"At least {stability.get('required_samples', 10)} valid samples "
                    f"over {stability.get('required_span_seconds', 20)} s."
                ),
                "reason": str(stability.get("message") or "The reading is unstable."),
                "calibration_limitation": None,
                "next_step": "Wait for more samples and retry once readings stabilise.",
            }
        )

    return details


def _next_steps(
    intended_use: str,
    status: str,
    *,
    tds: Dict[str, Any],
    calibration_verified: bool,
) -> List[str]:
    steps: List[str] = []
    if status == "INCONCLUSIVE":
        steps.append("Wait for fresh, stable readings and confirm the sensor calibration before relying on a result.")
    if intended_use == "drinking":
        if tds["status"] == "below_project_target":
            steps.append(
                "Review the project-specific low-TDS target with other water-quality "
                "checks; low TDS alone is not an official unsafe determination."
            )
        if not calibration_verified:
            steps.append("Calibrate the pH/TDS probes and record the calibration date before relying on the result.")
        steps.append(
            "Laboratory testing is required to confirm potability (microbiological, "
            "heavy-metal and pesticide parameters are not measured)."
        )
    elif intended_use == "domestic":
        steps.append(
            "Treat each domestic use separately; obtain laboratory confirmation for "
            "any use involving ingestion."
        )
    elif intended_use == "irrigation":
        steps.append(
            "Have electrical conductivity (EC), sodium adsorption ratio (SAR), "
            "chloride and boron measured before irrigation decisions."
        )
    elif intended_use == "swimming":
        steps.append(
            "Perform microbiological testing and apply site-specific recreational "
            "water criteria; these sensors cannot certify safe swimming."
        )
    elif intended_use == "general":
        steps.append(
            "Use this result for non-potable purposes only; keep the water away "
            "from drinking or cooking uses until separately assessed."
        )
    elif intended_use == "aquaculture":
        steps.append(
            "Measure dissolved oxygen, ammonia, nitrite, salinity and temperature "
            "against species-specific criteria before stocking or continuing operation."
        )
    return steps


# ---------------------------------------------------------------------------
# Suitability block
# ---------------------------------------------------------------------------

def _suitability(
    intended_use: str,
    status: str,
    *,
    ph: Dict[str, Any],
    tds: Dict[str, Any],
    turbidity: Dict[str, Any],
    temperature: Dict[str, Any],
    criteria: ScreeningCriteria,
    aquaculture_context: Optional[str],
) -> Dict[str, Any]:
    limitations: List[str] = [_LIMITATION_NOT_CERTIFIED]
    criteria_items: List[Dict[str, Any]] = [ph, tds, turbidity, temperature]

    if intended_use in ("drinking", "domestic"):
        standard_code = BIS_CODE
        standard = BIS_NAME
        description = (
            "Drinking-water screening using BIS IS 10500 reference values."
            if intended_use == "drinking" else
            "Domestic-use screening using BIS IS 10500 reference values. The "
            "project-specific strict TDS target is not applied to domestic use."
        )
        limitations = [
            _LIMITATION_NOT_CERTIFIED,
            "Temperature has no configured drinking-water pass/fail limit.",
            "TDS values are stored as mg/L; 1 mg/L ≈ 1 ppm for typical dilute water.",
        ]
    elif intended_use == "irrigation":
        standard_code = "FAO-TDS-PH"
        standard = IRRIGATION_NAME
        description = (
            "Irrigation screening using FAO-style TDS salinity categories and a "
            "6.5–8.4 pH reference. TDS is not electrical conductivity."
        )
        criteria_items = [
            ph,
            tds,
            _entry(
                "ec", "Electrical conductivity", None, "µS/cm", "not_measured",
                "FAO/CPCB irrigation guidance: EC ≤ 2250 µS/cm (context-dependent)",
                "Not measured by this device; TDS must not be substituted for EC.",
            ),
            _entry(
                "sar", "Sodium adsorption ratio", None, "", "not_measured",
                "FAO irrigation guidance: crop/soil-specific SAR limits",
            ),
            _entry(
                "boron", "Boron", None, "mg/L", "not_measured",
                "FAO irrigation guidance: boron toxicity depends on crop",
            ),
            turbidity,
            temperature,
        ]
        limitations = [
            "TDS is a salinity proxy, not electrical conductivity; EC, SAR, chloride "
            "and boron are required for irrigation decisions.",
            "Crop and soil tolerance vary; this screening cannot certify irrigation suitability.",
            "The drinking-water <200 mg/L project target is never applied to irrigation.",
        ]
    elif intended_use == "swimming":
        standard_code = "CPCB-DBU-B"
        standard = CPCB_B_NAME
        description = (
            "Swimming/recreation screening: pH and turbidity are compared with "
            "documented references where available. Microbiology is not measured."
        )
        criteria_items = [
            ph,
            turbidity,
            _entry(
                "total_coliform", "Total coliform", None, "MPN/100 mL", "not_measured",
                "CPCB Class B: total coliform ≤ 500 MPN/100 mL",
            ),
            _entry(
                "dissolved_oxygen", "Dissolved oxygen", None, "mg/L", "not_measured",
                "CPCB Class B: DO ≥ 5 mg/L",
            ),
            tds,
            temperature,
        ]
        limitations = [
            "These sensors cannot certify safe swimming; microbiological and oxygen-demand "
            "testing plus site-specific criteria are required.",
            "No universal TDS or temperature pass/fail limit is applied.",
            "Visual clarity is not a microbiological indicator.",
        ]
    elif intended_use == "general":
        standard_code = "PROJECT-GENERAL-NONPOTABLE"
        standard = "Project general (non-potable) screening references"
        description = (
            "General non-potable use screening (cleaning, gardening, cooling, "
            "construction). pH is screened against the BIS reference; TDS and "
            "temperature are shown for context with no pass/fail limit."
        )
        criteria_items = [ph, tds, turbidity, temperature]
        limitations = [
            _LIMITATION_NOT_CERTIFIED,
            "No TDS pass/fail limit is configured for general non-potable use.",
            "Temperature has no configured pass/fail limit.",
            "This use is separate from drinking, domestic ingestion, irrigation, "
            "recreation and aquaculture assessments.",
        ]
    elif intended_use == "aquaculture":
        standard_code = "AQUACULTURE-NO-CONFIGURED-CRITERIA"
        standard = "No species-specific aquaculture criteria configured"
        description = (
            "Aquaculture requires species-specific criteria. The four available "
            "readings are displayed, but they are insufficient for a suitability verdict."
        )
        criteria_items = [
            ph, tds, turbidity, temperature,
            _entry("dissolved_oxygen", "Dissolved oxygen", None, "mg/L", "not_measured",
                   "Species-specific aquaculture requirement; not measured by this device."),
            _entry("ammonia", "Ammonia / ammonium", None, "mg/L", "not_measured",
                   "Species-specific aquaculture requirement; not measured by this device."),
            _entry("salinity", "Salinity", None, "ppt", "not_measured",
                   "Species-specific aquaculture requirement; not measured by this device."),
        ]
        limitations = [
            "Insufficient parameters for a reliable aquaculture suitability assessment.",
            "Dissolved oxygen, ammonia, nitrite and salinity are not measured by this hardware.",
            "No species-specific criteria are configured; this screening cannot certify water as safe for fish.",
        ]
        if aquaculture_context:
            limitations.append(f"Species/farming context supplied: {aquaculture_context}.")
    else:  # pragma: no cover - API validates the enum
        standard_code = "UNKNOWN"
        standard = "No reference profile configured"
        description = "No criteria are configured for this intended use."

    result_label = OVERALL_LABELS[status]
    if status == "REVIEW_RECOMMENDED" and intended_use == "irrigation":
        result_label = "Review recommended — other irrigation criteria not measured"
    if status == "INCONCLUSIVE" and intended_use == "aquaculture":
        result_label = "Insufficient parameters for a reliable aquaculture suitability assessment"

    return {
        "use": intended_use,
        "use_label": USE_LABELS[intended_use],
        "description": description,
        "standard_code": standard_code,
        "standard": standard,
        "criteria_version": CRITERIA_VERSION,
        "result": status,
        "result_label": result_label,
        "summary": "",
        "criteria_available": intended_use != "aquaculture",
        "criteria": criteria_items,
        "limitations": limitations,
        "reference_profile": {
            "code": standard_code,
            "name": standard,
            "jurisdiction": "India" if intended_use != "aquaculture" else "Not configured",
        },
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def assess(
    readings: Mapping[str, Any],
    *,
    intended_use: str,
    reading_mode: str,
    reading_timestamp: Optional[datetime] = None,
    turbidity_unit: Optional[str] = None,
    calibration: Optional[Mapping[str, str]] = None,
    stability: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
    criteria: Optional[ScreeningCriteria] = None,
    aquaculture_context: Optional[str] = None,
) -> Dict[str, Any]:
    """Assess four readings for one intended use.

    ``stability`` is the result of the rolling-window stability service. A
    non-stable window makes the assessment INCONCLUSIVE; it never produces a
    green pass. Stability and calibration are reported separately.
    """

    criteria = criteria or default_criteria()
    now = now or datetime.now(timezone.utc)
    if reading_timestamp is not None and reading_timestamp.tzinfo is None:
        reading_timestamp = reading_timestamp.replace(tzinfo=timezone.utc)

    age_seconds = (
        (now - reading_timestamp).total_seconds()
        if reading_timestamp is not None else None
    )

    validation = validate_readings(
        readings,
        turbidity_unit=turbidity_unit,
        max_age_seconds=age_seconds if reading_mode == "live" else None,
    )

    ph_value = _finite(readings.get("ph"))
    tds_value = _finite(readings.get("tds"))
    turbidity_value = _finite(readings.get("turbidity"))
    temperature_value = _finite(readings.get("temperature"))

    calibration = calibration or {}
    # A demo/simulated value is labelled as SIMULATION, but it still cannot be
    # treated as a calibrated NTU measurement unless the calibration is reported.
    turbidity_calibrated = (
        turbidity_unit == "ntu"
        and calibration.get("turbidity") == "calibrated"
    )

    ph_range = {
        "drinking": (criteria.ph_min, criteria.ph_max, BIS_NAME),
        "domestic": (criteria.ph_min, criteria.ph_max, BIS_NAME),
        "general": (criteria.ph_min, criteria.ph_max, BIS_NAME),
        "irrigation": (criteria.irrigation_ph_min, criteria.irrigation_ph_max, IRRIGATION_NAME),
        "swimming": (criteria.swimming_ph_min, criteria.swimming_ph_max, CPCB_B_NAME),
        "aquaculture": (criteria.aquaculture_ph_min, criteria.aquaculture_ph_max, CPCB_D_NAME),
    }[intended_use]
    ph_eval = _evaluate_ph(ph_value, *ph_range)

    if intended_use == "drinking":
        tds_eval = _evaluate_drinking_tds(tds_value, criteria)
    elif intended_use == "domestic":
        tds_eval = _evaluate_domestic_tds(tds_value, criteria)
    elif intended_use == "irrigation":
        tds_eval = _evaluate_irrigation_tds(tds_value, criteria)
    else:
        tds_eval = _evaluate_informational_tds(tds_value, intended_use)

    turbidity_eval = _evaluate_turbidity(
        turbidity_value, turbidity_unit,
        turbidity_calibrated=turbidity_calibrated,
        criteria=criteria,
    )
    temperature_eval = _evaluate_temperature(temperature_value, intended_use)
    evaluated = [ph_eval, tds_eval, turbidity_eval, temperature_eval]

    if reading_mode == "demo":
        calibration_status = "simulated"
    elif calibration and all(
        calibration.get(key) == "calibrated"
        for key in ("ph", "tds", "turbidity", "temperature")
    ):
        calibration_status = "calibrated"
    elif calibration:
        calibration_status = "provisional"
    else:
        calibration_status = "unknown"

    calibration_verified = calibration_status == "calibrated" or reading_mode == "demo"
    stale = (
        reading_mode == "live"
        and age_seconds is not None
        and age_seconds > FRESH_WITHIN_SECONDS
    )

    status = _overall_status(
        intended_use,
        ph=ph_eval,
        tds=tds_eval,
        turbidity=turbidity_eval,
        temperature=temperature_eval,
        errors=validation["errors"],
        stale=stale,
        stability=stability,
        calibration_verified=calibration_verified,
        reading_mode=reading_mode,
    )

    rating_summary = _summary(
        intended_use,
        status,
        ph=ph_eval,
        tds=tds_eval,
        turbidity=turbidity_eval,
        calibration_verified=calibration_verified,
        reading_mode=reading_mode,
    )

    details = _reason_details(
        intended_use,
        evaluated=evaluated,
        ph=ph_eval,
        tds=tds_eval,
        turbidity=turbidity_eval,
        calibration=calibration,
        calibration_status=calibration_status,
        reading_mode=reading_mode,
        stability=stability,
    )

    warnings = list(validation["warnings"])
    if reading_mode == "demo":
        warnings.insert(
            0,
            "SIMULATION — simulated readings, not captured from a physical sensor. "
            "Use demo mode only to understand how an assessment is presented.",
        )
    elif calibration_status == "provisional":
        warnings.append(
            "Sensor calibration is provisional/unverified; stability does not imply "
            "a calibrated measurement. Calibrate the probes for measurement-grade values."
        )
    elif calibration_status == "unknown":
        warnings.append("No sensor calibration status was reported with this reading.")
    if stability and stability.get("message"):
        warnings.append(str(stability["message"]))

    attention = [
        {
            "parameter": item["parameter"],
            "label": item["label"],
            "value": item["value"],
            "unit": item["unit"],
            "status": item["status"],
            "status_label": item["status_label"],
            "message": item["note"] or item["status_label"],
        }
        for item in evaluated
        if item["status"] in CONCERN_STATUSES
    ]

    suitability = _suitability(
        intended_use,
        status,
        ph=ph_eval,
        tds=tds_eval,
        turbidity=turbidity_eval,
        temperature=temperature_eval,
        criteria=criteria,
        aquaculture_context=aquaculture_context,
    )
    suitability["summary"] = rating_summary

    low_tds_drinking = (
        intended_use == "drinking" and tds_eval["status"] == "below_project_target"
    )
    overall_label = OVERALL_LABELS[status]
    if low_tds_drinking:
        # The project-specific TDS preference is surfaced in the headline even
        # when calibration/stability makes the overall result inconclusive.
        overall_label = (
            "Not suitable by the project's strict TDS target — more data or "
            "calibration required"
            if status == "INCONCLUSIVE"
            else "Not suitable by the project's strict TDS target"
        )
        suitability["result_label"] = overall_label

    return {
        "criteria_version": CRITERIA_VERSION,
        "reference_profile": {
            "code": BIS_CODE,
            "name": BIS_NAME,
            "jurisdiction": "India",
            "tds_unit_note": "Sensor TDS is stored as mg/L; for dilute water 1 mg/L ≈ 1 ppm.",
            "official_limits": {
                "ph": "6.5–8.5",
                "tds_acceptable_mg_l": criteria.tds_acceptable_max,
                "tds_permissible_mg_l": criteria.tds_permissible_max,
                "turbidity_acceptable_ntu": criteria.turbidity_ntu_acceptable_max,
                "turbidity_permissible_ntu": criteria.turbidity_ntu_permissible_max,
            },
            "demo_rules": {
                "DEMO_STRICT_TDS_RULE": {
                    "enabled": criteria.demo_strict_tds_rule,
                    "applies_to": ["drinking"],
                    "strict_target_mg_l": criteria.strict_tds_target,
                    "is_official_standard": False,
                    "note": (
                        "Project-specific demo preference for the drinking profile only. "
                        "A value below the target is not an official determination that "
                        "the water is unsafe."
                    ),
                }
            },
        },
        "intended_use": intended_use,
        "intended_use_label": USE_LABELS[intended_use],
        "reading_mode": reading_mode,
        "reading_timestamp": reading_timestamp.isoformat() if reading_timestamp else None,
        "readings": {
            "ph": ph_eval,
            "tds": tds_eval,
            "turbidity": turbidity_eval,
            "temperature": temperature_eval,
        },
        "overall": {
            "status": status,
            "label": overall_label,
            "summary": rating_summary,
            "reasons": [detail["reason"] for detail in details],
            "reason_details": details,
        },
        "attention": attention,
        "suitability": suitability,
        "data_quality": {
            "demo_mode": reading_mode == "demo",
            "reading_mode": reading_mode,
            "freshness": "simulated" if reading_mode == "demo"
                         else ("stale" if stale else "fresh"),
            "age_seconds": age_seconds,
            "calibration_status": calibration_status,
            "calibration_verified": calibration_verified,
            "stability": stability,
            "errors": validation["errors"],
            "warnings": warnings,
        },
        "next_steps": _next_steps(
            intended_use, status, tds=tds_eval,
            calibration_verified=calibration_verified,
        ),
        "prediction": {
            "available": False,
            "message": "Future prediction unavailable — forecasting model not configured.",
            "model_version": None,
            "horizon_minutes": None,
        },
    }
