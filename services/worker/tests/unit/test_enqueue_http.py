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


def test_enqueue_idempotent_replay_same_task_id() -> None:
    calls: list[dict] = []

    def capture(kwargs: dict) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(id="task-once")

    client = _client(apply_async=capture)
    body = _valid_body()
    headers = {"Authorization": "Bearer sekrit", "Idempotency-Key": "sess-1"}
    r1 = client.post("/internal/extraction/enqueue", headers=headers, json=body)
    r2 = client.post("/internal/extraction/enqueue", headers=headers, json=body)
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r1.json()["task_id"] == r2.json()["task_id"] == "task-once"
    assert len(calls) == 1


def test_enqueue_idempotent_defaults_to_session_id() -> None:
    calls: list[dict] = []

    def capture(kwargs: dict) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(id="task-sid")

    client = _client(apply_async=capture)
    body = _valid_body()
    r1 = _post_enqueue(client, body)
    r2 = _post_enqueue(client, body)
    assert r1.json()["task_id"] == r2.json()["task_id"] == "task-sid"
    assert len(calls) == 1


def test_enqueue_dispatch_busy_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import enqueue_http as mod

    class _BusySem:
        def acquire(self, blocking: bool = True) -> bool:
            assert blocking is False
            return False

        def release(self) -> None:
            raise AssertionError("release must not run when admit fails")

    monkeypatch.setattr(mod, "_dispatch_sem", _BusySem())
    resp = _post_enqueue(_client(apply_async=lambda kwargs: SimpleNamespace(id="x")), _valid_body())
    assert resp.status_code == 503
    assert resp.json()["error"] == "unavailable"


def test_enqueue_broker_failure_returns_unavailable() -> None:
    def boom(_kwargs: dict) -> SimpleNamespace:
        raise RuntimeError("broker down")

    resp = _post_enqueue(_client(apply_async=boom), _valid_body())
    assert resp.status_code == 503
    assert resp.json()["error"] == "unavailable"


def test_enqueue_rejects_invalid_content_length() -> None:
    client = _client(apply_async=lambda kwargs: SimpleNamespace(id="t1"))
    headers = {
        "Authorization": "Bearer sekrit",
        "Content-Type": "application/json",
        "Content-Length": "not-an-int",
    }
    resp = client.post("/internal/extraction/enqueue", headers=headers, content=b"{}")
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_content_length"


def test_enqueue_rejects_empty_and_bad_json_body() -> None:
    client = _client(apply_async=lambda kwargs: SimpleNamespace(id="t1"))
    empty = client.post(
        "/internal/extraction/enqueue",
        headers={"Authorization": "Bearer sekrit", "Content-Type": "application/json"},
        content=b"",
    )
    assert empty.status_code == 400
    bad = _post_enqueue(client, b"{not-json", raw=True)
    assert bad.status_code == 400
    assert bad.json()["error"] == "invalid_json"


def test_enqueue_rejects_missing_org_id() -> None:
    body = _valid_body()
    del body["org_id"]
    resp = _post_enqueue(_client(apply_async=lambda kwargs: SimpleNamespace(id="t1")), body)
    assert resp.status_code == 400


def test_idempo_expired_entry_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import enqueue_http as mod

    calls: list[dict] = []

    def capture(kwargs: dict) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(id=f"task-{len(calls)}")

    monkeypatch.setattr(mod, "_IDEMPOTENCY_TTL_SEC", 0.01)
    client = _client(apply_async=capture)
    body = _valid_body()
    headers = {"Authorization": "Bearer sekrit", "Idempotency-Key": "expire-me"}
    assert client.post("/internal/extraction/enqueue", headers=headers, json=body).status_code == 202
    import time

    time.sleep(0.05)
    assert client.post("/internal/extraction/enqueue", headers=headers, json=body).status_code == 202
    assert len(calls) == 2


def test_run_uvicorn_builds_server(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import enqueue_http as mod

    ran = {"n": 0}

    class _FakeServer:
        def __init__(self, _config: object) -> None:
            ran["n"] += 1

        def run(self) -> None:
            return None

    monkeypatch.setattr(mod, "uvicorn", SimpleNamespace(Config=lambda *a, **k: object(), Server=_FakeServer), raising=False)
    # Patch inside function via module after import uvicorn — call with stubbed import.
    import types

    fake_uv = types.SimpleNamespace(
        Config=lambda *a, **k: object(),
        Server=_FakeServer,
    )
    monkeypatch.setitem(__import__("sys").modules, "uvicorn", fake_uv)
    mod._run_uvicorn(_settings(port=18099))
    assert ran["n"] == 1


def test_bearer_length_mismatch_and_empty_expected() -> None:
    from app.enqueue_http import _bearer_matches

    assert _bearer_matches("a", "") is False
    assert _bearer_matches("ab", "a") is False
    assert _bearer_matches("same", "same") is True


@pytest.mark.asyncio
async def test_read_json_limited_stream_cap_and_no_content_length(monkeypatch: pytest.MonkeyPatch) -> None:
    from starlette.requests import Request

    from app import enqueue_http as mod

    monkeypatch.setattr(mod, "MAX_ENQUEUE_BODY_BYTES", 8)

    async def receive():
        return {"type": "http.request", "body": b"{\"a\":1,\"pad\":true}", "more_body": False}

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
             "path": "/", "raw_path": b"/", "query_string": b"", "headers": [], "client": ("127.0.0.1", 1),
             "server": ("127.0.0.1", 80)}
    req = Request(scope, receive)
    mod._check_content_length(req)
    with pytest.raises(ValueError, match="payload_too_large"):
        await mod._read_json_limited(req)


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
