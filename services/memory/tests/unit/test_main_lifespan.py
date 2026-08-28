"""Unit tests for FastAPI app lifespan wiring."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.client import StaticTokenValidator
from app.config import Settings
from app.main import create_app


def test_create_app_without_database_url_not_ready() -> None:
    settings = Settings(database_url="", embedding_api_token="tok")
    validator = StaticTokenValidator({}, available=True)
    app = create_app(settings=settings, validator=validator)
    with TestClient(app) as client:
        resp = client.get("/ready")
        assert resp.status_code == 503


@pytest.mark.asyncio
async def test_build_embed_no_token_raises() -> None:
    from app.main import _build_embed

    holder: dict = {}
    cfg = Settings(embedding_api_token=None)
    embed = _build_embed(cfg, holder)
    with pytest.raises(RuntimeError, match="not configured"):
        await embed("text")


def test_create_app_full_lifespan_mocked() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex",
        redis_url="redis://127.0.0.1:6379/0",
        embedding_api_token="embed-tok",
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
    mock_redis = MagicMock()
    mock_redis.aclose = AsyncMock()
    mock_client = MagicMock()
    mock_client.aclose = AsyncMock()

    with (
        patch("app.main.create_engine", return_value=mock_engine),
        patch("app.main.create_session_factory", return_value=MagicMock()),
        patch("app.main.PgVectorStore", return_value=MagicMock()),
        patch("app.main.PiiService", return_value=MagicMock()),
        patch("app.main.Redis.from_url", return_value=mock_redis),
        patch("app.main.EmbeddingClient", return_value=mock_client),
        patch("app.main.build_write_orchestrator", return_value=MagicMock()),
    ):
        app = create_app(settings=settings, validator=validator)
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200


def test_create_app_postgres_unreachable_not_ready() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex",
        embedding_api_token="embed-tok",
    )
    validator = StaticTokenValidator({}, available=True)

    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock(side_effect=OSError("connection refused"))
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)
    mock_engine = MagicMock()
    mock_engine.connect = MagicMock(return_value=mock_conn)
    mock_engine.dispose = AsyncMock()

    with (
        patch("app.main.create_engine", return_value=mock_engine),
        patch("app.main.create_session_factory", return_value=MagicMock()),
        patch("app.main.PgVectorStore", return_value=MagicMock()),
        patch("app.main.PiiService", return_value=MagicMock()),
        patch("app.main.build_write_orchestrator", return_value=MagicMock()),
    ):
        app = create_app(settings=settings, validator=validator)
        with TestClient(app) as client:
            assert app.state.memory.ready is False
            assert app.state.memory.ready_error == "database not reachable"
            assert client.get("/ready").status_code == 503
