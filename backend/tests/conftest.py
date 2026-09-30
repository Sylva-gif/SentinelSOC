import os

os.environ["DATABASE_URL"] = "sqlite:///./test-sentinel.db"
os.environ["JWT_SECRET"] = "test-only-secret-not-for-deployment"

os.environ["ASYNC_MODE"] = "inline"
os.environ["SERVICE_ROLE"] = "all"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app, request_times
from app.models import DetectionRule, User
from app.security import hash_password


@pytest.fixture
def client():
    request_times.clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        db.add_all([
            User(username="admin", password_hash=hash_password("DemoAdmin!2026"), role="admin"),
            User(username="analyst", password_hash=hash_password("DemoAnalyst!2026"), role="analyst"),
            User(username="manager", password_hash=hash_password("DemoManager!2026"), role="soc_manager"),
            DetectionRule(key="auth-failure-burst", name="Rafale d’échecs d’authentification", event_type="auth_failure",
                          threshold=3, window_minutes=15, severity="high", enabled=True),
        ])
        db.commit()
    with TestClient(app) as test_client:
        yield test_client


def token(client: TestClient, username: str = "analyst", password: str = "DemoAnalyst!2026") -> str:
    response = client.post("/api/auth/token", data={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(client)}"}