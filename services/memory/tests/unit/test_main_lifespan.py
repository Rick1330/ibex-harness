"""Unit tests for FastAPI app lifespan wiring."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.client import StaticTokenValidator
from app.config import Settings
from app.main import create_app


@pytest.fixture
def closing_validator() -> tuple[type, list[bool]]:
    """A validator that records every channel close into a shared list."""
    closed: list[bool] = []

    class _ClosingValidator:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def aclose(self) -> None:
            closed.append(True)

    return _ClosingValidator, closed


def test_create_app_without_database_url_not_ready() -> None:
    settings = Settings(database_url="", embedding_api_token="tok")
    validator = StaticTokenValidator({}, available=True)
    app = create_app(settings=settings, validator=validator)
    with TestClient(app) as client:
        resp = client.get("/ready")
        assert resp.status_code == 503


def test_not_ready_lifespan_still_flushes_tracing() -> None:
    """The not-ready early return never reaches _shutdown_memory."""
    settings = Settings(database_url="", embedding_api_token="tok")
    validator = StaticTokenValidator({}, available=True)
    app = create_app(settings=settings, validator=validator)
    with (
        patch("app.main.configure_tracing") as configure,
        patch("app.main.shutdown_tracing") as shutdown,
        TestClient(app),
    ):
        pass
    configure.assert_called_once_with("")
    shutdown.assert_called_once_with()


async def test_memory_lifespan_forwards_the_ca_file_to_the_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deleting ``ca_file=`` from the memory lifespan would downgrade the dial."""
    from app.main import MemoryAppState, _memory_service_lifespan

    captured: dict[str, object] = {}

    class _RecordingValidator:
        def __init__(
            self, target: str, timeout_seconds: float, ca_file: str | None = None
        ) -> None:
            captured.update(
                target=target,
                timeout_seconds=timeout_seconds,
                ca_file=ca_file,
            )

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr("app.main.GRPCTokenValidator", _RecordingValidator)
    monkeypatch.setattr("app.main.configure_tracing", lambda *_a, **_k: None)
    monkeypatch.setattr("app.main.shutdown_tracing", lambda *_a, **_k: None)

    settings = Settings(
        database_url="",
        auth_grpc_addr="auth.example.com:9091",
        auth_grpc_ca_file="/tmp/ca.pem",
    )
    state = MemoryAppState(settings=settings)

    async with _memory_service_lifespan(state, settings, None):
        assert state.validator is not None

    assert captured["target"] == "auth.example.com:9091"
    assert captured["ca_file"] == "/tmp/ca.pem"


@pytest.mark.asyncio
async def test_not_ready_lifespan_releases_resources_when_consumer_raises(
    monkeypatch: pytest.MonkeyPatch,
    closing_validator: tuple[type, list[bool]],
) -> None:
    """A consumer exception must not skip the gRPC channel close or the flush.

    The not-ready path has no ``finally`` of its own, so an exception thrown
    into the generator at ``yield`` used to leak the aio channel and the
    OTel exporter (python:S9152).
    """
    from app.main import MemoryAppState

    validator_cls, closed = closing_validator

    monkeypatch.setattr("app.main.GRPCTokenValidator", validator_cls)
    monkeypatch.setattr("app.main.configure_tracing", lambda *_a, **_k: None)
    shutdown = MagicMock()
    monkeypatch.setattr("app.main.shutdown_tracing", shutdown)

    settings = Settings(database_url="")
    state = MemoryAppState(settings=settings)

    with pytest.raises(RuntimeError, match="consumer boom"):
        await _consume_raising(state, settings)

    assert closed, "auth channel was not closed after a consumer exception"
    shutdown.assert_called_once_with()


@pytest.mark.asyncio
async def test_not_ready_lifespan_closes_channel_when_the_flush_raises(
    monkeypatch: pytest.MonkeyPatch,
    closing_validator: tuple[type, list[bool]],
) -> None:
    """A raising flush must not skip the gRPC channel close.

    ``shutdown_tracing`` force-flushes and then shuts the provider down without
    a handler, so an exporter timeout raises. Sequencing the close after it
    plainly would leak exactly the channel this cleanup exists to release.
    """
    from app.main import MemoryAppState

    validator_cls, closed = closing_validator

    monkeypatch.setattr("app.main.GRPCTokenValidator", validator_cls)
    monkeypatch.setattr("app.main.configure_tracing", lambda *_a, **_k: None)
    shutdown = MagicMock(side_effect=RuntimeError("flush boom"))
    monkeypatch.setattr("app.main.shutdown_tracing", shutdown)

    settings = Settings(database_url="")
    state = MemoryAppState(settings=settings)

    with pytest.raises(RuntimeError, match="flush boom"):
        await _consume_raising(state, settings)

    assert closed, "auth channel was not closed after a failing tracing flush"
    shutdown.assert_called_once_with()


@pytest.mark.asyncio
async def test_not_ready_lifespan_surfaces_the_close_error_and_keeps_the_flush_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both failures stay visible: the close error propagates, flush is its cause."""
    from app.main import MemoryAppState

    closed: list[bool] = []

    class _FailingCloseValidator:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def aclose(self) -> None:
            closed.append(True)
            raise OSError("close boom")

    monkeypatch.setattr("app.main.GRPCTokenValidator", _FailingCloseValidator)
    monkeypatch.setattr("app.main.configure_tracing", lambda *_a, **_k: None)
    shutdown = MagicMock(side_effect=RuntimeError("flush boom"))
    monkeypatch.setattr("app.main.shutdown_tracing", shutdown)

    settings = Settings(database_url="")
    state = MemoryAppState(settings=settings)

    with pytest.raises(OSError, match="close boom") as excinfo:
        await _consume_raising(state, settings)

    assert closed
    assert shutdown.call_count == 1
    # The flush error is not discarded: it is chained behind the close error.
    context = excinfo.value.__context__
    assert isinstance(context, RuntimeError)
    assert str(context) == "flush boom"


async def _consume_raising(state: object, settings: object) -> None:
    """Enter the not-ready lifespan and blow up the consumer side."""
    from app.main import _memory_service_lifespan

    async with _memory_service_lifespan(state, settings, None):  # type: ignore[arg-type]
        raise RuntimeError("consumer boom")


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
        patch("app.main.shutdown_tracing") as shutdown,
    ):
        app = create_app(settings=settings, validator=validator)
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/ready").status_code == 200
            assert app.state.memory.ready is True
    shutdown.assert_called_once_with()


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


def test_build_rerank_is_none_when_the_flag_is_off() -> None:
    from app.main import _build_rerank

    assert _build_rerank(Settings(rerank_enabled=False)) is None


def test_build_rerank_requires_hybrid_and_says_so() -> None:
    from app.main import _build_rerank

    cfg = Settings(rerank_enabled=True, search_hybrid_enabled=False)

    with patch("app.main.logger.warning") as warning:
        assert _build_rerank(cfg) is None

    warning.assert_called_once()
    assert "hybrid" in warning.call_args.args[0]


def test_build_rerank_uses_the_budget_settings() -> None:
    from app.clients.rerank import RerankClient
    from app.main import _build_rerank

    cfg = Settings(
        rerank_enabled=True,
        search_hybrid_enabled=True,
        rerank_base_url="http://reranker.test:80",
        rerank_timeout_ms=200,
        rerank_connect_timeout_ms=25,
        rerank_max_retries=1,
    )

    client = _build_rerank(cfg)

    assert isinstance(client, RerankClient)
    assert client._max_retries == 1
    assert client._client.base_url.host == "reranker.test"
    assert client._client.timeout.read == pytest.approx(0.2)
    assert client._client.timeout.connect == pytest.approx(0.025)
    # Defaults to TEI's own --max-client-batch-size; a split at 50 would 413.
    assert client._batch_size == 32


def test_build_rerank_honours_a_configured_batch_size() -> None:
    from app.main import _build_rerank

    cfg = Settings(
        rerank_enabled=True,
        search_hybrid_enabled=True,
        rerank_base_url="http://reranker.test:80",
        rerank_client_batch_size=16,
    )

    client = _build_rerank(cfg)

    assert client is not None
    assert client._batch_size == 16


def test_build_rerank_warns_when_the_batch_size_exceeds_the_server_default() -> None:
    """Above 32 the split no longer protects a stock server: it answers 413."""
    from app.main import _build_rerank

    cfg = Settings(
        rerank_enabled=True,
        search_hybrid_enabled=True,
        rerank_base_url="http://reranker.test:80",
        rerank_client_batch_size=48,
    )

    with patch("app.main.logger.warning") as warning:
        client = _build_rerank(cfg)

    assert client is not None
    warning.assert_called_once()
    assert "max-client-batch-size" in warning.call_args.args[0]
    # The message names the request size a search can actually build.
    assert warning.call_args.args[1] == 48


def test_build_rerank_does_not_warn_when_the_window_cap_keeps_requests_small() -> None:
    """A request carries at most ``min(batch size, window cap)`` texts."""
    from app.main import _build_rerank

    cfg = Settings(
        rerank_enabled=True,
        search_hybrid_enabled=True,
        rerank_base_url="http://reranker.test:80",
        rerank_client_batch_size=48,
        rerank_max_candidates=10,
    )

    with patch("app.main.logger.warning") as warning:
        assert _build_rerank(cfg) is not None

    warning.assert_not_called()


def test_build_rerank_does_not_warn_at_the_server_default() -> None:
    from app.main import _build_rerank

    cfg = Settings(
        rerank_enabled=True,
        search_hybrid_enabled=True,
        rerank_base_url="http://reranker.test:80",
        rerank_client_batch_size=32,
    )

    with patch("app.main.logger.warning") as warning:
        assert _build_rerank(cfg) is not None

    warning.assert_not_called()
