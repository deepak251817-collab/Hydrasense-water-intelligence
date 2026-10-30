def test_public_station_viewing_no_auth_required(client, seeded_water_data):
    response = client.get("/api/public/stations/TEST-STA-01")
    assert response.status_code == 200
    data = response.json()
    assert data["station_code"] == "TEST-STA-01"
    assert data["station_name"] == "Station Beta"
    assert data["zone"] == "Central Zone"
    assert data["location"] == "Zone B Point 1"
    assert data["latitude"] == 12.9716
    assert data["longitude"] == 77.5946
    assert data["public_warning"] == "NORMAL"
    assert data["public_message"] == "Water is clear and potable."
    assert data["water_source"]["source_code"] == "TEST-SOURCE"
    assert data["water_source"]["name"] == "Test River Basin"


def test_public_station_not_found_returns_404(client):
    response = client.get("/api/public/stations/NONEXISTENT-CODE")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_public_station_listing_is_read_only_and_public_safe(client, seeded_water_data):
    response = client.get("/api/public/stations")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    station = rows[0]
    assert station["station_code"] == "TEST-STA-01"
    assert station["water_source"]["source_code"] == "TEST-SOURCE"
    # Public-safe: no diagnostics, credentials or private identifiers.
    assert "diagnostics" not in station
    assert "device_id" not in station
    assert "owner_id" not in station


def test_public_station_listing_excludes_inactive(client, seeded_water_data, db_session):
    from app.models.water import MonitoringStation

    station = db_session.query(MonitoringStation).filter_by(
        station_code="TEST-STA-01"
    ).one()
    station.is_active = False
    db_session.commit()
    assert client.get("/api/public/stations").json() == []
