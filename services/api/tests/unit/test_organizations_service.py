"""Unit tests for organization service lifecycle."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from apierror_py import NOT_FOUND, SERVICE_DEGRADED, VALIDATION_ERROR

from app.errors import ApiError
from app.revocation_publish import RecordingOrgSuspendPublisher
from app.schemas.organizations import OrganizationPatch
from app.services import organizations as org_service
from tests.unit.org_user_test_support import sample_org_row


class _MapResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


def _org(**overrides):
    return SimpleNamespace(**sample_org_row(overrides.pop("id", uuid4()), **overrides))


@pytest.mark.asyncio
async def test_get_organization_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_MapResult(None))
    with pytest.raises(ApiError) as exc:
        await org_service.get_organization(session, uuid4())
    assert exc.value.code == NOT_FOUND


@pytest.mark.asyncio
async def test_suspend_publishes_event() -> None:
    org_id = uuid4()
    row = _org(id=org_id, status="suspended")
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_MapResult(row))
    session.commit = AsyncMock()
    pub = RecordingOrgSuspendPublisher()
    out = await org_service.suspend_organization(session, org_id, pub)
    assert out.status == "suspended"
    assert pub.org_ids == [str(org_id)]


@pytest.mark.asyncio
async def test_patch_organization() -> None:
    org_id = uuid4()
    current = _org(id=org_id)
    updated = _org(id=org_id, name="Renamed")
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_MapResult(current), _MapResult(updated)])
    session.commit = AsyncMock()
    out = await org_service.patch_organization(
        session, org_id, OrganizationPatch(name="Renamed")
    )
    assert out.name == "Renamed"


@pytest.mark.asyncio
async def test_get_deletion_job_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_MapResult(None))
    with pytest.raises(ApiError) as exc:
        await org_service.get_deletion_job(session, uuid4(), uuid4())
    assert exc.value.code == NOT_FOUND


@pytest.mark.asyncio
async def test_get_deletion_job_ok() -> None:
    org_id = uuid4()
    job_id = uuid4()
    row = _org(id=org_id)
    job = SimpleNamespace(
        id=job_id,
        org_id=org_id,
        status="succeeded",
        error=None,
        created_at=row.created_at,
        updated_at=row.updated_at,
        started_at=row.created_at,
        finished_at=row.updated_at,
    )
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_MapResult(job))
    out = await org_service.get_deletion_job(session, org_id, job_id)
    assert out.status == "succeeded"


@pytest.mark.asyncio
async def test_enqueue_already_cancelled_without_failed_job() -> None:
    org_id = uuid4()
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _MapResult(_org(id=org_id, status="cancelled")),
            _MapResult({"status": "succeeded"}),
        ]
    )
    with pytest.raises(ApiError) as exc:
        await org_service.enqueue_org_deletion(session, org_id, enqueue_fn=lambda *_: None)
    assert exc.value.code == VALIDATION_ERROR


@pytest.mark.asyncio
async def test_enqueue_rejects_unconfigured_broker() -> None:
    org_id = uuid4()
    session = AsyncMock()
    with pytest.raises(ApiError) as exc:
        await org_service.enqueue_org_deletion(
            session, org_id, enqueue_fn=org_service.unconfigured_org_deletion_enqueue
        )
    assert exc.value.code == SERVICE_DEGRADED
    session.execute.assert_not_called()


def _pending_job_fixture(org_id, *, extra_executes: int = 0):
    current = _org(id=org_id)
    job = SimpleNamespace(
        id=uuid4(),
        org_id=org_id,
        status="pending",
        error=None,
        created_at=current.created_at,
        updated_at=current.updated_at,
        started_at=None,
        finished_at=None,
    )
    session = AsyncMock()
    # get org, create job, cancel org (after successful enqueue)
    side_effect: list = [_MapResult(current), _MapResult(job), MagicMock()]
    side_effect.extend(MagicMock() for _ in range(extra_executes))
    session.execute = AsyncMock(side_effect=side_effect)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session, job


@pytest.mark.asyncio
async def test_enqueue_org_deletion() -> None:
    org_id = uuid4()
    session, job = _pending_job_fixture(org_id)
    calls: list[tuple[str, str]] = []

    def enqueue(job_id: str, oid: str) -> None:
        calls.append((job_id, oid))

    out = await org_service.enqueue_org_deletion(session, org_id, enqueue_fn=enqueue)
    assert out.status == "pending"
    assert calls == [(str(job.id), str(org_id))]
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_enqueue_marks_failed_without_cancelling_org() -> None:
    org_id = uuid4()
    current = _org(id=org_id)
    job = SimpleNamespace(
        id=uuid4(),
        org_id=org_id,
        status="pending",
        error=None,
        created_at=current.created_at,
        updated_at=current.updated_at,
        started_at=None,
        finished_at=None,
    )
    session = AsyncMock()
    # get, create, mark failed (no cancel)
    session.execute = AsyncMock(side_effect=[_MapResult(current), _MapResult(job), MagicMock()])
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    def boom(_j: str, _o: str) -> None:
        raise RuntimeError("broker down")

    with pytest.raises(ApiError) as exc:
        await org_service.enqueue_org_deletion(session, org_id, enqueue_fn=boom)
    assert exc.value.code == SERVICE_DEGRADED
    session.commit.assert_awaited_once()
    fail_sql, fail_params = session.execute.await_args_list[-1].args[:2]
    assert "failed" in str(fail_sql)
    assert fail_params["org_id"] == str(org_id)


@pytest.mark.asyncio
async def test_enqueue_retries_when_prior_job_failed() -> None:
    org_id = uuid4()
    cancelled = _org(id=org_id, status="cancelled")
    job = SimpleNamespace(
        id=uuid4(),
        org_id=org_id,
        status="pending",
        error=None,
        created_at=cancelled.created_at,
        updated_at=cancelled.updated_at,
        started_at=None,
        finished_at=None,
    )
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _MapResult(cancelled),
            _MapResult({"status": "failed"}),
            _MapResult(job),
            MagicMock(),  # cancel
        ]
    )
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    calls: list[tuple[str, str]] = []

    out = await org_service.enqueue_org_deletion(
        session, org_id, enqueue_fn=lambda j, o: calls.append((j, o))
    )
    assert out.status == "pending"
    assert calls == [(str(job.id), str(org_id))]
