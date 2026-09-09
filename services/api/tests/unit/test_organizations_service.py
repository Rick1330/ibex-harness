"""Unit tests for organization service lifecycle."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from apierror_py import NOT_FOUND, VALIDATION_ERROR

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
async def test_enqueue_already_cancelled() -> None:
    org_id = uuid4()
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_MapResult(_org(id=org_id, status="cancelled")))
    with pytest.raises(ApiError) as exc:
        await org_service.enqueue_org_deletion(session, org_id, enqueue_fn=lambda *_: None)
    assert exc.value.code == VALIDATION_ERROR


@pytest.mark.asyncio
async def test_enqueue_org_deletion() -> None:
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
    session.execute = AsyncMock(
        side_effect=[_MapResult(current), _MapResult(job), MagicMock()]
    )
    session.commit = AsyncMock()
    calls: list[tuple[str, str]] = []

    def enqueue(job_id: str, oid: str) -> None:
        calls.append((job_id, oid))

    out = await org_service.enqueue_org_deletion(session, org_id, enqueue_fn=enqueue)
    assert out.status == "pending"
    assert calls == [(str(job.id), str(org_id))]


@pytest.mark.asyncio
async def test_enqueue_swallows_enqueue_errors() -> None:
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
    session.execute = AsyncMock(
        side_effect=[_MapResult(current), _MapResult(job), MagicMock()]
    )
    session.commit = AsyncMock()

    def boom(_j: str, _o: str) -> None:
        raise RuntimeError("broker down")

    out = await org_service.enqueue_org_deletion(session, org_id, enqueue_fn=boom)
    assert out.status == "pending"
