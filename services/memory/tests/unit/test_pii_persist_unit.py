"""Unit tests for PII persist helper (mocked session factory)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from app.pii.persist import MemoryPiiUpdate, update_memory_pii_flags


class _FakeResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class _FakeSession:
    def __init__(self, rowcount: int) -> None:
        self._rowcount = rowcount

    async def execute(self, statement: object, params: object | None = None) -> _FakeResult:
        del statement, params
        return _FakeResult(self._rowcount)

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
    await update_memory_pii_flags(
        _factory_for(session),  # type: ignore[arg-type]
        MemoryPiiUpdate(
            org_id=uuid4(),
            memory_id=uuid4(),
            content="[EMAIL_ADDRESS]",
            status="active",
            pii_detected=True,
            pii_redacted=True,
        ),
    )


@pytest.mark.asyncio
async def test_update_memory_pii_flags_wrong_rowcount() -> None:
    session = _FakeSession(rowcount=0)
    with pytest.raises(RuntimeError, match="expected 1 row"):
        await update_memory_pii_flags(
            _factory_for(session),  # type: ignore[arg-type]
            MemoryPiiUpdate(
                org_id=uuid4(),
                memory_id=uuid4(),
                content="x",
                status="active",
                pii_detected=False,
                pii_redacted=False,
            ),
        )


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
    )
    assert update.org_id == org
    assert update.memory_id == mid
    assert update.content == "c"
    assert update.status == "quarantined"
