"""Rule-based recommendations derived from triggered screening rules.

Scope and rules of this module:

- Recommendations are returned ONLY when a use is ``caution``,
  ``outside_configured_ranges`` or ``insufficient_data``. A result inside the
  configured ranges returns an empty recommendation set — no advice is invented
  for a rule that did not fire.
- Every recommendation is keyed by ``(use, parameter, direction)`` and is built
  from the parameter entry the engine actually evaluated: the advice can never
  mention a parameter the rule was not about.
- Only the four measured inputs (pH, TDS, turbidity, temperature) plus data
  quality (freshness / stability / calibration) can appear as a cause or an
  action. Unmeasured quantities (microbiology, dissolved oxygen, EC/SAR,
  heavy metals, rainfall, location, ML outputs, history) are never used as a
  cause, and are only ever named in ``missing_assessments``, which states
  explicitly that this hardware does not measure them.
- Causes are worded as *possible*, never asserted: a single reading cannot
  identify a source.
- Drinking advice never claims that treatment or re-testing makes water safe,
  and always ends with laboratory confirmation.
- Temperature carries no advice: there is no configured temperature threshold,
  so it cannot drive an action.
- The LLM layer (when present) may only rephrase these strings; it may not add
  facts, parameters or verdicts.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from app.services.screening_states import (
    CAUTION,
    INSUFFICIENT,
    OUTSIDE,
    WITHIN,
    canonical_state,
)

# The closed vocabularies this module accepts.
USES: Tuple[str, ...] = (
    "drinking",
    "domestic",
    "irrigation",
    "swimming",
    "general",
    "aquaculture",
)
PARAMETERS: Tuple[str, ...] = ("ph", "tds", "turbidity", "data_quality")
DIRECTIONS: Tuple[str, ...] = (
    "below",
    "below_target",
    "above",
    "above_severe",
    "missing",
    "unvalidated",
    "invalid",
)
URGENCY_LEVELS: Tuple[str, ...] = ("low", "medium", "high")

# Status -> direction, for engines that do not carry a direction themselves.
STATUS_DIRECTION: Dict[str, str] = {
    "below_reference": "below",
    "above_reference": "above",
    "below_project_target": "below_target",
    "above_acceptable": "above",
    "above_permissible": "above_severe",
    "slight_restriction": "above",
    "severe_restriction": "above_severe",
    "outside_limits": "above",          # refined from value bounds when present
    "within_permissible": "above",      # refined from value bounds when present
    "not_measured": "missing",
    "not_comparable": "unvalidated",
    "invalid": "invalid",
}

# Unmeasured quantities. Guarded by tests: no ``possible_causes`` or ``actions``
# string may name any of them — only ``missing_assessments`` may.
UNMEASURED_TERMS: Tuple[str, ...] = (
    "dissolved oxygen",
    "bacteria",
    "bacterial",
    "microbiol",
    "coliform",
    "e. coli",
    "legionella",
    "heavy metal",
    "lead",
    "arsenic",
    "nitrate",
    "nitrite",
    "pesticide",
    "ammonia",
    "salinity",
    "sodium adsorption",
    "specific conductance",
    "electrical conductivity",
    "rainfall",
    "river location",
    "anomaly score",
    "ml prediction",
    "forecast",
)

_LAB_DRINKING = (
    "Arrange laboratory confirmation before relying on this water: these four "
    "sensors cannot confirm that the water is safe."
)

# What this hardware cannot assess for each use. Named only here, always as
# "not measured by these sensors".
MISSING_ASSESSMENTS: Dict[str, List[str]] = {
    "drinking": [
        "Microbiological indicators and chemical contaminants beyond pH, TDS, "
        "temperature and turbidity are not measured by these sensors — they "
        "require laboratory testing.",
    ],
    "domestic": [
        "Parameters that vary by domestic activity (including microbiological "
        "and chemical contaminants) are not measured by these sensors.",
    ],
    "irrigation": [
        "EC, SAR, chloride and boron are not measured by these sensors; "
        "electrical conductivity and sodium adsorption ratio in particular "
        "are required for a validated irrigation assessment.",
    ],
    "swimming": [
        "Microbiological indicators required for recreational-water assessment "
        "are not measured by these sensors.",
    ],
    "general": [
        "This screening covers the four measured indicators only; any other "
        "water-quality parameter is not measured by these sensors, so keep "
        "the water away from drinking or cooking uses until separately "
        "assessed.",
    ],
    "aquaculture": [
        "Dissolved oxygen, ammonia, nitrite, salinity and species-specific "
        "criteria are not measured by these sensors, so no aquaculture "
        "suitability verdict can be produced from them.",
    ],
}


def _rule(
    urgency: str,
    causes: Sequence[str],
    actions: Sequence[str],
    avoid: Sequence[str],
) -> Dict[str, Any]:
    if urgency not in URGENCY_LEVELS:
        raise ValueError(f"Unknown urgency: {urgency!r}")
    return {
        "urgency": urgency,
        "possible_causes": list(causes),
        "actions": list(actions),
        "avoid": list(avoid),
    }


def _ph_rules(use: str, *, lab: Optional[str]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    """pH outside the configured range for one use."""
    actions_common = [
        "Re-sample at the same point and repeat the pH measurement before "
        "acting on it.",
        "Check the pH probe against a fresh buffer and record the calibration "
        "date.",
    ]
    actions_high = actions_common + [
        "Check for alkaline contact near the sampling point (cement, ash or "
        "carbonate-rich runoff) while the repeat reading is taken.",
    ]
    actions_low = actions_common + [
        "Check for acidic influence near the sampling point (organic decay, "
        "acid drainage or CO2-rich inflow) while the repeat reading is taken.",
    ]
    avoid = ["Avoid using this water for drinking or cooking until a repeat reading is inside the configured range."]
    if lab:
        actions_high = actions_high + [lab]
        actions_low = actions_low + [lab]
    return {
        (use, "ph", "above"): _rule(
            "high",
            [
                "Possible alkaline influence such as carbonate-rich geology, "
                "cement contact or an upstream discharge — a single reading "
                "cannot identify the source.",
                "Possible pH probe drift or a stale calibration.",
            ],
            actions_high,
            avoid,
        ),
        (use, "ph", "below"): _rule(
            "high",
            [
                "Possible acidic influence such as acid drainage, "
                "CO₂-rich water or an upstream discharge — a single reading "
                "cannot identify the source.",
                "Possible pH probe drift or a stale calibration.",
            ],
            actions_low,
            avoid,
        ),
    }


def _missing_value_rules(use: str, *, lab: Optional[str]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    """A sensor that reported no value, or reported an impossible one."""
    out: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for parameter in ("ph", "tds", "turbidity"):
        actions = [
            "Check the sensor connection, power and probe condition, then "
            "capture a fresh reading.",
            "Do not base a use decision on an absent value: no value is not a "
            "passing value.",
        ]
        if lab:
            actions.append(lab)
        out[(use, parameter, "missing")] = _rule(
            "medium",
            [
                "This sensor reported no value for the reading — the cause is "
                "a device, wiring or probe fault, not a water-quality finding.",
            ],
            actions,
            ["Avoid treating a missing value as evidence that the parameter is within range."],
        )
        invalid_actions = [
            "Verify the probe and re-sample, then repeat the measurement with a "
            "checked instrument.",
            "Record the sensor fault so the reading history shows why this "
            "value was rejected.",
        ]
        if lab:
            invalid_actions.append(lab)
        out[(use, parameter, "invalid")] = _rule(
            "medium",
            [
                "An out-of-range value normally indicates a sensor fault "
                "rather than a real measurement.",
            ],
            invalid_actions,
            ["Avoid acting on this value until it has been reproduced with a verified probe."],
        )
    return out


def _turbidity_rules(use: str, *, lab: Optional[str]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    actions_above = [
        "Re-sample after the water settles and compare it with the stored "
        "reading.",
        "Inspect the sampling point and any upstream activity that could "
        "stir up sediment.",
    ]
    actions_severe = list(actions_above) + [
        "Do not rely on this water for the intended use until a repeat reading "
        "is inside the configured range.",
    ]
    if lab:
        actions_above = actions_above + [lab]
        actions_severe = actions_severe + [lab]
    return {
        (use, "turbidity", "above"): _rule(
            "medium",
            [
                "Possible suspended sediment from runoff, bank disturbance or "
                "turbulence upstream — not confirmed by this reading.",
                "Possible air bubbles or a fouled optical surface on the sensor.",
            ],
            actions_above,
            ["Avoid drawing a conclusion from a single elevated reading."],
        ),
        (use, "turbidity", "above_severe"): _rule(
            "high",
            [
                "Possible heavy sediment load from runoff, discharge or "
                "disturbance upstream — not confirmed by this reading.",
                "Possible air bubbles or a fouled optical surface on the sensor.",
            ],
            actions_severe,
            ["Avoid using this water for the intended purpose until it is re-tested."],
        ),
        (use, "turbidity", "unvalidated"): _rule(
            "medium",
            [
                "The turbidity sensor reports a relative index that is not "
                "calibrated NTU — this is a measurement limitation, not a "
                "finding about the water.",
            ],
            [
                "Calibrate the turbidity sensor against reference standards "
                "before treating the value as a turbidity limit.",
                "Use the index only as a trend indicator until calibration is "
                "recorded.",
            ]
            + ([lab] if lab else []),
            [
                "Avoid comparing the index value with an NTU limit or "
                "presenting it as an NTU measurement.",
            ],
        ),
    }


def _data_quality_rules(use: str, *, lab: Optional[str]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    missing_actions = [
        "Wait for a fresh, stable window of readings and re-run the assessment.",
        "Check the station connection and sampling interval if no fresh window "
        "arrives.",
    ]
    unverified_actions = [
        "Calibrate the probes with reference solutions, record the calibration "
        "date, then re-assess.",
    ]
    if lab:
        missing_actions.append(lab)
        unverified_actions.append(lab)
    return {
        (use, "data_quality", "missing"): _rule(
            "medium",
            [
                "No fresh, stable four-sensor window is available: the reading "
                "is stale, unstable or incomplete, so no conclusion can be drawn.",
            ],
            missing_actions,
            ["Avoid making a use decision from an old or unstable reading."],
        ),
        (use, "data_quality", "unvalidated"): _rule(
            "medium",
            [
                "Sensor calibration is unverified or provisional — stability "
                "of a reading does not prove it is calibrated.",
            ],
            unverified_actions,
            ["Avoid presenting a stable reading as a calibrated measurement."],
        ),
    }


def _build_rules() -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    """Assemble the flat (use, parameter, direction) rule table."""
    rules: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    # Shared per-use advice lines that do not name an unmeasured parameter.
    drinking_lab = _LAB_DRINKING
    domestic_lab = (
        "Obtain laboratory confirmation for any domestic use that involves "
        "ingestion before relying on this water."
    )

    for use in USES:
        lab = drinking_lab if use == "drinking" else (domestic_lab if use == "domestic" else None)

        # --- pH -----------------------------------------------------------
        rules.update(_ph_rules(use, lab=lab))

        # --- TDS ----------------------------------------------------------
        if use == "drinking":
            rules[(use, "tds", "below_target")] = _rule(
                "low",
                [
                    "Possible very soft or low-mineral water, or a TDS probe "
                    "under-reading — the project target is a screening "
                    "preference, not a safety finding.",
                ],
                [
                    "Repeat the measurement to confirm the low reading.",
                    "Treat this as a project screening flag only; low TDS on "
                    "its own does not classify the water.",
                    drinking_lab,
                ],
                ["Avoid treating a low TDS value as evidence of potability."],
            )

        tds_above_actions = [
            "Re-sample and repeat the TDS measurement before acting on it.",
            "Inspect the intake and any upstream discharge points that could "
            "raise dissolved solids.",
        ]
        tds_avoid = ["Avoid relying on this water for the intended use until the reading is re-confirmed."]
        if lab:
            tds_above_actions.append(lab)

        rules[(use, "tds", "above")] = _rule(
            "medium",
            [
                "Possible elevated dissolved solids from an upstream discharge, "
                "runoff or mineral-rich geology — a single reading cannot "
                "identify the source.",
                "Possible probe fouling or calibration drift inflating the "
                "reading.",
            ],
            tds_above_actions,
            tds_avoid,
        )
        rules[(use, "tds", "above_severe")] = _rule(
            "high",
            [
                "Possible strong dissolved-solids load from an upstream "
                "discharge, runoff or mineral-rich geology — not confirmed by "
                "this reading.",
                "Possible probe fouling or calibration drift inflating the "
                "reading.",
            ],
            [
                "Re-sample and repeat the TDS measurement before acting on it.",
                "Inspect the intake and any upstream discharge points that could "
                "raise dissolved solids.",
                "Do not rely on this water for the intended use until the "
                "reading is re-confirmed.",
            ]
            + ([lab] if lab else []),
            tds_avoid,
        )

        # --- Turbidity ----------------------------------------------------
        rules.update(_turbidity_rules(use, lab=lab))

        # --- Data quality -------------------------------------------------
        rules.update(_data_quality_rules(use, lab=lab))

    return rules


#: The complete rule table, keyed by (use, parameter, direction).
RULES: Dict[Tuple[str, str, str], Dict[str, Any]] = _build_rules()


def direction_for(entry: Mapping[str, Any]) -> Optional[str]:
    """Direction of a parameter entry, or None when it carries no concern."""
    explicit = entry.get("direction")
    if isinstance(explicit, str) and explicit in DIRECTIONS:
        return explicit
    return STATUS_DIRECTION.get(str(entry.get("status", "")))


def build(
    *,
    use: str,
    state: str,
    entries: Iterable[Mapping[str, Any]],
    authority: bool = False,
) -> Dict[str, Any]:
    """Recommendations for one assessment.

    ``entries`` are the engine's own evaluated parameter entries (with
    ``parameter``/``status``/``label`` and, where available, ``value`` and
    ``direction``). Returns an empty ``recommendations`` list when the result
    is ``within_configured_ranges``.
    """
    if state == WITHIN or use not in USES:
        return {
            "recommendations": [],
            "missing_assessments": [],
            "urgency": None,
            "authority_actions": [],
        }

    recommendations: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()
    for entry in entries:
        parameter = str(entry.get("parameter", ""))
        if parameter not in ("ph", "tds", "turbidity", "data_quality"):
            # Temperature and any other entry carry no rule: no threshold means
            # no advice.
            continue
        direction = direction_for(entry)
        if direction is None:
            continue
        rule = RULES.get((use, parameter, direction))
        if rule is None:
            continue
        if (parameter, direction) in seen:
            continue
        seen.add((parameter, direction))
        recommendations.append(
            {
                "parameter": parameter,
                "label": entry.get("label") or parameter,
                "direction": direction,
                "status": entry.get("status"),
                "value": entry.get("value"),
                "unit": entry.get("unit") or "",
                "reason": entry.get("reason") or entry.get("note") or entry.get("status_label"),
                **rule,
            }
        )

    if not recommendations:
        # The result is not a pass but no single parameter rule fired (stale,
        # unstable or uncalibrated window): the honest advice is about data
        # quality, never about a parameter.
        rule = RULES[(use, "data_quality", "missing")]
        recommendations.append(
            {
                "parameter": "data_quality",
                "label": "Reading quality",
                "direction": "missing",
                "status": "not_available",
                "value": None,
                "unit": "",
                "reason": (
                    "The assessment could not be completed from the available "
                    "readings."
                ),
                **rule,
            }
        )

    urgency: Optional[str] = None
    for item in recommendations:
        if urgency is None or URGENCY_LEVELS.index(item["urgency"]) > URGENCY_LEVELS.index(urgency):
            urgency = item["urgency"]

    missing = list(MISSING_ASSESSMENTS.get(use, [])) if recommendations else []
    return {
        "recommendations": recommendations,
        "missing_assessments": missing,
        "urgency": urgency,
        "authority_actions": authority_actions(use=use, state=state) if authority else [],
    }


def authority_actions(*, use: str, state: str) -> List[str]:
    """Incident workflow steps for an authority facing a non-passing result."""
    steps: List[str] = []
    if state == INSUFFICIENT:
        steps.append(
            "Confirm data quality first: check the station connection, "
            "calibration status and reading freshness before opening an "
            "incident."
        )
    if state in (CAUTION, OUTSIDE, INSUFFICIENT):
        steps.append(
            "Record the triggering reading and time window, then collect a "
            "labelled grab sample at the station."
        )
    steps.append(
        "Inspect the upstream stretch and any nearby outfalls for visible "
        "discharge or disturbance."
    )
    steps.append(
        "Notify the pollution control authority and raise an incident with the "
        "stored readings and alert reason attached."
    )
    steps.append(
        "Track the laboratory result against the incident until it is resolved."
    )
    return steps


def _entries_from_screening(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Entries of the canonical screening engine, including data-quality."""
    entries: List[Dict[str, Any]] = list(result.get("readings", {}).values())
    for detail in result.get("overall", {}).get("reason_details", []):
        if detail.get("parameter") in ("calibration", "stability"):
            direction = "missing" if detail.get("parameter") == "stability" else "unvalidated"
            entries.append(
                {
                    "parameter": "data_quality",
                    "label": detail.get("label") or "Reading quality",
                    "status": detail.get("status"),
                    "status_label": detail.get("status_label"),
                    "value": detail.get("value"),
                    "unit": detail.get("unit") or "",
                    "reason": detail.get("reason"),
                    "direction": direction,
                }
            )
    return entries


def for_screening(result: Mapping[str, Any], *, authority: bool = False) -> Dict[str, Any]:
    """Recommendations for a canonical four-parameter screening result."""
    state = result.get("overall", {}).get("state") or canonical_state(
        result.get("overall", {}).get("status", ""), engine="screening"
    )
    return build(
        use=result.get("intended_use", ""),
        state=state,
        entries=_entries_from_screening(result),
        authority=authority,
    )


def for_station_assessment(
    assessment: Mapping[str, Any], *, authority: bool = False
) -> Dict[str, Any]:
    """Recommendations for a station (public/authority) assessment record."""
    state = assessment.get("state") or canonical_state(
        assessment.get("result", ""), engine="station"
    )
    return build(
        use=assessment.get("use", ""),
        state=state,
        entries=assessment.get("parameters", []),
        authority=authority,
    )


__all__ = [
    "USES",
    "PARAMETERS",
    "DIRECTIONS",
    "URGENCY_LEVELS",
    "UNMEASURED_TERMS",
    "STATUS_DIRECTION",
    "RULES",
    "MISSING_ASSESSMENTS",
    "build",
    "direction_for",
    "authority_actions",
    "for_screening",
    "for_station_assessment",
]
