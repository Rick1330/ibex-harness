from __future__ import annotations

from types import SimpleNamespace

import pytest
from _enqueue_http_test_helpers import (
    _ledger,
    _post_enqueue,
    _settings,
    _valid_body,
    reset_enqueue_state,
)
from pydantic import ValidationError
from starlette.testclient import TestClient

from app.config import Settings
from app.enqueue_http import create_enqueue_app, start_enqueue_server


@pytest.fixture(autouse=True)
def _reset_enqueue_state() -> None:
    reset_enqueue_state()

def test_run_uvicorn_builds_server(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import enqueue_http as mod

    ran = {"n": 0}

    class _FakeServer:
        def __init__(self, _config: object) -> None:
            ran["n"] += 1

        def run(self) -> None:
            return None

    monkeypatch.setattr(
        mod,
        "uvicorn",
        SimpleNamespace(Config=lambda *a, **k: object(), Server=_FakeServer),
        raising=False,
    )
    # Patch inside function via module after import uvicorn — call with stubbed import.
    import types

    fake_uv = types.SimpleNamespace(
        Config=lambda *a, **k: object(),
        Server=_FakeServer,
    )
    monkeypatch.setitem(__import__("sys").modules, "uvicorn", fake_uv)
    mod._run_uvicorn(_settings(port=18099))
    assert ran["n"] == 1


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
        app = create_enqueue_app(_settings(), apply_async=None, ledger=_ledger)
        client = TestClient(app)
        resp = _post_enqueue(client, _valid_body())
        assert resp.status_code == 202
        assert resp.json()["task_id"] == "celery-1"
        assert called
    finally:
        mod.extract_session_memories = orig


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
