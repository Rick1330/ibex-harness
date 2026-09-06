"""Unit tests for internal extraction enqueue HTTP surface."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError
from starlette.testclient import TestClient

from app.config import Settings
from app.enqueue_http import (
    MAX_ENQUEUE_BODY_BYTES,
    create_enqueue_app,
    reset_enqueue_http_for_tests,
    start_enqueue_server,
)


@pytest.fixture(autouse=True)
def _reset_enqueue_flag() -> None:
    reset_enqueue_http_for_tests()


def _settings(*, token: str | None = "sekrit", host: str = "127.0.0.1", port: int = 18007) -> SimpleNamespace:
    tok = SecretStr(token) if token else None
    return SimpleNamespace(
        enqueue_api_token=tok,
        enqueue_host=host,
        enqueue_port=port,
    )


def _valid_body(**overrides: object) -> dict:
    body: dict = {
        "org_id": str(uuid4()),
        "agent_id": str(uuid4()),
        "session_id": str(uuid4()),
        "turns": [{"turn_index": 0, "role": "user", "content": "hello world xx"}],
    }
    body.update(overrides)
    return body


def _post_enqueue(client: TestClient, body: dict | bytes, *, token: str = "sekrit", raw: bool = False):
    headers = {"Authorization": f"Bearer {token}"}
    if raw:
        headers["Content-Type"] = "application/json"
        return client.post("/internal/extraction/enqueue", headers=headers, content=body)
    return client.post("/internal/extraction/enqueue", headers=headers, json=body)


def _client(token: str = "sekrit", apply_async=None) -> TestClient:
    return TestClient(create_enqueue_app(_settings(token=token), apply_async=apply_async))


def test_enqueue_rejects_missing_and_bad_bearer() -> None:
    calls: list[dict] = []
    client = _client(apply_async=lambda kwargs: calls.append(kwargs) or SimpleNamespace(id="t1"))
    assert client.post("/internal/extraction/enqueue", json=_valid_body()).status_code == 401
    assert _post_enqueue(client, _valid_body(), token="wrong").status_code == 401
    assert calls == []


def test_enqueue_rejects_malformed_payload() -> None:
    client = _client(apply_async=lambda kwargs: SimpleNamespace(id="t1"))
    resp = _post_enqueue(client, {"org_id": "not-a-uuid", "turns": []})
    assert resp.status_code == 400


def test_enqueue_rejects_non_object_json() -> None:
    client = _client(apply_async=lambda kwargs: SimpleNamespace(id="t1"))
    resp = _post_enqueue(client, b"[1,2,3]", raw=True)
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_json"


def test_enqueue_rejects_oversized_content_length() -> None:
    client = _client(apply_async=lambda kwargs: SimpleNamespace(id="t1"))
    headers = {
        "Authorization": "Bearer sekrit",
        "Content-Type": "application/json",
        "Content-Length": str(MAX_ENQUEUE_BODY_BYTES + 1),
    }
    resp = client.post("/internal/extraction/enqueue", headers=headers, content=b"{}")
    assert resp.status_code == 400
    assert resp.json()["error"] == "payload_too_large"


def test_enqueue_accepts_valid_payload() -> None:
    captured: list[dict] = []

    def capture(kwargs: dict) -> SimpleNamespace:
        captured.append(kwargs)
        return SimpleNamespace(id="task-abc")

    body = _valid_body()
    resp = _post_enqueue(_client(apply_async=capture), body)
    assert resp.status_code == 202
    assert resp.json()["task_id"] == "task-abc"
    assert captured[0]["org_id"] == body["org_id"]
    assert captured[0]["turns"][0]["role"] == "user"


def test_enqueue_broker_failure_returns_unavailable() -> None:
    def boom(_kwargs: dict) -> SimpleNamespace:
        raise RuntimeError("broker down")

    resp = _post_enqueue(_client(apply_async=boom), _valid_body())
    assert resp.status_code == 503
    assert resp.json()["error"] == "unavailable"


def test_enqueue_uses_celery_when_no_inject() -> None:
    from app import enqueue_http as mod

    called: list[dict] = []

    class _Task:
        @staticmethod
        def apply_async(*, kwargs: dict) -> SimpleNamespace:
            called.append(kwargs)
            return SimpleNamespace(id="celery-1")

    orig = mod.extract_session_memories
    mod.extract_session_memories = _Task  # type: ignore[assignment]
    try:
        app = create_enqueue_app(_settings(), apply_async=None)
        client = TestClient(app)
        resp = _post_enqueue(client, _valid_body())
        assert resp.status_code == 202
        assert resp.json()["task_id"] == "celery-1"
        assert called
    finally:
        mod.extract_session_memories = orig


def test_health() -> None:
    assert _client().get("/health").status_code == 200


def test_start_enqueue_server_disabled_without_token(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        start_enqueue_server(_settings(token=None))
        start_enqueue_server(_settings(token="   "))
    assert "worker_enqueue_http_disabled" in caplog.text


def test_start_enqueue_server_starts_once(monkeypatch: pytest.MonkeyPatch) -> None:
    runs = {"n": 0}

    def fake_run(_settings: object) -> None:
        runs["n"] += 1

    monkeypatch.setattr("app.enqueue_http._run_uvicorn", fake_run)
    settings = _settings()
    start_enqueue_server(settings)
    start_enqueue_server(settings)
    from app import enqueue_http as mod

    assert mod._enqueue_started is True
    # daemon thread invokes target asynchronously; allow a moment
    import time

    deadline = time.time() + 2
    while runs["n"] < 1 and time.time() < deadline:
        time.sleep(0.01)
    assert runs["n"] == 1


def test_config_rejects_duplicate_ports_when_token_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_WORKER_METRICS_PORT", "8006")
    monkeypatch.setenv("IBEX_WORKER_ENQUEUE_PORT", "8006")
    monkeypatch.setenv("IBEX_WORKER_ENQUEUE_API_TOKEN", "tok")
    with pytest.raises(ValidationError, match="enqueue_port and metrics_port"):
        Settings(_env_file=None)


def test_config_allows_duplicate_ports_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_WORKER_METRICS_PORT", "8006")
    monkeypatch.setenv("IBEX_WORKER_ENQUEUE_PORT", "8006")
    monkeypatch.delenv("IBEX_WORKER_ENQUEUE_API_TOKEN", raising=False)
    settings = Settings(_env_file=None)
    assert settings.enqueue_port == settings.metrics_port == 8006


def test_config_allows_distinct_ports_with_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_WORKER_METRICS_PORT", "8006")
    monkeypatch.setenv("IBEX_WORKER_ENQUEUE_PORT", "8007")
    monkeypatch.setenv("IBEX_WORKER_ENQUEUE_API_TOKEN", "tok")
    settings = Settings(_env_file=None)
    assert settings.enqueue_port == 8007
    assert settings.metrics_port == 8006
