"""Drain and readiness probes."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.auth.client import StaticTokenValidator
from app.drain import DrainState
from app.main import create_app
from tests.unit.operator.conftest import mock_engine, operator_settings


@pytest.mark.asyncio
async def test_drain_wait_cancels_registered_tasks() -> None:
    drain = DrainState()

    async def long_running() -> None:
        await asyncio.sleep(60)

    task = asyncio.create_task(long_running())
    await drain.register_sse(task)
    drain.begin_drain()
    await drain.wait_sse_drain(0.1)
    assert task.cancelled() or task.done()


@pytest.mark.asyncio
async def test_drain_register_while_draining_cancels() -> None:
    drain = DrainState()
    drain.begin_drain()

    async def noop() -> None:
        await asyncio.sleep(0)

    task = asyncio.create_task(noop())
    with pytest.raises(RuntimeError, match="draining"):
        await drain.register_sse(task)


def test_ready_fails_when_auth_down() -> None:
    settings = operator_settings()
    validator = StaticTokenValidator({}, available=False)
    with (
        patch("app.main.create_engine", return_value=mock_engine()),
        patch("app.main.create_session_factory", return_value=MagicMock()),
        patch("authclient.revoke.GRPCTokenRevoker", return_value=MagicMock(aclose=AsyncMock())),
        patch("authclient.tokens.GRPCTokenManager", return_value=MagicMock(aclose=AsyncMock())),
        patch(
            "authclient.provider_credentials.GRPCProviderCredentialManager",
            return_value=MagicMock(aclose=AsyncMock()),
        ),
    ):
        app = create_app(settings=settings, validator=validator)
        with TestClient(app) as client:
            resp = client.get("/ready")
            assert resp.status_code == 503
            assert "auth" in resp.json()["error"]["message"].lower()


def test_ready_fails_when_postgres_down() -> None:
    settings = operator_settings()
    validator = StaticTokenValidator({}, available=True)
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock(
        side_effect=OperationalError("SELECT 1", {}, Exception("refused"))
    )
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)
    mock_engine = MagicMock()
    mock_engine.connect = MagicMock(return_value=mock_conn)
    mock_engine.dispose = AsyncMock()
    with (
        patch("app.main.create_engine", return_value=mock_engine),
        patch("app.main.create_session_factory", return_value=MagicMock()),
        patch("authclient.revoke.GRPCTokenRevoker", return_value=MagicMock(aclose=AsyncMock())),
        patch("authclient.tokens.GRPCTokenManager", return_value=MagicMock(aclose=AsyncMock())),
        patch(
            "authclient.provider_credentials.GRPCProviderCredentialManager",
            return_value=MagicMock(aclose=AsyncMock()),
        ),
    ):
        app = create_app(settings=settings, validator=validator)
        with TestClient(app) as client:
            resp = client.get("/ready")
            assert resp.status_code == 503
            assert "database" in resp.json()["error"]["message"].lower()


def test_ready_returns_draining(app_client) -> None:
    app, client = app_client
    app.state.api.drain.begin_drain()
    resp = client.get("/ready")
    assert resp.status_code == 503
    assert "drain" in resp.json()["error"]["message"].lower()
