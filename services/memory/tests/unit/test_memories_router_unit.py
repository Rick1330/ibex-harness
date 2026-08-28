"""Unit tests for POST /v1/memories router (mocked orchestrator)."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import RedisError

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.deps import get_write_orchestrator
from app.exceptions import DuplicateMemoryError, EmbeddingServiceError, ValidationError
from app.idempotency.redis_store import (
    ClaimKind,
    ClaimOutcome,
    IdempotencyRecord,
    IdempotencyState,
    pending_record,
)
from app.main import create_app
from app.permissions import MEMORY_WRITE
from app.write.models import WriteOutcome, WriteOutcomeKind
from tests.unit.memory_test_support import sample_memory_row

ORG = uuid4()
AGENT = uuid4()
TOKEN = "router-test-token"


def _post_memory(
    http: TestClient,
    *,
    content: str = "hello",
    idempotency_key: str | None = None,
):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key
    return http.post(
        "/v1/memories",
        headers=headers,
        json={"agent_id": str(AGENT), "content": content},
    )


def _with_idempotency_store(http: TestClient, store: object) -> None:
    from app.deps import get_idempotency_store

    http.app.dependency_overrides[get_idempotency_store] = lambda: store


def _memory_row():
    return sample_memory_row(org_id=ORG, agent_id=AGENT, content="hello")


@pytest.fixture
def client() -> TestClient:
    settings = Settings(
        database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex",
        embedding_api_token="unit-test-token",
    )
    validator = StaticTokenValidator(
        {TOKEN: ValidateResult(org_id=ORG, permissions=MEMORY_WRITE, agent_id=AGENT)}
    )
    app = create_app(settings=settings, validator=validator)
    mock_orch = AsyncMock()
    app.dependency_overrides[get_write_orchestrator] = lambda: mock_orch
    return TestClient(app), mock_orch


class _FakeStore:
    def __init__(self, claim_outcome) -> None:
        self.claim_outcome = claim_outcome
        self.committed: list[tuple] = []
        self.released: list[tuple] = []

    async def claim(self, _token, fp):
        return self.claim_outcome

    async def commit(self, token, *, fingerprint, status, body):
        self.committed.append((token, fingerprint, status, body))

    async def release(self, token, fp):
        self.released.append((token, fp))


def test_create_memory_201(client) -> None:
    http, mock_orch = client
    mock_orch.create = AsyncMock(
        return_value=WriteOutcome(kind=WriteOutcomeKind.CREATED, memory=_memory_row())
    )
    with http:
        resp = _post_memory(http)
    assert resp.status_code == 201
    assert resp.json()["data"]["content"] == "hello"


def test_create_memory_202_quarantine(client) -> None:
    http, mock_orch = client
    row = replace(_memory_row(), status="quarantined", pii_detected=True)
    mock_orch.create = AsyncMock(
        return_value=WriteOutcome(kind=WriteOutcomeKind.QUARANTINED, memory=row)
    )
    with http:
        resp = _post_memory(http, content="Contact Jordan")
    assert resp.status_code == 202
    assert resp.json()["data"]["status"] == "quarantined"


def test_create_memory_409_duplicate(client) -> None:
    http, mock_orch = client
    mock_orch.create = AsyncMock(side_effect=DuplicateMemoryError(uuid4()))
    with http:
        resp = _post_memory(http, content="dup")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "DUPLICATE_CONTENT"


def test_create_memory_400_validation(client) -> None:
    http, mock_orch = client
    mock_orch.create = AsyncMock(side_effect=ValidationError("bad", field="content"))
    with http:
        resp = _post_memory(http, content="x")
    assert resp.status_code == 400


def test_create_memory_503_embedding(client) -> None:
    http, mock_orch = client
    mock_orch.create = AsyncMock(side_effect=EmbeddingServiceError("down"))
    with http:
        resp = _post_memory(http, content="x")
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "EMBEDDING_FAILED"


def _post_validation(http: TestClient, payload: dict) -> object:
    return http.post(
        "/v1/memories",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json=payload,
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"agent_id": "not-a-uuid", "content": "hello"},
        {"agent_id": str(AGENT), "content": ""},
        {"agent_id": str(AGENT), "content": "x" * 10_001},
    ],
    ids=["bad_agent_id", "empty_content", "oversized_content"],
)
def test_create_memory_request_validation_errors(client, payload) -> None:
    http, mock_orch = client
    with http:
        resp = _post_validation(http, payload)
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"
    mock_orch.create.assert_not_called()


def test_create_memory_request_validation_metadata_depth(client) -> None:
    http, mock_orch = client
    nested: dict = {"a": {}}
    current = nested
    for _ in range(6):
        current["child"] = {}
        current = current["child"]
    with http:
        resp = _post_validation(http, {"agent_id": str(AGENT), "content": "hello", "metadata": nested})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"
    mock_orch.create.assert_not_called()


def test_create_memory_duplicate_release_error_still_returns_domain_error(client) -> None:
    http, mock_orch = client

    class _FailingReleaseStore(_FakeStore):
        async def release(self, token, fp):
            raise RedisError("down")

    store = _FailingReleaseStore(ClaimOutcome(kind=ClaimKind.MISS, record=None))
    _with_idempotency_store(http, store)
    mock_orch.create = AsyncMock(side_effect=DuplicateMemoryError(uuid4()))
    with http:
        resp = _post_memory(http, content="dup", idempotency_key="key-1")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "DUPLICATE_CONTENT"


def test_create_memory_commit_failure_still_returns_201(client) -> None:
    http, mock_orch = client

    class _FailingCommitStore(_FakeStore):
        async def commit(self, token, *, fingerprint, status, body):
            raise RedisError("down")

    store = _FailingCommitStore(ClaimOutcome(kind=ClaimKind.MISS, record=None))
    _with_idempotency_store(http, store)
    mock_orch.create = AsyncMock(
        return_value=WriteOutcome(kind=WriteOutcomeKind.CREATED, memory=_memory_row())
    )
    with http:
        resp = _post_memory(http, idempotency_key="key-1")
    assert resp.status_code == 201
    assert resp.json()["data"]["content"] == "hello"


def test_create_memory_idempotency_hit(client) -> None:
    http, mock_orch = client
    completed = IdempotencyRecord(
        fingerprint="ignored",
        state=IdempotencyState.COMPLETED,
        status=201,
        body=b'{"data":{"content":"cached"}}',
    )
    _with_idempotency_store(http, _FakeStore(ClaimOutcome(kind=ClaimKind.HIT, record=completed)))
    with http:
        resp = _post_memory(http, idempotency_key="key-1")
    assert resp.status_code == 201
    assert resp.headers.get("X-Idempotency-Replayed") == "true"
    mock_orch.create.assert_not_called()


def test_create_memory_idempotency_conflict(client) -> None:
    http, _mock_orch = client
    _with_idempotency_store(
        http, _FakeStore(ClaimOutcome(kind=ClaimKind.CONFLICT, record=pending_record("fp")))
    )
    with http:
        resp = _post_memory(http, idempotency_key="key-1")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_create_memory_idempotency_in_progress(client) -> None:
    http, _mock_orch = client
    _with_idempotency_store(
        http,
        _FakeStore(ClaimOutcome(kind=ClaimKind.IN_PROGRESS, record=pending_record("fp"))),
    )
    with http:
        resp = _post_memory(http, idempotency_key="key-1")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "IDEMPOTENCY_IN_PROGRESS"


@pytest.mark.parametrize(
    ("side_effect", "expected_status"),
    [
        (DuplicateMemoryError(uuid4()), 409),
        (ValidationError("bad", field="content"), 400),
        (EmbeddingServiceError("down"), 503),
    ],
    ids=["duplicate", "validation", "embedding"],
)
def test_create_memory_error_releases_idempotency(client, side_effect, expected_status) -> None:
    http, mock_orch = client
    store = _FakeStore(ClaimOutcome(kind=ClaimKind.MISS, record=None))
    _with_idempotency_store(http, store)
    mock_orch.create = AsyncMock(side_effect=side_effect)
    with http:
        resp = _post_memory(http, content="x", idempotency_key="key-1")
    assert resp.status_code == expected_status
    assert len(store.released) == 1


def test_create_memory_unexpected_error_releases_idempotency(client) -> None:
    http, mock_orch = client
    store = _FakeStore(ClaimOutcome(kind=ClaimKind.MISS, record=None))
    _with_idempotency_store(http, store)
    mock_orch.create = AsyncMock(side_effect=RuntimeError("boom"))
    with http, pytest.raises(RuntimeError, match="boom"):
        _post_memory(http, content="x", idempotency_key="key-1")
    assert len(store.released) == 1


def test_create_memory_quarantine_commits_idempotency(client) -> None:
    http, mock_orch = client
    store = _FakeStore(ClaimOutcome(kind=ClaimKind.MISS, record=None))
    _with_idempotency_store(http, store)
    row = replace(_memory_row(), status="quarantined", pii_detected=True)
    mock_orch.create = AsyncMock(
        return_value=WriteOutcome(kind=WriteOutcomeKind.QUARANTINED, memory=row)
    )
    with http:
        resp = _post_memory(http, content="Contact Jordan", idempotency_key="key-1")
    assert resp.status_code == 202
    assert len(store.committed) == 1
    assert store.committed[0][2] == 202
