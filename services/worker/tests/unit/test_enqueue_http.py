"""Unit tests for internal extraction enqueue HTTP surface."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import SecretStr
from starlette.testclient import TestClient

from app.enqueue_http import create_enqueue_app, reset_enqueue_http_for_tests


@pytest.fixture(autouse=True)
def _reset_enqueue_flag() -> None:
    reset_enqueue_http_for_tests()


def _settings(token: str = "sekrit") -> SimpleNamespace:
    return SimpleNamespace(enqueue_api_token=SecretStr(token) if token else None)


def test_enqueue_rejects_missing_bearer() -> None:
    calls: list[dict] = []
    app = create_enqueue_app(_settings(), apply_async=lambda kwargs: calls.append(kwargs) or SimpleNamespace(id="t1"))
    client = TestClient(app)
    resp = client.post(
        "/internal/extraction/enqueue",
        json={
            "org_id": str(uuid4()),
            "agent_id": str(uuid4()),
            "session_id": str(uuid4()),
            "turns": [{"turn_index": 0, "role": "user", "content": "hello world xx"}],
        },
    )
    assert resp.status_code == 401
    assert calls == []


def test_enqueue_rejects_bad_token() -> None:
    app = create_enqueue_app(_settings(), apply_async=lambda kwargs: SimpleNamespace(id="t1"))
    client = TestClient(app)
    resp = client.post(
        "/internal/extraction/enqueue",
        headers={"Authorization": "Bearer wrong"},
        json={
            "org_id": str(uuid4()),
            "agent_id": str(uuid4()),
            "session_id": str(uuid4()),
            "turns": [{"turn_index": 0, "role": "user", "content": "hello world xx"}],
        },
    )
    assert resp.status_code == 401


def test_enqueue_rejects_malformed_payload() -> None:
    app = create_enqueue_app(_settings(), apply_async=lambda kwargs: SimpleNamespace(id="t1"))
    client = TestClient(app)
    resp = client.post(
        "/internal/extraction/enqueue",
        headers={"Authorization": "Bearer sekrit"},
        json={"org_id": "not-a-uuid", "turns": []},
    )
    assert resp.status_code == 400


def test_enqueue_accepts_valid_payload() -> None:
    captured: list[dict] = []

    def capture(kwargs: dict) -> SimpleNamespace:
        captured.append(kwargs)
        return SimpleNamespace(id="task-abc")

    org, agent, sess = uuid4(), uuid4(), uuid4()
    app = create_enqueue_app(_settings(), apply_async=capture)
    client = TestClient(app)
    resp = client.post(
        "/internal/extraction/enqueue",
        headers={"Authorization": "Bearer sekrit"},
        json={
            "org_id": str(org),
            "agent_id": str(agent),
            "session_id": str(sess),
            "turns": [{"turn_index": 0, "role": "user", "content": "hello world xx"}],
        },
    )
    assert resp.status_code == 202
    assert resp.json()["task_id"] == "task-abc"
    assert len(captured) == 1
    assert captured[0]["org_id"] == str(org)
    assert captured[0]["session_id"] == str(sess)
    assert captured[0]["turns"][0]["role"] == "user"


def test_health() -> None:
    app = create_enqueue_app(_settings())
    client = TestClient(app)
    assert client.get("/health").status_code == 200
