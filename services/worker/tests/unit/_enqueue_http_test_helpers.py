"""Shared test doubles and request builders for the worker enqueue HTTP tests."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from pydantic import SecretStr
from starlette.testclient import TestClient

from app.enqueue_http import create_enqueue_app, reset_enqueue_http_for_tests
from app.idempotency_ledger import ClaimOutcome, ClaimToken


class _Ledger:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str, str], tuple[str, ClaimToken, int, bytes | None]] = {}
        self.claim_error: Exception | None = None
        self.finalize_error: Exception | None = None
        self.release_error: Exception | None = None
        self.ping_error: Exception | None = None

    async def ping(self) -> None:
        if self.ping_error is not None:
            raise self.ping_error

    async def claim(self, *, org_id, agent_id, key, request_hash) -> ClaimOutcome:
        if self.claim_error is not None:
            raise self.claim_error
        record_key = (str(org_id), str(agent_id), key)
        existing = self.records.get(record_key)
        if existing is not None:
            old_hash, claim, status, response = existing
            if old_hash != request_hash:
                return ClaimOutcome(kind="conflict", claim=claim)
            if response is not None:
                return ClaimOutcome(kind="replay", claim=claim, status=status, response=response)
            return ClaimOutcome(kind="in_progress", claim=claim, retry_after=1)
        claim = ClaimToken(uuid4(), org_id, agent_id, key, request_hash, 1)
        self.records[record_key] = (request_hash, claim, 0, None)
        return ClaimOutcome(kind="owned", claim=claim)

    async def finalize(self, claim, *, status, response) -> None:
        if self.finalize_error is not None:
            raise self.finalize_error
        record_key = (str(claim.org_id), str(claim.agent_id), claim.key)
        request_hash, _, _, _ = self.records[record_key]
        self.records[record_key] = (request_hash, claim, status, response)

    async def release(self, claim) -> None:
        if self.release_error is not None:
            raise self.release_error
        self.records.pop((str(claim.org_id), str(claim.agent_id), claim.key), None)


_ledger = _Ledger()


def reset_enqueue_state() -> None:
    _ledger.records.clear()
    _ledger.claim_error = None
    _ledger.finalize_error = None
    _ledger.release_error = None
    _ledger.ping_error = None
    reset_enqueue_http_for_tests()


def _settings(**overrides: object) -> SimpleNamespace:
    token = overrides.get("token", "sekrit")
    host = overrides.get("host", "127.0.0.1")
    port = overrides.get("port", 18007)
    redis_url = overrides.get("redis_url")
    broker_url = overrides.get("broker_url")
    tok = SecretStr(str(token)) if token else None
    resolved = broker_url if broker_url is not None else redis_url
    return SimpleNamespace(
        enqueue_api_token=tok,
        enqueue_host=host,
        enqueue_port=port,
        redis_url=redis_url,
        resolved_broker_url=resolved,
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


def _post_enqueue(
    client: TestClient, body: dict | bytes, *, token: str = "sekrit", raw: bool = False
):
    headers = {"Authorization": f"Bearer {token}"}
    if isinstance(body, dict) and "session_id" in body:
        headers["Idempotency-Key"] = str(body["session_id"])
    if raw:
        headers["Content-Type"] = "application/json"
        return client.post("/internal/extraction/enqueue", headers=headers, content=body)
    return client.post("/internal/extraction/enqueue", headers=headers, json=body)


def _client(token: str = "sekrit", apply_async=None) -> TestClient:
    return TestClient(
        create_enqueue_app(_settings(token=token), apply_async=apply_async, ledger=_ledger)
    )


class _RedisStub:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.closed = False

    async def ping(self) -> bool:
        if self.error is not None:
            raise self.error
        return True

    async def aclose(self) -> None:
        self.closed = True


def _patch_redis(monkeypatch, error: Exception | None = None) -> _RedisStub:
    client = _RedisStub(error)
    monkeypatch.setattr("redis.asyncio.Redis.from_url", lambda *_args, **_kwargs: client)
    return client
