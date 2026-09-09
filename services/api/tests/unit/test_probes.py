"""Probe endpoint unit tests."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.main import create_app


def test_health_ok() -> None:
    settings = Settings(database_url=None)
    validator = StaticTokenValidator({})
    with TestClient(create_app(settings=settings, validator=validator)) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_ready_degraded_without_database() -> None:
    settings = Settings(database_url=None)
    org = uuid4()
    validator = StaticTokenValidator({"t": ValidateResult(org_id=org, permissions=0)})
    with TestClient(create_app(settings=settings, validator=validator)) as client:
        response = client.get("/ready")
        assert response.status_code == 503
        err = response.json()["error"]
        assert err["code"] == "SERVICE_DEGRADED"
        assert "DATABASE" in err["message"].upper() or "database" in err["message"].lower()
        assert err["request_id"]
