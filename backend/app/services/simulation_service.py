"""Three-river simulation mode — SIMULATED DATA, NOT LIVE SENSOR DATA.

Generates plausible randomised readings for exactly the four sensors this
project supports (pH, TDS, temperature, turbidity index) for the three
demonstration rivers:

- Arkavathi River
- Cauvery River
- Vrishabhavathi River

Every sample is persisted to ``sensor_readings`` with ``source = "simulator"``
so it is always distinguishable from physical ESP32 telemetry (``source =
"esp32"``). Simulated readings are never mixed into ML ground truth: the
relative-index turbidity unit keeps them out of the NTU-trained inference path,
exactly like hardware index rows.

Scenarios
---------
``normal``                  random variation around the river baseline
``gradual_deterioration``   steady drift toward cloudier, higher-TDS water
``sudden_change``           stable, then an abrupt step change
``sensor_fault``            one sensor stops reporting (stored as NULL — a
                            sensor fault never fabricates a value)

Reproducibility: pass ``seed`` for a repeatable sequence (used by tests).

The turbidity index follows the firmware's documented direction and bands
(``firmware/hydrasense_esp32``): 0-100, higher = cloudier,
CLEARER < 30, MODERATE 30-54, CLOUDIER >= 55. It is never NTU.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.water import MonitoringStation, SensorReading
from app.services.water_suitability import assess_reading, persist_assessments

SCENARIOS = (
    "normal",
    "gradual_deterioration",
    "sudden_change",
    "sensor_fault",
)

DEFAULT_INTERVAL_SECONDS = 5.0
MAX_KEPT_SAMPLES = 50

TURBIDITY_UNIT_RELATIVE = "relative_index_0_100"

# Demonstration baselines per river (plausible surface-water ranges only).
# These are SIMULATED starting points, not measured field values.
RIVER_BASELINES: Dict[str, Dict[str, float]] = {
    "ARKAVATHI": {"ph": 7.2, "tds": 320.0, "temperature": 26.5, "turbidity_index": 26.0},
    "CAUVERY": {"ph": 7.4, "tds": 280.0, "temperature": 27.2, "turbidity_index": 20.0},
    "VRISHABHAVATHI": {"ph": 7.0, "tds": 380.0, "temperature": 27.8, "turbidity_index": 38.0},
}
DEFAULT_BASELINE = {"ph": 7.2, "tds": 320.0, "temperature": 26.5, "turbidity_index": 30.0}

FAULT_SENSORS = ("temperature", "tds", "ph", "turbidity_index")


def turbidity_band(index: float) -> str:
    """Firmware-compatible band for the relative index (NOT NTU)."""
    if index < 30.0:
        return "CLEARER"
    if index < 55.0:
        return "MODERATE"
    return "CLOUDIER"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class SimulationState:
    """Process-wide simulation control state (demo controls, not user data)."""

    running: bool = False
    station_code: Optional[str] = None
    source_code: Optional[str] = None
    scenario: str = "normal"
    seed: Optional[int] = None
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS
    step: int = 0
    samples_generated: int = 0
    started_at: Optional[datetime] = None
    last_sample_at: Optional[datetime] = None
    last_fault_sensor: Optional[str] = None
    recent_samples: List[Dict[str, Any]] = field(default_factory=list)
    # asyncio.Task handle is attached by the API layer; kept untyped here so
    # the service stays importable without an event loop.
    task: Any = None


state = SimulationState()


def reset_state() -> None:
    """Stop and clear the current simulation session (used by tests)."""
    state.running = False
    state.station_code = None
    state.source_code = None
    state.scenario = "normal"
    state.seed = None
    state.interval_seconds = DEFAULT_INTERVAL_SECONDS
    state.step = 0
    state.samples_generated = 0
    state.started_at = None
    state.last_sample_at = None
    state.last_fault_sensor = None
    state.recent_samples = []
    state.task = None


def _next_values(
    rng: random.Random,
    baseline: Dict[str, float],
    scenario: str,
    step: int,
    last_fault: Optional[str],
) -> Tuple[Dict[str, Optional[float]], Optional[str]]:
    """Compute the four sensor values for one simulation step."""

    ph = baseline["ph"] + rng.uniform(-0.08, 0.08)
    tds = baseline["tds"] + rng.uniform(-10.0, 10.0)
    temperature = baseline["temperature"] + rng.uniform(-0.4, 0.4)
    index = baseline["turbidity_index"] + rng.uniform(-3.0, 3.0)

    if scenario == "gradual_deterioration":
        index += step * 1.6
        tds += step * 7.0
        ph -= step * 0.035
        temperature += step * 0.05
    elif scenario == "sudden_change":
        if step >= 3:
            index += 28.0 + rng.uniform(0.0, 8.0)
            tds += 180.0 + rng.uniform(0.0, 40.0)
            ph -= 0.5
    elif scenario == "sensor_fault":
        # The fault alternates which sensor dropped out; a missing sensor is
        # stored as NULL — never zero, never an invented value.
        pass

    values: Dict[str, Optional[float]] = {
        "ph": round(_clamp(ph, 4.0, 10.5), 2),
        "tds": round(_clamp(tds, 0.0, 5000.0), 1),
        "temperature": round(_clamp(temperature, 0.0, 55.0), 1),
        "turbidity_index": round(_clamp(index, 0.0, 100.0), 1),
    }

    if scenario == "sensor_fault":
        # Rotate the failing sensor so repeated generation shows different faults.
        position = (step // 3) % len(FAULT_SENSORS)
        faulted = FAULT_SENSORS[position]
        values[faulted] = None
        return values, faulted

    return values, None


def generate_sample(
    db: Session,
    station_code: str,
    scenario: str = "normal",
    seed: Optional[int] = None,
    advance_state: bool = True,
) -> SensorReading:
    """Generate and persist ONE simulated reading for a station.

    The reading is stored with ``source = "simulator"`` and the relative
    turbidity index unit, then the standard suitability assessments are
    derived from it — the same derived-data path hardware telemetry uses.
    """

    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown simulation scenario: {scenario!r}")

    station = (
        db.query(MonitoringStation)
        .filter(MonitoringStation.station_code == station_code)
        .first()
    )
    if station is None:
        raise ValueError(f"Unknown station_code: {station_code!r}")

    source_code = (
        station.water_source.source_code if station.water_source is not None else None
    )
    baseline = RIVER_BASELINES.get(source_code or "", DEFAULT_BASELINE)

    if advance_state and state.station_code == station_code:
        step = state.step
        rng = state_rng(seed)
    else:
        step = 0
        rng = random.Random(seed)

    values, faulted = _next_values(rng, baseline, scenario, step, state.last_fault_sensor)

    now = datetime.now(timezone.utc)
    reading = SensorReading(
        station_id=station.id,
        device_id=f"SIM-{station_code}",
        timestamp=now,
        ph=values["ph"],
        tds=values["tds"],
        temperature=values["temperature"],
        turbidity=values["turbidity_index"],
        turbidity_unit=TURBIDITY_UNIT_RELATIVE,
        turbidity_status=(
            turbidity_band(values["turbidity_index"])
            if values["turbidity_index"] is not None
            else None
        ),
        turbidity_index=values["turbidity_index"],
        source="simulator",
        diagnostics={
            "simulation": {
                "simulated": True,
                "label": "SIMULATED DATA — NOT LIVE SENSOR DATA",
                "scenario": scenario,
                "seed": seed,
                "step": step,
                "fault_sensor": faulted,
            }
        },
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)

    # Derived screening data, same path as hardware telemetry.
    try:
        suitability = assess_reading(reading)
        persist_assessments(db, station.id, suitability)
    except Exception:  # noqa: BLE001 - a derived-data failure keeps the sample
        db.rollback()

    if advance_state:
        state.station_code = station_code
        state.source_code = source_code
        state.scenario = scenario
        state.seed = seed
        state.step = step + 1
        state.samples_generated += 1
        state.last_sample_at = now
        if faulted:
            state.last_fault_sensor = faulted

    summary = {
        "id": reading.id,
        "station_code": station_code,
        "source_code": source_code,
        "timestamp": now.isoformat(),
        "scenario": scenario,
        "step": step,
        "ph": values["ph"],
        "tds": values["tds"],
        "temperature": values["temperature"],
        "turbidity_index": values["turbidity_index"],
        "turbidity_status": reading.turbidity_status,
        "fault_sensor": faulted,
        "source": "simulator",
        "simulated": True,
    }
    if advance_state:
        state.recent_samples.append(summary)
        state.recent_samples = state.recent_samples[-MAX_KEPT_SAMPLES:]
    return reading


def state_rng(seed: Optional[int]) -> random.Random:
    """A stable RNG for an in-progress run (seeded once, then advanced)."""

    if not hasattr(state, "_rng") or state._rng is None:  # type: ignore[attr-defined]
        state._rng = random.Random(seed)  # type: ignore[attr-defined]
    return state._rng  # type: ignore[attr-defined]


def start(
    station_code: str,
    scenario: str = "normal",
    seed: Optional[int] = None,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
) -> SimulationState:
    """Configure (or reconfigure) the simulation run. Does not generate yet."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown simulation scenario: {scenario!r}")
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be > 0")

    state.running = True
    state.station_code = station_code
    state.scenario = scenario
    state.seed = seed
    state.interval_seconds = interval_seconds
    state.step = 0
    state.started_at = datetime.now(timezone.utc)
    state._rng = random.Random(seed)  # type: ignore[attr-defined]
    return state


def pause() -> SimulationState:
    state.running = False
    state.task = None
    return state


def state_payload() -> Dict[str, Any]:
    return {
        "running": state.running,
        "station_code": state.station_code,
        "source_code": state.source_code,
        "scenario": state.scenario,
        "seed": state.seed,
        "interval_seconds": state.interval_seconds,
        "step": state.step,
        "samples_generated": state.samples_generated,
        "started_at": state.started_at.isoformat() if state.started_at else None,
        "last_sample_at": state.last_sample_at.isoformat() if state.last_sample_at else None,
        "simulated": True,
        "label": "SIMULATED DATA — NOT LIVE SENSOR DATA",
        "scenarios": list(SCENARIOS),
        "recent_samples": list(reversed(state.recent_samples)),
    }
