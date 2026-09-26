from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_api_responses_are_no_store() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/v1/operator/session/me")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_sse_responses_are_not_buffered_or_cached() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/v1/operator/events/stream")
    assert "no-cache" in response.headers["cache-control"]
    assert response.headers["x-accel-buffering"] == "no"
