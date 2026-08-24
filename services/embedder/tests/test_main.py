"""FastAPI health/ready endpoint tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_health_always_ok() -> None:
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready_ok_with_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IBEX_EMBEDDING_DIM", raising=False)
    monkeypatch.delenv("IBEX_EMBEDDING_MODEL", raising=False)
    monkeypatch.setenv("IBEX_EMBEDDING_PROFILE", "cpu")
    with TestClient(app) as client:
        resp = client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["profile"] == "cpu"
    assert body["dimensions"] == 384
    assert body["backend"] == "stub"


def test_ready_fails_on_geometry_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_EMBEDDING_PROFILE", "cpu")
    monkeypatch.setenv("IBEX_EMBEDDING_DIM", "1024")
    monkeypatch.setenv("IBEX_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    with TestClient(app) as client:
        resp = client.get("/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "service_not_ready"
    assert "dimensions" in body["error"]["message"].lower()
