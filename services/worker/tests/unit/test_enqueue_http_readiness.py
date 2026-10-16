from __future__ import annotations

from types import SimpleNamespace

import pytest
from _enqueue_http_test_helpers import (
    _client,
    _ledger,
    _patch_redis,
    _settings,
    reset_enqueue_state,
)
from pydantic import SecretStr
from starlette.testclient import TestClient

from app.enqueue_http import create_enqueue_app


@pytest.fixture(autouse=True)
def _reset_enqueue_state() -> None:
    reset_enqueue_state()

def test_health() -> None:
    assert _client().get("/health").status_code == 200


def test_ready_requires_enqueue_token_and_redis_url() -> None:
    assert _client().get("/ready").status_code == 503
    assert (
        TestClient(create_enqueue_app(_settings(token=None, redis_url="redis://redis")))
        .get("/ready")
        .status_code
        == 503
    )
    assert TestClient(create_enqueue_app(_settings(redis_url=""))).get("/ready").status_code == 503


def test_broker_url_falls_back_to_redis_url_when_resolved_missing() -> None:
    from app.enqueue_http import _broker_url

    settings = SimpleNamespace(redis_url="redis://fallback:6379/1")
    assert _broker_url(settings) == "redis://fallback:6379/1"
    assert (
        _broker_url(SimpleNamespace(resolved_broker_url="  ", redis_url="redis://x")) == "redis://x"
    )
    assert _broker_url(SimpleNamespace(resolved_broker_url=None, redis_url=None)) is None


def test_ready_uses_redis_url_fallback_when_resolved_broker_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_redis(monkeypatch)
    settings = SimpleNamespace(
        enqueue_api_token=SecretStr("sekrit"),
        enqueue_host="127.0.0.1",
        enqueue_port=18007,
        redis_url="redis://fallback",
    )
    response = TestClient(create_enqueue_app(settings, ledger=_ledger)).get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_ready_returns_ready_after_redis_ping(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = _patch_redis(monkeypatch)
    response = TestClient(
        create_enqueue_app(_settings(redis_url="redis://redis"), ledger=_ledger)
    ).get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "service": "worker"}
    assert redis.closed is True


@pytest.mark.parametrize("error", [OSError("connection refused"), TimeoutError("slow")])
def test_ready_returns_not_ready_when_redis_fails(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    _patch_redis(monkeypatch, error)
    response = TestClient(
        create_enqueue_app(_settings(redis_url="redis://redis"), ledger=_ledger)
    ).get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_ready_is_not_ready_without_database_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_redis(monkeypatch)
    response = TestClient(create_enqueue_app(_settings(redis_url="redis://redis"))).get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_ready_is_not_ready_when_database_ping_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_redis(monkeypatch)
    _ledger.ping_error = OSError("connection refused")
    response = TestClient(
        create_enqueue_app(_settings(redis_url="redis://redis"), ledger=_ledger)
    ).get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
