import os
import sys
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

# Add backend directory to sys.path
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

# The JWT signing secret must come from the environment (startup fails when it
# is missing). Provide a clearly test-only value before the app is imported;
# nothing here is ever used outside the test run.
os.environ.setdefault(
    "JWT_SECRET_KEY", "hydrasense-tests-only-signing-key-0123456789abcdef"
)
# Rate limits are exercised explicitly by tests/test_security_hardening.py so
# that ordinary auth tests are not throttled by shared counters.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from app.main import app
from app.core.database import Base, get_db
from app.core.security import get_password_hash, create_access_token
from app.models.user import User, UserRole
from app.models.device import ProductDevice
from app.models.water import WaterSource, MonitoringStation

# In-memory SQLite for fast, isolated test runs
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def authority_user(db_session) -> User:
    user = User(
        email="authority_test@hydrasense.local",
        password_hash=get_password_hash("TestPassword123!"),
        full_name="Authority Test User",
        role=UserRole.AUTHORITY,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def product_user(db_session) -> User:
    user = User(
        email="product_test@hydrasense.local",
        password_hash=get_password_hash("TestPassword123!"),
        full_name="Product Test User",
        role=UserRole.PRODUCT_USER,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def authority_token_headers(authority_user) -> dict:
    token = create_access_token(
        subject=authority_user.id,
        role=authority_user.role.value,
        email=authority_user.email
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def product_token_headers(product_user) -> dict:
    token = create_access_token(
        subject=product_user.id,
        role=product_user.role.value,
        email=product_user.email
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def seeded_water_data(db_session):
    source = WaterSource(
        source_code="TEST-SOURCE",
        name="Test River Basin",
        source_type="RIVER",
        description="A test river basin for unit testing.",
    )
    db_session.add(source)
    db_session.flush()

    station = MonitoringStation(
        station_code="TEST-STA-01",
        water_source_id=source.id,
        station_name="Station Beta",
        zone="Central Zone",
        location="Zone B Point 1",
        latitude=12.9716,
        longitude=77.5946,
        public_warning="NORMAL",
        public_message="Water is clear and potable.",
        is_active=True,
    )
    db_session.add(station)
    db_session.commit()
    db_session.refresh(station)
    return {"source": source, "station": station}
