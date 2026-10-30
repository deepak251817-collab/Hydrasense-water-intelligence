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


# ---------------------------------------------------------------------------
# ESP32 hardware telemetry: NULL = uncalibrated/failed sensor (never "safe"),
# source provenance, diagnostics blob, duplicate guard.
# ---------------------------------------------------------------------------
HARDWARE_DIAGNOSTICS = {
    "ph": {"raw_adc": 19952, "voltage_v": 2.494, "calibration_status": "pending"},
    "tds": {"raw_adc": 32, "voltage_v": 0.004, "calibration_status": "pending"},
    "turbidity": {"raw_adc": 12592, "voltage_v": 1.574, "calibration_status": "pending"},
    "temperature": {"sensor": "DS18B20", "valid": True},
    "device": {"uptime_ms": 69112, "wifi_rssi_dbm": -41, "errors": []},
}


# 14. Uncalibrated ESP32 reading: NULL sensor values + raw diagnostics stored.
#     No fabricated pH/NTU/ppm, no ML prediction, provenance recorded.
def test_uncalibrated_hardware_reading_stored_without_fabrication(db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-001",
        "device_id": "ESP32-HS-001",
        "timestamp": "2026-10-22T10:15:30Z",
        "pH": None,
        "turbidity": None,
        "tds": None,
        "temperature": 27.0,
        "source": "esp32",
        "diagnostics": HARDWARE_DIAGNOSTICS,
    })
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True

    reading = db_session.query(SensorReading).filter(SensorReading.device_id == "ESP32-HS-001").first()
    assert reading is not None
    assert reading.ph is None
    assert reading.turbidity is None
    assert reading.tds is None
    assert reading.temperature == 27.0
    assert reading.source == "esp32"
    assert reading.diagnostics["ph"]["raw_adc"] == 19952
    assert reading.diagnostics["tds"]["voltage_v"] == 0.004
    # NULL sensor values -> ML must NOT run (no prediction from missing data).
    assert reading.anomaly_label is None
    assert reading.water_quality_label is None
    assert reading.ml_processed_at is None


# 15. Absent `source` defaults to "simulator" — simulated and physical readings
#     stay distinguishable even for legacy payloads.
def test_missing_source_defaults_to_simulator(db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-001",
        "device_id": "STATION-ARK-001",
        "timestamp": "2026-10-22T10:15:30Z",
        "pH": 7.1,
        "turbidity": 4.0,
        "tds": 200.0,
        "temperature": 25.0,
    })
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True
    reading = db_session.query(SensorReading).filter(SensorReading.device_id == "STATION-ARK-001").first()
    assert reading.source == "simulator"
    assert reading.diagnostics is None
    # Full values -> ML runs as before.
    assert reading.water_quality_label is not None


# 16. Invalid source tag rejected.
def test_invalid_source_tag_rejection(db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-001",
        "device_id": "ESP32-HS-001",
        "timestamp": "2026-10-22T10:15:30Z",
        "pH": None,
        "turbidity": None,
        "tds": None,
        "temperature": 27.0,
        "source": "bad tag with spaces!",
    })
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is False
    assert db_session.query(SensorReading).count() == 0


# 17. Malformed diagnostics (non-object / oversized) rejected.
def test_malformed_diagnostics_rejection(db_session, seeded_stations):
    base = {
        "station_code": "ARK-001",
        "device_id": "ESP32-HS-001",
        "timestamp": "2026-10-22T10:15:30Z",
        "pH": None,
        "turbidity": None,
        "tds": None,
        "temperature": 27.0,
    }
    not_object = dict(base, diagnostics=[1, 2, 3])
    assert process_telemetry_payload(json.dumps(not_object), db_session_factory=lambda: db_session) is False
    oversized = dict(base, diagnostics={"blob": "x" * 9000})
    assert process_telemetry_payload(json.dumps(oversized), db_session_factory=lambda: db_session) is False
    assert db_session.query(SensorReading).count() == 0


# 18. Failed DS18B20 -> temperature NULL (not a fabricated 0 or -127),
#     reading still ingested, ML skipped.
def test_failed_temperature_sensor_stored_as_null(db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-002",
        "device_id": "ESP32-HS-001",
        "timestamp": "2026-10-22T10:16:00Z",
        "pH": None,
        "turbidity": None,
        "tds": None,
        "temperature": None,
        "source": "esp32",
        "diagnostics": {"temperature": {"sensor": "DS18B20", "valid": False, "error": "disconnected"}},
    })
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True
    reading = db_session.query(SensorReading).filter(SensorReading.device_id == "ESP32-HS-001").first()
    assert reading is not None
    assert reading.temperature is None
    assert reading.water_quality_label is None


# 19. Duplicate guard: redelivered message (same device_id + timestamp) does
# not create a second row (retransmits keep the identical device clock value).
def test_duplicate_telemetry_not_stored_twice(db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-001",
        "device_id": "ESP32-HS-001",
        "timestamp": "2026-10-22T10:15:30Z",
        "pH": None,
        "turbidity": None,
        "tds": None,
        "temperature": 27.0,
        "source": "esp32",
    })
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True
    assert db_session.query(SensorReading).count() == 1

    # A NEW reading (different timestamp) is still stored.
    payload2 = json.dumps({
        "station_code": "ARK-001",
        "device_id": "ESP32-HS-001",
        "timestamp": "2026-10-22T10:15:33Z",
        "pH": None,
        "turbidity": None,
        "tds": None,
        "temperature": 27.1,
        "source": "esp32",
    })
    assert process_telemetry_payload(payload2, db_session_factory=lambda: db_session) is True
    assert db_session.query(SensorReading).count() == 2


# 19b. Live turbidity relative index (ESP32): value 0-100 stored verbatim, unit
#      tag + status band travel in diagnostics, never labelled NTU.
def test_live_turbidity_relative_index_stored(db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-001",
        "device_id": "ESP32-HS-001",
        "timestamp": "2026-10-22T10:20:00Z",
        "pH": None,
        "turbidity": 61.7,
        "tds": None,
        "temperature": 27.0,
        "source": "esp32",
        "diagnostics": {
            "turbidity": {
                "unit": "relative_index_0_100",
                "raw_adc": 8431,
                "voltage_v": 1.054,
                "sensor_output_v": 1.581,
                "relative_index": 61.7,
                "relative_status": "CLOUDIER",
                "calibration_status": "provisional_index",
            },
        },
    })
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True
    reading = db_session.query(SensorReading).filter(SensorReading.device_id == "ESP32-HS-001").first()
    assert reading is not None
    assert reading.turbidity == 61.7
    turb_diag = reading.diagnostics["turbidity"]
    assert turb_diag["unit"] == "relative_index_0_100"
    assert turb_diag["relative_status"] == "CLOUDIER"
    assert turb_diag["sensor_output_v"] == 1.581
    # Not calibrated NTU -> ML must not treat it as a full measurement set.
    assert reading.water_quality_label is None


# 19c. Boundary: turbidity index exactly 0 and exactly 100 both accepted;
#      negative index rejected.
def test_turbidity_relative_index_boundaries(db_session, seeded_stations):
    base = {
        "station_code": "ARK-001",
        "device_id": "ESP32-HS-001",
        "pH": None,
        "tds": None,
        "temperature": 27.0,
        "source": "esp32",
    }
    for ts, value in [("2026-10-22T10:21:00Z", 0.0), ("2026-10-22T10:21:03Z", 100.0)]:
        payload = json.dumps(dict(base, timestamp=ts, turbidity=value))
        assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True
    assert db_session.query(SensorReading).count() == 2

    bad = json.dumps(dict(base, timestamp="2026-10-22T10:21:06Z", turbidity=-0.5))
    assert process_telemetry_payload(bad, db_session_factory=lambda: db_session) is False


# 20. Authority endpoints expose provenance + diagnostics + NULL values honestly.
def test_latest_reading_endpoint_exposes_hardware_fields(client, authority_token_headers, db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-001",
        "device_id": "ESP32-HS-001",
        "timestamp": "2026-10-22T10:15:30Z",
        "pH": None,
        "turbidity": None,
        "tds": None,
        "temperature": 27.0,
        "source": "esp32",
        "diagnostics": HARDWARE_DIAGNOSTICS,
    })
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True

    res = client.get("/api/authority/stations/ARK-001/readings/latest", headers=authority_token_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["pH"] is None
    assert data["temperature"] == 27.0
    assert data["source"] == "esp32"
    assert data["diagnostics"]["ph"]["calibration_status"] == "pending"

    res_analysis = client.get(
        "/api/authority/stations/ARK-001/readings/latest/analysis", headers=authority_token_headers
    )
    assert res_analysis.status_code == 200
    analysis = res_analysis.json()
    assert analysis["ph"] is None
    assert analysis["source"] == "esp32"
    assert analysis["ml"]["ml_processed_at"] is None  # no fabricated ML result


# ---------------------------------------------------------------------------
# Relative turbidity units: the ESP32 index (0-100) is NOT NTU. The unit is
# stored per row, validated, and surfaced through the API.
# ---------------------------------------------------------------------------
# 21. Top-level unit/status contract (as documented for the device) is stored.
def test_top_level_turbidity_unit_and_status_stored(db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-001",
        "device_id": "ESP32-HS-001",
        "timestamp": "2026-10-24T09:00:00Z",
        "pH": None,
        "turbidity": 68.2,
        "turbidity_status": "CLOUDIER",
        "turbidity_unit": "relative_index_0_100",
        "tds": None,
        "temperature": 27.0,
        "source": "esp32",
    })
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True
    reading = db_session.query(SensorReading).filter(SensorReading.device_id == "ESP32-HS-001").first()
    assert reading.turbidity == 68.2
    assert reading.turbidity_unit == "relative_index_0_100"
    assert reading.turbidity_status == "CLOUDIER"


# 22. Current firmware contract: unit/status live inside diagnostics.turbidity.
def test_diagnostics_turbidity_unit_fallback(db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-001",
        "device_id": "ESP32-HS-001",
        "timestamp": "2026-10-24T09:00:03Z",
        "pH": None,
        "turbidity": 41.5,
        "tds": None,
        "temperature": 27.0,
        "source": "esp32",
        "diagnostics": {
            "turbidity": {
                "unit": "relative_index_0_100",
                "raw_adc": 5000,
                "voltage_v": 0.625,
                "sensor_output_v": 0.938,
                "relative_index": 41.5,
                "relative_status": "MODERATE",
                "calibration_status": "provisional_index",
            }
        },
    })
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True
    reading = db_session.query(SensorReading).filter(SensorReading.device_id == "ESP32-HS-001").first()
    assert reading.turbidity_unit == "relative_index_0_100"
    assert reading.turbidity_status == "MODERATE"


# 23. Index above 100 rejected; 0 and 100 accepted.
def test_relative_index_out_of_range_rejected(db_session, seeded_stations):
    base = {
        "station_code": "ARK-001",
        "device_id": "ESP32-HS-001",
        "pH": None,
        "tds": None,
        "temperature": 27.0,
        "turbidity_unit": "relative_index_0_100",
        "source": "esp32",
    }
    for ts, value in [("2026-10-24T09:01:00Z", 0.0), ("2026-10-24T09:01:03Z", 100.0)]:
        assert process_telemetry_payload(
            json.dumps(dict(base, timestamp=ts, turbidity=value)),
            db_session_factory=lambda: db_session,
        ) is True
    assert db_session.query(SensorReading).count() == 2

    too_high = dict(base, timestamp="2026-10-24T09:01:06Z", turbidity=100.5)
    ok, reason = validate_telemetry_payload(too_high)
    assert ok is False
    assert "0, 100" in reason
    assert process_telemetry_payload(
        json.dumps(too_high), db_session_factory=lambda: db_session
    ) is False
    assert db_session.query(SensorReading).count() == 2


# 24. NTU-style values are NOT bounded by 100 (simulator keeps working) and the
#     simulator's explicit `ntu` unit is stored; a band is dropped for NTU.
def test_ntu_unit_does_not_get_index_bounds(db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-002",
        "device_id": "STATION-ARK-002",
        "timestamp": "2026-10-24T09:02:00Z",
        "pH": 7.1,
        "turbidity": 78.5,
        "turbidity_status": "CLOUDIER",  # meaningless for NTU -> dropped
        "turbidity_unit": "ntu",
        "tds": 220.0,
        "temperature": 25.0,
        "source": "simulator",
    })
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True
    reading = db_session.query(SensorReading).filter(SensorReading.device_id == "STATION-ARK-002").first()
    assert reading.turbidity == 78.5
    assert reading.turbidity_unit == "ntu"
    assert reading.turbidity_status is None


# 25. Ingestion upper bounds reject physically implausible values (stuck ADC,
#     shorted probe or a malicious publisher) instead of storing them.
def test_ingestion_upper_bounds_are_enforced():
    base = {
        "station_code": "ARK-001",
        "device_id": "ESP32-HS-001",
        "timestamp": "2026-10-24T09:05:00Z",
        "pH": 7.0,
        "tds": 50000.0,
        "temperature": 25.0,
        "turbidity": 4000.0,
        "turbidity_unit": "ntu",
        "source": "esp32",
    }
    assert validate_telemetry_payload(base) == (True, "Valid")

    too_much_tds = dict(base, tds=50000.1)
    ok, reason = validate_telemetry_payload(too_much_tds)
    assert ok is False and "tds out of valid physical range" in reason

    too_much_turbidity = dict(base, turbidity=4000.1)
    ok, reason = validate_telemetry_payload(too_much_turbidity)
    assert ok is False and "turbidity out of valid physical range" in reason


def test_ingestion_bounds_reject_non_finite_values():
    base = {
        "station_code": "ARK-001",
        "device_id": "ESP32-HS-001",
        "timestamp": "2026-10-24T09:06:00Z",
        "pH": 7.0,
        "tds": float("nan"),
        "temperature": 25.0,
        "turbidity": 10.0,
        "source": "esp32",
    }
    ok, _reason = validate_telemetry_payload(base)
    assert ok is False


# 26. Malformed unit/status values are rejected without crashing the subscriber.
@pytest.mark.parametrize("bad", [
    {"turbidity_unit": 42},
    {"turbidity_unit": "relative index with spaces"},
    {"turbidity_status": "VERY_CLOUDY"},
    {"turbidity_status": 3},
])
def test_malformed_turbidity_metadata_rejected(db_session, seeded_stations, bad):
    payload = json.dumps({
        "station_code": "ARK-001",
        "device_id": "ESP32-HS-001",
        "timestamp": "2026-10-24T09:03:00Z",
        "pH": None,
        "turbidity": 50.0,
        "tds": None,
        "temperature": 27.0,
        "source": "esp32",
        **bad,
    })
    ok, _reason = validate_telemetry_payload(json.loads(payload))
    assert ok is False
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is False
    assert db_session.query(SensorReading).count() == 0


# 26. Missing unit -> stored as NULL (unknown), never assumed NTU or index.
def test_missing_turbidity_unit_stored_as_unknown(db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-003",
        "device_id": "LEGACY-DEVICE",
        "timestamp": "2026-10-24T09:04:00Z",
        "pH": 7.0,
        "turbidity": 12.0,
        "tds": 200.0,
        "temperature": 25.0,
    })
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True
    reading = db_session.query(SensorReading).filter(SensorReading.device_id == "LEGACY-DEVICE").first()
    assert reading.turbidity == 12.0
    assert reading.turbidity_unit is None   # unknown, not "ntu" and not relative index
    assert reading.turbidity_status is None


# 27. Null turbidity -> no unit/status even if metadata is present.
def test_null_turbidity_drops_unit_and_status(db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-001",
        "device_id": "ESP32-HS-001",
        "timestamp": "2026-10-24T09:05:00Z",
        "pH": None,
        "turbidity": None,
        "turbidity_unit": "relative_index_0_100",
        "turbidity_status": "CLOUDIER",
        "tds": None,
        "temperature": 27.0,
        "source": "esp32",
    })
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True
    reading = db_session.query(SensorReading).filter(SensorReading.device_id == "ESP32-HS-001").first()
    assert reading.turbidity is None
    assert reading.turbidity_unit is None
    assert reading.turbidity_status is None


# 28. Relative index is not fed to the NTU-trained ML models, even when every
#     other value is present.
def test_relative_index_skips_ml(db_session, seeded_stations):
    payload = json.dumps({
        "station_code": "ARK-001",
        "device_id": "ESP32-HS-001",
        "timestamp": "2026-10-24T09:06:00Z",
        "pH": 7.05,
        "turbidity": 55.0,
        "turbidity_unit": "relative_index_0_100",
        "turbidity_status": "CLOUDIER",
        "tds": 210.0,
        "temperature": 27.0,
        "source": "esp32",
    })
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True
    reading = db_session.query(SensorReading).filter(SensorReading.device_id == "ESP32-HS-001").first()
    assert reading.turbidity == 55.0
    assert reading.water_quality_label is None
    assert reading.anomaly_label is None
    assert reading.ml_processed_at is None


# 29. API exposes turbidity_unit/turbidity_status on latest + history endpoints.
def test_api_exposes_turbidity_unit_and_status(
    client, authority_token_headers, db_session, seeded_stations
):
    payload = json.dumps({
        "station_code": "ARK-001",
        "device_id": "ESP32-HS-001",
        "timestamp": "2026-10-24T09:07:00Z",
        "pH": None,
        "turbidity": 77.7,
        "turbidity_unit": "relative_index_0_100",
        "turbidity_status": "CLOUDIER",
        "tds": None,
        "temperature": 27.0,
        "source": "esp32",
    })
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is True

    latest = client.get(
        "/api/authority/stations/ARK-001/readings/latest", headers=authority_token_headers
    )
    assert latest.status_code == 200
    body = latest.json()
    assert body["turbidity"] == 77.7
    assert body["turbidity_unit"] == "relative_index_0_100"
    assert body["turbidity_status"] == "CLOUDIER"

    history = client.get(
        "/api/authority/stations/ARK-001/readings", headers=authority_token_headers
    )
    assert history.status_code == 200
    rows = history.json()
    assert rows[0]["turbidity_unit"] == "relative_index_0_100"
    assert rows[0]["turbidity_status"] == "CLOUDIER"

# ---------------------------------------------------------------------------
# MQTT integration hardening: parser edge cases, subscriber contract and
# callback resilience (no broker required).
# ---------------------------------------------------------------------------
# 30. Valid JSON that is not an object is rejected without crashing.
@pytest.mark.parametrize("payload", ["[]", "\"just a string\"", "null", "42", "true"])
def test_non_object_json_payload_rejected(db_session, seeded_stations, payload):
    assert process_telemetry_payload(payload, db_session_factory=lambda: db_session) is False
    assert db_session.query(SensorReading).count() == 0


# 31. Every required field is enforced (missing -> rejected, nothing stored).
@pytest.mark.parametrize("missing", [
    "station_code", "device_id", "timestamp", "pH", "turbidity", "tds", "temperature",
])
def test_missing_required_field_rejected(db_session, seeded_stations, missing):
    payload = {
        "station_code": "ARK-001",
        "device_id": "STATION-ARK-001",
        "timestamp": "2026-10-25T08:00:00Z",
        "pH": 7.1,
        "turbidity": 4.2,
        "tds": 205.0,
        "temperature": 25.0,
    }
    payload.pop(missing)
    ok, reason = validate_telemetry_payload(payload)
    assert ok is False and missing in reason
    assert process_telemetry_payload(
        json.dumps(payload), db_session_factory=lambda: db_session
    ) is False
    assert db_session.query(SensorReading).count() == 0


# 32. Non-numeric sensor values (string/dict/list/bool) are rejected.
@pytest.mark.parametrize("field,value", [
    ("pH", "not-a-number"),
    ("turbidity", {"value": 4.0}),
    ("tds", [200]),
    ("temperature", True),
])
def test_non_numeric_sensor_value_rejected(db_session, seeded_stations, field, value):
    payload = {
        "station_code": "ARK-001",
        "device_id": "STATION-ARK-001",
        "timestamp": "2026-10-25T08:00:03Z",
        "pH": 7.1,
        "turbidity": 4.2,
        "tds": 205.0,
        "temperature": 25.0,
    }
    payload[field] = value
    ok, _reason = validate_telemetry_payload(payload)
    assert ok is False
    assert process_telemetry_payload(
        json.dumps(payload), db_session_factory=lambda: db_session
    ) is False
    assert db_session.query(SensorReading).count() == 0


# 33. Timestamp handling: bad formats rejected, UTC offsets accepted.
def test_timestamp_formats(db_session, seeded_stations):
    base = {
        "station_code": "ARK-001",
        "device_id": "STATION-ARK-001",
        "pH": 7.0,
        "turbidity": 4.0,
        "tds": 200.0,
        "temperature": 25.0,
    }
    for bad_ts in ["not-a-date", "2026-10-25", "", None, 12345]:
        payload = dict(base, timestamp=bad_ts)
        assert process_telemetry_payload(
            json.dumps(payload), db_session_factory=lambda: db_session
        ) is False
    assert db_session.query(SensorReading).count() == 0

    # ISO-8601 with an explicit offset must be accepted.
    payload = dict(base, timestamp="2026-10-25T13:30:00+05:30")
    assert process_telemetry_payload(
        json.dumps(payload), db_session_factory=lambda: db_session
    ) is True
    reading = db_session.query(SensorReading).first()
    assert reading is not None
    assert reading.timestamp.year == 2026 and reading.timestamp.hour == 13


# 34. Subscriber contract: topic pattern + QoS 1 subscription.
def test_subscriber_topic_pattern_and_subscription(db_session):
    from app.services.mqtt_service import MQTTSubscriberService

    service = MQTTSubscriberService(db_session_factory=lambda: db_session)
    assert service.topic == "hydrasense/stations/+/telemetry"

    calls = {}

    def fake_subscribe(topic, qos=0):
        calls["topic"] = topic
        calls["qos"] = qos
        return (0, 1)

    service.client.subscribe = fake_subscribe
    service.client.on_connect(service.client, None, None, 0)
    assert calls["topic"] == "hydrasense/stations/+/telemetry"
    assert calls["qos"] == 1
    assert service.is_connected is True


# 35. The on_message callback ingests valid payloads and swallows bad ones.
def test_on_message_callback_ingests_and_survives_bad_payloads(db_session, seeded_stations):
    from app.services.mqtt_service import MQTTSubscriberService

    service = MQTTSubscriberService(db_session_factory=lambda: db_session)

    class Msg:
        topic = "hydrasense/stations/ARK-001/telemetry"

        def __init__(self, payload: bytes):
            self.payload = payload

    # Malformed JSON must not raise out of the callback.
    service.client.on_message(service.client, None, Msg(b"{not json"))
    assert db_session.query(SensorReading).count() == 0

    good = json.dumps({
        "station_code": "ARK-001",
        "device_id": "ESP32-HS-001",
        "timestamp": "2026-10-25T08:10:00Z",
        "pH": None,
        "turbidity": 42.0,
        "turbidity_unit": "relative_index_0_100",
        "turbidity_status": "MODERATE",
        "tds": None,
        "temperature": 27.0,
        "source": "esp32",
    }).encode("utf-8")
    service.client.on_message(service.client, None, Msg(good))
    reading = db_session.query(SensorReading).filter(SensorReading.device_id == "ESP32-HS-001").first()
    assert reading is not None
    assert reading.source == "esp32"
    assert reading.turbidity_unit == "relative_index_0_100"
    assert reading.turbidity_status == "MODERATE"
