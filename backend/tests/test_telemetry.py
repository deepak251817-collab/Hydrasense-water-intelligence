import json
from datetime import datetime, timezone
import pytest
from app.models.water import WaterSource, MonitoringStation, SensorReading
from app.services.mqtt_service import process_telemetry_payload, validate_telemetry_payload


@pytest.fixture
def seeded_stations(db_session):
    source = WaterSource(
        source_code="ARKAVATHI-TEST",
        name="Arkavathi Test Basin",
        source_type="RIVER",
        description="Testing source",
    )
    db_session.add(source)
    db_session.flush()

    stations = []
    for code in ["ARK-001", "ARK-002", "ARK-003"]:
        s = MonitoringStation(
            station_code=code,
            water_source_id=source.id,
            station_name=f"Station {code}",
            zone="Catchment Zone",
            location=f"Location {code}",
            latitude=13.0,
            longitude=77.0,
            public_warning="NORMAL",
            public_message="Water clear",
            is_active=True,
        )
        db_session.add(s)
        stations.append(s)

    db_session.commit()
    return stations


# 1. Valid telemetry
def test_valid_telemetry_ingestion(db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-001",
        "device_id": "STATION-ARK-001",
        "timestamp": "2026-08-31T23:00:00Z",
        "pH": 7.2,
        "turbidity": 4.5,
        "tds": 210.0,
        "temperature": 25.5
    })

    result = process_telemetry_payload(payload, db_session_factory=lambda: db_session)
    assert result is True

    reading = db_session.query(SensorReading).filter(SensorReading.device_id == "STATION-ARK-001").first()
    assert reading is not None
    assert reading.ph == 7.2
    assert reading.turbidity == 4.5
    assert reading.tds == 210.0
    assert reading.temperature == 25.5


# 2. Invalid JSON
def test_invalid_json_payload(db_session, seeded_stations):
    invalid_json = "{ station_code: ARK-001, pH: 7.0 "  # Broken syntax
    result = process_telemetry_payload(invalid_json, db_session_factory=lambda: db_session)
    assert result is False
    assert db_session.query(SensorReading).count() == 0


# 3. Unknown station
def test_unknown_station_rejection(db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "UNKNOWN-999",
        "device_id": "STATION-UNK-999",
        "timestamp": "2026-08-31T23:00:00Z",
        "pH": 7.0,
        "turbidity": 5.0,
        "tds": 200.0,
        "temperature": 25.0
    })
    result = process_telemetry_payload(payload, db_session_factory=lambda: db_session)
    assert result is False
    assert db_session.query(SensorReading).count() == 0


# 4. Invalid pH
def test_invalid_ph_rejection(db_session, seeded_stations):
    payload_high = json.dumps({
        "station_code": "ARK-001",
        "device_id": "STATION-ARK-001",
        "timestamp": "2026-08-31T23:00:00Z",
        "pH": 15.5,  # > 14
        "turbidity": 5.0,
        "tds": 200.0,
        "temperature": 25.0
    })
    result_high = process_telemetry_payload(payload_high, db_session_factory=lambda: db_session)
    assert result_high is False

    payload_neg = json.dumps({
        "station_code": "ARK-001",
        "device_id": "STATION-ARK-001",
        "timestamp": "2026-08-31T23:00:00Z",
        "pH": -1.0,  # < 0
        "turbidity": 5.0,
        "tds": 200.0,
        "temperature": 25.0
    })
    result_neg = process_telemetry_payload(payload_neg, db_session_factory=lambda: db_session)
    assert result_neg is False


# 5. Negative TDS
def test_negative_tds_rejection(db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-001",
        "device_id": "STATION-ARK-001",
        "timestamp": "2026-08-31T23:00:00Z",
        "pH": 7.0,
        "turbidity": 5.0,
        "tds": -50.0,  # Negative
        "temperature": 25.0
    })
    result = process_telemetry_payload(payload, db_session_factory=lambda: db_session)
    assert result is False


# 6. Negative turbidity
def test_negative_turbidity_rejection(db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-001",
        "device_id": "STATION-ARK-001",
        "timestamp": "2026-08-31T23:00:00Z",
        "pH": 7.0,
        "turbidity": -10.0,  # Negative
        "tds": 200.0,
        "temperature": 25.0
    })
    result = process_telemetry_payload(payload, db_session_factory=lambda: db_session)
    assert result is False


# 7. Invalid temperature
def test_invalid_temperature_rejection(db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-001",
        "device_id": "STATION-ARK-001",
        "timestamp": "2026-08-31T23:00:00Z",
        "pH": 7.0,
        "turbidity": 5.0,
        "tds": 200.0,
        "temperature": 150.0  # Extreme out of range
    })
    result = process_telemetry_payload(payload, db_session_factory=lambda: db_session)
    assert result is False


# 8. Latest reading authority endpoint
def test_latest_reading_endpoint(client, authority_token_headers, db_session, seeded_stations):
    payload1 = json.dumps({
        "station_code": "ARK-001",
        "device_id": "STATION-ARK-001",
        "timestamp": "2026-08-31T23:00:00Z",
        "pH": 7.0,
        "turbidity": 4.0,
        "tds": 200.0,
        "temperature": 25.0
    })
    payload2 = json.dumps({
        "station_code": "ARK-001",
        "device_id": "STATION-ARK-001",
        "timestamp": "2026-08-31T23:05:00Z",  # Newest
        "pH": 6.8,
        "turbidity": 12.0,
        "tds": 350.0,
        "temperature": 27.5
    })

    process_telemetry_payload(payload1, db_session_factory=lambda: db_session)
    process_telemetry_payload(payload2, db_session_factory=lambda: db_session)

    res = client.get("/api/authority/stations/ARK-001/readings/latest", headers=authority_token_headers)
    assert res.status_code == 200
    data = res.json()

    assert data["station_code"] == "ARK-001"
    assert data["pH"] == 6.8
    assert data["turbidity"] == 12.0
    assert data["tds"] == 350.0
    assert data["temperature"] == 27.5


# 9. Multiple readings for one station
def test_multiple_readings_for_one_station(client, authority_token_headers, db_session, seeded_stations):
    for i in range(3):
        payload = json.dumps({
            "station_code": "ARK-002",
            "device_id": "STATION-ARK-002",
            "timestamp": f"2026-08-31T23:0{i}:00Z",
            "pH": 7.0 + i * 0.1,
            "turbidity": 5.0 + i,
            "tds": 200.0 + i * 10,
            "temperature": 25.0 + i
        })
        process_telemetry_payload(payload, db_session_factory=lambda: db_session)

    res = client.get("/api/authority/stations/ARK-002/readings", headers=authority_token_headers)
    assert res.status_code == 200
    history = res.json()
    assert len(history) == 3
    # Check ordering descending by timestamp
    assert history[0]["pH"] == 7.2
    assert history[2]["pH"] == 7.0


# 10. Multiple stations receiving telemetry
def test_multiple_stations_receiving_telemetry(db_session, seeded_stations):
    for code in ["ARK-001", "ARK-002", "ARK-003"]:
        payload = json.dumps({
            "station_code": code,
            "device_id": f"STATION-{code}",
            "timestamp": "2026-08-31T23:00:00Z",
            "pH": 7.1,
            "turbidity": 4.0,
            "tds": 190.0,
            "temperature": 24.5
        })
        assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True

    for code in ["ARK-001", "ARK-002", "ARK-003"]:
        station = db_session.query(MonitoringStation).filter(MonitoringStation.station_code == code).first()
        reading = db_session.query(SensorReading).filter(SensorReading.station_id == station.id).first()
        assert reading is not None
        assert reading.device_id == f"STATION-{code}"


# 11. Authority role requirement
def test_authority_role_requirement(client, product_token_headers, db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-001",
        "device_id": "STATION-ARK-001",
        "timestamp": "2026-08-31T23:00:00Z",
        "pH": 7.0,
        "turbidity": 4.0,
        "tds": 200.0,
        "temperature": 25.0
    })
    process_telemetry_payload(payload, db_session_factory=lambda: db_session)

    # 403 when called by PRODUCT_USER role
    res_product = client.get("/api/authority/stations/ARK-001/readings/latest", headers=product_token_headers)
    assert res_product.status_code == 403

    # 401 when called unauthenticated
    res_no_auth = client.get("/api/authority/stations/ARK-001/readings/latest")
    assert res_no_auth.status_code == 401


# 12. Public endpoint unchanged
def test_public_endpoint_unchanged(client, db_session, seeded_stations):
    res = client.get("/api/public/stations/ARK-001")
    assert res.status_code == 200
    data = res.json()
    assert data["station_code"] == "ARK-001"
    assert "public_warning" in data
    assert "public_message" in data


# ---------------------------------------------------------------------------
# Phase 6: ML integration (MQTT -> validation -> ML inference -> PostgreSQL)
# ---------------------------------------------------------------------------
def _assert_ml_fields_present(reading: SensorReading) -> None:
    """A processed reading carries a complete, internally consistent ML result."""
    assert reading.anomaly_label in (0, 1)
    assert reading.anomaly_score is not None
    assert reading.water_quality_label in ("Safe", "Unsafe")
    assert reading.safe_probability is not None and 0.0 <= reading.safe_probability <= 1.0
    assert reading.unsafe_probability is not None and 0.0 <= reading.unsafe_probability <= 1.0
    assert abs((reading.safe_probability + reading.unsafe_probability) - 1.0) < 1e-6
    assert reading.ml_processed_at is not None


# 13a. Normal MQTT reading -> stored -> ML result generated
def test_normal_reading_gets_ml_result(db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-001",
        "device_id": "STATION-ARK-001",
        "timestamp": "2026-08-31T23:00:00Z",
        "pH": 7.2,
        "turbidity": 4.5,
        "tds": 210.0,
        "temperature": 25.5,
    })
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True

    reading = db_session.query(SensorReading).filter(SensorReading.device_id == "STATION-ARK-001").first()
    assert reading is not None
    _assert_ml_fields_present(reading)


# 13b. Deterioration-like reading -> stored -> ML result generated
def test_deterioration_like_reading_gets_ml_result(db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-002",
        "device_id": "STATION-ARK-002",
        "timestamp": "2026-08-31T23:00:00Z",
        "pH": 5.0,
        "turbidity": 60.0,
        "tds": 900.0,
        "temperature": 25.0,
    })
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True

    reading = db_session.query(SensorReading).filter(SensorReading.device_id == "STATION-ARK-002").first()
    assert reading is not None
    _assert_ml_fields_present(reading)
    # Random Forest predicts the benchmark dataset's class for these conditions.
    assert reading.water_quality_label == "Unsafe"
    assert reading.unsafe_probability >= reading.safe_probability


# 13c. Sensor-fault reading -> validation rejects -> nothing stored, no ML result
def test_sensor_fault_reading_not_stored_and_no_ml_result(db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-001",
        "device_id": "STATION-ARK-001",
        "timestamp": "2026-08-31T23:00:00Z",
        "pH": 7.0,
        "turbidity": -5.0,  # sensor fault: negative
        "tds": 200.0,
        "temperature": 25.0,
    })
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is False
    assert db_session.query(SensorReading).count() == 0  # no fabricated ML result either


# 13c-bis. Telemetry-valid but ML-invalid reading -> stored, ML fields stay NULL.
# Temperature 65 degC passes live telemetry validation [-20, 70] but lies outside
# the Phase 5 ML physical range [-10, 60]; ingestion must remain functional and
# no fabricated ML prediction may be stored.
def test_telemetry_valid_but_ml_invalid_stored_without_ml(db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-001",
        "device_id": "STATION-ARK-001",
        "timestamp": "2026-08-31T23:00:00Z",
        "pH": 7.0,
        "turbidity": 4.0,
        "tds": 200.0,
        "temperature": 65.0,  # valid for telemetry, outside ML range
    })
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True

    reading = db_session.query(SensorReading).filter(SensorReading.device_id == "STATION-ARK-001").first()
    assert reading is not None  # ingestion remained functional
    assert reading.anomaly_label is None
    assert reading.anomaly_score is None
    assert reading.water_quality_label is None
    assert reading.safe_probability is None
    assert reading.unsafe_probability is None
    assert reading.ml_processed_at is None


# 13d/e. Unknown station and malformed message keep existing behavior
# (tests 2 and 3 above) AND never produce ML results.
def test_unknown_station_and_malformed_produce_no_ml_results(db_session, seeded_stations):
    unknown = json.dumps({
        "station_code": "UNKNOWN-999", "device_id": "X", "timestamp": "2026-08-31T23:00:00Z",
        "pH": 7.0, "turbidity": 4.0, "tds": 200.0, "temperature": 25.0,
    })
    assert process_telemetry_payload(unknown, db_session_factory=lambda: db_session) is False
    malformed = "{ broken json"
    assert process_telemetry_payload(malformed, db_session_factory=lambda: db_session) is False
    assert db_session.query(SensorReading).count() == 0


# 13f. Multiple stations -> correct ML processing per reading
def test_multiple_stations_ml_processed_per_reading(db_session, seeded_stations):
    for code in ["ARK-001", "ARK-002", "ARK-003"]:
        payload = json.dumps({
            "station_code": code,
            "device_id": f"STATION-{code}",
            "timestamp": "2026-08-31T23:00:00Z",
            "pH": 7.1,
            "turbidity": 4.0,
            "tds": 190.0,
            "temperature": 24.5,
        })
        assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True

    for code in ["ARK-001", "ARK-002", "ARK-003"]:
        station = db_session.query(MonitoringStation).filter(MonitoringStation.station_code == code).first()
        reading = db_session.query(SensorReading).filter(SensorReading.station_id == station.id).first()
        assert reading is not None
        _assert_ml_fields_present(reading)


# 13g. MQTT broker failure -> graceful recovery remains intact
def test_mqtt_broker_failure_graceful_recovery(db_session):
    from app.services.mqtt_service import MQTTSubscriberService

    service = MQTTSubscriberService(host="127.0.0.1", port=1, db_session_factory=lambda: db_session)
    # Must not raise even though nothing is listening; the app stays active.
    service.start()
    assert service.is_connected is False
    service.stop()


# Phase 6: ML service failure must not break ingestion (no fake prediction).
def test_ml_failure_keeps_ingestion_functional(db_session, seeded_stations, monkeypatch):
    from importlib import import_module
    mqtt_module = import_module("app.services.mqtt_service")  # the true module (the package re-export shadows the submodule attribute)

    class BrokenService:
        is_available = False

        def load_models(self):
            return False

    monkeypatch.setattr(mqtt_module, "ml_service", BrokenService())
    payload = json.dumps({
        "station_code": "ARK-003",
        "device_id": "STATION-ARK-003",
        "timestamp": "2026-08-31T23:00:00Z",
        "pH": 7.0,
        "turbidity": 4.0,
        "tds": 200.0,
        "temperature": 25.0,
    })
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True
    reading = db_session.query(SensorReading).filter(SensorReading.device_id == "STATION-ARK-003").first()
    assert reading is not None  # ingestion functional
    assert reading.water_quality_label is None  # no fabricated prediction
    assert reading.ml_processed_at is None
