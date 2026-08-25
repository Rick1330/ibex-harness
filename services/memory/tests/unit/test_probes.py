from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import MemoryAppState, create_app


def test_health_and_ready() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/health").json() == {"status": "ok"}
        ready = client.get("/ready")
        assert ready.status_code == 200
        assert ready.json()["service"] == "memory"


def test_metrics_exposes_prometheus() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]


def test_ready_returns_503_when_state_has_error() -> None:
    application = create_app()
    state = MemoryAppState(ready=False, ready_error="db unavailable")
    application.state.memory = state
    with TestClient(application) as client:
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "service_not_ready"
