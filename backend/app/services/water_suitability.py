"""Water Suitability Assessment — standards-based screening from stored readings.

What this module is
-------------------
A deterministic, explainable assessment of which intended uses the available
measurements can support. It compares ONLY measurements that are genuinely
comparable to the applicable criterion:

- the reading must come from physical hardware (``source == "esp32"``);
- the sensor must report ``calibration_status == "calibrated"``;
- turbidity must be stored in NTU (the ESP32's provisional relative index is
  NOT NTU and is never compared against an NTU limit);
- the reading must be fresh (older readings are reported as stale, never as a
  current conclusion).

Simulated readings are labelled and excluded from threshold comparison. Missing
parameters are reported as missing — never inferred, never defaulted.

Standards implemented (verified values)
---------------------------------------
BIS IS 10500:2012, Drinking Water — Specification (Amendment 4), Table 1:

- pH 6.5–8.5 (acceptable; the standard allows NO relaxation)
- Total dissolved solids 500 mg/L acceptable / 2000 mg/L permissible
  (in the absence of an alternate source)
- Turbidity 1 NTU acceptable / 5 NTU permissible
- Microbiological (Table 6): E. coli / thermotolerant coliform shall not be
  detectable in any 100 mL sample — a laboratory test this station cannot run.

CPCB Designated Best Use (DBU) surface-water criteria (CPCB "Water Quality
Criteria" table):

- Class A (drinking source, disinfection only): pH 6.5–8.5, DO >= 6 mg/L,
  BOD5 <= 2 mg/L, total coliform <= 50 MPN/100 mL
- Class B (outdoor bathing): pH 6.5–8.5, DO >= 5 mg/L, BOD5 <= 3 mg/L,
  total coliform <= 500 MPN/100 mL
- Class D (wildlife and fisheries): pH 6.5–8.5, DO >= 4 mg/L,
  free ammonia <= 1.2 mg/L (as N)
- Class E (irrigation, industrial cooling, controlled waste disposal):
  pH 6.0–8.5, EC <= 2250 micromhos/cm at 25 C, SAR <= 26, boron <= 2 mg/L

A CPCB surface-water class is a source-water classification, NOT drinking-water
certification. The drinking-water assessment uses BIS IS 10500 and can never
conclude "safe to drink": microbiology and the unmeasured chemical parameters
require laboratory confirmation.

Result codes
------------
``preliminary_suitable``   every criterion for the use was measured and within
                           its acceptable limit (never emitted for drinking
                           water, whose required microbiological tests this
                           station cannot perform)
``treatment_required``     a measured value is inside the permissible (relaxed)
                           range, or the use requires treatment by its class
``outside_limits``         at least one measured value exceeds the applicable
                           limit
``lab_confirmation_required`` all measurable criteria pass but required
                           laboratory parameters are unavailable (drinking water)
``insufficient_data``      no comparable measurement, missing critical
                           parameters, or stale data
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("hydrasense.suitability")

RULESET_VERSION = "2026.10.1"

# Freshness thresholds mirror the dashboard's telemetry link states.
FRESH_WITHIN = timedelta(minutes=5)
DELAYED_WITHIN = timedelta(minutes=60)

# Provenance values that may be compared against a standard.
COMPARABLE_SOURCE = "esp32"
COMPARABLE_CALIBRATION = "calibrated"


@dataclass(frozen=True)
class Criterion:
    """One comparable limit from a documented standard."""

    key: str                       # reading field ("ph", "tds", "turbidity") or virtual key
    label: str
    unit: str
    acceptable_min: Optional[float] = None
    acceptable_max: Optional[float] = None
    permissible_min: Optional[float] = None
    permissible_max: Optional[float] = None
    reference: str = ""
    critical: bool = True


@dataclass(frozen=True)
class UseSpec:
    """A supported intended use and the standard that governs it."""

    code: str
    label: str
    standard_code: str
    standard_name: str
    description: str
    criteria: tuple[Criterion, ...]
    # Parameters the standard requires that this station cannot measure. They
    # are always reported as missing and block any "suitable" conclusion.
    required_unmeasured: tuple[tuple[str, str, str], ...] = ()  # (parameter, label, why)
    limitations: tuple[str, ...] = ()


BIS_REF = "BIS IS 10500:2012 (Amd. 4), Table 1"
CPCB_B = "CPCB DBU Class B (outdoor bathing)"
CPCB_D = "CPCB DBU Class D (wildlife & fisheries)"
CPCB_E = "CPCB DBU Class E (irrigation / industrial cooling)"

DRINKING_LIMITATIONS = (
    "BIS IS 10500 requires microbiological (E. coli / thermotolerant coliform) and "
    "chemical parameters this station does not measure; passing pH/TDS/turbidity "
    "never certifies drinking-water safety.",
    "A CPCB surface-water class describes a source water, not treated tap water.",
)

USES: tuple[UseSpec, ...] = (
    UseSpec(
        code="drinking",
        label="Drinking water",
        standard_code="BIS-IS-10500:2012",
        standard_name="BIS IS 10500:2012 Drinking Water — Specification (Amd. 4)",
        description="Potable use, assessed against BIS IS 10500 acceptable and permissible limits.",
        criteria=(
            Criterion(
                key="ph",
                label="pH",
                unit="",
                acceptable_min=6.5,
                acceptable_max=8.5,
                reference=f"{BIS_REF}: pH 6.5–8.5 (acceptable; no relaxation permitted)",
            ),
            Criterion(
                key="tds",
                label="Total dissolved solids",
                unit="mg/L",
                acceptable_max=500,
                permissible_max=2000,
                reference=f"{BIS_REF}: TDS 500 mg/L acceptable, 2000 mg/L permissible",
            ),
            Criterion(
                key="turbidity",
                label="Turbidity",
                unit="NTU",
                acceptable_max=1,
                permissible_max=5,
                reference=f"{BIS_REF}: turbidity 1 NTU acceptable, 5 NTU permissible",
            ),
        ),
        required_unmeasured=(
            ("ecoli", "E. coli / thermotolerant coliform", "Absence in 100 mL required (BIS IS 10500 Table 6) — laboratory test"),
            ("nitrate", "Nitrate (as NO3)", "45 mg/L limit — laboratory test"),
            ("fluoride", "Fluoride", "1.0 mg/L acceptable / 1.5 mg/L permissible — laboratory test"),
            ("arsenic", "Arsenic", "0.01 mg/L acceptable / 0.05 mg/L permissible — laboratory test"),
            ("lead", "Lead", "0.01 mg/L limit — laboratory test"),
            ("hardness", "Total hardness (as CaCO3)", "200 mg/L acceptable / 600 mg/L permissible — laboratory test"),
            ("chloride", "Chloride", "250 mg/L acceptable / 1000 mg/L permissible — laboratory test"),
            ("sulfate", "Sulfate", "200 mg/L acceptable / 400 mg/L permissible — laboratory test"),
        ),
        limitations=DRINKING_LIMITATIONS,
    ),
    UseSpec(
        code="domestic",
        label="Domestic use (non-drinking)",
        standard_code="BIS-IS-10500:2012",
        standard_name="BIS IS 10500:2012 Drinking Water — Specification (Amd. 4)",
        description=(
            "Household uses such as washing and cleaning. Domestic water that may be "
            "ingested is still governed by the drinking-water requirements."
        ),
        criteria=(
            Criterion(
                key="ph",
                label="pH",
                unit="",
                acceptable_min=6.5,
                acceptable_max=8.5,
                reference=f"{BIS_REF}: pH 6.5–8.5 (acceptable; no relaxation permitted)",
            ),
            Criterion(
                key="tds",
                label="Total dissolved solids",
                unit="mg/L",
                acceptable_max=500,
                permissible_max=2000,
                reference=f"{BIS_REF}: TDS 500 mg/L acceptable, 2000 mg/L permissible",
            ),
            Criterion(
                key="turbidity",
                label="Turbidity",
                unit="NTU",
                acceptable_max=1,
                permissible_max=5,
                reference=f"{BIS_REF}: turbidity 1 NTU acceptable, 5 NTU permissible",
            ),
        ),
        required_unmeasured=(
            ("ecoli", "E. coli / thermotolerant coliform", "Absence in 100 mL required for any potable domestic use — laboratory test"),
            ("hardness", "Total hardness (as CaCO3)", "200 mg/L acceptable / 600 mg/L permissible — laboratory test"),
            ("chloride", "Chloride", "250 mg/L acceptable / 1000 mg/L permissible — laboratory test"),
        ),
        limitations=(
            "Domestic water that can be ingested must satisfy the full drinking-water requirements.",
        ),
    ),
    UseSpec(
        code="bathing",
        label="Outdoor bathing",
        standard_code="CPCB-DBU-B",
        standard_name="CPCB Designated Best Use — Class B (outdoor bathing)",
        description="Organised outdoor bathing, assessed against CPCB Class B criteria.",
        criteria=(
            Criterion(key="ph", label="pH", unit="", acceptable_min=6.5, acceptable_max=8.5,
                      reference=f"{CPCB_B}: pH 6.5–8.5"),
        ),
        # Parameters this hardware does not measure (listed as required, never
        # evaluated as measurements): oxygen demand and microbiology.
        required_unmeasured=(
            ("dissolved_oxygen", "Dissolved oxygen", "CPCB Class B requires DO >= 5 mg/L — no DO sensor is installed"),
            ("bod", "BOD (5 days, 20 °C)", "CPCB Class B requires BOD5 <= 3 mg/L — laboratory test"),
            ("total_coliform", "Total coliform", "CPCB Class B requires <= 500 MPN/100 mL — laboratory test"),
        ),
        limitations=(
            "Bathing suitability depends on microbiology (total coliform) and oxygen "
            "demand, which this station does not measure.",
        ),
    ),
    UseSpec(
        code="irrigation",
        label="Irrigation",
        standard_code="CPCB-DBU-E",
        standard_name="CPCB Designated Best Use — Class E (irrigation)",
        description="Agricultural irrigation, assessed against CPCB Class E criteria.",
        criteria=(
            Criterion(key="ph", label="pH", unit="", acceptable_min=6.0, acceptable_max=8.5,
                      reference=f"{CPCB_E}: pH 6.0–8.5"),
        ),
        # EC, SAR and boron are required by CPCB Class E but are not measured
        # by this four-sensor station — reported as required, never evaluated.
        required_unmeasured=(
            ("ec", "Electrical conductivity", "CPCB Class E requires EC <= 2250 micromhos/cm at 25 °C — not measured here"),
            ("sar", "Sodium adsorption ratio", "CPCB Class E requires SAR <= 26 — needs full ion analysis"),
            ("boron", "Boron", "CPCB Class E requires boron <= 2 mg/L — laboratory test"),
        ),
        limitations=(
            "TDS is not electrical conductivity: a TDS reading cannot be substituted "
            "for the CPCB Class E conductivity limit.",
            "Crop-specific salinity/toxicity guidance (e.g. FAO irrigation water "
            "quality) needs EC, SAR, sodium, chloride and boron — not measured here.",
        ),
    ),
    UseSpec(
        code="industrial",
        label="Industrial cooling",
        standard_code="CPCB-DBU-E",
        standard_name="CPCB Designated Best Use — Class E (industrial cooling)",
        description="Industrial cooling water, assessed against CPCB Class E criteria.",
        criteria=(
            Criterion(key="ph", label="pH", unit="", acceptable_min=6.0, acceptable_max=8.5,
                      reference=f"{CPCB_E}: pH 6.0–8.5"),
        ),
        required_unmeasured=(
            ("ec", "Electrical conductivity", "CPCB Class E requires EC <= 2250 micromhos/cm at 25 °C — not measured here"),
        ),
        limitations=(
            "Actual cooling-system requirements (hardness, chloride, silica, scaling "
            "indices) depend on the plant and are not measured by this station.",
        ),
    ),
    UseSpec(
        code="aquatic_life",
        label="Aquatic life (fisheries)",
        standard_code="CPCB-DBU-D",
        standard_name="CPCB Designated Best Use — Class D (propagation of wildlife & fisheries)",
        description="Fisheries and wildlife propagation, assessed against CPCB Class D criteria.",
        criteria=(
            Criterion(key="ph", label="pH", unit="", acceptable_min=6.5, acceptable_max=8.5,
                      reference=f"{CPCB_D}: pH 6.5–8.5"),
        ),
        required_unmeasured=(
            ("dissolved_oxygen", "Dissolved oxygen", "CPCB Class D requires DO >= 4 mg/L — no DO sensor is installed"),
            ("free_ammonia", "Free ammonia (as N)", "CPCB Class D requires free ammonia <= 1.2 mg/L — laboratory test"),
        ),
        limitations=(
            "Dissolved oxygen and free ammonia are not measured by this station; "
            "ecological suitability also depends on habitat and toxicants.",
        ),
    ),
)

USES_BY_CODE = {use.code: use for use in USES}

RESULT_LABELS = {
    "preliminary_suitable": "Preliminary screening indicates potential suitability for this use",
    "treatment_required": "Treatment or further assessment required",
    "outside_limits": "One or more measured criteria are outside the applicable limits",
    "lab_confirmation_required": "Laboratory confirmation required",
    "insufficient_data": "Insufficient data to determine suitability",
}

STATUS_LABELS = {
    "within_acceptable": "Within acceptable limit",
    "within_permissible": "Within permissible limit (relaxed)",
    "outside_limits": "Outside the applicable limit",
    "not_measured": "Not measured",
    "not_comparable": "Not comparable to this criterion",
}


# ---------------------------------------------------------------------------
# Measurement extraction
# ---------------------------------------------------------------------------

@dataclass
class Measurement:
    value: Optional[float]
    unit: str
    provenance: str          # "esp32" | "simulator" | "unknown"
    measured: bool
    comparable: bool
    reason: Optional[str] = None


def _diag(reading: Any, key: str) -> dict:
    diagnostics = getattr(reading, "diagnostics", None) or {}
    entry = diagnostics.get(key) if isinstance(diagnostics, dict) else None
    return entry if isinstance(entry, dict) else {}


def _measurement(reading: Any, key: str) -> Measurement:
    """Resolve one parameter's value and whether it may be compared to a limit."""
    if reading is None:
        return Measurement(None, "", "unknown", False, False, "No reading available")

    source = (getattr(reading, "source", None) or "unknown").lower()

    if key == "turbidity":
        value = getattr(reading, "turbidity", None)
        unit_tag = getattr(reading, "turbidity_unit", None)
        # Display unit reflects what was actually stored — never "NTU" for a
        # relative index.
        if unit_tag == "ntu":
            unit = "NTU"
        elif unit_tag == "relative_index_0_100":
            unit = "index 0–100 (not NTU)"
        else:
            unit = unit_tag or ""
        if value is None:
            return Measurement(None, unit, source, False, False, "No turbidity value stored")
        if source != COMPARABLE_SOURCE:
            return Measurement(value, unit, source, True, False,
                               f"Simulated demonstration value ({source}) — not compared to a standard")
        if unit_tag != "ntu":
            return Measurement(
                value, unit, source, True, False,
                "Reported as a provisional relative index, not NTU — not comparable to an NTU limit",
            )
        status = _diag(reading, "turbidity").get("calibration_status")
        if status != COMPARABLE_CALIBRATION:
            shown = status or "no calibration status reported"
            return Measurement(
                value, unit, source, True, False,
                f"Uncalibrated turbidity estimate ({shown}) — not compared to an NTU limit",
            )
        return Measurement(value, unit, source, True, True)

    if key in ("ph", "tds"):
        attr = "ph" if key == "ph" else "tds"
        value = getattr(reading, attr, None)
        unit = "" if key == "ph" else "mg/L"
        if value is None:
            return Measurement(None, unit, source, False, False, "No value stored for this reading")
        if source != COMPARABLE_SOURCE:
            return Measurement(value, unit, source, True, False,
                               f"Simulated demonstration value ({source}) — not compared to a standard")
        status = _diag(reading, key).get("calibration_status")
        if status != COMPARABLE_CALIBRATION:
            shown = status or "no calibration status reported"
            return Measurement(value, unit, source, True, False,
                               f"Uncalibrated/provisional estimate ({shown}) — not compared to a standard")
        return Measurement(value, unit, source, True, True)

    # Parameters this station does not measure (DO, BOD, coliform, EC, SAR, ...).
    return Measurement(None, "", source, False, False,
                       "Not measured by this station")


def _age(reading: Any, now: datetime) -> Optional[timedelta]:
    if reading is None or getattr(reading, "timestamp", None) is None:
        return None
    timestamp = reading.timestamp
    if timestamp.tzinfo is None:          # SQLite returns naive datetimes
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return now - timestamp


def _freshness(age: Optional[timedelta]) -> str:
    if age is None:
        return "no_data"
    if age <= FRESH_WITHIN:
        return "fresh"
    if age <= DELAYED_WITHIN:
        return "delayed"
    return "stale"


# ---------------------------------------------------------------------------
# Criterion evaluation
# ---------------------------------------------------------------------------

def _evaluate(criterion: Criterion, measurement: Measurement) -> dict:
    entry: dict[str, Any] = {
        "parameter": criterion.key,
        "label": criterion.label,
        # The stored value's own unit (e.g. the relative index), falling back to
        # the criterion unit only when the value carries none (pH).
        "unit": measurement.unit or criterion.unit,
        "value": measurement.value,
        "reference": criterion.reference,
        "critical": criterion.critical,
    }

    if not measurement.measured:
        entry.update(status="not_measured", status_label=STATUS_LABELS["not_measured"],
                     note=measurement.reason)
        return entry

    if not measurement.comparable:
        entry.update(status="not_comparable", status_label=STATUS_LABELS["not_comparable"],
                     note=measurement.reason)
        return entry

    value = measurement.value
    assert value is not None

    within_acceptable = (
        (criterion.acceptable_min is None or value >= criterion.acceptable_min)
        and (criterion.acceptable_max is None or value <= criterion.acceptable_max)
    )
    if within_acceptable:
        entry.update(status="within_acceptable", status_label=STATUS_LABELS["within_acceptable"])
        return entry

    if criterion.permissible_min is not None or criterion.permissible_max is not None:
        within_permissible = (
            (criterion.permissible_min is None or value >= criterion.permissible_min)
            and (criterion.permissible_max is None or value <= criterion.permissible_max)
        )
        if within_permissible:
            entry.update(
                status="within_permissible",
                status_label=STATUS_LABELS["within_permissible"],
                note="Only the relaxed permissible limit is met; treatment or an alternate source is required.",
            )
            return entry

    entry.update(status="outside_limits", status_label=STATUS_LABELS["outside_limits"])
    return entry


def _result_code(use: UseSpec, evaluated: list[dict], freshness: str) -> str:
    if freshness == "stale":
        return "insufficient_data"
    if any(e["status"] == "outside_limits" for e in evaluated):
        return "outside_limits"
    if any(e["status"] == "within_permissible" for e in evaluated):
        return "treatment_required"
    if not any(e["status"] in ("within_acceptable", "within_permissible") for e in evaluated):
        return "insufficient_data"

    compared = {e["parameter"] for e in evaluated if e["status"] == "within_acceptable"}
    critical = {c.key for c in use.criteria if c.critical}

    # A use can only be called preliminarily suitable when every critical
    # criterion was actually measured and passed — otherwise data is missing.
    if critical <= compared:
        if use.code in ("drinking", "domestic"):
            # Microbiology and the remaining BIS chemical parameters are not
            # measurable here, so safety can never be concluded.
            return "lab_confirmation_required"
        if use.required_unmeasured:
            # The standard needs parameters this station does not measure, so
            # passing the measured subset must never read as suitability.
            return "insufficient_data"
        return "preliminary_suitable"

    return "insufficient_data"


def _explain(use: UseSpec, code: str, evaluated: list[dict], freshness: str,
            age: Optional[timedelta]) -> str:
    passed = [e["label"] for e in evaluated if e["status"] == "within_acceptable"]
    relaxed = [e["label"] for e in evaluated if e["status"] == "within_permissible"]
    failed = [e["label"] for e in evaluated if e["status"] == "outside_limits"]
    unmeasured = [e["label"] for e in evaluated if e["status"] in ("not_measured", "not_comparable")]

    if freshness == "stale":
        hours = int(age.total_seconds() // 3600) if age else None
        return (
            f"The latest reading is older than {DELAYED_WITHIN.total_seconds() / 60:.0f} minutes"
            + (f" ({hours} h old)" if hours is not None else "")
            + ", so no current suitability conclusion is drawn for this use."
        )

    parts: list[str] = []
    if failed:
        parts.append(f"Outside the applicable limits: {', '.join(failed)}.")
    if relaxed:
        parts.append(f"Only the relaxed permissible limit is met for: {', '.join(relaxed)}.")
    if passed:
        parts.append(f"Within acceptable limits: {', '.join(passed)}.")
    if unmeasured:
        parts.append(f"Not available for comparison: {', '.join(unmeasured)}.")
    if use.required_unmeasured:
        parts.append(
            "Required by the applicable standard but not measured by this station: "
            + ", ".join(label for _key, label, _why in use.required_unmeasured)
            + "."
        )
    if code == "lab_confirmation_required":
        parts.append(
            "Required BIS parameters (microbiological and unmeasured chemical tests) "
            "need laboratory confirmation before any drinking-water conclusion."
        )
    if code == "insufficient_data" and not parts:
        parts.append("No comparable measurement is available for this use.")
    return " ".join(parts)


def _missing(use: UseSpec, evaluated: list[dict]) -> list[dict]:
    missing = [
        {
            "parameter": e["parameter"],
            "label": e["label"],
            "why": e.get("note") or "Not measured by this station",
            "required_by": use.standard_name,
        }
        for e in evaluated
        if e["status"] in ("not_measured", "not_comparable")
    ]
    for key, label, why in use.required_unmeasured:
        missing.append(
            {
                "parameter": key,
                "label": label,
                "why": why,
                "required_by": use.standard_name,
            }
        )
    return missing


# ---------------------------------------------------------------------------
# Public API of the service
# ---------------------------------------------------------------------------

def assess_use(use: UseSpec, reading: Any, now: Optional[datetime] = None) -> dict[str, Any]:
    """Assess one intended use against one reading."""
    now = now or datetime.now(timezone.utc)
    age = _age(reading, now)
    freshness = _freshness(age)

    evaluated = [_evaluate(criterion, _measurement(reading, criterion.key))
                 for criterion in use.criteria]
    code = _result_code(use, evaluated, freshness)
    missing = _missing(use, evaluated)

    measured_values = []
    if reading is not None:
        for key, label, unit in (
            ("ph", "pH", ""),
            ("tds", "Total dissolved solids", "mg/L"),
            ("turbidity", "Turbidity", (getattr(reading, "turbidity_unit", None) or "")),
            ("temperature", "Temperature", "°C"),
        ):
            value = getattr(reading, key, None)
            if value is not None:
                measured_values.append({
                    "parameter": key,
                    "label": label,
                    "value": value,
                    "unit": (
                        "index 0–100 (not NTU)" if unit == "relative_index_0_100"
                        else "NTU" if unit == "ntu"
                        else unit
                    ),
                    "source": getattr(reading, "source", "unknown"),
                })

    return {
        "use": use.code,
        "use_label": use.label,
        "description": use.description,
        "standard_code": use.standard_code,
        "standard": use.standard_name,
        "ruleset_version": RULESET_VERSION,
        "result": code,
        "result_label": RESULT_LABELS[code],
        "summary": _explain(use, code, evaluated, freshness, age),
        "parameters": evaluated,
        "missing_parameters": missing,
        "measured_values": measured_values,
        "limitations": list(use.limitations),
        "data_quality": {
            "freshness": freshness,
            "age_seconds": int(age.total_seconds()) if age is not None else None,
            "reading_id": getattr(reading, "id", None),
            "reading_timestamp": (
                (reading.timestamp.replace(tzinfo=timezone.utc)
                 if reading.timestamp.tzinfo is None else reading.timestamp).isoformat()
                if reading is not None and getattr(reading, "timestamp", None) is not None
                else None
            ),
            "device_source": getattr(reading, "source", None),
            "comparable_parameters": [
                e["parameter"] for e in evaluated
                if e["status"] in ("within_acceptable", "within_permissible", "outside_limits")
            ],
            "excluded_parameters": [
                {"parameter": e["parameter"], "reason": e.get("note")}
                for e in evaluated if e["status"] == "not_comparable"
            ],
        },
    }


def assess_reading(reading: Any, use_codes: Optional[Iterable[str]] = None,
                   now: Optional[datetime] = None) -> list[dict[str, Any]]:
    """Assess every supported use (or the requested subset) for one reading."""
    now = now or datetime.now(timezone.utc)
    codes = list(use_codes) if use_codes else [use.code for use in USES]
    unknown = [code for code in codes if code not in USES_BY_CODE]
    if unknown:
        raise ValueError(f"Unsupported intended use(s): {', '.join(sorted(unknown))}")
    return [assess_use(USES_BY_CODE[code], reading, now=now) for code in codes]


def _to_record(station_id: int, assessment: dict[str, Any]) -> dict[str, Any]:
    """Map an assessment dict onto the WaterSuitabilityAssessment columns."""
    quality = assessment["data_quality"]
    reading_timestamp = quality.get("reading_timestamp")
    return {
        "station_id": station_id,
        "reading_id": quality["reading_id"],
        "reading_timestamp": (
            datetime.fromisoformat(reading_timestamp) if reading_timestamp else None
        ),
        "use_code": assessment["use"],
        "standard_code": assessment["standard_code"],
        "standard_version": assessment["ruleset_version"],
        "result_code": assessment["result"],
        "result_label": assessment["result_label"],
        "summary": assessment["summary"],
        "parameters": assessment["parameters"],
        "missing_parameters": assessment["missing_parameters"],
        "measured_values": assessment["measured_values"],
        "data_quality": quality,
        "limitations": assessment["limitations"],
    }


def persist_assessments(db: Session, station_id: int,
                        assessments: list[dict[str, Any]]) -> None:
    """Store assessments for their input reading (idempotent per reading+use).

    Recalculating for the same reading never duplicates rows; a new reading
    produces a new set, which is how the history accumulates.
    """
    from app.models.water import WaterSuitabilityAssessment  # local import (avoid cycles)

    for assessment in assessments:
        reading_id = assessment["data_quality"]["reading_id"]
        if reading_id is None:
            continue  # nothing to attach the assessment to
        exists = (
            db.query(WaterSuitabilityAssessment.id)
            .filter(
                WaterSuitabilityAssessment.reading_id == reading_id,
                WaterSuitabilityAssessment.use_code == assessment["use"],
                WaterSuitabilityAssessment.standard_version == RULESET_VERSION,
            )
            .first()
        )
        if exists:
            continue
        db.add(WaterSuitabilityAssessment(**_to_record(station_id, assessment)))
    db.commit()
