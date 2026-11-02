"""Water Suitability Assessment tests.

Covers the honesty contract: only calibrated, physical, fresh measurements are
compared with BIS IS 10500 / CPCB limits; everything else is reported as
missing or not comparable. Boundary values and every result category are
exercised, plus persistence idempotency and public/authority access rules.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.models.water import MonitoringStation, SensorReading, WaterSuitabilityAssessment
from app.services.mqtt_service import process_telemetry_payload
from app.services.water_suitability import (
    RULESET_VERSION,
    USES,
    assess_reading,
    assess_use,
    USES_BY_CODE,
)


NOW = datetime.now(timezone.utc)


def make_reading(
    station_id: int,
    *,
    ph=None,
    turbidity=None,
    turbidity_unit=None,
    tds=None,
    temperature=27.0,
    source="esp32",
    timestamp=None,
    diagnostics=None,
    device_id="ESP32-HS-001",
) -> SensorReading:
    return SensorReading(
        station_id=station_id,
        device_id=device_id,
        timestamp=timestamp or NOW,
        ph=ph,
        turbidity=turbidity,
        turbidity_unit=turbidity_unit,
        tds=tds,
        temperature=temperature,
        source=source,
        diagnostics=diagnostics,
    )


def calibrated_diag(**values):
    diag = {"device": {"uptime_ms": 1000, "errors": []}}
    for key, value in values.items():
        diag[key] = {"calibration_status": value}
    return diag


def assessment(reading, use):
    return assess_use(USES_BY_CODE[use], reading, now=NOW)


def param(result, key):
    return next(p for p in result["parameters"] if p["parameter"] == key)


# ---------------------------------------------------------------------------
# Measurement provenance and comparability
# ---------------------------------------------------------------------------

class TestComparability:
    def test_calibrated_physical_values_are_compared(self):
        reading = make_reading(
            1, ph=7.1, tds=310.0, turbidity=0.6, turbidity_unit="ntu",
            diagnostics=calibrated_diag(ph="calibrated", tds="calibrated", turbidity="calibrated"),
        )
        result = assessment(reading, "drinking")

        assert param(result, "ph")["status"] == "within_acceptable"
        assert param(result, "tds")["status"] == "within_acceptable"
        assert param(result, "turbidity")["status"] == "within_acceptable"
        assert result["data_quality"]["comparable_parameters"] == ["ph", "tds", "turbidity"]

    def test_ntu_turbidity_without_calibration_is_not_compared(self):
        reading = make_reading(
            1, ph=7.1, tds=310.0, turbidity=0.6, turbidity_unit="ntu",
            diagnostics=calibrated_diag(ph="calibrated", tds="calibrated"),
        )
        result = assessment(reading, "drinking")
        turbidity = param(result, "turbidity")
        assert turbidity["status"] == "not_comparable"
        assert "uncalibrated" in turbidity["note"].lower()

    def test_relative_index_turbidity_is_never_compared_to_ntu(self):
        reading = make_reading(
            1, ph=7.1, tds=310.0, turbidity=68.0, turbidity_unit="relative_index_0_100",
            diagnostics=calibrated_diag(ph="calibrated", tds="calibrated"),
        )
        result = assessment(reading, "drinking")
        turbidity = param(result, "turbidity")

        assert turbidity["status"] == "not_comparable"
        assert "relative index" in turbidity["note"].lower()
        assert "turbidity" not in result["data_quality"]["comparable_parameters"]
        assert any(e["parameter"] == "turbidity"
                   for e in result["data_quality"]["excluded_parameters"])

    def test_uncalibrated_estimate_is_not_compared(self):
        reading = make_reading(
            1, ph=9.8, tds=900.0, turbidity=500.0, turbidity_unit="ntu",
            diagnostics=calibrated_diag(ph="demo_estimate", tds="demo_estimate"),
        )
        result = assessment(reading, "drinking")

        assert param(result, "ph")["status"] == "not_comparable"
        assert param(result, "tds")["status"] == "not_comparable"
        assert "demo_estimate" in param(result, "ph")["note"]
        # An excluded out-of-range estimate must not trigger outside_limits.
        assert result["result"] == "insufficient_data"

    def test_missing_calibration_status_is_not_compared(self):
        reading = make_reading(1, ph=7.0, tds=200.0, turbidity=1.0, turbidity_unit="ntu")
        result = assessment(reading, "drinking")
        assert param(result, "ph")["status"] == "not_comparable"

    def test_simulated_reading_is_excluded_from_comparison(self):
        reading = make_reading(
            1, ph=7.0, tds=200.0, turbidity=4.0, turbidity_unit="ntu", source="simulator",
        )
        result = assessment(reading, "drinking")

        assert param(result, "ph")["status"] == "not_comparable"
        assert "simulated" in param(result, "ph")["note"].lower()
        assert result["result"] == "insufficient_data"

    def test_no_reading_returns_insufficient_data(self):
        result = assessment(None, "drinking")
        assert result["result"] == "insufficient_data"
        assert result["data_quality"]["freshness"] == "no_data"
        assert all(p["status"] == "not_measured" for p in result["parameters"])
        assert result["measured_values"] == []


# ---------------------------------------------------------------------------
# Boundary values and result categories
# ---------------------------------------------------------------------------

class TestResultCategories:
    def test_ph_at_limits_is_within_acceptable(self):
        for ph in (6.5, 8.5):
            reading = make_reading(
                1, ph=ph, tds=100.0, turbidity=0.5, turbidity_unit="ntu",
                diagnostics=calibrated_diag(ph="calibrated", tds="calibrated", turbidity="calibrated"),
            )
            assert param(assessment(reading, "drinking"), "ph")["status"] == "within_acceptable"

    def test_ph_just_outside_limit_is_outside_limits(self):
        reading = make_reading(
            1, ph=8.51, tds=100.0, turbidity=0.5, turbidity_unit="ntu",
            diagnostics=calibrated_diag(ph="calibrated", tds="calibrated", turbidity="calibrated"),
        )
        result = assessment(reading, "drinking")
        assert param(result, "ph")["status"] == "outside_limits"
        assert result["result"] == "outside_limits"
        assert "Outside the applicable limits: pH" in result["summary"]

    def test_tds_between_acceptable_and_permissible_is_treatment_required(self):
        reading = make_reading(
            1, ph=7.2, tds=1200.0, turbidity=0.5, turbidity_unit="ntu",
            diagnostics=calibrated_diag(ph="calibrated", tds="calibrated", turbidity="calibrated"),
        )
        result = assessment(reading, "drinking")
        assert param(result, "tds")["status"] == "within_permissible"
        assert result["result"] == "treatment_required"

    def test_tds_above_permissible_is_outside_limits(self):
        reading = make_reading(
            1, ph=7.2, tds=2001.0, turbidity=0.5, turbidity_unit="ntu",
            diagnostics=calibrated_diag(ph="calibrated", tds="calibrated", turbidity="calibrated"),
        )
        result = assessment(reading, "drinking")
        assert param(result, "tds")["status"] == "outside_limits"
        assert result["result"] == "outside_limits"

    def test_drinking_never_concludes_safe_to_drink(self):
        """All measurable drinking criteria pass -> lab confirmation, not 'suitable'."""
        reading = make_reading(
            1, ph=7.2, tds=300.0, turbidity=0.5, turbidity_unit="ntu",
            diagnostics=calibrated_diag(ph="calibrated", tds="calibrated", turbidity="calibrated"),
        )
        result = assessment(reading, "drinking")
        assert result["result"] == "lab_confirmation_required"
        assert any(m["parameter"] == "ecoli" for m in result["missing_parameters"])
        assert "laboratory" in result["summary"].lower()
        assert any("never certifies drinking-water safety" in text
                   for text in result["limitations"])

    def test_irrigation_requires_ec_sar_boron(self):
        reading = make_reading(
            1, ph=7.2, tds=400.0, turbidity=1.0, turbidity_unit="ntu",
            diagnostics=calibrated_diag(ph="calibrated", tds="calibrated", turbidity="calibrated"),
        )
        result = assessment(reading, "irrigation")
        assert result["result"] == "insufficient_data"
        missing = {m["parameter"] for m in result["missing_parameters"]}
        assert {"ec", "sar", "boron"} <= missing
        assert "TDS is not electrical conductivity" in " ".join(result["limitations"])

    def test_irrigation_passes_ph_but_never_declares_suitability(self):
        reading = make_reading(
            1, ph=7.0, tds=300.0, turbidity=1.0, turbidity_unit="ntu",
            diagnostics=calibrated_diag(ph="calibrated", tds="calibrated", turbidity="calibrated"),
        )
        result = assessment(reading, "irrigation")
        assert param(result, "ph")["status"] == "within_acceptable"
        assert result["result"] == "insufficient_data"

    def test_stale_reading_is_never_a_current_conclusion(self):
        old = NOW - timedelta(hours=3)
        reading = make_reading(
            1, ph=7.0, tds=200.0, turbidity=0.5, turbidity_unit="ntu",
            timestamp=old,
            diagnostics=calibrated_diag(ph="calibrated", tds="calibrated", turbidity="calibrated"),
        )
        result = assessment(reading, "drinking")
        assert result["data_quality"]["freshness"] == "stale"
        assert result["result"] == "insufficient_data"
        assert "no current suitability conclusion" in result["summary"]

    def test_every_supported_use_is_assessed(self):
        reading = make_reading(1, temperature=27.0)
        results = assess_reading(reading, now=NOW)
        assert [r["use"] for r in results] == [u.code for u in USES]
        codes = {r["result"] for r in results}
        assert codes <= {
            "preliminary_suitable", "treatment_required", "outside_limits",
            "lab_confirmation_required", "insufficient_data",
        }


# ---------------------------------------------------------------------------
# API: authority endpoint, persistence, RBAC
# ---------------------------------------------------------------------------

def _seed_station_with_reading(db_session, reading):
    db_session.add(reading)
    db_session.commit()
    db_session.refresh(reading)
    return reading


@pytest.fixture
def station_with_calibrated_reading(db_session, seeded_water_data):
    station = seeded_water_data["station"]
    # Timestamp at *fixture* time, not module-import time: the API assesses
    # freshness against the real clock at request time, and a full-suite run
    # can reach this fixture minutes after import (NOW would read "delayed").
    reading = make_reading(
        station.id, ph=7.2, tds=300.0, turbidity=0.5, turbidity_unit="ntu",
        timestamp=datetime.now(timezone.utc),
        diagnostics=calibrated_diag(ph="calibrated", tds="calibrated", turbidity="calibrated"),
    )
    _seed_station_with_reading(db_session, reading)
    return station, reading


class TestIngestionIntegration:
    def test_ingesting_a_reading_stores_its_assessments(
        self, db_session, seeded_water_data
    ):
        station = seeded_water_data["station"]
        payload = json.dumps({
            "station_code": station.station_code,
            "device_id": "ESP32-HS-001",
            "timestamp": NOW.isoformat().replace("+00:00", "Z"),
            "pH": 7.2,
            "turbidity": 1.0,
            "tds": 300.0,
            "temperature": 26.0,
            "source": "esp32",
            "diagnostics": {
                "ph": {"calibration_status": "calibrated"},
                "tds": {"calibration_status": "calibrated"},
                "turbidity": {"unit": "ntu", "calibration_status": "calibrated"},
            },
        })

        assert process_telemetry_payload(
            payload, db_session_factory=lambda: db_session
        ) is True

        rows = db_session.query(WaterSuitabilityAssessment).all()
        assert len(rows) == len(USES)
        assert {row.use_code for row in rows} == {use.code for use in USES}
        drinking = next(row for row in rows if row.use_code == "drinking")
        assert drinking.result_code == "lab_confirmation_required"
        assert drinking.standard_version == RULESET_VERSION
        assert drinking.reading_id is not None
        assert drinking.summary


class TestAuthoritySuitabilityAPI:
    def test_requires_authentication(self, client, seeded_water_data):
        res = client.get(f"/api/authority/stations/{seeded_water_data['station'].station_code}/suitability")
        assert res.status_code == 401

    def test_rejects_product_users(self, client, seeded_water_data, product_token_headers):
        res = client.get(
            f"/api/authority/stations/{seeded_water_data['station'].station_code}/suitability",
            headers=product_token_headers,
        )
        assert res.status_code == 403

    def test_unknown_station_returns_404(self, client, authority_token_headers):
        res = client.get("/api/authority/stations/NOPE-999/suitability",
                         headers=authority_token_headers)
        assert res.status_code == 404

    def test_returns_all_assessments(self, client, authority_token_headers,
                                     station_with_calibrated_reading):
        station, _ = station_with_calibrated_reading
        res = client.get(f"/api/authority/stations/{station.station_code}/suitability",
                         headers=authority_token_headers)
        assert res.status_code == 200
        body = res.json()
        assert body["station_code"] == station.station_code
        assert body["ruleset_version"] == RULESET_VERSION
        assert len(body["assessments"]) == len(USES)
        drinking = next(a for a in body["assessments"] if a["use"] == "drinking")
        assert drinking["result"] == "lab_confirmation_required"
        assert drinking["standard_code"] == "BIS-IS-10500:2012"
        assert drinking["data_quality"]["freshness"] == "fresh"

    def test_persists_one_row_per_use_and_is_idempotent(
        self, client, db_session, authority_token_headers, station_with_calibrated_reading
    ):
        station, reading = station_with_calibrated_reading
        url = f"/api/authority/stations/{station.station_code}/suitability"
        client.get(url, headers=authority_token_headers)
        client.get(url, headers=authority_token_headers)

        rows = db_session.query(WaterSuitabilityAssessment).all()
        assert len(rows) == len(USES)
        assert {row.reading_id for row in rows} == {reading.id}
        assert {row.result_code for row in rows} == {"lab_confirmation_required",
                                                     "insufficient_data"}

    def test_new_reading_produces_new_assessment_set(
        self, client, db_session, authority_token_headers, station_with_calibrated_reading
    ):
        station, first = station_with_calibrated_reading
        url = f"/api/authority/stations/{station.station_code}/suitability"
        client.get(url, headers=authority_token_headers)

        # Strictly newer than the fixture reading (which is stamped at fixture
        # time, not at the module's NOW), so it becomes the latest reading.
        first_ts = first.timestamp
        if first_ts.tzinfo is None:  # SQLite hands back naive UTC
            first_ts = first_ts.replace(tzinfo=timezone.utc)
        second = make_reading(
            station.id, ph=9.5, tds=300.0, turbidity=0.5, turbidity_unit="ntu",
            timestamp=first_ts + timedelta(seconds=5),
            diagnostics=calibrated_diag(ph="calibrated", tds="calibrated", turbidity="calibrated"),
        )
        _seed_station_with_reading(db_session, second)
        client.get(url, headers=authority_token_headers)

        rows = db_session.query(WaterSuitabilityAssessment).all()
        assert len(rows) == len(USES) * 2
        assert {row.reading_timestamp is not None for row in rows} == {True}


# ---------------------------------------------------------------------------
# API: public endpoints (QR water-body page)
# ---------------------------------------------------------------------------

class TestPublicSuitabilityAPI:
    def test_public_assessment_needs_no_auth(
        self, client, station_with_calibrated_reading
    ):
        station, _ = station_with_calibrated_reading
        res = client.get(f"/api/public/stations/{station.station_code}/suitability")
        assert res.status_code == 200
        body = res.json()
        assert len(body["assessments"]) == len(USES)
        drinking = next(a for a in body["assessments"] if a["use"] == "drinking")
        assert drinking["result"] == "lab_confirmation_required"

    def test_public_payload_has_no_device_diagnostics(
        self, client, station_with_calibrated_reading
    ):
        station, _ = station_with_calibrated_reading
        res = client.get(f"/api/public/stations/{station.station_code}/suitability")
        text = res.text
        assert "diagnostics" not in text
        assert "raw_adc" not in text

    def test_public_unknown_station_returns_404(self, client):
        assert client.get("/api/public/stations/NOPE-999/suitability").status_code == 404
        assert client.get("/api/public/stations/NOPE-999/readings/latest").status_code == 404

    def test_public_latest_reading_is_public_safe(
        self, client, station_with_calibrated_reading
    ):
        station, reading = station_with_calibrated_reading
        res = client.get(f"/api/public/stations/{station.station_code}/readings/latest")
        assert res.status_code == 200
        body = res.json()
        assert body["station_code"] == station.station_code
        assert body["pH"] == pytest.approx(7.2)
        assert "diagnostics" not in body
        assert "device_id" not in body

    def test_public_history_is_ordered_and_bounded(
        self, client, db_session, station_with_calibrated_reading
    ):
        station, _ = station_with_calibrated_reading
        for offset in (30, 20, 10):
            _seed_station_with_reading(
                db_session,
                make_reading(station.id, ph=7.0, timestamp=NOW - timedelta(seconds=offset)),
            )
        res = client.get(f"/api/public/stations/{station.station_code}/readings?limit=2")
        assert res.status_code == 200
        rows = res.json()
        assert len(rows) == 2
        assert rows[0]["timestamp"] >= rows[1]["timestamp"]

    def test_public_no_reading_station_reports_missing_data(
        self, client, db_session, seeded_water_data
    ):
        station = seeded_water_data["station"]
        res = client.get(f"/api/public/stations/{station.station_code}/suitability")
        assert res.status_code == 200
        body = res.json()
        assert all(a["result"] == "insufficient_data" for a in body["assessments"])
        assert all(a["data_quality"]["freshness"] == "no_data" for a in body["assessments"])
