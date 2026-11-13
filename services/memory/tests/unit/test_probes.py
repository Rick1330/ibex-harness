from __future__ import annotations

import asyncio
from typing import Self
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY, generate_latest

from app.auth.client import StaticTokenValidator
from app.config import Settings
from app.main import MemoryAppState, create_app


def _counter_value(name: str, labels: dict[str, str]) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    return float(value) if value is not None else 0.0


def test_health_and_ready() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex",
        embedding_api_token="unit-test-token",
    )
    with (
        patch("app.probes.postgres_ready", AsyncMock(return_value=True)),
        TestClient(
            create_app(
                settings=settings,
                validator=StaticTokenValidator({}, available=True),
            )
        ) as client,
    ):
        assert client.get("/health").json() == {"status": "ok"}
        ready = client.get("/ready")
        assert ready.status_code == 200
        assert ready.json()["service"] == "memory"


def test_metrics_exposes_prometheus() -> None:
    with TestClient(create_app()) as client:
        client.get("/health")
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        body = response.text
        assert "ibex_memory_http_requests_total" in body
        assert "ibex_memory_http_request_duration_seconds" in body
        assert 'status="200"' in body
        assert "ibex_process_up" in body


def test_http_metrics_count_status_and_latency() -> None:
    labels = {"method": "GET", "route": "/health", "status": "200"}
    duration_labels = {"method": "GET", "route": "/health"}
    before = _counter_value("ibex_memory_http_requests_total", labels)
    before_duration = _counter_value(
        "ibex_memory_http_request_duration_seconds_count", duration_labels
    )
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
    assert _counter_value("ibex_memory_http_requests_total", labels) >= before + 1.0
    assert (
        _counter_value("ibex_memory_http_request_duration_seconds_count", duration_labels)
        >= before_duration + 1.0
    )
    body = generate_latest().decode()
    assert 'route="/health"' in body
    assert 'status="200"' in body


def test_ready_returns_503_when_state_has_error() -> None:
    application = create_app(settings=Settings(database_url=None))
    state = MemoryAppState(ready=False, ready_error="db unavailable")
    application.state.memory = state
    with TestClient(application) as client:
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "service_not_ready"
        assert response.json()["error"]["dependency"] == "bootstrap"


# --- P1-06: /ready is live, not startup-only -------------------------------


class _FakeConnection:
    """Minimal async connection; ``error`` is raised from execute()."""

    def __init__(self, error: Exception | None = None) -> None:
        self._error = error

    async def execute(self, _statement: object) -> None:
        if self._error is not None:
            raise self._error

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False


class _FakeEngine:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error
        self.connect_calls = 0

    def connect(self) -> _FakeConnection:
        self.connect_calls += 1
        return _FakeConnection(self._error)


class _FakeRedis:
    def __init__(self, *, pong: object = True, error: Exception | None = None) -> None:
        self._pong = pong
        self._error = error

    async def ping(self) -> object:
        if self._error is not None:
            raise self._error
        return self._pong


class _SlowValidator:
    def __init__(self, delay: float = 5.0) -> None:
        self._delay = delay
        self.calls = 0

    async def ready(self) -> bool:
        self.calls += 1
        await asyncio.sleep(self._delay)
        return True


def _ready_client(state: MemoryAppState) -> TestClient:
    """App with injected state; the lifespan mutates only the original object."""
    application = create_app(settings=Settings(database_url=None))
    application.state.memory = state
    return TestClient(application)


def _live_state(
    *,
    validator: object | None = None,
    engine: object | None = None,
    redis: object | None = None,
) -> MemoryAppState:
    return MemoryAppState(
        ready=True,
        validator=validator if validator is not None else StaticTokenValidator({}, available=True),
        engine=engine if engine is not None else _FakeEngine(),
        redis=redis,
    )


def test_ready_live_checks_pass() -> None:
    engine = _FakeEngine()
    state = _live_state(engine=engine, redis=None)
    with _ready_client(state) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "service": "memory"}
    assert engine.connect_calls == 1


def test_ready_reports_failing_auth() -> None:
    state = _live_state(validator=StaticTokenValidator({}, available=False))
    with _ready_client(state) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()["error"]
    assert body["dependency"] == "auth"
    assert body["message"] == "auth gRPC not reachable"
    assert body["code"] == "service_not_ready"


def test_ready_reports_failing_postgres() -> None:
    state = _live_state(engine=_FakeEngine(OSError("connection refused")))
    with _ready_client(state) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()["error"]
    assert body["dependency"] == "postgres"
    assert body["message"] == "database not reachable"


def test_ready_reports_failing_redis() -> None:
    state = _live_state(redis=_FakeRedis(error=ConnectionError("redis down")))
    with _ready_client(state) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()["error"]
    assert body["dependency"] == "redis"
    assert body["message"] == "redis not reachable"


def test_ready_treats_a_false_redis_ping_as_failing() -> None:
    state = _live_state(redis=_FakeRedis(pong=False))
    with _ready_client(state) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["error"]["dependency"] == "redis"


def test_ready_ignores_an_unconfigured_redis() -> None:
    state = _live_state(redis=None)
    with _ready_client(state) as client:
        response = client.get("/ready")
    assert response.status_code == 200


def test_ready_bootstrap_failure_fails_fast_without_probing() -> None:
    """A process that never wired its dependencies must not probe them."""
    validator = StaticTokenValidator({}, available=True)
    state = MemoryAppState(
        ready=False,
        ready_error="IBEX_MEMORY_DATABASE_URL not set",
        validator=validator,
        engine=None,
    )
    probe = AsyncMock(return_value=True)
    with patch("app.probes._check_auth", probe), _ready_client(state) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()["error"]
    assert body["dependency"] == "bootstrap"
    assert body["message"] == "IBEX_MEMORY_DATABASE_URL not set"
    probe.assert_not_awaited()


def test_ready_recovers_after_a_transient_bootstrap_failure() -> None:
    """A fully wired process re-checks live deps and can report ready again."""
    state = MemoryAppState(
        ready=False,
        ready_error="database not reachable",
        validator=StaticTokenValidator({}, available=True),
        engine=_FakeEngine(OSError("connection refused")),
    )
    with _ready_client(state) as client:
        first = client.get("/ready")
        assert first.status_code == 503
        assert first.json()["error"]["dependency"] == "postgres"
        # The dependency recovers while the process stays up.
        state.engine = _FakeEngine()
        state.ready = True
        state.ready_error = None
        second = client.get("/ready")
    assert second.status_code == 200
    assert second.json() == {"status": "ready", "service": "memory"}


def test_ready_after_bootstrap_auth_failure_recovers_without_a_restart() -> None:
    """The startup refresh failed on auth; once auth answers, /ready is ready."""
    state = MemoryAppState(
        ready=False,
        ready_error="auth gRPC not reachable",
        validator=StaticTokenValidator({}, available=True),
        engine=_FakeEngine(),
    )
    with _ready_client(state) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "service": "memory"}


@pytest.mark.asyncio
async def test_check_auth_without_a_validator_is_not_ready() -> None:
    from app import probes

    assert await probes._check_auth(None) is False


@pytest.mark.asyncio
async def test_check_postgres_without_an_engine_is_not_ready() -> None:
    from app import probes

    assert await probes._check_postgres(None) is False


@pytest.mark.asyncio
async def test_check_postgres_swallows_an_unexpected_driver_error() -> None:
    """A probe fails closed on any error; it must never turn /ready into a 500."""

    class _ExplodingEngine:
        def connect(self) -> object:
            raise RuntimeError("driver exploded")

    from app import probes

    assert await probes._check_postgres(_ExplodingEngine()) is False


def test_ready_without_state_reports_not_ready() -> None:
    application = create_app(settings=Settings(database_url=None))
    application.state.memory = None
    with TestClient(application) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["error"]["dependency"] == "memory"


def test_ready_overall_budget_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import probes

    monkeypatch.setattr(probes, "_READY_OVERALL_TIMEOUT_S", 0.01)
    validator = _SlowValidator(delay=5.0)
    state = _live_state(validator=validator)
    with _ready_client(state) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()["error"]
    assert body["dependency"] == "timeout"
    assert body["message"] == "readiness checks timed out"


def test_ready_per_check_budget_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import probes

    monkeypatch.setattr(probes, "_READY_CHECK_TIMEOUT_S", 0.01)
    validator = _SlowValidator(delay=5.0)
    state = _live_state(validator=validator)
    with _ready_client(state) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["error"]["dependency"] == "auth"
