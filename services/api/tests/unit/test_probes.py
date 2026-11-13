"""Probe endpoint unit tests."""

from __future__ import annotations

import asyncio
from typing import Self
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.main import create_app

_REDIS_URL = "redis://127.0.0.1:6379/0"


class _FakeConnection:
    async def execute(self, _statement: object) -> None:
        return None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False


class _FakeEngine:
    def connect(self) -> _FakeConnection:
        return _FakeConnection()

    async def dispose(self) -> None:
        return None


def _healthy_client(settings: Settings) -> TestClient:
    """App with a healthy auth validator; the DB engine is injected per test.

    The API never fast-fails on the startup flag, so an engine set after the
    lifespan has run is enough to exercise the live readiness path. Redis stays
    unset at startup so no fan-in task dials a real server.
    """
    return TestClient(
        create_app(
            settings=settings,
            validator=StaticTokenValidator({}, available=True),
        )
    )


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


def test_ready_ok_when_postgres_auth_and_redis_pass() -> None:
    with _healthy_client(Settings(database_url=None)) as client:
        client.app.state.api.engine = _FakeEngine()  # type: ignore[attr-defined]
        client.app.state.settings.redis_url = _REDIS_URL
        with patch(
            "app.probes._redis_status", AsyncMock(return_value="ok")
        ) as redis_status:
            response = client.get("/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready", "service": "api"}
        # The same helper as /v1/operator/platform/health, same URL: the two
        # surfaces cannot disagree about Redis.
        redis_status.assert_awaited_once_with(_REDIS_URL)


def test_ready_degraded_when_redis_is_unreachable() -> None:
    with _healthy_client(Settings(database_url=None)) as client:
        client.app.state.api.engine = _FakeEngine()  # type: ignore[attr-defined]
        client.app.state.settings.redis_url = _REDIS_URL
        with patch("app.probes._redis_status", AsyncMock(return_value="unavailable")):
            response = client.get("/ready")
        assert response.status_code == 503
        err = response.json()["error"]
        assert err["code"] == "SERVICE_DEGRADED"
        assert err["message"] == "redis not reachable"


def test_ready_ignores_an_unconfigured_redis() -> None:
    with _healthy_client(Settings(database_url=None)) as client:
        client.app.state.api.engine = _FakeEngine()  # type: ignore[attr-defined]
        with patch("app.probes._redis_status", AsyncMock()) as redis_status:
            response = client.get("/ready")
        assert response.status_code == 200
        redis_status.assert_not_awaited()


def test_ready_redis_check_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import probes

    monkeypatch.setattr(probes, "_READY_CHECK_TIMEOUT_S", 0.01)

    async def _slow(_url: str) -> str:
        await asyncio.sleep(5)
        return "ok"

    with _healthy_client(Settings(database_url=None)) as client:
        client.app.state.api.engine = _FakeEngine()  # type: ignore[attr-defined]
        client.app.state.settings.redis_url = _REDIS_URL
        with patch("app.probes._redis_status", _slow):
            response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "redis not reachable"


def test_ready_fails_closed_on_a_malformed_redis_url() -> None:
    # A configuration fault must read as not-ready, never as a 500 probe.
    with _healthy_client(Settings(database_url=None)) as client:
        client.app.state.api.engine = _FakeEngine()  # type: ignore[attr-defined]
        client.app.state.settings.redis_url = "not-a-redis-url"
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "redis not reachable"


def test_metrics_and_openapi() -> None:
    settings = Settings(database_url=None)
    validator = StaticTokenValidator({})
    with TestClient(create_app(settings=settings, validator=validator)) as client:
        assert client.get("/metrics").status_code == 200
        assert "paths" in client.get("/openapi.json").json()
