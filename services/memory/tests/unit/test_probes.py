from __future__ import annotations

from unittest.mock import AsyncMock, patch

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
        patch("app.main._postgres_ready", AsyncMock(return_value=True)),
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
        _counter_value(
            "ibex_memory_http_request_duration_seconds_count", duration_labels
        )
        >= before_duration + 1.0
    )
    body = generate_latest().decode()
    assert 'route="/health"' in body
    assert 'status="200"' in body


def test_ready_returns_503_when_state_has_error() -> None:
    application = create_app()
    state = MemoryAppState(ready=False, ready_error="db unavailable")
    application.state.memory = state
    with TestClient(application) as client:
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "service_not_ready"
