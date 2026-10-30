"""Incident + laboratory workflow tests.

These cover the workflow rules the UI depends on: RBAC, incident creation
validation, forward-only transitions, verbatim lab results with fixed
provenance, demo/manual distinction, and a real PDF report.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.water import SensorReading
from app.schemas.incident import LabResultEntry


def _reading(db, station, **overrides) -> SensorReading:
    reading = SensorReading(
        station_id=station.id,
        device_id="ESP32-HS-001",
        timestamp=overrides.pop("timestamp", datetime.now(timezone.utc)),
        ph=overrides.pop("ph", 6.2),
        tds=overrides.pop("tds", 420.0),
        temperature=overrides.pop("temperature", 24.5),
        turbidity=overrides.pop("turbidity", 63.0),
        turbidity_unit=overrides.pop("turbidity_unit", "relative_index_0_100"),
        turbidity_index=overrides.pop("turbidity_index", 63.0),
        turbidity_status=overrides.pop("turbidity_status", "CLOUDIER"),
        source=overrides.pop("source", "esp32"),
        **overrides,
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading


def _incident_payload(station, **overrides):
    payload = {
        "station_code": station.station_code,
        "title": "Sudden pH drop with rising turbidity",
        "summary": "A rapid drop in pH and rising turbidity were observed.",
        "priority": "high",
        "alert_reason": "pH 6.2 below the configured screening range.",
        "explanation": "pH fell sharply between consecutive readings.",
    }
    payload.update(overrides)
    return payload


def _create_incident(client, headers, station, **overrides):
    response = client.post(
        "/api/authority/incidents",
        headers=headers,
        json=_incident_payload(station, **overrides),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_incident_endpoints_require_authority(client, seeded_water_data, product_token_headers):
    station = seeded_water_data["station"]
    assert client.get("/api/authority/incidents").status_code == 401
    assert (
        client.get("/api/authority/incidents", headers=product_token_headers).status_code
        == 403
    )
    assert (
        client.post(
            "/api/authority/incidents",
            headers=product_token_headers,
            json=_incident_payload(station),
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/authority/lab-contacts", headers=product_token_headers
        ).status_code
        == 403
    )


def test_create_incident_records_reference_and_audit_event(
    client, seeded_water_data, authority_token_headers, db_session
):
    station = seeded_water_data["station"]
    reading = _reading(db_session, station)

    body = _create_incident(
        client, authority_token_headers, station, reading_id=reading.id
    )

    assert body["reference"] == f"INC-{body['id']:06d}"
    assert body["status"] == "raised"
    assert body["origin"] == "manual"
    assert body["is_demo"] is False
    assert body["explanation_source"] == "authority_manual"
    assert body["allowed_transitions"] == ["lab_notified", "resolved"]
    assert [event["to_status"] for event in body["events"]] == ["raised"]
    assert body["events"][0]["from_status"] is None
    assert len(body["readings"]) == 1
    assert body["readings"][0]["id"] == reading.id
    assert body["readings"][0]["simulated"] is False
    assert body["threshold_profile_version"]

    listed = client.get("/api/authority/incidents", headers=authority_token_headers)
    assert listed.status_code == 200
    items = listed.json()
    assert [item["reference"] for item in items] == [body["reference"]]
    assert items[0]["is_demo"] is False

    filtered = client.get(
        "/api/authority/incidents?status=raised&station_code=" + station.station_code,
        headers=authority_token_headers,
    )
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1


def test_create_incident_rejects_bad_station_and_foreign_reading(
    client, seeded_water_data, authority_token_headers, db_session
):
    station = seeded_water_data["station"]

    unknown = client.post(
        "/api/authority/incidents",
        headers=authority_token_headers,
        json=_incident_payload(station, station_code="NOPE-999"),
    )
    assert unknown.status_code == 404

    # A reading from a different station must not be attachable.
    from app.models.water import MonitoringStation, WaterSource

    other_source = WaterSource(
        source_code="OTHER-SRC", name="Other", source_type="LAKE"
    )
    db_session.add(other_source)
    db_session.flush()
    other_station = MonitoringStation(
        station_code="OTHER-001",
        water_source_id=other_source.id,
        station_name="Other Station",
        zone="Zone",
        location="Elsewhere",
        latitude=1.0,
        longitude=2.0,
        public_warning="NORMAL",
        public_message="",
        is_active=True,
    )
    db_session.add(other_station)
    db_session.commit()
    foreign_reading = _reading(db_session, other_station)

    mismatch = client.post(
        "/api/authority/incidents",
        headers=authority_token_headers,
        json=_incident_payload(station, reading_id=foreign_reading.id),
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["detail"]["code"] == "reading_station_mismatch"


def test_create_incident_ignores_client_supplied_origin(
    client, seeded_water_data, authority_token_headers
):
    """A caller cannot claim demo provenance to dodge the honest label rule."""

    station = seeded_water_data["station"]
    response = client.post(
        "/api/authority/incidents",
        headers=authority_token_headers,
        json={**_incident_payload(station), "origin": "demo"},
    )
    assert response.status_code == 201
    assert response.json()["origin"] == "manual"
    assert response.json()["is_demo"] is False


def test_full_workflow_to_resolution(
    client, seeded_water_data, authority_token_headers, monkeypatch
):
    import app.core.config as config

    monkeypatch.setattr(config.settings, "SMTP_HOST", "", raising=False)

    station = seeded_water_data["station"]
    contact = client.post(
        "/api/authority/lab-contacts",
        headers=authority_token_headers,
        json={
            "name": "Dr Rao",
            "organization": "State Water Laboratory",
            "email": "lab@example.org",
            "phone": "+91-0000000000",
            "accreditation": "NABL-1234",
        },
    )
    assert contact.status_code == 201, contact.text
    contact_id = contact.json()["id"]

    incident = _create_incident(client, authority_token_headers, station)

    notified = client.post(
        f"/api/authority/incidents/{incident['id']}/notify-lab",
        headers=authority_token_headers,
        json={"lab_contact_id": contact_id, "note": "Requested confirmatory analysis."},
    )
    assert notified.status_code == 200, notified.text
    body = notified.json()
    assert body["status"] == "lab_notified"
    # No SMTP configured: the workflow advances but delivery is reported honestly.
    assert body["lab_notification_status"] == "smtp_unconfigured"
    assert body["lab_notified_at"] is None
    assert body["lab_contact"]["organization"] == "State Water Laboratory"
    assert body["allowed_transitions"] == ["sample_collected", "resolved"]

    collected = client.post(
        f"/api/authority/incidents/{incident['id']}/sample-collected",
        headers=authority_token_headers,
        json={"sample_id": "S-2026-001", "note": "Collected at the station outlet."},
    )
    assert collected.status_code == 200, collected.text
    assert collected.json()["status"] == "sample_collected"
    assert collected.json()["sample_id"] == "S-2026-001"

    wrong_sample = client.post(
        f"/api/authority/incidents/{incident['id']}/lab-result",
        headers=authority_token_headers,
        json={
            "sample_id": "S-2026-999",
            "results": [{"parameter": "pH", "value": 6.4, "unit": "pH"}],
        },
    )
    assert wrong_sample.status_code == 422
    assert wrong_sample.json()["detail"]["code"] == "sample_mismatch"

    result = client.post(
        f"/api/authority/incidents/{incident['id']}/lab-result",
        headers=authority_token_headers,
        json={
            "sample_id": "S-2026-001",
            "summary": "Confirmatory laboratory analysis.",
            "document_reference": "LAB-REPORT-77.pdf",
            "results": [
                {"parameter": "pH", "value": 6.4, "unit": "pH", "method": "ISE"},
                {
                    "parameter": "Total coliforms",
                    "value": 12.0,
                    "unit": "CFU/100 mL",
                    "method": "Membrane filtration",
                },
            ],
        },
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["status"] == "result_received"
    assert body["result_received_at"]
    assert len(body["lab_results"]) == 1
    stored = body["lab_results"][0]
    assert stored["source"] == "laboratory"
    assert stored["derived_from_sensors"] is False
    assert stored["sample_id"] == "S-2026-001"
    assert [entry["source"] for entry in stored["results"]] == [
        "laboratory", "laboratory"
    ]

    resolved = client.post(
        f"/api/authority/incidents/{incident['id']}/resolve",
        headers=authority_token_headers,
        json={"resolution_summary": "Confirmed contamination; source remediation completed."},
    )
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert body["status"] == "resolved"
    assert body["resolved_at"]
    assert body["allowed_transitions"] == []
    assert [event["to_status"] for event in body["events"]] == [
        "raised",
        "lab_notified",
        "sample_collected",
        "result_received",
        "resolved",
    ]


def test_invalid_transitions_are_rejected(
    client, seeded_water_data, authority_token_headers
):
    station = seeded_water_data["station"]
    incident = _create_incident(client, authority_token_headers, station)

    # Cannot record a lab result before a sample exists.
    early_result = client.post(
        f"/api/authority/incidents/{incident['id']}/lab-result",
        headers=authority_token_headers,
        json={
            "sample_id": "S-1",
            "results": [{"parameter": "pH", "value": 7.0, "unit": "pH"}],
        },
    )
    assert early_result.status_code == 409
    assert early_result.json()["detail"]["code"] == "invalid_transition"

    # Resolve directly, then nothing may advance.
    resolved = client.post(
        f"/api/authority/incidents/{incident['id']}/resolve",
        headers=authority_token_headers,
        json={"resolution_summary": "False alarm: sensor fouling."},
    )
    assert resolved.status_code == 200
    assert "before a laboratory result" in resolved.json()["events"][-1]["note"]

    contact = client.post(
        "/api/authority/lab-contacts",
        headers=authority_token_headers,
        json={
            "name": "Lab",
            "organization": "Lab Org",
            "email": "lab2@example.org",
        },
    )
    notify_after = client.post(
        f"/api/authority/incidents/{incident['id']}/notify-lab",
        headers=authority_token_headers,
        json={"lab_contact_id": contact.json()["id"]},
    )
    assert notify_after.status_code == 409

    again = client.post(
        f"/api/authority/incidents/{incident['id']}/resolve",
        headers=authority_token_headers,
        json={"resolution_summary": "Again."},
    )
    assert again.status_code == 409


def test_lab_result_entry_rejects_non_finite_values():
    with pytest.raises(ValidationError):
        LabResultEntry(parameter="ph", value=float("nan"), unit="pH")
    with pytest.raises(ValidationError):
        LabResultEntry(parameter="ph", value=float("inf"), unit="pH")


def test_incident_report_pdf_is_generated(
    client, seeded_water_data, authority_token_headers, db_session
):
    station = seeded_water_data["station"]
    reading = _reading(db_session, station)
    incident = _create_incident(
        client, authority_token_headers, station, reading_id=reading.id
    )

    response = client.get(
        f"/api/authority/incidents/{incident['id']}/report.pdf",
        headers=authority_token_headers,
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert (
        f"{incident['reference']}-report.pdf" in response.headers["content-disposition"]
    )

    pdf = response.content
    assert pdf.startswith(b"%PDF-")
    assert pdf.rstrip().endswith(b"%%EOF")
    # The content stream is uncompressed, so the honesty wording is inspectable.
    assert b"NOT NTU" in pdf
    assert b"preliminary screening" in pdf
    assert b"Laboratory results" in pdf
    # The stored reading is quoted, not invented.
    assert b"pH 6.2 pH" in pdf


def test_report_requires_authority(
    client, seeded_water_data, authority_token_headers, product_token_headers
):
    station = seeded_water_data["station"]
    incident = _create_incident(client, authority_token_headers, station)
    assert (
        client.get(
            f"/api/authority/incidents/{incident['id']}/report.pdf",
            headers=product_token_headers,
        ).status_code
        == 403
    )
    assert (
        client.get(f"/api/authority/incidents/{incident['id']}/report.pdf").status_code
        == 401
    )


def test_lab_contacts_are_validated_and_filtered(
    client, authority_token_headers
):
    invalid = client.post(
        "/api/authority/lab-contacts",
        headers=authority_token_headers,
        json={"name": "X", "organization": "Y", "email": "not-an-email"},
    )
    assert invalid.status_code == 422

    created = client.post(
        "/api/authority/lab-contacts",
        headers=authority_token_headers,
        json={"name": "Lab", "organization": "Org", "email": "ok@example.org"},
    )
    assert created.status_code == 201
    listed = client.get(
        "/api/authority/lab-contacts", headers=authority_token_headers
    )
    assert listed.status_code == 200
    assert [row["email"] for row in listed.json()] == ["ok@example.org"]


def test_listing_unknown_station_returns_404(client, authority_token_headers):
    response = client.get(
        "/api/authority/incidents?station_code=UNKNOWN-1",
        headers=authority_token_headers,
    )
    assert response.status_code == 404
