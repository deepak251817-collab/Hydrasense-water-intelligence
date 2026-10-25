"""Baseline time-series forecasting with honest readiness + evaluation gates.

Design (task: "Add a Validated Forecasting Capability"):

1. **Readiness first.** Before any model runs, the stored history for the
   station is inspected per parameter (valid sample count and time span).
   When history is inadequate the endpoint reports ``status = unavailable``
   with observed-vs-required numbers — the data pipeline and UI state exist,
   but no forecast is claimed.

2. **Time-aware evaluation.** For each parameter a transparent baseline model
   (Ridge on a normalised time index + previous reading, forecast recursively)
   is compared against a naive persistence forecast on a chronological
   holdout (last 20% of the ordered series — no random shuffle, no
   future leakage).

3. **Show only what evaluation supports.** Forecast points are returned only
   when the candidate model's holdout MAE strictly beats persistence on the
   same holdout. Otherwise the parameter carries an explicit
   ``model_not_better_than_baseline`` reason (metrics still shown for
   transparency, but no forecast numbers).

4. **Honest uncertainty.** The band is the holdout MAE, clearly labelled as a
   constant-width empirical approximation — not a probabilistic interval.

5. **Traceability.** The response reports which data sources (simulator /
   esp32 / ...) the training history came from, and flags forecasts trained on
   simulated demo readings as demonstration output, not real-world evidence.

Units: turbidity is forecast in the dominant stored unit of the station.
A relative 0–100 index is forecast as an index (labelled as such) and is
never described as NTU.
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from sqlalchemy.orm import Session

from app.models.water import MonitoringStation, SensorReading
from app.schemas.forecast import (
    ForecastModelInfo,
    ForecastParameterResult,
    ForecastPoint,
    ForecastReadiness,
    ForecastReadinessParameter,
    ForecastResponse,
    UncertaintyInfo,
)

# --- Configurable readiness requirements -----------------------------------
MIN_SAMPLES = 96          # minimum valid points per parameter
MIN_SPAN_DAYS = 7         # minimum history span per parameter
TEST_FRACTION = 0.2       # chronological holdout fraction (at least MIN_TEST)
MIN_TEST = 8
MIN_TRAIN = 32
DEFAULT_HORIZON_HOURS = 24
MAX_HORIZON_HOURS = 168
MAX_POINTS = 96

REASON_INSUFFICIENT_DATA = "insufficient_data"
REASON_NO_SUPPORTED_MODELS = "no_supported_models"
REASON_MODEL_NOT_SUPPORTED = "model_not_better_than_baseline"
REASON_UNKNOWN_TURBIDITY_UNIT = "unknown_turbidity_unit"

_MODEL_NAME = "ridge (time index + previous reading), recursive"
_EVALUATION = "chronological train/test split (last 20% held out), one-step-ahead"
_UNCERTAINTY_NOTE = (
    "± MAE measured on the chronological holdout — a constant-width empirical "
    "approximation, not a probabilistic interval. Real uncertainty grows with "
    "the forecast horizon."
)

PARAM_ORDER = ("ph", "tds", "temperature", "turbidity")

_PARAM_META = {
    "ph": {"label": "pH", "unit": "pH"},
    "tds": {"label": "TDS", "unit": "mg/L (≈ ppm)"},
    "temperature": {"label": "Temperature", "unit": "°C"},
}


def model_supported(model_mae: float, baseline_mae: float) -> bool:
    """Forecast is shown only when the model strictly beats persistence."""
    return model_mae < baseline_mae


def _metric(value: float) -> str:
    """3 significant digits so '0.0468 vs 0.0471' doesn't read as a tie."""
    return f"{value:.4g}"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _station_readings(db: Session, station_id: int) -> List[SensorReading]:
    return (
        db.query(SensorReading)
        .filter(SensorReading.station_id == station_id)
        .order_by(SensorReading.timestamp.asc())
        .all()
    )


def _finite(value) -> bool:
    return value is not None and math.isfinite(float(value))


def _dominant_turbidity_unit(rows: Sequence[SensorReading]) -> Optional[str]:
    """Unit of the most recent turbidity reading (authoritative for forecast)."""
    for row in reversed(rows):
        if _finite(row.turbidity) and row.turbidity_unit:
            return row.turbidity_unit
    return None


def _extract_series(
    rows: Sequence[SensorReading], parameter: str, turbidity_unit: Optional[str]
) -> Tuple[List[datetime], List[float], Optional[str]]:
    """Valid (timestamp, value) pairs for one parameter, oldest first.

    Never fabricates a value: missing/non-finite readings are skipped.
    For turbidity only rows matching ``turbidity_unit`` are used, so a
    relative index and NTU rows are never mixed in one series.
    """
    timestamps: List[datetime] = []
    values: List[float] = []
    for row in rows:
        ts = _as_utc(row.timestamp)
        if parameter == "ph":
            value = row.ph
            valid = _finite(value) and 0.0 <= float(value) <= 14.0
        elif parameter == "tds":
            value = row.tds
            valid = _finite(value) and float(value) >= 0.0
        elif parameter == "temperature":
            value = row.temperature
            valid = _finite(value) and -50.0 <= float(value) <= 100.0
        elif parameter == "turbidity":
            if not turbidity_unit or row.turbidity_unit != turbidity_unit:
                continue
            value = row.turbidity
            valid = _finite(value)
            if valid and turbidity_unit == "relative_index_0_100":
                valid = 0.0 <= float(value) <= 100.0
        else:  # pragma: no cover - defensive
            valid = False
        if valid:
            timestamps.append(ts)
            values.append(float(value))
    return timestamps, values, turbidity_unit


def _parameter_meta(parameter: str, turbidity_unit: Optional[str]) -> Dict[str, str]:
    if parameter != "turbidity":
        return dict(_PARAM_META[parameter])
    if turbidity_unit == "relative_index_0_100":
        return {
            "label": "Turbidity Index",
            "unit": "0–100 (relative index, NOT NTU)",
        }
    if turbidity_unit == "ntu":
        return {"label": "Turbidity", "unit": "NTU"}
    return {"label": "Turbidity", "unit": turbidity_unit or "unknown"}


def _unavailable(
    parameter: str,
    reason: str,
    message: str,
    turbidity_unit: Optional[str] = None,
    model: Optional[ForecastModelInfo] = None,
    last_observed: Optional[float] = None,
    last_observed_at: Optional[datetime] = None,
) -> ForecastParameterResult:
    meta = _parameter_meta(parameter, turbidity_unit)
    return ForecastParameterResult(
        parameter=parameter,
        label=meta["label"],
        unit=meta["unit"],
        status="unavailable",
        reason=reason,
        message=message,
        last_observed=last_observed,
        last_observed_at=last_observed_at,
        model=model,
        points=[],
    )


def _fit_and_evaluate(
    times_hours: Sequence[float], values: Sequence[float]
) -> Optional[Tuple[ForecastModelInfo, np.ndarray, np.ndarray]]:
    """Fit Ridge on (time, lag) features; evaluate on chronological holdout.

    Returns (model_info, fitted_pipeline, usable_feature_rows) or None when
    the series is too short for the configured train/test minimums.
    """
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    n = len(values)
    if n < MIN_TRAIN + MIN_TEST + 1:
        return None

    # Feature rows: predict value[i] from [time[i], value[i-1]].
    span_hours = max(times_hours[-1] - times_hours[0], 1e-9)
    rows_x = np.array(
        [[(times_hours[i] - times_hours[0]) / span_hours, values[i - 1]]
         for i in range(1, n)],
        dtype=float,
    )
    rows_y = np.array(values[1:], dtype=float)

    split = int(len(rows_y) * (1.0 - TEST_FRACTION))
    split = min(max(split, MIN_TRAIN), len(rows_y) - MIN_TEST)
    if split < MIN_TRAIN or len(rows_y) - split < MIN_TEST:
        return None

    x_train, y_train = rows_x[:split], rows_y[:split]
    x_test, y_test = rows_x[split:], rows_y[split:]

    model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    model.fit(x_train, y_train)

    pred = model.predict(x_test)
    naive = x_test[:, 1]  # persistence: previous reading carried forward

    mae = float(np.mean(np.abs(pred - y_test)))
    rmse = float(np.sqrt(np.mean((pred - y_test) ** 2)))
    base_mae = float(np.mean(np.abs(naive - y_test)))
    base_rmse = float(np.sqrt(np.mean((naive - y_test) ** 2)))

    info = ForecastModelInfo(
        name=_MODEL_NAME,
        evaluation=_EVALUATION,
        train_size=int(split),
        test_size=int(len(rows_y) - split),
        mae=mae,
        rmse=rmse,
        baseline_mae=base_mae,
        baseline_rmse=base_rmse,
    )
    return info, model, rows_x


def _forecast_points(
    model,
    times_hours: Sequence[float],
    values: Sequence[float],
    last_ts: datetime,
    horizon_hours: float,
    mae: float,
) -> List[ForecastPoint]:
    """Recursive multi-step forecast on an evenly spaced grid covering the horizon."""
    median_step = _median_step_hours(times_hours)
    count = max(1, min(MAX_POINTS, round(horizon_hours / median_step)))
    step = horizon_hours / count

    span_hours = max(times_hours[-1] - times_hours[0], 1e-9)
    prev = values[-1]
    t_next = times_hours[-1]
    points: List[ForecastPoint] = []
    for k in range(1, count + 1):
        t_next += step
        feature = np.array(
            [[(t_next - times_hours[0]) / span_hours, prev]], dtype=float
        )
        prev = float(model.predict(feature)[0])
        ts = last_ts + timedelta(hours=step * k)
        points.append(
            ForecastPoint(
                timestamp=ts,
                value=prev,
                lower=prev - mae,
                upper=prev + mae,
            )
        )
    return points


def _median_step_hours(times_hours: Sequence[float]) -> float:
    deltas = [
        b - a for a, b in zip(times_hours, times_hours[1:]) if b - a > 0
    ]
    if not deltas:
        return 1.0
    # Keep the grid sane: at least 5 minutes between forecast steps.
    return max(statistics.median(deltas), 5.0 / 60.0)


def _evaluate_parameter(
    parameter: str,
    rows: Sequence[SensorReading],
    turbidity_unit: Optional[str],
    horizon_hours: int,
) -> ForecastParameterResult:
    timestamps, values, unit = _extract_series(rows, parameter, turbidity_unit)
    meta = _parameter_meta(parameter, unit)

    if len(values) < MIN_SAMPLES:
        return _unavailable(
            parameter,
            REASON_INSUFFICIENT_DATA,
            (
                f"Forecasting unavailable for {meta['label']}: {len(values)} valid "
                f"sample(s) stored; at least {MIN_SAMPLES} are required. The "
                "readiness check runs automatically as history accumulates."
            ),
            turbidity_unit=unit,
        )

    span_days = (timestamps[-1] - timestamps[0]).total_seconds() / 86400.0
    if span_days < MIN_SPAN_DAYS:
        return _unavailable(
            parameter,
            REASON_INSUFFICIENT_DATA,
            (
                f"Forecasting unavailable for {meta['label']}: history spans "
                f"{span_days:.1f} days; at least {MIN_SPAN_DAYS} days are required."
            ),
            turbidity_unit=unit,
        )

    times_hours = [
        (ts - timestamps[0]).total_seconds() / 3600.0 for ts in timestamps
    ]
    fitted = _fit_and_evaluate(times_hours, values)
    if fitted is None:
        return _unavailable(
            parameter,
            REASON_INSUFFICIENT_DATA,
            (
                f"Forecasting unavailable for {meta['label']}: not enough usable "
                "points after removing missing/invalid readings."
            ),
            turbidity_unit=unit,
        )

    info, model, _ = fitted
    last_observed = values[-1]
    last_observed_at = timestamps[-1]

    if not model_supported(info.mae, info.baseline_mae):
        return _unavailable(
            parameter,
            REASON_MODEL_NOT_SUPPORTED,
            (
                f"Forecast not published for {meta['label']}: holdout MAE "
                f"{_metric(info.mae)} did not beat the persistence baseline "
                f"({_metric(info.baseline_mae)}) on the chronological test split. "
                "No forecast numbers are shown when evaluation does not support "
                "the model."
            ),
            turbidity_unit=unit,
            model=info,
            last_observed=last_observed,
            last_observed_at=last_observed_at,
        )

    points = _forecast_points(
        model, times_hours, values, last_observed_at, horizon_hours, info.mae
    )
    message = (
        f"{meta['label']} forecast over the next {horizon_hours} h, supported by "
        f"holdout evaluation (MAE {_metric(info.mae)} vs persistence "
        f"{_metric(info.baseline_mae)}). Model outputs, not measurements."
    )
    if parameter == "turbidity" and unit == "relative_index_0_100":
        message += " Relative index trend only — not NTU, no NTU compliance implied."

    return ForecastParameterResult(
        parameter=parameter,
        label=meta["label"],
        unit=meta["unit"],
        status="ready",
        message=message,
        last_observed=last_observed,
        last_observed_at=last_observed_at,
        model=info,
        uncertainty=UncertaintyInfo(
            width=info.mae, note=_UNCERTAINTY_NOTE
        ),
        points=points,
    )


def build_forecast(
    db: Session, station: MonitoringStation, horizon_hours: int = DEFAULT_HORIZON_HOURS
) -> ForecastResponse:
    """Full honest forecast payload for one station."""
    rows = _station_readings(db, station.id)

    data_sources: Dict[str, int] = {}
    for row in rows:
        data_sources[row.source] = data_sources.get(row.source, 0) + 1
    trained_on_simulated = any(
        row.source == "simulator" for row in rows
    )

    turbidity_unit = _dominant_turbidity_unit(rows)

    # Readiness report (always present, even when unavailable).
    readiness_params: List[ForecastReadinessParameter] = []
    max_span_days = 0.0
    any_sufficient = False
    for parameter in PARAM_ORDER:
        timestamps, values, _ = _extract_series(rows, parameter, turbidity_unit)
        span_days = (
            (timestamps[-1] - timestamps[0]).total_seconds() / 86400.0
            if timestamps
            else 0.0
        )
        sufficient = (
            len(values) >= MIN_SAMPLES and span_days >= MIN_SPAN_DAYS
        )
        any_sufficient = any_sufficient or sufficient
        max_span_days = max(max_span_days, span_days)
        readiness_params.append(
            ForecastReadinessParameter(
                parameter=parameter,
                valid_samples=len(values),
                span_days=round(span_days, 2),
                sufficient=sufficient,
            )
        )

    results = [
        _evaluate_parameter(parameter, rows, turbidity_unit, horizon_hours)
        for parameter in PARAM_ORDER
    ]
    ready = [r for r in results if r.status == "ready"]

    now = datetime.now(timezone.utc)
    readiness = ForecastReadiness(
        min_samples_required=MIN_SAMPLES,
        min_span_days_required=MIN_SPAN_DAYS,
        observed_span_days=round(max_span_days, 2),
        parameters=readiness_params,
    )

    if ready:
        status = "ready"
        reason = None
        message = (
            f"Baseline forecast available for {len(ready)} of {len(PARAM_ORDER)} "
            f"parameters over the next {horizon_hours} h, after time-aware holdout "
            "evaluation against a persistence baseline. Forecasts are model "
            "outputs, not measurements or guarantees."
        )
        if trained_on_simulated:
            message += (
                " Training history includes simulated demo readings — treat this "
                "as demonstration output, not real-world evidence."
            )
    elif any_sufficient:
        status = "unavailable"
        reason = REASON_NO_SUPPORTED_MODELS
        message = (
            "Forecasting unavailable: sufficient history exists, but evaluation "
            "did not support the models (holdout MAE did not beat the "
            "persistence baseline for any parameter)."
        )
    else:
        status = "unavailable"
        reason = REASON_INSUFFICIENT_DATA
        best = max(
            (p.valid_samples for p in readiness_params), default=0
        )
        message = (
            f"Forecasting unavailable: insufficient historical data "
            f"(best parameter has {best} valid samples; "
            f"{MIN_SAMPLES} samples spanning at least {MIN_SPAN_DAYS} days "
            "are required)."
        )

    return ForecastResponse(
        station_code=station.station_code,
        generated_at=now,
        horizon_hours=horizon_hours,
        status=status,
        unavailable_reason=reason,
        message=message,
        data_sources=data_sources,
        trained_on_simulated=trained_on_simulated,
        readiness=readiness,
        parameters=results,
    )
