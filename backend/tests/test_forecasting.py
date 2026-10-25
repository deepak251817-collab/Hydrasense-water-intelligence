"""Validated forecasting capability: readiness gates, evaluation, honesty.

Pins the required behaviours:
- inadequate history => status `unavailable` with observed-vs-required numbers
  (pipeline/UI prepared, but forecasting NOT claimed);
- adequate history  => baseline model evaluated on a chronological holdout
  against persistence, with MAE/RMSE reported;
- forecast points exist only when evaluation supports the model;
- uncertainty is labelled as an empirical holdout band, not a probability;
- turbidity is forecast in its stored unit and never called NTU when it is a
  relative 0–100 index;
- forecasts trained on simulated rows are flagged as demonstration output;
- horizon validation and authority-only access.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.models.water import SensorReading
from app.services.forecasting import (
    MIN_SAMPLES,
    MIN_SPAN_DAYS,
    build_forecast,
    model_supported,
)

NOW = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)


def _insert(
    db,
    station_id,
    count,
    step_minutes=60,
    source="simulator",
    unit="relative_index_0_100",
    values=None,
):
    """Insert `count` readings; `values` is an iterable of (ph,tds,temp,turb)."""
    if values is None:
        values = [(7.0, 300.0, 26.0, 20.0)] * count
    rows = []
    for i, (ph, tds, temp, turb) in enumerate(values):
        rows.append(
            SensorReading(
                station_id=station_id,
                device_id="ESP32-FC-001",
                timestamp=NOW + timedelta(minutes=step_minutes * i),
                ph=ph,
                tds=tds,
                temperature=temp,
                turbidity=turb,
                turbidity_unit=unit,
                turbidity_index=turb if unit == "relative_index_0_100" else None,
                source=source,
            )
        )
    db.add_all(rows)
    db.commit()


def _trendy_series(count, start, drift, noise, seed=11):
    """Clear linear trend + small noise: a model should beat persistence."""
    rng = np.random.default_rng(seed)
    return [
        (
            float(np.clip(start + drift * i + rng.normal(0, noise), 0.1, 13.9)),
            float(np.clip(300 + drift * i * 800 + rng.normal(0, 2), 0, 5000)),
            float(np.clip(26 + drift * i * 10 + rng.normal(0, 0.05), -10, 60)),
            float(np.clip(20 + drift * i * 20 + rng.normal(0, 0.1), 0, 100)),
        )
        for i in range(count)
    ]


class TestDecisionFunction:
    def test_forecast_shown_only_when_model_beats_persistence(self):
        assert model_supported(0.3, 0.4) is True
        assert model_supported(0.5, 0.4) is False
        assert model_supported(0.4, 0.4) is False  # tie => conservative


class TestInsufficientData:
    def test_unavailable_when_history_is_too_short(
        self, client, authority_token_headers, db_session, seeded_water_data
    ):
        _insert(db_session, seeded_water_data["station"].id, count=5)
        res = client.get(
            "/api/authority/stations/TEST-STA-01/forecast",
            headers=authority_token_headers,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "unavailable"
        assert body["unavailable_reason"] == "insufficient_data"
        assert str(MIN_SAMPLES) in body["message"]
        # Readiness reports observed vs required for every parameter.
        readiness = {p["parameter"]: p for p in body["readiness"]["parameters"]}
        assert set(readiness) == {"ph", "tds", "temperature", "turbidity"}
        assert readiness["ph"]["valid_samples"] == 5
        assert readiness["ph"]["sufficient"] is False
        assert body["readiness"]["min_samples_required"] == MIN_SAMPLES
        assert body["readiness"]["min_span_days_required"] == MIN_SPAN_DAYS
        # No parameter claims a forecast.
        assert all(p["status"] == "unavailable" for p in body["parameters"])
        assert all(p["points"] == [] for p in body["parameters"])

    def test_unavailable_when_span_is_shorter_than_a_week(
        self, client, authority_token_headers, db_session, seeded_water_data
    ):
        # 100 samples but only ~4.2 days: sample count ok, span not.
        _insert(db_session, seeded_water_data["station"].id, count=100, step_minutes=60)
        res = client.get(
            "/api/authority/stations/TEST-STA-01/forecast",
            headers=authority_token_headers,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "unavailable"
        assert body["unavailable_reason"] == "insufficient_data"
        turb = next(p for p in body["parameters"] if p["parameter"] == "turbidity")
        assert "days" in turb["message"]

    def test_index_unit_is_never_labelled_ntu(
        self, client, authority_token_headers, db_session, seeded_water_data
    ):
        _insert(db_session, seeded_water_data["station"].id, count=5)
        res = client.get(
            "/api/authority/stations/TEST-STA-01/forecast",
            headers=authority_token_headers,
        )
        turb = next(
            p for p in res.json()["parameters"] if p["parameter"] == "turbidity"
        )
        assert "0–100" in turb["unit"]
        assert "NTU" in turb["unit"]  # explicitly "NOT NTU"
        assert "NTU" not in turb["label"] or "Index" in turb["label"]


class TestSupportedForecast:
    def test_trendy_history_yields_evaluated_forecast(
        self, client, authority_token_headers, db_session, seeded_water_data
    ):
        _insert(
            db_session,
            seeded_water_data["station"].id,
            count=300,
            step_minutes=60,
            source="simulator",
            values=_trendy_series(300, start=7.0, drift=0.0027, noise=0.0005),
        )
        res = client.get(
            "/api/authority/stations/TEST-STA-01/forecast?horizon_hours=24",
            headers=authority_token_headers,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "ready", body["message"]
        assert body["horizon_hours"] == 24
        assert body["trained_on_simulated"] is True
        assert body["data_sources"]["simulator"] == 300
        assert "simulated" in body["message"]

        ready = [p for p in body["parameters"] if p["status"] == "ready"]
        assert ready, "expected at least one supported parameter"
        ph = next(p for p in body["parameters"] if p["parameter"] == "ph")
        assert ph["status"] == "ready"
        # Evaluation beat persistence on the chronological holdout.
        assert ph["model"]["mae"] < ph["model"]["baseline_mae"]
        assert ph["model"]["train_size"] > 0 and ph["model"]["test_size"] > 0
        # Forecast horizon: last point lands at the requested horizon.
        assert len(ph["points"]) > 0
        last = datetime.fromisoformat(ph["points"][-1]["timestamp"])
        first = datetime.fromisoformat(ph["points"][0]["timestamp"])
        last_observed = datetime.fromisoformat(ph["last_observed_at"])
        assert last > first > last_observed
        span = (last - last_observed).total_seconds() / 3600.0
        assert abs(span - 24) < 1e-6
        # Uncertainty is the holdout MAE band, explicitly labelled.
        assert ph["uncertainty"]["method"] == "holdout_mae"
        assert ph["uncertainty"]["width"] == pytest.approx(ph["model"]["mae"])
        assert "not a probabilistic interval" in ph["uncertainty"]["note"]
        # Model outputs are labelled as such in the message.
        assert "not measurements" in ph["message"]

    def test_model_not_supported_reports_metrics_without_points(
        self, client, authority_token_headers, db_session, seeded_water_data
    ):
        # A bounded random walk: persistence is near-optimal, so the candidate
        # model should fail the strict beat-the-baseline gate.
        rng = np.random.default_rng(5)
        values = []
        level = 300.0
        for _ in range(200):
            level = float(np.clip(level + rng.normal(0, 60), 80, 900))
            values.append((7.0, level, 26.0, 20.0))
        _insert(db_session, seeded_water_data["station"].id, count=200, values=values)
        res = client.get(
            "/api/authority/stations/TEST-STA-01/forecast",
            headers=authority_token_headers,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        tds = next(p for p in body["parameters"] if p["parameter"] == "tds")
        if tds["reason"] == "model_not_better_than_baseline":
            # Transparency: metrics are shown, but no forecast numbers.
            assert tds["points"] == []
            assert tds["model"] is not None
            assert tds["model"]["mae"] >= tds["model"]["baseline_mae"]
            assert body["status"] == "unavailable"
            assert body["unavailable_reason"] == "no_supported_models"
        else:
            # If the model genuinely won on this draw, it must pass the gate.
            assert tds["status"] == "ready"


class TestEndpointGuards:
    def test_unknown_station_404(self, client, authority_token_headers):
        res = client.get(
            "/api/authority/stations/NOPE/forecast", headers=authority_token_headers
        )
        assert res.status_code == 404

    def test_horizon_bounds_validated(
        self, client, authority_token_headers, seeded_water_data
    ):
        assert client.get(
            "/api/authority/stations/TEST-STA-01/forecast?horizon_hours=0",
            headers=authority_token_headers,
        ).status_code == 422
        assert client.get(
            "/api/authority/stations/TEST-STA-01/forecast?horizon_hours=500",
            headers=authority_token_headers,
        ).status_code == 422

    def test_requires_authority(self, client, seeded_water_data):
        assert (
            client.get("/api/authority/stations/TEST-STA-01/forecast").status_code
            == 401
        )

    def test_product_user_forbidden(
        self, client, product_token_headers, seeded_water_data
    ):
        res = client.get(
            "/api/authority/stations/TEST-STA-01/forecast",
            headers=product_token_headers,
        )
        assert res.status_code in (401, 403)


class TestBuildForecastDirect:
    def test_empty_station_is_unavailable(
        self, db_session, seeded_water_data
    ):
        result = build_forecast(db_session, seeded_water_data["station"])
        assert result.status == "unavailable"
        assert result.unavailable_reason == "insufficient_data"
        assert result.data_sources == {}
        assert result.trained_on_simulated is False
