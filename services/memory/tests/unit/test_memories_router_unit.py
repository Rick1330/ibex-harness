"""Unit tests for POST /v1/memories router (mocked orchestrator)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

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
from app.write.models import MemoryRow, WriteOutcome, WriteOutcomeKind

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


def _memory_row() -> MemoryRow:
    now = datetime.now(tz=UTC)
    return MemoryRow(
        id=uuid4(),
        org_id=ORG,
        agent_id=AGENT,
        content="hello",
        content_tokens=1,
        category="factual",
        confidence=0.8,
        status="active",
        source="user_provided",
        pii_detected=False,
        pii_redacted=False,
        session_id=None,
        metadata={},
        retrieval_count=0,
        usefulness_score=0.5,
        valid_from=now,
        valid_until=None,
        created_at=now,
        updated_at=now,
    )


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


def test_create_memory_duplicate_releases_idempotency(client) -> None:
    http, mock_orch = client
    store = _FakeStore(ClaimOutcome(kind=ClaimKind.MISS, record=None))
    _with_idempotency_store(http, store)
    mock_orch.create = AsyncMock(side_effect=DuplicateMemoryError(uuid4()))
    with http:
        resp = _post_memory(http, content="dup", idempotency_key="key-1")
    assert resp.status_code == 409
    assert len(store.released) == 1


def test_create_memory_validation_releases_idempotency(client) -> None:
    http, mock_orch = client
    store = _FakeStore(ClaimOutcome(kind=ClaimKind.MISS, record=None))
    _with_idempotency_store(http, store)
    mock_orch.create = AsyncMock(side_effect=ValidationError("bad", field="content"))
    with http:
        resp = _post_memory(http, content="x", idempotency_key="key-1")
    assert resp.status_code == 400
    assert len(store.released) == 1


def test_create_memory_embedding_releases_idempotency(client) -> None:
    http, mock_orch = client
    store = _FakeStore(ClaimOutcome(kind=ClaimKind.MISS, record=None))
    _with_idempotency_store(http, store)
    mock_orch.create = AsyncMock(side_effect=EmbeddingServiceError("down"))
    with http:
        resp = _post_memory(http, content="x", idempotency_key="key-1")
    assert resp.status_code == 503
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
