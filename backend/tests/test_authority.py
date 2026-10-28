def test_authority_me_success(client, authority_token_headers, authority_user):
    response = client.get("/api/authority/me", headers=authority_token_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == authority_user.id
    assert data["email"] == authority_user.email
    assert data["role"] == "AUTHORITY"


def test_authority_stations_returns_all_stations(client, authority_token_headers, seeded_water_data):
    response = client.get("/api/authority/stations", headers=authority_token_headers)
    assert response.status_code == 200
    stations = response.json()
    assert len(stations) >= 1
    assert any(s["station_code"] == "TEST-STA-01" for s in stations)
    station = next(s for s in stations if s["station_code"] == "TEST-STA-01")
    assert station["station_name"] == "Station Beta"
    assert station["water_source"]["source_code"] == "TEST-SOURCE"


def test_authority_endpoints_unauthorized_without_token(client):
    res_me = client.get("/api/authority/me")
    assert res_me.status_code == 401

    res_sta = client.get("/api/authority/stations")
    assert res_sta.status_code == 401

    res_alerts = client.get("/api/authority/alerts")
    assert res_alerts.status_code == 401


def test_authority_alerts_forbidden_for_product_user(client, product_token_headers):
    response = client.get("/api/authority/alerts", headers=product_token_headers)
    assert response.status_code == 403


def test_authority_alerts_derived_from_station_readings(
    client, db_session, authority_token_headers, seeded_water_data
):
    """Alerts come from the latest stored reading — nothing fabricated."""
    from datetime import datetime, timezone

    from app.models.water import SensorReading

    station = seeded_water_data["station"]
    db_session.add(SensorReading(
        station_id=station.id,
        device_id="ESP32-API-ALERT-1",
        timestamp=datetime.now(timezone.utc),
        ph=9.8,                    # danger band -> critical pH alert
        tds=320.0,
        turbidity=18.0,
        turbidity_unit="relative_index_0_100",
        temperature=26.0,
        source="esp32",
    ))
    db_session.commit()

    response = client.get("/api/authority/alerts", headers=authority_token_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert body["critical_count"] >= 1
    ph_alert = next(a for a in body["items"] if a["parameter"] == "ph")
    assert ph_alert["station_code"] == station.station_code
    assert ph_alert["station_name"] == station.station_name
    assert ph_alert["simulated"] is False
    # Every alert carries its threshold provenance.
    assert ph_alert["threshold_classification"] is not None
    assert ph_alert["threshold_profile_version"] is not None
    # The response ships the active threshold profile alongside the items.
    assert body["threshold_profile"]


def test_authority_alerts_mark_simulated_readings(
    client, db_session, authority_token_headers, seeded_water_data
):
    from datetime import datetime, timezone

    from app.models.water import SensorReading

    station = seeded_water_data["station"]
    db_session.add(SensorReading(
        station_id=station.id,
        device_id="SIM-ALERT-1",
        timestamp=datetime.now(timezone.utc),
        ph=7.2,
        tds=2400.0,                # above permissible -> critical
        turbidity=12.0,
        turbidity_unit="relative_index_0_100",
        temperature=25.0,
        source="simulator",
    ))
    db_session.commit()

    response = client.get("/api/authority/alerts", headers=authority_token_headers)
    assert response.status_code == 200
    tds_alert = next(
        a for a in response.json()["items"]
        if a["parameter"] == "tds" and a["station_code"] == station.station_code
    )
    assert tds_alert["simulated"] is True
    assert tds_alert["source"] == "simulator"


def test_authority_alerts_empty_for_station_without_readings(
    client, authority_token_headers, seeded_water_data
):
    response = client.get("/api/authority/alerts", headers=authority_token_headers)
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0
