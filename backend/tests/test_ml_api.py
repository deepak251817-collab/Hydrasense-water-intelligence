"""Phase 6 — Authority ML analysis API tests.

Covers: authorized authority access, unauthorized/forbidden access, invalid
reading id, no-ML-result readings, valid ML results, latest-station analysis,
and existing-endpoint regression. Public endpoints must never expose ML
analysis.
"""
import json

import pytest

from app.models.water import MonitoringStation, SensorReading, WaterSource
from app.services.mqtt_service import process_telemetry_payload


@pytest.fixture
def station_with_readings(db_session):
    """A seeded station plus one ingested telemetry reading (with ML result)."""
    source = WaterSource(
        source_code="ARKAVATHI-TEST",
        name="Arkavathi Test Basin",
        source_type="RIVER",
        description="Testing source",
    )
    db_session.add(source)
    db_session.flush()
    station = MonitoringStation(
        station_code="ARK-001",
        water_source_id=source.id,
        station_name="Station ARK-001",
        zone="Catchment Zone",
        location="Location ARK-001",
        latitude=13.0,
        longitude=77.0,
        public_warning="NORMAL",
        public_message="Water clear",
        is_active=True,
    )
    db_session.add(station)
    db_session.commit()
    return station


def _ingest(db_session, station_code, device_id, ph, turbidity, tds, temperature):
    payload = json.dumps({
        "station_code": station_code,
        "device_id": device_id,
        "timestamp": "2026-08-31T23:00:00Z",
        "pH": ph,
        "turbidity": turbidity,
        "tds": tds,
        "temperature": temperature,
    })
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True
    return db_session.query(SensorReading).filter(SensorReading.device_id == device_id).first()


# --- Authorized authority access -------------------------------------------------
def test_authority_can_fetch_reading_analysis(
    client, authority_token_headers, db_session, station_with_readings
):
    reading = _ingest(db_session, "ARK-001", "DEV-1", 7.2, 4.5, 210.0, 25.5)
    res = client.get(f"/api/authority/readings/{reading.id}/analysis", headers=authority_token_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["reading_id"] == reading.id
    assert data["station_code"] == "ARK-001"
    assert data["ph"] == 7.2
    assert data["tds"] == 210.0
    ml = data["ml"]
    assert ml["anomaly_label"] in (0, 1)
    assert ml["water_quality_label"] in ("Safe", "Unsafe")
    assert 0.0 <= ml["safe_probability"] <= 1.0
    assert 0.0 <= ml["unsafe_probability"] <= 1.0
    assert ml["ml_processed_at"] is not None
    # No internal model paths are ever exposed.
    assert "joblib" not in json.dumps(data)
    assert "ml/models" not in json.dumps(data)


def test_authority_can_fetch_latest_station_analysis(
    client, authority_token_headers, db_session, station_with_readings
):
    _ingest(db_session, "ARK-001", "DEV-1", 7.0, 4.0, 200.0, 25.0)
    res = client.get("/api/authority/stations/ARK-001/readings/latest/analysis", headers=authority_token_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["station_code"] == "ARK-001"
    assert "ml" in data
    assert data["ml"]["ml_processed_at"] is not None


# --- Unauthorized / forbidden access ---------------------------------------------
def test_unauthenticated_access_rejected(client, db_session, station_with_readings):
    reading = _ingest(db_session, "ARK-001", "DEV-1", 7.0, 4.0, 200.0, 25.0)
    res = client.get(f"/api/authority/readings/{reading.id}/analysis")
    assert res.status_code == 401


def test_non_authority_role_forbidden(
    client, product_token_headers, db_session, station_with_readings
):
    reading = _ingest(db_session, "ARK-001", "DEV-1", 7.0, 4.0, 200.0, 25.0)
    res = client.get(f"/api/authority/readings/{reading.id}/analysis", headers=product_token_headers)
    assert res.status_code == 403


def test_non_authority_role_forbidden_on_latest_station_analysis(
    client, product_token_headers, db_session, station_with_readings
):
    _ingest(db_session, "ARK-001", "DEV-1", 7.0, 4.0, 200.0, 25.0)
    res = client.get(
        "/api/authority/stations/ARK-001/readings/latest/analysis", headers=product_token_headers
    )
    assert res.status_code == 403


# --- Invalid reading id -----------------------------------------------------------
def test_invalid_reading_id_returns_404(client, authority_token_headers, db_session):
    res = client.get("/api/authority/readings/999999/analysis", headers=authority_token_headers)
    assert res.status_code == 404


def test_invalid_station_code_returns_404_on_latest_analysis(client, authority_token_headers):
    res = client.get(
        "/api/authority/stations/NOPE-999/readings/latest/analysis", headers=authority_token_headers
    )
    assert res.status_code == 404


def test_station_without_readings_returns_404_on_latest_analysis(
    client, authority_token_headers, db_session, station_with_readings
):
    res = client.get(
        "/api/authority/stations/ARK-001/readings/latest/analysis", headers=authority_token_headers
    )
    assert res.status_code == 404


# --- No ML result (NULL fields) ---------------------------------------------------
def test_reading_without_ml_result_returns_null_ml_block(
    client, authority_token_headers, db_session, station_with_readings
):
    reading = SensorReading(
        station_id=station_with_readings.id,
        device_id="DEV-NOML",
        timestamp=__import__("datetime").datetime(2026, 8, 31, 23, 0, 0),
        ph=7.0,
        turbidity=4.0,
        tds=200.0,
        temperature=25.0,
        # ML fields left NULL (as if inference failed/skipped)
    )
    db_session.add(reading)
    db_session.commit()
    db_session.refresh(reading)

    res = client.get(f"/api/authority/readings/{reading.id}/analysis", headers=authority_token_headers)
    assert res.status_code == 200
    ml = res.json()["ml"]
    assert ml["anomaly_label"] is None
    assert ml["anomaly_score"] is None
    assert ml["water_quality_label"] is None
    assert ml["safe_probability"] is None
    assert ml["unsafe_probability"] is None
    assert ml["ml_processed_at"] is None


# --- Existing endpoint regression ---------------------------------------------------
def test_existing_authority_endpoints_still_work(
    client, authority_token_headers, db_session, station_with_readings
):
    _ingest(db_session, "ARK-001", "DEV-1", 7.0, 4.0, 200.0, 25.0)
    assert client.get("/api/authority/me", headers=authority_token_headers).status_code == 200
    assert client.get("/api/authority/stations", headers=authority_token_headers).status_code == 200
    assert client.get(
        "/api/authority/stations/ARK-001/readings/latest", headers=authority_token_headers
    ).status_code == 200
    assert client.get(
        "/api/authority/stations/ARK-001/readings", headers=authority_token_headers
    ).status_code == 200


def test_public_endpoint_does_not_expose_ml_analysis(client, db_session, station_with_readings):
    _ingest(db_session, "ARK-001", "DEV-1", 7.0, 4.0, 200.0, 25.0)
    res = client.get("/api/public/stations/ARK-001")
    assert res.status_code == 200
    body = res.text
    for forbidden in ("anomaly_label", "anomaly_score", "water_quality_label",
                      "safe_probability", "unsafe_probability", "ml_processed_at", "analysis"):
        assert forbidden not in body
