from __future__ import annotations

from types import SimpleNamespace

import pytest
from _enqueue_http_test_helpers import (
    _client,
    _ledger,
    _post_enqueue,
    _valid_body,
    reset_enqueue_state,
)

from app.idempotency_ledger import fingerprint_enqueue


@pytest.fixture(autouse=True)
def _reset_enqueue_state() -> None:
    reset_enqueue_state()

def test_enqueue_claim_failure_never_dispatches() -> None:
    calls: list[dict] = []
    _ledger.claim_error = RuntimeError("database down")
    try:
        response = _post_enqueue(
            _client(apply_async=lambda kwargs: calls.append(kwargs)), _valid_body()
        )
    finally:
        _ledger.claim_error = None
    assert response.status_code == 503
    assert calls == []


def test_enqueue_finalize_failure_returns_503_without_release() -> None:
    calls: list[dict] = []
    _ledger.finalize_error = RuntimeError("database write failed")
    try:
        response = _post_enqueue(
            _client(apply_async=lambda kwargs: calls.append(kwargs) or SimpleNamespace(id="task")),
            _valid_body(),
        )
    finally:
        _ledger.finalize_error = None
    assert response.status_code == 503
    assert len(calls) == 1
    assert _ledger.records


def test_enqueue_release_failure_is_translated_to_503() -> None:
    _ledger.release_error = RuntimeError("database release failed")
    try:
        response = _post_enqueue(
            _client(apply_async=lambda _: (_ for _ in ()).throw(RuntimeError("broker down"))),
            _valid_body(),
        )
    finally:
        _ledger.release_error = None
    assert response.status_code == 503
    assert response.json() == {"error": "unavailable"}


def test_enqueue_conflicts_when_full_payload_changes() -> None:
    calls: list[dict] = []
    client = _client(apply_async=lambda kwargs: calls.append(kwargs) or SimpleNamespace(id="one"))
    body = _valid_body()
    key = body["session_id"]
    first = client.post(
        "/internal/extraction/enqueue",
        headers={"Authorization": "Bearer sekrit", "Idempotency-Key": key},
        json=body,
    )
    changed = dict(body)
    changed["turns"] = [{"turn_index": 0, "role": "user", "content": "different"}]
    second = client.post(
        "/internal/extraction/enqueue",
        headers={"Authorization": "Bearer sekrit", "Idempotency-Key": key},
        json=changed,
    )
    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json() == {"error": "idempotency_conflict"}
    assert len(calls) == 1


def test_enqueue_fingerprint_covers_every_turn_field() -> None:
    body = _valid_body()
    changed = dict(body)
    changed["turns"] = [{"turn_index": 0, "role": "assistant", "content": "hello world xx"}]
    assert fingerprint_enqueue(body) != fingerprint_enqueue(changed)


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


def test_enqueue_concurrent_idempotent_replay() -> None:
    import threading
    import time

    calls: list[dict] = []
    lock = threading.Lock()

    def slow_capture(kwargs: dict) -> SimpleNamespace:
        with lock:
            calls.append(kwargs)
        time.sleep(0.15)
        return SimpleNamespace(id="task-shared")

    client = _client(apply_async=slow_capture)
    body = _valid_body()
    headers = {"Authorization": "Bearer sekrit", "Idempotency-Key": "concurrent-sess"}
    barrier = threading.Barrier(8)
    results: list[int] = []
    task_ids: list[str] = []
    out_lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        resp = client.post("/internal/extraction/enqueue", headers=headers, json=body)
        with out_lock:
            results.append(resp.status_code)
            task_ids.append(resp.json().get("task_id", ""))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=5)
        assert not th.is_alive()
    assert results.count(202) == 1
    assert results.count(409) == 7
    assert task_ids.count("task-shared") == 1
    assert len(calls) == 1


def test_enqueue_dispatch_fail_clears_idempo_reservation() -> None:
    calls = {"n": 0}

    def boom(_kwargs: dict) -> SimpleNamespace:
        calls["n"] += 1
        raise RuntimeError("broker down")

    client = _client(apply_async=boom)
    body = _valid_body()
    headers = {"Authorization": "Bearer sekrit", "Idempotency-Key": "fail-clear"}
    assert (
        client.post("/internal/extraction/enqueue", headers=headers, json=body).status_code == 503
    )

    def ok(kwargs: dict) -> SimpleNamespace:
        calls["n"] += 1
        return SimpleNamespace(id="recovered")

    client2 = _client(apply_async=ok)
    resp = client2.post("/internal/extraction/enqueue", headers=headers, json=body)
    assert resp.status_code == 202
    assert resp.json()["task_id"] == "recovered"
    assert calls["n"] == 2


@pytest.mark.parametrize("key_mode", ["explicit", "session_id"])
@pytest.mark.parametrize("delay", [0.0, 0.05], ids=["immediate", "delayed"])
def test_enqueue_idempotent_replay_returns_original_task(
    key_mode: str, delay: float
) -> None:
    calls: list[dict] = []

    def capture(kwargs: dict) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(id="task-once")

    client = _client(apply_async=capture)
    body = _valid_body()
    key = body["session_id"] if key_mode == "session_id" else "explicit-key"
    headers = {"Authorization": "Bearer sekrit", "Idempotency-Key": key}
    first = client.post("/internal/extraction/enqueue", headers=headers, json=body)
    if delay:
        import time

        time.sleep(delay)
    replay = client.post("/internal/extraction/enqueue", headers=headers, json=body)
    assert first.status_code == replay.status_code == 202
    assert first.json()["task_id"] == replay.json()["task_id"] == "task-once"
    assert len(calls) == 1
