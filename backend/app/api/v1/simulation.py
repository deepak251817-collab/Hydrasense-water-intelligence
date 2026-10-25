"""Simulation controls for the three demonstration rivers.

Start / pause / generate-sample endpoints backed by the ``simulation_runs``
singleton row, so the controls are consistent across API workers and frontend
sessions and survive application restarts.

A per-process poller (started from the app lifespan) drives generation while
the run is ``running``. Only the worker that holds the unexpired generation
lease produces samples, so multiple workers never run duplicate loops.

Every generated row lands in ``sensor_readings`` with ``source = "simulator"``
and the label SIMULATED DATA — NOT LIVE SENSOR DATA.

Authority-only: simulation is a demonstration control, not a public action.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_authority
from app.core.database import SessionLocal, get_db
from app.models.user import User
from app.schemas.simulation import (
    SimulationGenerateRequest,
    SimulationStartRequest,
    SimulationStateResponse,
)
from app.services import simulation_service

logger = logging.getLogger("hydrasense.simulation")

router = APIRouter(prefix="/simulation", tags=["Simulation"])

POLL_TICK_SECONDS = 0.5
_poller_task: asyncio.Task | None = None


def _generation_tick(worker_id: str) -> None:
    """Claim the lease; generate one sample when the interval has elapsed."""

    db = SessionLocal()
    try:
        if not simulation_service.claim_lease(db, worker_id):
            return  # another worker holds the lease, or the run is paused
        run = simulation_service.get_run(db)
        if run.status != "running" or not run.station_code:
            return

        now = datetime.now(timezone.utc)
        last = run.last_sample_at
        if last is not None:
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if (now - last).total_seconds() < (run.interval_seconds or 0):
                return

        simulation_service.generate_sample(
            db,
            station_code=run.station_code,
            scenario=run.scenario,
            seed=run.seed,
            step=run.step,
            update_run=True,
        )
        # Renew after the (possibly slow) generation so a slow sample does not
        # let a second worker start generating concurrently.
        simulation_service.claim_lease(db, worker_id)
    except Exception as err:  # noqa: BLE001 - a tick failure must not kill the loop
        logger.error("Simulation tick failed: %s", err, exc_info=True)
        db.rollback()
    finally:
        db.close()


async def _poll_loop(worker_id: str) -> None:
    while True:
        await asyncio.sleep(POLL_TICK_SECONDS)
        await asyncio.to_thread(_generation_tick, worker_id)


def start_simulation_poller() -> None:
    """Start this worker's generation loop (idempotent)."""
    global _poller_task
    if _poller_task is None or _poller_task.done():
        _poller_task = asyncio.get_running_loop().create_task(
            _poll_loop(simulation_service.WORKER_ID)
        )
        logger.info("Simulation poller started (worker=%s)", simulation_service.WORKER_ID)


def stop_simulation_poller() -> None:
    global _poller_task
    if _poller_task is not None and not _poller_task.done():
        _poller_task.cancel()
    _poller_task = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/state", response_model=SimulationStateResponse)
def get_simulation_state(
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    return simulation_service.state_payload(db)


@router.post("/start", response_model=SimulationStateResponse)
def start_simulation(
    payload: SimulationStartRequest,
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    """Start (or restart) the persistent simulation run for one station."""

    try:
        simulation_service.start(
            db,
            station_code=payload.station_code,
            scenario=payload.scenario,
            seed=payload.seed,
            interval_seconds=payload.interval_seconds,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    logger.info(
        "Simulation started: station=%s scenario=%s seed=%s interval=%ss",
        payload.station_code, payload.scenario, payload.seed, payload.interval_seconds,
    )
    return simulation_service.state_payload(db)


@router.post("/pause", response_model=SimulationStateResponse)
def pause_simulation(
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    simulation_service.pause(db)
    logger.info("Simulation paused")
    return simulation_service.state_payload(db)


@router.post("/generate", response_model=SimulationStateResponse)
def generate_samples(
    payload: SimulationGenerateRequest,
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    """Generate sample(s) immediately without starting the timed run."""

    station_code = payload.station_code or simulation_service.get_run(db).station_code
    if not station_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="station_code is required when no simulation has run yet",
        )

    try:
        for _ in range(payload.count):
            simulation_service.generate_sample(
                db,
                station_code=station_code,
                scenario=payload.scenario,
                seed=payload.seed,
                update_run=True,
            )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    return simulation_service.state_payload(db)
