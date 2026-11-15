"""Capture archiver → memory artifact refs: the link is written with the archive.

Why this file exists: a memory forget can only erase the copies of a memory it
can find. Before migration 000072 nothing linked a memory to its object-store
capture, its ClickHouse evidence, or the session event that carried it, so those
copies were unreachable by a forget and unprovable after one. The archiver now
records that link at write time, in the same transaction as ``archived_to``,
because provenance that was never written cannot be recovered by a later schema
change.

Real database, not mocks: the task runs through ``session_as_app_org``, so every
write is checked by the RLS policy and the tenant grants production uses. The
object-store PUT is the only stub — this suite has no MinIO — and every assertion
here is about the rows Postgres ends up with.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from prometheus_client import REGISTRY
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.tasks import capture_redaction
from app.tasks.capture_redaction import _CaptureJob
from tests.integration.tenant_pinning_support import (
    CapturePolicySeed,
    SessionEventSeed,
    SessionSeed,
    count_rows,
    fetch_all,
    fetch_one,
    seed_capture_policy,
    seed_org,
    seed_session,
    seed_session_event,
    seed_tenant_rows,
)

pytestmark = pytest.mark.integration

_COVERAGE_METRIC = "ibex_worker_capture_archive_without_memory_id_total"


@dataclass(frozen=True, slots=True)
class _ArchiveCase:
    """One capture event to archive, and the URI the stubbed PUT returns."""

    org_id: UUID
    event_id: int
    payload: dict[str, object]
    archive_uri: str


@dataclass(frozen=True, slots=True)
class _Archiver:
    """Run the archiver for one case, with the object-store PUT stubbed."""

    owner: async_sessionmaker[AsyncSession]
    dsn: str
    monkeypatch: pytest.MonkeyPatch

    async def run(self, case: _ArchiveCase) -> dict[str, str]:
        """Archive ``case``'s event and return the task result."""
        self.monkeypatch.setattr(
            capture_redaction,
            "_put_archive_blob",
            lambda _settings, _job, _payload, _kind: case.archive_uri,
        )
        self.monkeypatch.setattr(
            capture_redaction, "get_settings", lambda: Settings(database_url=self.dsn)
        )
        return await capture_redaction._run(
            _CaptureJob(
                org_id=str(case.org_id),
                event_id=str(case.event_id),
                payload=case.payload,
            )
        )


@pytest.fixture
def archiver(
    owner_factory: async_sessionmaker[AsyncSession],
    capability_worker_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> _Archiver:
    """The archiver under test, running as the tenant identity on a real DB."""
    return _Archiver(
        owner=owner_factory, dsn=capability_worker_dsn, monkeypatch=monkeypatch
    )


def _coverage_count() -> float:
    """Current value of the no-memory-id counter, or 0 when it has never fired."""
    value = REGISTRY.get_sample_value(_COVERAGE_METRIC)
    return 0.0 if value is None else value


async def _seed_full_capture_event(
    owner_factory: async_sessionmaker[AsyncSession],
    *,
    org_id: UUID,
    data: dict[str, object],
) -> tuple[UUID, int]:
    """Seed one org in ``full`` capture mode with a session and one event."""
    _, agent_id = await seed_tenant_rows(owner_factory, org_id, tag=org_id.hex[:8])
    session_id = uuid4()
    await seed_session(
        owner_factory,
        SessionSeed(org_id=org_id, agent_id=agent_id, session_id=session_id),
    )
    await seed_capture_policy(owner_factory, CapturePolicySeed(org_id=org_id, mode="full"))
    event_id = await seed_session_event(
        owner_factory,
        SessionEventSeed(org_id=org_id, session_id=session_id, data=data),
    )
    return session_id, event_id


async def _seed_capture(
    owner_factory: async_sessionmaker[AsyncSession], *, payload: dict[str, object]
) -> tuple[UUID, _ArchiveCase]:
    """Seed an org with one capture event and the case that archives it."""
    org_id = uuid4()
    await seed_org(owner_factory, org_id)
    session_id, event_id = await _seed_full_capture_event(
        owner_factory, org_id=org_id, data=payload
    )
    case = _ArchiveCase(
        org_id=org_id,
        event_id=event_id,
        payload=payload,
        archive_uri=f"s3://ibex-sessions/{org_id}/capture/full/{event_id}.json",
    )
    return session_id, case


async def _seed_memory_capture(
    owner_factory: async_sessionmaker[AsyncSession],
) -> tuple[UUID, UUID, _ArchiveCase]:
    """Seed one memory id, the payload that names it, and the archive case."""
    memory_id = uuid4()
    payload = {"memory_ids": [str(memory_id)], "query": "dark mode"}
    session_id, case = await _seed_capture(owner_factory, payload=payload)
    return memory_id, session_id, case


def _expected_refs(
    session_id: UUID, case: _ArchiveCase
) -> list[tuple[str, str, str | None]]:
    """The refs one archived capture of one memory must leave behind."""
    return [
        ("objectstore", case.archive_uri, str(session_id)),
        ("session_event", str(case.event_id), str(session_id)),
    ]


async def _artifact_refs(
    owner_factory: async_sessionmaker[AsyncSession], *, org_id: UUID, memory_id: UUID
) -> list[tuple[str, str, str | None]]:
    """Every ref of one memory in one org, ordered by store."""
    rows = await fetch_all(
        owner_factory,
        """
        SELECT store, locator, session_id::text
          FROM ibex_core.memory_artifact_refs
         WHERE org_id = :org AND memory_id = :memory
         ORDER BY store
        """,
        org=org_id,
        memory=memory_id,
    )
    return [(row[0], row[1], row[2]) for row in rows]


async def _archived_to(
    owner_factory: async_sessionmaker[AsyncSession], *, org_id: UUID, event_id: int
) -> str | None:
    """The archive URI the capture event row records."""
    row = await fetch_one(
        owner_factory,
        "SELECT archived_to FROM ibex_core.session_events WHERE id = :id AND org_id = :org",
        id=event_id,
        org=org_id,
    )
    return row[0]


async def _ref_count(
    owner_factory: async_sessionmaker[AsyncSession], org_id: UUID
) -> int:
    """How many artifact refs the org holds at all."""
    return await count_rows(
        owner_factory,
        "SELECT count(*) FROM ibex_core.memory_artifact_refs WHERE org_id = :org",
        org=org_id,
    )


def _require_archived(out: dict[str, str], case: _ArchiveCase) -> None:
    """The archiver reports the event it archived, in ``full`` mode."""
    assert out == {
        "status": "archived",
        "mode": "full",
        "event_id": str(case.event_id),
    }


@pytest.mark.asyncio
async def test_archive_records_one_ref_per_store_for_a_memory_id(
    archiver: _Archiver,
) -> None:
    """One memory id in the payload yields one objectstore ref and one event ref.

    The session id on both rows is read from the event the archiver just updated,
    so a ref carries the session without a second round trip.
    """
    memory_id, session_id, case = await _seed_memory_capture(archiver.owner)

    out = await archiver.run(case)

    _require_archived(out, case)
    assert (
        await _artifact_refs(archiver.owner, org_id=case.org_id, memory_id=memory_id)
        == _expected_refs(session_id, case)
    )
    assert (
        await _archived_to(archiver.owner, org_id=case.org_id, event_id=case.event_id)
        == case.archive_uri
    )


@pytest.mark.asyncio
async def test_redelivered_archive_keeps_one_ref_per_store(
    archiver: _Archiver,
) -> None:
    """Archiving the same event twice still leaves one ref per store.

    A redelivered Celery task is normal, so the write is ``ON CONFLICT DO
    NOTHING`` on ``(org_id, memory_id, store, locator)``. A second row would make
    the erasure worklist do the same store twice and report two deletions for one
    object.
    """
    memory_id, session_id, case = await _seed_memory_capture(archiver.owner)

    for _ in range(2):
        await archiver.run(case)

    assert (
        await _artifact_refs(archiver.owner, org_id=case.org_id, memory_id=memory_id)
        == _expected_refs(session_id, case)
    )
    assert await _ref_count(archiver.owner, case.org_id) == 2


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"model": "gpt-4o-mini"}, id="no-memory-key"),
        pytest.param({"memory_ids": ["not-a-uuid"]}, id="unusable-memory-id"),
        pytest.param({"memory_ids": []}, id="empty-memory-id-list"),
    ],
)
@pytest.mark.asyncio
async def test_archive_without_a_memory_id_records_no_ref_and_counts_it(
    archiver: _Archiver, payload: dict[str, object]
) -> None:
    """No usable memory id means no ref — and a visible coverage hole.

    Inventing a link would point an erasure at an object that may belong to
    another memory or another tenant, so the archiver writes nothing. The event
    is still archived; the counter is what makes the missing provenance visible
    instead of silent.
    """
    _session_id, case = await _seed_capture(archiver.owner, payload=payload)
    before = _coverage_count()

    out = await archiver.run(case)

    _require_archived(out, case)
    assert await _ref_count(archiver.owner, case.org_id) == 0
    assert _coverage_count() - before == 1
    assert (
        await _archived_to(archiver.owner, org_id=case.org_id, event_id=case.event_id)
        == case.archive_uri
    )
