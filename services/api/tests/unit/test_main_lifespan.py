"""Unit tests for FastAPI app lifespan wiring."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.auth.client import StaticTokenValidator
from app.config import Settings
from app.main import create_app


def test_create_app_without_database_url_not_ready() -> None:
    settings = Settings(database_url=None)
    validator = StaticTokenValidator({}, available=True)
    app = create_app(settings=settings, validator=validator)
    with TestClient(app) as client:
        resp = client.get("/ready")
        assert resp.status_code == 503
        assert app.state.api.ready is False


def test_create_app_full_lifespan_mocked() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex",
        auth_grpc_addr="127.0.0.1:50051",
    )
    validator = StaticTokenValidator({}, available=True)

    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)
    mock_engine.connect = MagicMock(return_value=mock_conn)

    with (
        patch("app.main.create_engine", return_value=mock_engine),
        patch("app.main.create_session_factory", return_value=MagicMock()),
        patch("authclient.revoke.GRPCTokenRevoker") as revoker_cls,
        patch("authclient.tokens.GRPCTokenManager") as manager_cls,
    ):
        revoker = MagicMock()
        revoker.aclose = AsyncMock()
        revoker_cls.return_value = revoker
        manager = MagicMock()
        manager.aclose = AsyncMock()
        manager_cls.return_value = manager
        app = create_app(settings=settings, validator=validator)
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/ready").status_code == 200
            assert app.state.api.ready is True
            assert app.state.api.token_manager is manager
        manager.aclose.assert_awaited()
        revoker.aclose.assert_awaited()


def test_create_app_auth_unreachable_not_ready() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex",
    )
    validator = StaticTokenValidator({}, available=False)
    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()

    with (
        patch("app.main.create_engine", return_value=mock_engine),
        patch("app.main.create_session_factory", return_value=MagicMock()),
    ):
        app = create_app(settings=settings, validator=validator)
        with TestClient(app) as client:
            assert app.state.api.ready is False
            assert app.state.api.ready_error == "auth gRPC not reachable"
            assert client.get("/ready").status_code == 503


def test_create_app_postgres_unreachable_not_ready() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex",
    )
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
    ):
        app = create_app(settings=settings, validator=validator)
        with TestClient(app) as client:
            assert app.state.api.ready is False
            assert app.state.api.ready_error == "database not reachable"
            assert client.get("/ready").status_code == 503


def _recording_auth_client(captured: dict[str, object], role: str) -> type:
    class _Recording:
        def __init__(
            self, target: str, timeout_seconds: float, ca_file: str | None = None
        ) -> None:
            captured[role] = {
                "target": target,
                "timeout_seconds": timeout_seconds,
                "ca_file": ca_file,
            }

        async def aclose(self) -> None:
            return None

    return _Recording


async def test_api_lifespan_forwards_the_ca_file_to_every_auth_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deleting a ``ca_file=`` argument would silently downgrade one auth hop."""
    from app.main import ApiAppState, _api_service_lifespan

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "app.main.GRPCTokenValidator", _recording_auth_client(captured, "validator")
    )
    monkeypatch.setattr(
        "authclient.revoke.GRPCTokenRevoker", _recording_auth_client(captured, "revoker")
    )
    monkeypatch.setattr(
        "authclient.tokens.GRPCTokenManager", _recording_auth_client(captured, "token_manager")
    )
    monkeypatch.setattr(
        "authclient.provider_credentials.GRPCProviderCredentialManager",
        _recording_auth_client(captured, "provider_credentials"),
    )

    settings = Settings(
        database_url=None,
        auth_grpc_addr="auth.example.com:9091",
        auth_grpc_ca_file="/tmp/ca.pem",
    )
    state = ApiAppState(settings=settings)

    async with _api_service_lifespan(state, settings, None):
        assert state.validator is not None

    assert set(captured) == {
        "validator",
        "revoker",
        "token_manager",
        "provider_credentials",
    }
    for role, call in captured.items():
        assert call["ca_file"] == "/tmp/ca.pem", role
        assert call["target"] == "auth.example.com:9091", role


def test_wire_publishers_budget_redis_and_preset() -> None:
    from app.budget_publish import NoopBudgetPublisher, RedisBudgetPublisher
    from app.main import ApiAppState, _wire_publishers

    with_redis = ApiAppState()
    _wire_publishers(with_redis, Settings(redis_url="redis://localhost:6379/0"))
    assert isinstance(with_redis.budget_publisher, RedisBudgetPublisher)

    preset = NoopBudgetPublisher()
    already = ApiAppState(budget_publisher=preset)
    _wire_publishers(already, Settings(redis_url="redis://localhost:6379/0"))
    assert already.budget_publisher is preset

    no_redis = ApiAppState()
    _wire_publishers(no_redis, Settings(redis_url=None))
    assert isinstance(no_redis.budget_publisher, NoopBudgetPublisher)
