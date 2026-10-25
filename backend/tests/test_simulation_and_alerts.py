"""Three-river simulation mode, danger-level alerts, general non-potable use.

Covers the requirements that:
- simulation produces plausible, seeded, clearly-labelled SIMULATED readings for
  exactly the four sensors (pH, TDS, temperature, turbidity index);
- a sensor fault stores NULL instead of a fabricated value;
- danger levels in any measured value raise an alert carrying the measured
  value, the configured reference and the data source;
- turbidity-index alerts are never compared with NTU limits;
- the shared screening service supports General Non-Potable Use and never
  applies the drinking-only strict TDS target to it.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.water import SensorReading
from app.services import simulation_service as sim
from app.services.alerting import reading_alerts
from app.services.alerting import test_alerts as build_saved_test_alerts
from app.services.water_screening import CRITERIA_VERSION, USE_LABELS, assess

NOW = datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clean_simulation_state():
    sim.reset_state()
    yield
    sim.reset_state()


def _reading(**overrides) -> SensorReading:
    base = dict(
        station_id=1,
        device_id="ESP32-TEST-001",
        timestamp=NOW,
        ph=7.2,
        tds=320.0,
        turbidity=18.0,
        turbidity_unit="relative_index_0_100",
        turbidity_index=18.0,
        temperature=25.0,
        source="esp32",
    )
    base.update(overrides)
    return SensorReading(**base)


# ---------------------------------------------------------------------------
# Simulation mode
# ---------------------------------------------------------------------------

class TestSimulationService:
    def test_generates_only_the_four_supported_sensors(
        self, db_session, seeded_water_data
    ):
        reading = sim.generate_sample(
            db_session, seeded_water_data["station"].station_code, scenario="normal", seed=7
        )
        assert reading.source == "simulator"
        assert reading.turbidity_unit == "relative_index_0_100"
        assert reading.turbidity_index is not None
        assert reading.turbidity_index == reading.turbidity
        # Exactly four measured values; none is silently replaced by zero.
        assert None not in (reading.ph, reading.tds, reading.temperature, reading.turbidity_index)
        # Clearly labelled as simulated in the stored diagnostics.
        label = reading.diagnostics["simulation"]["label"]
        assert "SIMULATED DATA" in label and "NOT LIVE" in label
        # Derived screening rows were created for the sample.
        from app.models.water import WaterSuitabilityAssessment
        rows = (
            db_session.query(WaterSuitabilityAssessment)
            .filter(WaterSuitabilityAssessment.reading_id == reading.id)
            .all()
        )
        assert {row.use_code for row in rows} == {
            use for use in ("drinking", "domestic", "bathing", "irrigation",
                            "industrial", "aquatic_life")
        }

    def test_seeded_generation_is_reproducible(self, db_session, seeded_water_data):
        code = seeded_water_data["station"].station_code
        first = sim.generate_sample(db_session, code, seed=42, advance_state=False)
        sim.reset_state()
        second = sim.generate_sample(db_session, code, seed=42, advance_state=False)
        assert (first.ph, first.tds, first.temperature, first.turbidity_index) == (
            second.ph, second.tds, second.temperature, second.turbidity_index
        )

    def test_unseeded_generation_varies(self, db_session, seeded_water_data):
        code = seeded_water_data["station"].station_code
        first = sim.generate_sample(db_session, code, advance_state=False)
        second = sim.generate_sample(db_session, code, advance_state=False)
        assert (first.ph, first.tds, first.temperature, first.turbidity_index) != (
            second.ph, second.tds, second.temperature, second.turbidity_index
        )

    def test_gradual_deterioration_moves_one_direction(self, db_session, seeded_water_data):
        code = seeded_water_data["station"].station_code
        sim.start(code, scenario="gradual_deterioration", seed=3)
        indexes = []
        for _ in range(6):
            reading = sim.generate_sample(db_session, code, scenario="gradual_deterioration", seed=None)
            indexes.append(reading.turbidity_index)
        assert indexes[-1] > indexes[0]
        assert all(0.0 <= value <= 100.0 for value in indexes)

    def test_sensor_fault_stores_null_never_a_number(self, db_session, seeded_water_data):
        code = seeded_water_data["station"].station_code
        readings = [
            sim.generate_sample(db_session, code, scenario="sensor_fault", advance_state=False)
            for _ in range(4)
        ]
        values = [
            (r.ph, r.tds, r.temperature, r.turbidity_index) for r in readings
        ]
        assert any(None in combo for combo in values), "a fault must store NULL, not a value"
        # The values that DO report stay inside plausible sensor ranges.
        for ph, tds, temperature, index in values:
            if ph is not None:
                assert 0.0 <= ph <= 14.0
            if tds is not None:
                assert 0.0 <= tds <= 5000.0
            if temperature is not None:
                assert -5.0 <= temperature <= 60.0
            if index is not None:
                assert 0.0 <= index <= 100.0

    def test_unknown_station_or_scenario_is_rejected(self, db_session, seeded_water_data):
        with pytest.raises(ValueError):
            sim.generate_sample(db_session, "NO-SUCH-STATION")
        with pytest.raises(ValueError):
            sim.generate_sample(
                db_session, seeded_water_data["station"].station_code, scenario="flood"
            )

    def test_demonstration_rivers_are_exactly_the_three_configured(self):
        assert set(sim.RIVER_BASELINES) == {"ARKAVATHI", "CAUVERY", "VRISHABHAVATHI"}

    def test_turbidity_bands_match_firmware_documentation(self):
        assert sim.turbidity_band(12.0) == "CLEARER"
        assert sim.turbidity_band(30.0) == "MODERATE"
        assert sim.turbidity_band(54.9) == "MODERATE"
        assert sim.turbidity_band(55.0) == "CLOUDIER"

    def test_state_payload_labels_samples_simulated(self, db_session, seeded_water_data):
        sim.generate_sample(
            db_session, seeded_water_data["station"].station_code, seed=1
        )
        payload = sim.state_payload()
        assert payload["simulated"] is True
        assert "NOT LIVE SENSOR DATA" in payload["label"]
        assert payload["recent_samples"][0]["simulated"] is True


class TestSimulationAPI:
    def test_requires_authority(self, client, seeded_water_data):
        assert client.get("/api/simulation/state").status_code == 401

    def test_rejects_product_users(self, client, product_token_headers):
        res = client.get("/api/simulation/state", headers=product_token_headers)
        assert res.status_code == 403

    def test_generate_endpoint_stores_simulated_samples(
        self, client, authority_token_headers, seeded_water_data
    ):
        res = client.post(
            "/api/simulation/generate",
            headers=authority_token_headers,
            json={
                "station_code": seeded_water_data["station"].station_code,
                "scenario": "normal",
                "seed": 5,
                "count": 2,
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["simulated"] is True
        assert body["samples_generated"] == 2
        assert len(body["recent_samples"]) == 2

    def test_unknown_station_returns_400(self, client, authority_token_headers):
        res = client.post(
            "/api/simulation/generate",
            headers=authority_token_headers,
            json={"station_code": "NOPE"},
        )
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# Danger-level alerts
# ---------------------------------------------------------------------------

class TestReadingAlerts:
    def test_normal_reading_has_no_danger_alerts(self):
        alerts = reading_alerts(_reading(), now=NOW)
        assert alerts == []

    def test_ph_danger_level_raises_critical_alert(self):
        alerts = reading_alerts(_reading(ph=5.1), now=NOW)
        ph = next(a for a in alerts if a["parameter"] == "ph")
        assert ph["severity"] == "critical"
        assert ph["value"] == 5.1
        assert "6.5" in ph["reference"]

    def test_ph_just_outside_range_raises_warning(self):
        alerts = reading_alerts(_reading(ph=8.7), now=NOW)
        ph = next(a for a in alerts if a["parameter"] == "ph")
        assert ph["severity"] == "warning"

    def test_tds_danger_and_watch_levels(self):
        critical = next(
            a for a in reading_alerts(_reading(tds=2400.0), now=NOW)
            if a["parameter"] == "tds"
        )
        assert critical["severity"] == "critical"
        warning = next(
            a for a in reading_alerts(_reading(tds=900.0), now=NOW)
            if a["parameter"] == "tds"
        )
        assert warning["severity"] == "warning"

    def test_turbidity_index_alert_never_claims_ntu(self):
        alerts = reading_alerts(_reading(turbidity_index=72.0, turbidity=72.0), now=NOW)
        turbidity = next(a for a in alerts if a["parameter"] == "turbidity_index")
        assert turbidity["unit"] == "0-100 index"
        combined = f"{turbidity['message']} {turbidity['reference']}"
        assert "not an NTU measurement" in turbidity["message"]
        # The configured NTU limits must never appear as an index comparison.
        assert "1 NTU acceptable" not in combined
        assert "0-100" in combined or "index" in combined.lower()

    def test_missing_sensor_value_raises_warning_not_zero(self):
        alerts = reading_alerts(_reading(tds=None), now=NOW)
        tds = next(a for a in alerts if a["parameter"] == "tds")
        assert tds["severity"] == "warning"
        assert tds["value"] is None

    def test_stale_reading_raises_freshness_alert(self):
        stale = _reading(timestamp=NOW - timedelta(minutes=30))
        alerts = reading_alerts(stale, now=NOW)
        assert any(a["parameter"] == "freshness" for a in alerts)

    def test_simulated_reading_is_labelled_in_alerts(self):
        sim_alerts = reading_alerts(
            _reading(source="simulator", ph=9.9), now=NOW
        )
        assert sim_alerts
        assert all(a["simulated"] is True for a in sim_alerts)
        assert all(a["source"] == "simulator" for a in sim_alerts)

    def test_no_reading_returns_no_alerts(self):
        assert reading_alerts(None) == []


class TestProductAlertsAPI:
    def test_requires_authentication(self, client):
        assert client.get("/api/product/alerts").status_code == 401

    def test_returns_empty_for_account_without_device(
        self, client, product_token_headers
    ):
        res = client.get("/api/product/alerts", headers=product_token_headers)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_rejects_authority_role(self, client, authority_token_headers):
        assert client.get(
            "/api/product/alerts", headers=authority_token_headers
        ).status_code == 403


# ---------------------------------------------------------------------------
# General non-potable use (shared screening service)
# ---------------------------------------------------------------------------

def _screen(**overrides):
    readings = {
        "ph": 7.2,
        "tds": 320.0,
        "turbidity": 18.0,
        "temperature": 25.0,
    }
    readings.update(overrides)
    kwargs = dict(
        intended_use="general",
        reading_mode="demo",
        reading_timestamp=NOW,
        turbidity_unit="relative_index_0_100",
    )
    return assess(readings, **kwargs)


class TestGeneralNonPotableUse:
    def test_use_is_labelled(self):
        assert USE_LABELS["general"] == "General Non-Potable Use"

    def test_within_ranges_but_never_certified(self):
        result = _screen()
        assert result["overall"]["status"] == "WITHIN_PROJECT_TARGETS"
        summary = result["overall"]["summary"]
        assert "within the configured general" in summary
        assert "not a safety certification" in summary

    def test_strict_drinking_tds_target_is_not_applied(self):
        # 150 mg/L is below the drinking-only <200 ppm demo target.
        result = _screen(tds=150.0)
        assert result["readings"]["tds"]["status"] == "informational"
        assert result["overall"]["status"] == "WITHIN_PROJECT_TARGETS"
        assert "strict" not in result["overall"]["summary"].lower()

    def test_ph_danger_is_unfavourable(self):
        result = _screen(ph=9.6)
        assert result["overall"]["status"] == "NOT_RECOMMENDED_BY_SCREENING"
        assert "Unfavourable measured indicators" in result["overall"]["summary"]

    def test_every_reason_is_reported(self):
        result = _screen(ph=9.6, tds=320.0)
        reasons = result["overall"]["reasons"]
        assert any("pH" in reason for reason in reasons)

    def test_criteria_version_recorded(self):
        assert _screen()["criteria_version"] == CRITERIA_VERSION

    def test_saved_test_alerts_are_derived_from_the_assessment(self):
        from app.models.water_test import ProductWaterTest

        result = _screen(ph=9.6)
        attention = result["attention"]
        assert attention, "a concern must appear in the attention list"
        test = ProductWaterTest(
            user_id=1,
            device_id="ESP32-PERSONAL-001",
            water_source="tap",
            intended_use="general",
            reading_mode="demo",
            reading_source="simulated",
            ph=9.6,
            tds=320.0,
            turbidity=18.0,
            turbidity_unit="relative_index_0_100",
            temperature=25.0,
            overall_status=result["overall"]["status"],
            criteria_version=result["criteria_version"],
            assessment=result,
        )
        alerts = build_saved_test_alerts(test)
        assert alerts, "a concerning saved test must raise at least one alert"
        assert all(a["test_id"] is None or a["test_id"] == 1 for a in alerts)
        assert {a["parameter"] for a in alerts} == {
            item["parameter"] for item in attention
        }
