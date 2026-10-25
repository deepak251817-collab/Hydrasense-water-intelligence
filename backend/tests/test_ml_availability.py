"""ML availability honesty: index readings are excluded, with a clear reason.

The NTU-trained models must never receive a relative turbidity index as if it
were NTU. These tests pin the exact user-facing status for that case, plus the
other legitimate "no result" reasons, on the authority analysis endpoints.
"""

from datetime import datetime, timezone

import pytest

from app.models.water import SensorReading
from app.services.ml_availability import (
    MESSAGES,
    REASON_MISSING_VALUES,
    REASON_NOT_PROCESSED,
    REASON_TURBIDITY_INDEX,
    STATUS_OK,
    STATUS_UNAVAILABLE,
    availability_for,
)

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)

INDEX_MESSAGE = "ML prediction unavailable for Turbidity Index readings."


def _reading(**overrides) -> SensorReading:
    base = dict(
        station_id=1,
        device_id="ESP32-TEST-002",
        timestamp=NOW,
        ph=7.2,
        turbidity=25.0,
        turbidity_unit="relative_index_0_100",
        turbidity_index=25.0,
        tds=300.0,
        temperature=26.0,
        source="esp32",
        ml_processed_at=NOW,
        anomaly_label=0,
        anomaly_score=0.4,
        water_quality_label="Safe",
        safe_probability=0.9,
        unsafe_probability=0.1,
    )
    base.update(overrides)
    return SensorReading(**base)


class TestAvailabilityHelper:
    def test_index_reading_is_excluded_with_the_required_message(self):
        result = availability_for(_reading())
        assert result["status"] == STATUS_UNAVAILABLE
        assert result["reason"] == REASON_TURBIDITY_INDEX
        assert result["message"].startswith(INDEX_MESSAGE)
        assert "NTU" in result["message"]

    def test_ntu_reading_with_results_is_ok(self):
        reading = _reading(
            turbidity_unit="ntu", turbidity=1.0, turbidity_index=None
        )
        assert availability_for(reading)["status"] == STATUS_OK

    def test_missing_values_report_missing_not_index(self):
        reading = _reading(
            tds=None, turbidity_unit="ntu", turbidity_index=None
        )
        result = availability_for(reading)
        assert result["reason"] == REASON_MISSING_VALUES
        assert result["message"] == MESSAGES[REASON_MISSING_VALUES]

    def test_unprocessed_reading_reports_not_processed(self):
        reading = _reading(
            turbidity_unit="ntu", turbidity=1.0, turbidity_index=None,
            ml_processed_at=None, anomaly_label=None, anomaly_score=None,
            water_quality_label=None, safe_probability=None,
            unsafe_probability=None,
        )
        result = availability_for(reading)
        assert result["reason"] == REASON_NOT_PROCESSED
        assert result["status"] == STATUS_UNAVAILABLE

    def test_missing_reading_is_unavailable(self):
        assert availability_for(None)["status"] == STATUS_UNAVAILABLE


class TestAnalysisEndpoints:
    def _index_reading(self, db_session, seeded_water_data):
        reading = _reading(station_id=seeded_water_data["station"].id)
        db_session.add(reading)
        db_session.commit()
        db_session.refresh(reading)
        return reading

    def test_index_reading_analysis_states_index_unavailable(
        self, client, authority_token_headers, db_session, seeded_water_data
    ):
        reading = self._index_reading(db_session, seeded_water_data)
        res = client.get(
            f"/api/authority/readings/{reading.id}/analysis",
            headers=authority_token_headers,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["ml_status"] == "unavailable"
        assert body["ml_unavailable_reason"] == REASON_TURBIDITY_INDEX
        assert body["ml_unavailable_message"].startswith(INDEX_MESSAGE)
        # No ML result is fabricated alongside the explanation.
        assert body["ml"]["water_quality_label"] is None
        assert body["ml"]["anomaly_label"] is None
        assert body["turbidity_index"] == 25.0

    def test_latest_analysis_states_index_unavailable(
        self, client, authority_token_headers, db_session, seeded_water_data
    ):
        self._index_reading(db_session, seeded_water_data)
        res = client.get(
            "/api/authority/stations/"
            f"{seeded_water_data['station'].station_code}/readings/latest/analysis",
            headers=authority_token_headers,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["ml_status"] == "unavailable"
        assert body["ml_unavailable_reason"] == REASON_TURBIDITY_INDEX

    def test_requires_authority(self, client, db_session, seeded_water_data):
        reading = self._index_reading(db_session, seeded_water_data)
        assert (
            client.get(f"/api/authority/readings/{reading.id}/analysis").status_code
            == 401
        )
