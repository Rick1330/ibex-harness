"""Unit tests for POST /v1/memories router (mocked orchestrator)."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from ibex_idempotency import (
    KIND_CONFLICT,
    KIND_IN_PROGRESS,
    KIND_OWNED,
    KIND_REPLAY,
    ClaimOutcome,
    ClaimToken,
    LedgerError,
)

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.deps import (
    get_memory_cache_writer,
    get_session_factory,
    get_write_orchestrator,
    require_memory_write,
)
from app.exceptions import (
    DuplicateMemoryError,
    EmbeddingServiceError,
    MemoryNotFoundError,
    MemoryOrganizationUnavailableError,
    StaleLifecycleError,
    ValidationError,
)
from app.main import create_app
from app.permissions import MEMORY_WRITE
from app.routers import memories as memories_router
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


def _with_idempotency_ledger(http: TestClient, ledger: object) -> None:
    from app.deps import get_idempotency_ledger

    http.app.dependency_overrides[get_idempotency_ledger] = lambda: ledger


def _owned_outcome() -> ClaimOutcome:
    claim = ClaimToken(uuid4(), ORG, AGENT, "key-1", "f" * 64, version=1)
    return ClaimOutcome(kind=KIND_OWNED, claim=claim)


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


class _FakeLedger:
    def __init__(self, claim_outcome) -> None:
        self.claim_outcome = claim_outcome
        self.finalized: list[tuple] = []
        self.released: list[object] = []

    async def claim(self, *, org_id, agent_id, key, request_hash):
        return self.claim_outcome

    async def finalize(self, claim, *, status, response):
        self.finalized.append((claim, status, response))

    async def release(self, claim):
        self.released.append(claim)


def test_create_memory_201(client) -> None:
    http, mock_orch = client
    mock_orch.create = AsyncMock(
        return_value=WriteOutcome(kind=WriteOutcomeKind.CREATED, memory=_memory_row())
    )
    with http:
        resp = _post_memory(http)
    assert resp.status_code == 201
    assert resp.json()["data"]["content"] == "hello"


def test_create_memory_passes_valid_interval_and_token_org(client) -> None:
    http, mock_orch = client
    mock_orch.create = AsyncMock(
        return_value=WriteOutcome(kind=WriteOutcomeKind.CREATED, memory=_memory_row())
    )
    with http:
        resp = http.post(
            "/v1/memories",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={
                "agent_id": str(AGENT),
                "content": "hello",
                "valid_from": "2026-09-01T00:00:00Z",
                "valid_until": "2026-09-08T00:00:00Z",
            },
        )
    assert resp.status_code == 201
    command = mock_orch.create.await_args.args[0]
    assert command.org_id == ORG
    assert command.valid_from is not None
    assert command.valid_until is not None


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


def test_create_memory_409_org_unavailable(client) -> None:
    http, mock_orch = client
    mock_orch.create = AsyncMock(side_effect=MemoryOrganizationUnavailableError())
    with http:
        resp = _post_memory(http, content="x")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "ORG_UNAVAILABLE"


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

    class _FailingReleaseLedger(_FakeLedger):
        async def release(self, claim):
            raise LedgerError("down")

    ledger = _FailingReleaseLedger(_owned_outcome())
    _with_idempotency_ledger(http, ledger)
    mock_orch.create = AsyncMock(side_effect=DuplicateMemoryError(uuid4()))
    with http:
        resp = _post_memory(http, content="dup", idempotency_key="key-1")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "DUPLICATE_CONTENT"


def test_create_memory_finalize_failure_fails_closed(client) -> None:
    http, mock_orch = client

    class _FailingFinalizeLedger(_FakeLedger):
        async def finalize(self, claim, *, status, response):
            raise LedgerError("down")

    ledger = _FailingFinalizeLedger(_owned_outcome())
    _with_idempotency_ledger(http, ledger)
    mock_orch.create = AsyncMock(
        return_value=WriteOutcome(kind=WriteOutcomeKind.CREATED, memory=_memory_row())
    )
    with http:
        resp = _post_memory(http, idempotency_key="key-1")
    # A committed write must not be reported as completed while its ledger
    # claim is still open: the endpoint fails closed instead of returning 201.
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "IDEMPOTENCY_UNAVAILABLE"


def test_create_memory_idempotency_hit(client) -> None:
    http, mock_orch = client
    replay = ClaimOutcome(kind=KIND_REPLAY, status=201, response=b'{"data":{"content":"cached"}}')
    _with_idempotency_ledger(http, _FakeLedger(replay))
    with http:
        resp = _post_memory(http, idempotency_key="key-1")
    assert resp.status_code == 201
    assert resp.headers.get("X-Idempotency-Replayed") == "true"
    mock_orch.create.assert_not_called()


def test_create_memory_idempotency_conflict(client) -> None:
    http, _mock_orch = client
    _with_idempotency_ledger(http, _FakeLedger(ClaimOutcome(kind=KIND_CONFLICT)))
    with http:
        resp = _post_memory(http, idempotency_key="key-1")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_create_memory_idempotency_in_progress(client) -> None:
    http, _mock_orch = client
    _with_idempotency_ledger(
        http, _FakeLedger(ClaimOutcome(kind=KIND_IN_PROGRESS, retry_after=5))
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
    ledger = _FakeLedger(_owned_outcome())
    _with_idempotency_ledger(http, ledger)
    mock_orch.create = AsyncMock(side_effect=side_effect)
    with http:
        resp = _post_memory(http, content="x", idempotency_key="key-1")
    assert resp.status_code == expected_status
    assert len(ledger.released) == 1


def test_create_memory_unexpected_error_releases_idempotency(client) -> None:
    http, mock_orch = client
    ledger = _FakeLedger(_owned_outcome())
    _with_idempotency_ledger(http, ledger)
    mock_orch.create = AsyncMock(side_effect=RuntimeError("boom"))
    with TestClient(http.app, raise_server_exceptions=False) as client_no_raise:
        resp = client_no_raise.post(
            "/v1/memories",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "X-Idempotency-Key": "key-1",
            },
            json={"agent_id": str(AGENT), "content": "x"},
        )
    assert resp.status_code == 500
    detail = resp.json()["detail"]
    assert detail["code"] == "INTERNAL_ERROR"
    assert detail["message"] == "Memory write failed"
    assert len(ledger.released) == 1


def test_create_memory_quarantine_commits_idempotency(client) -> None:
    http, mock_orch = client
    ledger = _FakeLedger(_owned_outcome())
    _with_idempotency_ledger(http, ledger)
    row = replace(_memory_row(), status="quarantined", pii_detected=True)
    mock_orch.create = AsyncMock(
        return_value=WriteOutcome(kind=WriteOutcomeKind.QUARANTINED, memory=row)
    )
    with http:
        resp = _post_memory(http, content="Contact Jordan", idempotency_key="key-1")
    assert resp.status_code == 202
    assert len(ledger.finalized) == 1
    assert ledger.finalized[0][1] == 202


def test_forget_returns_success_when_post_commit_cache_invalidation_fails(
    client, monkeypatch
) -> None:
    http, _mock_orch = client

    class _FakeContext:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    class _FakeSession(_FakeContext):
        def begin(self):
            return _FakeContext()

    class _FailingCacheWriter:
        async def forget_memory(self, **_kwargs):
            raise RuntimeError("unexpected cache failure")

    async def _forget(_session, _request):
        return 2

    memory_id = uuid4()
    monkeypatch.setattr(memories_router, "forget_memory_session", _forget)
    http.app.dependency_overrides[get_session_factory] = lambda: _FakeSession
    http.app.dependency_overrides[get_memory_cache_writer] = lambda: _FailingCacheWriter()
    with http:
        response = http.post(
            f"/v1/memories/{memory_id}/forget",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"expected_revision": 1},
        )
    assert response.status_code == 200
    assert response.json()["data"] == {
        "memory_id": str(memory_id),
        "revision": 2,
        "tombstoned": True,
    }


class _ForgetContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _ForgetSession(_ForgetContext):
    def begin(self):
        return _ForgetContext()


def test_forget_requires_agent_scoped_token(client) -> None:
    http, _mock_orch = client
    http.app.dependency_overrides[require_memory_write] = lambda: ValidateResult(
        org_id=ORG, permissions=MEMORY_WRITE, agent_id=None
    )
    with http:
        response = http.post(
            f"/v1/memories/{uuid4()}/forget",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"expected_revision": 1},
        )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "AGENT_SCOPE_REQUIRED"


@pytest.mark.parametrize(
    ("side_effect", "expected"),
    [
        (MemoryNotFoundError(), (404, "NOT_FOUND")),
        (StaleLifecycleError("stale"), (409, "STALE_LIFECYCLE_REVISION")),
        (MemoryOrganizationUnavailableError(), (409, "ORG_UNAVAILABLE")),
    ],
    ids=["not_found", "stale_lifecycle", "org_unavailable"],
)
def test_forget_maps_domain_errors(client, monkeypatch, side_effect, expected) -> None:
    http, _mock_orch = client
    expected_status, expected_code = expected

    async def _forget(_session, _request):
        raise side_effect

    monkeypatch.setattr(memories_router, "forget_memory_session", _forget)
    http.app.dependency_overrides[get_session_factory] = lambda: _ForgetSession
    http.app.dependency_overrides[get_memory_cache_writer] = lambda: None
    with http:
        response = http.post(
            f"/v1/memories/{uuid4()}/forget",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"expected_revision": 1},
        )
    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == expected_code
