"""Three-river simulation mode — persistent, shared across API workers.

Generates plausible randomised readings for exactly the four sensors this
project supports (pH, TDS, temperature, turbidity index) for the three
demonstration rivers: Arkavathi, Cauvery and Vrishabhavathi.

State lives in the ``simulation_runs`` singleton row (PostgreSQL), NOT in
process memory, so Start / Pause / Generate / scenario selection are consistent
across API workers and frontend sessions and survive an application restart.

Duplicate-loop protection: a worker may only generate while it holds an
unexpired lease on that row (``worker_id`` + ``lease_expires_at``). Leases are
renewed on every generation and expire if a worker dies, so multiple workers
never run two generation loops at once.

Every sample is persisted to ``sensor_readings`` with ``source = "simulator"``
and diagnostics label ``SIMULATED DATA — NOT LIVE SENSOR DATA``, so simulated
readings stay distinguishable from physical ESP32 telemetry.

Reproducibility: with a ``seed``, the RNG for a step is derived from
``(seed, step)`` — identical for any worker, in any process, at any time.

Turbidity index follows the firmware's documented direction and bands
(``firmware/hydrasense_esp32``): 0-100, higher = cloudier,
CLEARER < 30, MODERATE 30-54, CLOUDIER >= 55. It is never NTU.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.simulation import SimulationRun
from app.models.water import MonitoringStation, SensorReading
from app.services.water_suitability import assess_reading, persist_assessments

SCENARIOS = (
    "normal",
    "rain_runoff",
    "industrial_discharge",
    "sewage_like",
    "gradual_deterioration",
    "sudden_change",
    "sensor_fault",
)

# Human labels for the API/UI. Only the five demo scenarios are offered in the
# floating panel; the three legacy drifts stay supported for existing clients.
SCENARIO_LABELS = {
    "normal": "Normal",
    "rain_runoff": "Rain runoff (turbidity up)",
    "industrial_discharge": "Industrial discharge (TDS and pH jump)",
    "sewage_like": "Sewage-like (TDS up, pH down)",
    "sensor_fault": "Sensor fault (null readings)",
    "gradual_deterioration": "Gradual deterioration",
    "sudden_change": "Sudden change",
}

DEFAULT_INTERVAL_SECONDS = 5.0
# How long one worker's generation lease is valid without renewal. Long enough
# to cover a slow sample, short enough for another worker to take over quickly.
LEASE_SECONDS = 15
MAX_KEPT_SAMPLES = 50
RUN_ID = 1  # singleton row

TURBIDITY_UNIT_RELATIVE = "relative_index_0_100"

# Demonstration baselines per river (plausible surface-water ranges only).
# SIMULATED starting points, not measured field values.
RIVER_BASELINES: Dict[str, Dict[str, float]] = {
    "ARKAVATHI": {"ph": 7.2, "tds": 320.0, "temperature": 26.5, "turbidity_index": 26.0},
    "CAUVERY": {"ph": 7.4, "tds": 280.0, "temperature": 27.2, "turbidity_index": 20.0},
    "VRISHABHAVATHI": {"ph": 7.0, "tds": 380.0, "temperature": 27.8, "turbidity_index": 38.0},
}
DEFAULT_BASELINE = {"ph": 7.2, "tds": 320.0, "temperature": 26.5, "turbidity_index": 30.0}

FAULT_SENSORS = ("temperature", "tds", "ph", "turbidity_index")

# Per-process identity for lease ownership (unique per worker/process).
WORKER_ID = f"worker-{uuid.uuid4().hex[:12]}"


def turbidity_band(index: float) -> str:
    """Firmware-compatible band for the relative index (NOT NTU)."""
    if index < 30.0:
        return "CLEARER"
    if index < 55.0:
        return "MODERATE"
    return "CLOUDIER"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def rng_for(seed: Optional[int], step: int) -> random.Random:
    """Deterministic per-step RNG: same (seed, step) => same values anywhere."""
    if seed is None:
        return random.Random()
    return random.Random(f"{seed}:{step}")


# ---------------------------------------------------------------------------
# Persistent run state
# ---------------------------------------------------------------------------

def get_run(db: Session) -> SimulationRun:
    """Return the singleton run row, creating it on first use."""
    run = db.get(SimulationRun, RUN_ID)
    if run is None:
        run = SimulationRun(
            id=RUN_ID,
            status="paused",
            scenario="normal",
            interval_seconds=DEFAULT_INTERVAL_SECONDS,
            step=0,
            samples_generated=0,
        )
        db.add(run)
        try:
            db.commit()
        except Exception:  # concurrent first-use insert; re-read
            db.rollback()
            run = db.get(SimulationRun, RUN_ID)
            if run is None:
                raise
    return run


def start(
    db: Session,
    station_code: str,
    scenario: str = "normal",
    seed: Optional[int] = None,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    worker_id: str = WORKER_ID,
) -> SimulationRun:
    """Configure (or reconfigure) the run and mark it running.

    Counters restart so a seeded run is reproducible; any previous lease is
    replaced by the caller's, so exactly one worker will drive generation.
    """
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown simulation scenario: {scenario!r}")
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be > 0")

    station = (
        db.query(MonitoringStation)
        .filter(MonitoringStation.station_code == station_code)
        .first()
    )
    if station is None:
        raise ValueError(f"Unknown station_code: {station_code!r}")

    now = datetime.now(timezone.utc)
    run = get_run(db)
    run.station_code = station_code
    run.source_code = (
        station.water_source.source_code if station.water_source is not None else None
    )
    run.scenario = scenario
    run.seed = seed
    run.interval_seconds = float(interval_seconds)
    run.status = "running"
    run.step = 0
    run.samples_generated = 0
    run.started_at = now
    run.last_sample_at = None
    run.worker_id = worker_id
    run.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    db.commit()
    db.refresh(run)
    return run


def pause(db: Session, worker_id: Optional[str] = None) -> SimulationRun:
    """Stop generation and release the lease."""
    run = get_run(db)
    run.status = "paused"
    run.worker_id = None
    run.lease_expires_at = None
    db.commit()
    db.refresh(run)
    return run


def reset(db: Session, worker_id: Optional[str] = None) -> SimulationRun:
    """Pause the run and clear its configuration and counters.

    Generated readings stay in ``sensor_readings`` (they are labelled
    ``source = "simulator"`` and may back a demo already in progress), but the
    next Start begins again from step 0 with no station, scenario or seed.
    """
    run = get_run(db)
    run.status = "paused"
    run.station_code = None
    run.source_code = None
    run.scenario = "normal"
    run.seed = None
    run.interval_seconds = DEFAULT_INTERVAL_SECONDS
    run.step = 0
    run.samples_generated = 0
    run.started_at = None
    run.last_sample_at = None
    run.worker_id = None
    run.lease_expires_at = None
    db.commit()
    db.refresh(run)
    return run


def claim_lease(db: Session, worker_id: str, now: Optional[datetime] = None) -> bool:
    """Atomically claim/renew the generation lease for this worker.

    Returns True when the caller owns the lease (status must be running and the
    previous lease must be absent, expired, or already ours). This is the
    duplicate-loop guard: while one worker holds a valid lease, no other worker
    can generate.
    """
    now = now or datetime.now(timezone.utc)
    run = get_run(db)
    if run.status != "running":
        return False

    lease_until = _utc(run.lease_expires_at)
    owned = run.worker_id == worker_id
    free = run.worker_id is None or lease_until is None or lease_until <= now
    if not (owned or free):
        return False

    run.worker_id = worker_id
    run.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Sample generation
# ---------------------------------------------------------------------------

def _next_values(
    rng: random.Random,
    baseline: Dict[str, float],
    scenario: str,
    step: int,
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
    elif scenario == "rain_runoff":
        # First-flush runoff: cloudier water, some dissolved load, near-neutral
        # pH. Turbidity index crosses the firmware CLOUDIER band (>= 55).
        index += 34.0 + rng.uniform(0.0, 8.0)
        tds += 90.0 + rng.uniform(0.0, 40.0)
        ph -= 0.25
    elif scenario == "industrial_discharge":
        # Alkaline effluent with a large dissolved load: TDS well above the
        # acceptable reference and pH above the warning band, often critical.
        tds += 900.0 + rng.uniform(0.0, 200.0)
        ph += 1.9 + rng.uniform(0.0, 0.4)
        index += 12.0 + rng.uniform(0.0, 6.0)
    elif scenario == "sewage_like":
        # Organic/sewage signature: high dissolved solids with acidic pH.
        tds += 500.0 + rng.uniform(0.0, 120.0)
        ph -= 1.5 + rng.uniform(0.0, 0.3)
        index += 18.0 + rng.uniform(0.0, 6.0)

    values: Dict[str, Optional[float]] = {
        "ph": round(_clamp(ph, 4.0, 10.5), 2),
        "tds": round(_clamp(tds, 0.0, 5000.0), 1),
        "temperature": round(_clamp(temperature, 0.0, 55.0), 1),
        "turbidity_index": round(_clamp(index, 0.0, 100.0), 1),
    }

    if scenario == "sensor_fault":
        # Rotate which sensor dropped out; a missing sensor is stored as NULL —
        # never zero, never an invented value.
        faulted = FAULT_SENSORS[(step // 3) % len(FAULT_SENSORS)]
        values[faulted] = None
        return values, faulted

    return values, None


def generate_sample(
    db: Session,
    station_code: str,
    scenario: str = "normal",
    seed: Optional[int] = None,
    step: Optional[int] = None,
    update_run: bool = True,
) -> SensorReading:
    """Generate and persist ONE simulated reading for a station.

    The reading is stored with ``source = "simulator"`` and the relative
    turbidity index unit; the standard suitability assessments are then derived
    from it — the same path hardware telemetry uses.

    ``step`` decides the per-step RNG and the sensor-fault rotation. When
    ``update_run`` is true the persistent run counters advance, which is how an
    API worker's generation loop makes progress.
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

    run = get_run(db)
    if step is None:
        step = run.step if update_run else 0

    if update_run:
        # "Generate Sample" and the generation loop both advance the single
        # persistent run, keeping counters and config aligned with what was
        # actually generated. A manual generation never starts the timed run.
        run.station_code = station_code
        run.scenario = scenario
        run.seed = seed

    source_code = (
        station.water_source.source_code if station.water_source is not None else None
    )
    baseline = RIVER_BASELINES.get(source_code or "", DEFAULT_BASELINE)

    rng = rng_for(seed, step)
    values, faulted = _next_values(rng, baseline, scenario, step)

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

    if update_run:
        run = get_run(db)
        run.step = step + 1
        run.samples_generated = (run.samples_generated or 0) + 1
        run.last_sample_at = now
        run.source_code = source_code
        db.commit()

    return reading


def recent_samples(db: Session, limit: int = MAX_KEPT_SAMPLES) -> List[Dict[str, Any]]:
    """Most recent simulated readings (newest first) for the state payload."""
    rows = (
        db.query(SensorReading)
        .filter(SensorReading.source == "simulator")
        .order_by(SensorReading.timestamp.desc(), SensorReading.id.desc())
        .limit(limit)
        .all()
    )
    samples: List[Dict[str, Any]] = []
    for reading in rows:
        diagnostics = reading.diagnostics if isinstance(reading.diagnostics, dict) else {}
        simulation = diagnostics.get("simulation") if isinstance(diagnostics.get("simulation"), dict) else {}
        station = reading.station
        samples.append({
            "id": reading.id,
            "station_code": station.station_code if station else None,
            "source_code": station.water_source.source_code if station and station.water_source else None,
            "timestamp": reading.timestamp.isoformat() if reading.timestamp else None,
            "scenario": simulation.get("scenario"),
            "step": simulation.get("step", 0),
            "ph": reading.ph,
            "tds": reading.tds,
            "temperature": reading.temperature,
            "turbidity_index": reading.turbidity_index,
            "turbidity_status": reading.turbidity_status,
            "fault_sensor": simulation.get("fault_sensor"),
            "source": reading.source,
            "simulated": True,
        })
    return samples


def state_payload(db: Session) -> Dict[str, Any]:
    """Current simulation state straight from the database."""
    run = get_run(db)
    now = datetime.now(timezone.utc)
    lease_until = _utc(run.lease_expires_at)
    lease_active = bool(
        run.status == "running"
        and run.worker_id
        and lease_until
        and lease_until > now
    )
    return {
        "running": run.status == "running",
        "station_code": run.station_code,
        "source_code": run.source_code,
        "scenario": run.scenario,
        "seed": run.seed,
        "interval_seconds": run.interval_seconds,
        "step": run.step,
        "samples_generated": run.samples_generated,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "last_sample_at": run.last_sample_at.isoformat() if run.last_sample_at else None,
        "simulated": True,
        "label": "SIMULATED DATA — NOT LIVE SENSOR DATA",
        "scenarios": list(SCENARIOS),
        "scenario_labels": dict(SCENARIO_LABELS),
        "persistent": True,
        "worker_holding_lease": lease_active,
        "recent_samples": recent_samples(db),
    }
