"""Unit tests for lifecycle fencing and forget persistence (scripted sessions)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from app.exceptions import (
    MemoryNotFoundError,
    MemoryOrganizationUnavailableError,
    StaleLifecycleError,
)
from app.lifecycle import (
    ExtractionSessionFence,
    ForgetMemory,
    MemoryLifecycleEvent,
    _matches_session_fence,
    enqueue_memory_lifecycle_event,
    forget_memory_session,
    lock_organization_for_memory_write,
    require_extraction_session,
)

ORG = uuid4()
AGENT = uuid4()
MEM = uuid4()
SESSION = uuid4()


class _FakeMappings:
    def __init__(self, row: dict | None) -> None:
        self._row = row

    def one_or_none(self) -> dict | None:
        return self._row


class _FakeResult:
    def __init__(self, *, mapping: dict | None = None, scalar: object | None = None) -> None:
        self._mapping = mapping
        self._scalar = scalar

    def mappings(self) -> _FakeMappings:
        return _FakeMappings(self._mapping)

    def scalar_one_or_none(self) -> object | None:
        return self._scalar


class _ScriptedSession:
    """Async session double that returns queued results in call order."""

    def __init__(self, results: list[_FakeResult]) -> None:
        self._results = list(results)
        self.executed = 0

    async def execute(self, statement: object, params: object | None = None) -> _FakeResult:
        del statement, params
        assert self._results, "unexpected session.execute — script exhausted"
        self.executed += 1
        return self._results.pop(0)


def _fence(*, session_id: UUID | None, expected_revision: int | None) -> ExtractionSessionFence:
    return ExtractionSessionFence(
        org_id=ORG,
        agent_id=AGENT,
        session_id=session_id,
        expected_revision=expected_revision,
    )


def _forget(*, expected_revision: int = 1) -> ForgetMemory:
    return ForgetMemory(
        org_id=ORG,
        agent_id=AGENT,
        memory_id=MEM,
        expected_revision=expected_revision,
    )


async def _forget_success(results: list[_FakeResult]) -> tuple[int, int]:
    session = _ScriptedSession(list(results))
    with patch("app.lifecycle.lock_organization_for_memory_write", AsyncMock()):
        revision = await forget_memory_session(session, _forget())
    return revision, session.executed


async def _forget_raises(results: list[_FakeResult], exc, match) -> None:
    session = _ScriptedSession(list(results))
    with (
        patch("app.lifecycle.lock_organization_for_memory_write", AsyncMock()),
        pytest.raises(exc, match=match),
    ):
        await forget_memory_session(session, _forget())


async def _call_lock(session: _ScriptedSession) -> None:
    with patch("app.lifecycle.set_service_org", AsyncMock()):
        await lock_organization_for_memory_write(session, ORG)


@pytest.mark.asyncio
async def test_lock_organization_active_acquires_advisory_and_row_lock() -> None:
    session = _ScriptedSession(
        [_FakeResult(), _FakeResult(mapping={"status": "active", "deleted_at": None})]
    )
    await _call_lock(session)
    assert session.executed == 2


@pytest.mark.asyncio
async def test_lock_organization_missing_row_raises() -> None:
    session = _ScriptedSession([_FakeResult(), _FakeResult(mapping=None)])
    with pytest.raises(MemoryOrganizationUnavailableError):
        await _call_lock(session)


@pytest.mark.asyncio
async def test_lock_organization_cancelled_raises() -> None:
    session = _ScriptedSession(
        [_FakeResult(), _FakeResult(mapping={"status": "cancelled", "deleted_at": None})]
    )
    with pytest.raises(MemoryOrganizationUnavailableError):
        await _call_lock(session)


@pytest.mark.asyncio
async def test_lock_organization_deleted_raises() -> None:
    session = _ScriptedSession(
        [
            _FakeResult(),
            _FakeResult(mapping={"status": "active", "deleted_at": datetime.now(tz=UTC)}),
        ]
    )
    with pytest.raises(MemoryOrganizationUnavailableError):
        await _call_lock(session)


@pytest.mark.asyncio
async def test_require_session_absent_and_no_revision_is_noop() -> None:
    session = _ScriptedSession([])
    await require_extraction_session(session, _fence(session_id=None, expected_revision=None))
    assert session.executed == 0


@pytest.mark.asyncio
async def test_require_session_revision_without_session_id_raises() -> None:
    with pytest.raises(StaleLifecycleError, match="without session_id"):
        await require_extraction_session(
            _ScriptedSession([]), _fence(session_id=None, expected_revision=1)
        )


@pytest.mark.asyncio
async def test_require_session_missing_revision_raises() -> None:
    with pytest.raises(StaleLifecycleError, match="revision is required"):
        await require_extraction_session(
            _ScriptedSession([]), _fence(session_id=SESSION, expected_revision=None)
        )


@pytest.mark.asyncio
async def test_require_session_non_positive_revision_raises() -> None:
    with pytest.raises(StaleLifecycleError, match="revision is required"):
        await require_extraction_session(
            _ScriptedSession([]), _fence(session_id=SESSION, expected_revision=0)
        )


@pytest.mark.asyncio
async def test_require_session_matching_row_passes() -> None:
    session = _ScriptedSession(
        [
            _FakeResult(
                mapping={
                    "agent_id": AGENT,
                    "status": "completed",
                    "deleted_at": None,
                    "lifecycle_revision": 3,
                }
            )
        ]
    )
    with patch("app.lifecycle.set_service_org", AsyncMock()):
        await require_extraction_session(session, _fence(session_id=SESSION, expected_revision=3))
    assert session.executed == 1


@pytest.mark.asyncio
async def test_require_session_stale_row_raises() -> None:
    session = _ScriptedSession(
        [
            _FakeResult(
                mapping={
                    "agent_id": AGENT,
                    "status": "completed",
                    "deleted_at": None,
                    "lifecycle_revision": 1,
                }
            )
        ]
    )
    with (
        patch("app.lifecycle.set_service_org", AsyncMock()),
        pytest.raises(StaleLifecycleError, match="stale or ineligible"),
    ):
        await require_extraction_session(session, _fence(session_id=SESSION, expected_revision=3))


def test_matches_session_fence_all_branches() -> None:
    fence = _fence(session_id=SESSION, expected_revision=2)
    assert _matches_session_fence(None, fence) is False
    assert (
        _matches_session_fence(
            {"agent_id": uuid4(), "status": "completed", "deleted_at": None, "lifecycle_revision": 2},
            fence,
        )
        is False
    )
    assert (
        _matches_session_fence(
            {"agent_id": AGENT, "status": "active", "deleted_at": None, "lifecycle_revision": 2},
            fence,
        )
        is False
    )
    assert (
        _matches_session_fence(
            {
                "agent_id": AGENT,
                "status": "completed",
                "deleted_at": datetime.now(tz=UTC),
                "lifecycle_revision": 2,
            },
            fence,
        )
        is False
    )
    assert (
        _matches_session_fence(
            {"agent_id": AGENT, "status": "completed", "deleted_at": None, "lifecycle_revision": 1},
            fence,
        )
        is False
    )
    assert (
        _matches_session_fence(
            {"agent_id": AGENT, "status": "completed", "deleted_at": None, "lifecycle_revision": 2},
            fence,
        )
        is True
    )


@pytest.mark.asyncio
async def test_enqueue_rejects_non_positive_revision() -> None:
    event = MemoryLifecycleEvent(org_id=ORG, memory_id=MEM, revision=0, event_type="created")
    with pytest.raises(ValueError, match="positive"):
        await enqueue_memory_lifecycle_event(_ScriptedSession([]), event)


@pytest.mark.asyncio
async def test_enqueue_rejects_unknown_event_type() -> None:
    event = MemoryLifecycleEvent(org_id=ORG, memory_id=MEM, revision=1, event_type="bogus")
    with pytest.raises(ValueError, match="unsupported"):
        await enqueue_memory_lifecycle_event(_ScriptedSession([]), event)


@pytest.mark.asyncio
async def test_forget_full_path_advances_source_session() -> None:
    revision, executed = await _forget_success(
        [
            _FakeResult(scalar=SESSION),
            _FakeResult(scalar=SESSION),
            _FakeResult(mapping={"lifecycle_revision": 1, "tombstoned": False}),
            _FakeResult(mapping={"lifecycle_revision": 2}),
            _FakeResult(),
            _FakeResult(),
        ]
    )
    assert (revision, executed) == (2, 6)


@pytest.mark.asyncio
async def test_forget_without_source_session_skips_session_lock() -> None:
    revision, executed = await _forget_success(
        [
            _FakeResult(scalar=None),
            _FakeResult(mapping={"lifecycle_revision": 1, "tombstoned": False}),
            _FakeResult(mapping={"lifecycle_revision": 2}),
            _FakeResult(),
        ]
    )
    assert (revision, executed) == (2, 4)


@pytest.mark.asyncio
async def test_forget_missing_source_session_lock_skips_advance() -> None:
    revision, executed = await _forget_success(
        [
            _FakeResult(scalar=SESSION),
            _FakeResult(scalar=None),
            _FakeResult(mapping={"lifecycle_revision": 1, "tombstoned": False}),
            _FakeResult(mapping={"lifecycle_revision": 2}),
            _FakeResult(),
        ]
    )
    assert (revision, executed) == (2, 5)


@pytest.mark.asyncio
async def test_forget_missing_target_raises_not_found() -> None:
    await _forget_raises(
        [_FakeResult(scalar=None), _FakeResult(mapping=None)], MemoryNotFoundError, None
    )


@pytest.mark.asyncio
async def test_forget_tombstoned_target_raises_stale() -> None:
    await _forget_raises(
        [_FakeResult(scalar=None), _FakeResult(mapping={"lifecycle_revision": 1, "tombstoned": True})],
        StaleLifecycleError,
        "stale",
    )


@pytest.mark.asyncio
async def test_forget_target_revision_mismatch_raises_stale() -> None:
    await _forget_raises(
        [_FakeResult(scalar=None), _FakeResult(mapping={"lifecycle_revision": 5, "tombstoned": False})],
        StaleLifecycleError,
        "stale",
    )


@pytest.mark.asyncio
async def test_forget_tombstone_returns_nothing_raises_stale() -> None:
    await _forget_raises(
        [
            _FakeResult(scalar=None),
            _FakeResult(mapping={"lifecycle_revision": 1, "tombstoned": False}),
            _FakeResult(mapping=None),
        ],
        StaleLifecycleError,
        "changed during forget",
    )


@pytest.mark.asyncio
async def test_forget_rejects_non_positive_expected_revision() -> None:
    with pytest.raises(StaleLifecycleError, match="must be positive"):
        await forget_memory_session(_ScriptedSession([]), _forget(expected_revision=0))
