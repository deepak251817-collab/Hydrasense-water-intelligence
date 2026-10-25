"""Simulation controls for the three demonstration rivers.

Start / pause / generate-sample endpoints that drive
``app.services.simulation_service``. Generated rows land in
``sensor_readings`` with ``source = "simulator"`` and are labelled
SIMULATED DATA — NOT LIVE SENSOR DATA everywhere they appear.

Authority-only: simulation is a demonstration control, not a public action.
"""

from __future__ import annotations

import asyncio
import logging

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

_task: asyncio.Task | None = None


async def _generation_loop(station_code: str, scenario: str, seed: int | None) -> None:
    """Generate one simulated sample per interval while the run is active."""
    while simulation_service.state.running:
        try:
            await asyncio.to_thread(_generate_one, station_code, scenario, seed)
        except Exception as err:  # noqa: BLE001 - keep the run alive
            logger.error("Simulation sample failed: %s", err, exc_info=True)
        await asyncio.sleep(simulation_service.state.interval_seconds)


def _generate_one(station_code: str, scenario: str, seed: int | None) -> None:
    db = SessionLocal()
    try:
        # Per-step seed keeps a seeded run reproducible across samples.
        step_seed = None if seed is None else seed + simulation_service.state.step
        simulation_service.generate_sample(
            db,
            station_code=station_code,
            scenario=scenario,
            seed=step_seed,
        )
    finally:
        db.close()


def _stop_task() -> None:
    global _task
    if _task is not None and not _task.done():
        _task.cancel()
    _task = None


@router.get("/state", response_model=SimulationStateResponse)
def get_simulation_state(
    current_user: User = Depends(get_current_authority),
):
    return simulation_service.state_payload()


@router.post("/start", response_model=SimulationStateResponse)
async def start_simulation(
    payload: SimulationStartRequest,
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    """Start (or restart) a simulation run for one station."""

    from app.models.water import MonitoringStation

    station = (
        db.query(MonitoringStation)
        .filter(MonitoringStation.station_code == payload.station_code)
        .first()
    )
    if station is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown station_code: {payload.station_code}",
        )

    try:
        simulation_service.start(
            station_code=payload.station_code,
            scenario=payload.scenario,
            seed=payload.seed,
            interval_seconds=payload.interval_seconds,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    _stop_task()
    global _task
    _task = asyncio.create_task(
        _generation_loop(payload.station_code, payload.scenario, payload.seed)
    )
    simulation_service.state.task = _task
    logger.info(
        "Simulation started: station=%s scenario=%s seed=%s interval=%ss",
        payload.station_code, payload.scenario, payload.seed, payload.interval_seconds,
    )
    return simulation_service.state_payload()


@router.post("/pause", response_model=SimulationStateResponse)
async def pause_simulation(
    current_user: User = Depends(get_current_authority),
):
    _stop_task()
    simulation_service.pause()
    logger.info("Simulation paused")
    return simulation_service.state_payload()


@router.post("/generate", response_model=SimulationStateResponse)
def generate_samples(
    payload: SimulationGenerateRequest,
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    """Generate sample(s) immediately without starting a timed run."""

    station_code = payload.station_code or simulation_service.state.station_code
    if not station_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="station_code is required when no simulation has run yet",
        )

    try:
        for index in range(payload.count):
            seed = None if payload.seed is None else payload.seed + index
            simulation_service.generate_sample(
                db,
                station_code=station_code,
                scenario=payload.scenario,
                seed=seed,
            )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    simulation_service.state.station_code = station_code
    simulation_service.state.scenario = payload.scenario
    return simulation_service.state_payload()
