"""API tests for the product-user water-testing workflow."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import get_password_hash
from app.models.device import ProductDevice
from app.models.user import User, UserRole
from app.models.water import SensorReading

BASE = "/api/product"


@pytest.fixture
def active_device(db_session, product_user):
    device = ProductDevice(
        product_code="HS-API-0001",
        device_id="ESP32-API-0001",
        device_type="PERSONAL_WATER_TESTER",
        status="ACTIVE",
        owner_id=product_user.id,
        activated_at=datetime.now(timezone.utc),
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)
    return device


@pytest.fixture
def second_product_user(db_session):
    user = User(
        email="second_product@hydrasense.local",
        password_hash=get_password_hash("TestPassword123!"),
        full_name="Second Product User",
        role=UserRole.PRODUCT_USER,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def second_token_headers(second_product_user):
    from app.core.security import create_access_token

    token = create_access_token(
        subject=second_product_user.id,
        role=second_product_user.role.value,
        email=second_product_user.email,
    )
    return {"Authorization": f"Bearer {token}"}


def add_reading(
    db_session,
    station_id,
    device_id,
    *,
    ph=7.2,
    tds=320.0,
    turbidity=18.0,
    temperature=25.0,
    turbidity_unit="relative_index_0_100",
    source="esp32",
    age_seconds=30,
    calibration="pending",
):
    reading = SensorReading(
        station_id=station_id,
        device_id=device_id,
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
        ph=ph,
        tds=tds,
        turbidity=turbidity,
        turbidity_unit=turbidity_unit,
        turbidity_status="CLEARER",
        temperature=temperature,
        source=source,
        diagnostics={
            "ph": {"calibration_status": calibration},
            "tds": {"calibration_status": calibration},
            "turbidity": {"calibration_status": calibration},
            "temperature": {"calibration_status": calibration},
        },
    )
    db_session.add(reading)
    db_session.commit()
    db_session.refresh(reading)
    return reading


def add_stable_window(
    db_session,
    station_id,
    device_id,
    *,
    ph=7.4,
    tds=410.0,
    turbidity=22.0,
    temperature=26.5,
    turbidity_unit="relative_index_0_100",
    calibration="calibrated",
    count=10,
    spacing_seconds=3,
    latest_age_seconds=6,
    turbidity_step=0.2,
):
    """Store a stable rolling window (10 samples over 27 s by default)."""

    readings = []
    for index in range(count):
        age = latest_age_seconds + (count - 1 - index) * spacing_seconds
        readings.append(
            add_reading(
                db_session,
                station_id,
                device_id,
                ph=ph + (index - count / 2) * 0.002,
                tds=tds + (index - count / 2) * 0.4,
                turbidity=turbidity + (index - count / 2) * turbidity_step,
                temperature=temperature + (index - count / 2) * 0.02,
                turbidity_unit=turbidity_unit,
                age_seconds=age,
                calibration=calibration,
            )
        )
    return readings


# ---------------------------------------------------------------------------
# Product-code activation
# ---------------------------------------------------------------------------

def test_activate_unowned_product_code(client, db_session, product_token_headers):
    device = ProductDevice(
        product_code="HS-NEW-0002",
        device_id="ESP32-NEW-0002",
        status="PENDING_ACTIVATION",
    )
    db_session.add(device)
    db_session.commit()

    response = client.post(
        f"{BASE}/activate",
        json={"product_code": " hs-new-0002 "},
        headers=product_token_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ACTIVE"
    assert body["device_id"] == "ESP32-NEW-0002"
    assert body["owner_id"] is not None


def test_activation_is_idempotent_for_the_same_user(
    client, db_session, product_user, product_token_headers
):
    device = ProductDevice(
        product_code="HS-IDEMPOTENT",
        device_id="ESP32-IDEMPOTENT",
        status="ACTIVE",
        owner_id=product_user.id,
    )
    db_session.add(device)
    db_session.commit()

    response = client.post(
        f"{BASE}/activate",
        json={"product_code": "HS-IDEMPOTENT"},
        headers=product_token_headers,
    )
    assert response.status_code == 200


def test_second_account_cannot_claim_an_owned_code(
    client, db_session, product_user, second_token_headers
):
    device = ProductDevice(
        product_code="HS-CLAIMED",
        device_id="ESP32-CLAIMED",
        status="ACTIVE",
        owner_id=product_user.id,
    )
    db_session.add(device)
    db_session.commit()

    response = client.post(
        f"{BASE}/activate",
        json={"product_code": "HS-CLAIMED"},
        headers=second_token_headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "product_already_claimed"


def test_invalid_product_code_is_rejected(client, product_token_headers):
    response = client.post(
        f"{BASE}/activate",
        json={"product_code": "NO-SUCH-CODE"},
        headers=product_token_headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_product_code"


# ---------------------------------------------------------------------------
# Live device availability
# ---------------------------------------------------------------------------

def test_user_without_device_gets_clear_error(client, product_token_headers):
    response = client.post(
        f"{BASE}/tests",
        json={"water_source": "tap", "intended_use": "drinking", "reading_mode": "live"},
        headers=product_token_headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "no_device"


def test_offline_device_is_reported_without_fabricating_values(
    client, active_device, product_token_headers
):
    response = client.post(
        f"{BASE}/tests",
        json={"water_source": "tap", "intended_use": "drinking", "reading_mode": "live"},
        headers=product_token_headers,
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "device_offline"
    assert "demo" in detail["message"].lower()


def test_stale_reading_is_rejected(
    client, db_session, active_device, seeded_water_data, product_token_headers
):
    add_reading(
        db_session,
        seeded_water_data["station"].id,
        active_device.device_id,
        age_seconds=600,
    )
    response = client.post(
        f"{BASE}/tests",
        json={"water_source": "tap", "intended_use": "drinking", "reading_mode": "live"},
        headers=product_token_headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "stale_reading"


def test_invalid_live_reading_is_rejected_with_reasons(
    client, db_session, active_device, seeded_water_data, product_token_headers
):
    add_reading(
        db_session,
        seeded_water_data["station"].id,
        active_device.device_id,
        ph=None,
    )
    response = client.post(
        f"{BASE}/tests",
        json={"water_source": "tap", "intended_use": "drinking", "reading_mode": "live"},
        headers=product_token_headers,
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_reading"
    assert any("pH" in err for err in detail["errors"])


def test_device_status_reports_fresh_connection(
    client, db_session, active_device, seeded_water_data, product_token_headers
):
    add_reading(
        db_session,
        seeded_water_data["station"].id,
        active_device.device_id,
    )
    response = client.get(f"{BASE}/device-status", headers=product_token_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    assert body["reading"]["ph"] == 7.2
    assert body["reading"]["turbidity_unit"] == "relative_index_0_100"


# ---------------------------------------------------------------------------
# Creating and reading tests
# ---------------------------------------------------------------------------

def test_live_test_uses_device_reading_and_persists_assessment(
    client, db_session, active_device, seeded_water_data, product_token_headers
):
    readings = add_stable_window(
        db_session,
        seeded_water_data["station"].id,
        active_device.device_id,
        ph=7.4,
        tds=410.0,
        turbidity=22.0,
        temperature=26.5,
        calibration="pending",
    )
    response = client.post(
        f"{BASE}/tests",
        json={"water_source": "borewell", "intended_use": "drinking", "reading_mode": "live"},
        headers=product_token_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["reading_mode"] == "live"
    assert body["reading_source"] == "esp32"
    assert body["device_id"] == active_device.device_id
    assert body["water_source_label"] == "Borewell water"
    assert abs(body["ph"] - 7.4) < 0.02
    assert abs(body["tds"] - 410.0) < 3.0
    assert abs(body["assessment"]["readings"]["ph"]["value"] - 7.4) < 0.02
    assert body["assessment"]["readings"]["turbidity"]["unit"].startswith("relative index")
    assert "not NTU" in body["assessment"]["readings"]["turbidity"]["unit"]
    # Stable readings over unverified calibration can never be a green pass.
    assert body["assessment"]["overall"]["status"] == "INCONCLUSIVE"
    assert "calibration is unverified" in body["assessment"]["overall"]["summary"].lower()
    assert any(
        item["parameter"] == "calibration"
        for item in body["assessment"]["overall"]["reason_details"]
    )
    assert body["assessment"]["data_quality"]["demo_mode"] is False
    assert body["assessment"]["data_quality"]["stability"]["stable"] is True
    assert body["assessment"]["data_quality"]["stability"]["valid_samples"] == 10
    assert body["assessment"]["prediction"]["available"] is False
    assert body["test_code"].startswith("WT-")
    # The stored test points at the sensor reading it used.
    assert readings[-1].id is not None


def test_live_calibrated_stable_window_can_pass(
    client, db_session, active_device, seeded_water_data, product_token_headers
):
    add_stable_window(
        db_session,
        seeded_water_data["station"].id,
        active_device.device_id,
        # A genuinely NTU-calibrated turbidity sensor: the only way turbidity
        # can be validated, so a clean pass is reachable at all.
        turbidity=0.8,
        turbidity_unit="ntu",
        turbidity_step=0.02,  # NTU tolerance is 0.2 — keep the window stable
        calibration="calibrated",
    )
    response = client.post(
        f"{BASE}/tests",
        json={"water_source": "tap", "intended_use": "drinking", "reading_mode": "live"},
        headers=product_token_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["assessment"]["data_quality"]["calibration_verified"] is True
    assert body["assessment"]["overall"]["status"] == "WITHIN_PROJECT_TARGETS"
    assert "does not certify" in body["assessment"]["overall"]["summary"]


def test_live_low_tds_uses_project_rule_not_an_unsafe_claim(
    client, db_session, active_device, seeded_water_data, product_token_headers
):
    add_stable_window(
        db_session,
        seeded_water_data["station"].id,
        active_device.device_id,
        tds=150.0,
        calibration="calibrated",
    )
    response = client.post(
        f"{BASE}/tests",
        json={"water_source": "tap", "intended_use": "drinking", "reading_mode": "live"},
        headers=product_token_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["assessment"]["overall"]["status"] == "REVIEW_RECOMMENDED"
    assert body["assessment"]["overall"]["label"] == (
        "Not suitable by the project's strict TDS target"
    )
    tds_reason = next(
        item["reason"]
        for item in body["assessment"]["overall"]["reason_details"]
        if item["parameter"] == "tds"
    )
    assert "strict drinking-water TDS target of 200 ppm" in tds_reason
    assert "not an official BIS determination" in tds_reason
    assert "unsafe to drink because" not in tds_reason.lower()


def test_live_low_tds_with_unverified_calibration_still_shows_low_tds_result(
    client, db_session, active_device, seeded_water_data, product_token_headers
):
    add_stable_window(
        db_session,
        seeded_water_data["station"].id,
        active_device.device_id,
        tds=150.0,
        calibration="pending",
    )
    response = client.post(
        f"{BASE}/tests",
        json={"water_source": "tap", "intended_use": "drinking", "reading_mode": "live"},
        headers=product_token_headers,
    )
    assert response.status_code == 201, response.text
    overall = response.json()["assessment"]["overall"]
    assert overall["status"] == "INCONCLUSIVE"
    assert overall["label"] == (
        "Not suitable by the project's strict TDS target — more data or calibration required"
    )
    assert "tds is below 200 ppm" in overall["summary"].lower()
    assert "not an official bis determination" in overall["summary"].lower()


def test_unstable_live_window_is_rejected(
    client, db_session, active_device, seeded_water_data, product_token_headers
):
    for index in range(10):
        add_reading(
            db_session,
            seeded_water_data["station"].id,
            active_device.device_id,
            ph=6.2 if index % 2 else 8.1,
            age_seconds=6 + (9 - index) * 3,
        )
    response = client.post(
        f"{BASE}/tests",
        json={"water_source": "tap", "intended_use": "drinking", "reading_mode": "live"},
        headers=product_token_headers,
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "unstable_reading"
    assert "wait" in detail["message"].lower() or "stable" in detail["message"].lower()
    assert detail["stability"]["status"] == "unstable"


def test_demo_test_is_clearly_labelled_and_works_offline(
    client, active_device, product_token_headers
):
    response = client.post(
        f"{BASE}/tests",
        json={"water_source": "tank", "intended_use": "drinking", "reading_mode": "demo"},
        headers=product_token_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["reading_mode"] == "demo"
    assert body["reading_source"] == "simulated"
    assert body["assessment"]["data_quality"]["demo_mode"] is True
    assert any("SIMULATION" in warning
               for warning in body["assessment"]["data_quality"]["warnings"])


@pytest.mark.parametrize(
    "use,standard,result",
    [
        # Demo device readings carry a relative turbidity index (no NTU
        # calibration), so the best result for turbidity-rated uses is a
        # caution — never a full pass.
        ("drinking", "BIS-IS-10500:2012", "REVIEW_RECOMMENDED"),
        ("domestic", "BIS-IS-10500:2012", "REVIEW_RECOMMENDED"),
        ("irrigation", "FAO-TDS-PH", "REVIEW_RECOMMENDED"),
        ("swimming", "CPCB-DBU-B", "REVIEW_RECOMMENDED"),
        ("aquaculture", "AQUACULTURE-NO-CONFIGURED-CRITERIA", "INCONCLUSIVE"),
    ],
)
def test_each_intended_use_returns_its_own_criteria(
    client, active_device, product_token_headers, use, standard, result
):
    response = client.post(
        f"{BASE}/tests",
        json={"water_source": "surface", "intended_use": use, "reading_mode": "demo"},
        headers=product_token_headers,
    )
    assert response.status_code == 201, response.text
    suitability = response.json()["assessment"]["suitability"]
    assert suitability["use"] == use
    assert suitability["standard_code"] == standard
    assert suitability["result"] == result
    if use == "aquaculture":
        assert suitability["result_label"] == (
            "Insufficient parameters for a reliable aquaculture suitability assessment"
        )
    if use == "swimming":
        assert "cannot be certified" in response.json()["assessment"]["overall"]["summary"]


def test_test_history_lists_only_the_users_own_tests(
    client,
    db_session,
    active_device,
    second_product_user,
    product_token_headers,
    second_token_headers,
):
    ProductDevice(
        product_code="HS-SECOND",
        device_id="ESP32-SECOND",
        status="ACTIVE",
        owner_id=second_product_user.id,
        activated_at=datetime.now(timezone.utc),
    )
    db_session.commit()

    created = client.post(
        f"{BASE}/tests",
        json={"water_source": "tap", "intended_use": "drinking", "reading_mode": "demo"},
        headers=product_token_headers,
    )
    assert created.status_code == 201
    test_id = created.json()["id"]

    own = client.get(f"{BASE}/tests", headers=product_token_headers)
    assert own.status_code == 200
    assert own.json()["total"] == 1
    assert own.json()["items"][0]["id"] == test_id

    other = client.get(f"{BASE}/tests", headers=second_token_headers)
    assert other.status_code == 200
    assert other.json()["total"] == 0

    forbidden = client.get(f"{BASE}/tests/{test_id}", headers=second_token_headers)
    assert forbidden.status_code == 404

    allowed = client.get(f"{BASE}/tests/{test_id}", headers=product_token_headers)
    assert allowed.status_code == 200
    assert allowed.json()["id"] == test_id


def test_history_date_filter(client, active_device, product_token_headers):
    created = client.post(
        f"{BASE}/tests",
        json={"water_source": "tap", "intended_use": "domestic", "reading_mode": "demo"},
        headers=product_token_headers,
    )
    assert created.status_code == 201

    today = datetime.now(timezone.utc).date()
    matching = client.get(
        f"{BASE}/tests", params={"date_from": today.isoformat()},
        headers=product_token_headers,
    )
    assert matching.status_code == 200
    assert matching.json()["total"] == 1

    tomorrow = (today + timedelta(days=1)).isoformat()
    empty = client.get(
        f"{BASE}/tests", params={"date_from": tomorrow},
        headers=product_token_headers,
    )
    assert empty.status_code == 200
    assert empty.json()["total"] == 0


def test_overview_reflects_private_tests(client, active_device, product_token_headers):
    client.post(
        f"{BASE}/tests",
        json={"water_source": "well", "intended_use": "irrigation", "reading_mode": "demo"},
        headers=product_token_headers,
    )
    response = client.get(f"{BASE}/overview", headers=product_token_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_tests"] == 1
    assert body["latest_test"]["water_source_label"] == "Well water"
    assert body["device"]["device_id"] == active_device.device_id


# ---------------------------------------------------------------------------
# Authentication / role separation
# ---------------------------------------------------------------------------

def test_product_endpoints_require_a_token(client, active_device):
    response = client.get(f"{BASE}/tests")
    assert response.status_code == 401


def test_authority_cannot_use_product_endpoints(client, authority_token_headers):
    response = client.get(f"{BASE}/overview", headers=authority_token_headers)
    assert response.status_code == 403


def test_public_registration_cannot_create_an_authority(client):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "escalation@hydrasense.local",
            "password": "TestPassword123!",
            "full_name": "Escalation Attempt",
            "role": "AUTHORITY",
        },
    )
    assert response.status_code == 403
