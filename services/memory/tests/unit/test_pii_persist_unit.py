"""Unit tests for PII persist helper (mocked session factory)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from app.exceptions import StaleLifecycleError
from app.pii.persist import MemoryPiiUpdate, update_memory_pii_flags


class _FakeResult:
    def __init__(self, rowcount: int, revision: int = 1) -> None:
        self.rowcount = rowcount
        self.revision = revision

    def scalar_one(self) -> int:
        return self.revision


class _FakeSession:
    def __init__(self, rowcount: int) -> None:
        self._rowcount = rowcount

    async def execute(self, statement: object, params: object | None = None) -> _FakeResult:
        del statement, params
        return _FakeResult(self._rowcount, revision=2)

    @asynccontextmanager
    async def begin(self):
        yield self


def _factory_for(session: _FakeSession):
    @asynccontextmanager
    async def _factory():
        yield session

    return _factory


@pytest.mark.asyncio
async def test_update_memory_pii_flags_success() -> None:
    session = _FakeSession(rowcount=1)
    from unittest.mock import AsyncMock, patch

    with (
        patch("app.pii.persist.lock_organization_for_memory_write", AsyncMock()),
        patch("app.pii.persist.enqueue_memory_lifecycle_event", AsyncMock()) as enqueue,
    ):
        await update_memory_pii_flags(
            _factory_for(session),  # type: ignore[arg-type]
            MemoryPiiUpdate(
                org_id=uuid4(),
                memory_id=uuid4(),
                content="[EMAIL_ADDRESS]",
                status="active",
                pii_detected=True,
                pii_redacted=True,
                expected_revision=1,
            ),
        )
    enqueue.assert_awaited_once()
    event = enqueue.await_args.args[1]
    assert event.revision == 2
    assert event.event_type == "content_updated"


@pytest.mark.asyncio
async def test_update_memory_pii_flags_wrong_rowcount() -> None:
    session = _FakeSession(rowcount=0)
    factory = _factory_for(session)  # type: ignore[arg-type]
    update = MemoryPiiUpdate(
        org_id=uuid4(),
        memory_id=uuid4(),
        content="x",
        status="active",
        pii_detected=False,
        pii_redacted=False,
        expected_revision=1,
    )
    from unittest.mock import AsyncMock, patch

    with (
        patch("app.pii.persist.lock_organization_for_memory_write", AsyncMock()),
        pytest.raises(StaleLifecycleError),
    ):
        await update_memory_pii_flags(factory, update)


def test_memory_pii_update_fields() -> None:
    org = uuid4()
    mid = uuid4()
    update = MemoryPiiUpdate(
        org_id=org,
        memory_id=mid,
        content="c",
        status="quarantined",
        pii_detected=True,
        pii_redacted=False,
        expected_revision=1,
    )
    assert update.org_id == org
    assert update.memory_id == mid
    assert update.content == "c"
    assert update.status == "quarantined"
