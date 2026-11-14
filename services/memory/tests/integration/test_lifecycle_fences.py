"""Provisional GAP-007 lifecycle fence integration tests (real PostgreSQL required)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from ibex_idempotency import PostgresIdempotencyLedger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.conflict.persist import apply_supersession_session
from app.conflict.types import SupersedeApply
from app.exceptions import LegalHoldActiveError, StaleLifecycleError
from app.ledger_scope import tenant_ledger_session, tenant_scope
from app.lifecycle import (
    ForgetMemory,
    forget_memory_session,
)
from app.pipeline.context import WriteContext
from app.pipeline.write import WritePipeline
from app.routers.memories import ForgetMemoryContext
from app.routers.memory_write_support import erased_create_prepare
from app.schemas.memories import ForgetMemoryRequest
from app.vectorstore.base import SearchMode, SearchRequest, UpsertRequest
from app.vectorstore.pgvector_store import PgVectorStore
from app.write.models import CreateMemoryCommand
from app.write.orchestrator import MemoryWriteOrchestrator
from tests.integration import lifecycle_erasure_support
from tests.integration.conftest import seed_org_agent_memory, zero_embedding

pytestmark = pytest.mark.integration


_service_session = lifecycle_erasure_support.service_session
_execute_sql = lifecycle_erasure_support.execute_sql
_scalar = lifecycle_erasure_support.fetch_scalar
_rows = lifecycle_erasure_support.fetch_rows


async def _read_lifecycle(
    factory: async_sessionmaker[AsyncSession], *, org_id, memory_id
) -> tuple[int, bool, str, object]:
    rows = await _rows(
        factory,
        org_id,
        """SELECT lifecycle_revision, tombstoned, status, embedding
           FROM ibex_core.memories WHERE id=:id AND org_id=:org""",
        {"id": str(memory_id), "org": str(org_id)},
    )
    row = rows[0]
    return int(row.lifecycle_revision), bool(row.tombstoned), str(row.status), row.embedding


async def _read_outbox(
    factory: async_sessionmaker[AsyncSession], *, org_id, memory_id
) -> list[tuple[int, str]]:
    rows = await _rows(
        factory,
        org_id,
        """SELECT revision, event_type FROM ibex_core.memory_lifecycle_outbox
           WHERE org_id=:org AND memory_id=:id""",
        {"org": str(org_id), "id": str(memory_id)},
    )
    return [(int(row.revision), row.event_type) for row in rows]


async def _seed_memory_with_embedding(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    content: str,
    hotspot: int,
) -> tuple[object, object, object, list[float], PgVectorStore]:
    org_id, agent_id, memory_id = await seed_org_agent_memory(factory, content=content)
    query = zero_embedding(hotspot=hotspot)
    store = PgVectorStore(factory, settings)
    await store.upsert(
        UpsertRequest(
            memory_id=memory_id,
            org_id=org_id,
            embedding=query,
            embedding_model="test",
            expected_revision=1,
        )
    )
    return org_id, agent_id, memory_id, query, store


async def _assert_tombstoned_vector_fence(
    store: PgVectorStore,
    *,
    org_id,
    agent_id,
    memory_id,
    query: list[float],
) -> None:
    with pytest.raises(LookupError):
        await store.delete(memory_id=memory_id, org_id=org_id, expected_revision=2)
    stale_upsert = UpsertRequest(
        memory_id=memory_id,
        org_id=org_id,
        embedding=query,
        embedding_model="test",
        expected_revision=1,
    )
    with pytest.raises(LookupError):
        await store.upsert(stale_upsert)
    for mode in SearchMode:
        hits = await store.search(
            SearchRequest(
                org_id=org_id,
                agent_id=agent_id,
                query_embedding=query,
                limit=5,
                min_similarity=0.1,
                mode=mode,
            )
        )
        assert hits == []


async def test_forget_http_scope_revision_and_tombstone_vector_fence(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    org_id, agent_id, memory_id, query, store = await _seed_memory_with_embedding(
        session_factory, settings, content="forget lifecycle integration fixture", hotspot=11
    )

    # Invoke the actual handler with an authenticated, server-derived token scope.
    # Dependency authentication itself is covered by the HTTP router unit tests.
    from app.routers.memories import forget_memory

    token = SimpleNamespace(org_id=org_id, agent_id=agent_id)
    ctx = ForgetMemoryContext(token=token, session_factory=session_factory, cache_writer=None)
    response = await forget_memory(
        memory_id,
        ForgetMemoryRequest(expected_revision=1),
        ctx,
    )
    assert response.data.memory_id == memory_id
    assert response.data.revision == 2
    assert response.data.tombstoned is True

    with pytest.raises(HTTPException) as stale:
        await forget_memory(
            memory_id,
            ForgetMemoryRequest(expected_revision=1),
            ctx,
        )
    assert stale.value.status_code == 409

    revision, tombstoned, status, embedding = await _read_lifecycle(
        session_factory, org_id=org_id, memory_id=memory_id
    )
    assert (revision, tombstoned, status, embedding) == (2, True, "deleted", None)
    await _assert_tombstoned_vector_fence(
        store, org_id=org_id, agent_id=agent_id, memory_id=memory_id, query=query
    )
    assert await _read_outbox(
        session_factory, org_id=org_id, memory_id=memory_id
    ) == [(2, "forgotten")]


async def test_forget_outbox_failure_rolls_back_tombstone(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_id, agent_id, memory_id = await seed_org_agent_memory(
        session_factory, content="outbox atomic rollback fixture"
    )
    # Force the exact revision's unique key to conflict after the mutation executes.
    await _execute_sql(
        session_factory,
        org_id,
        """INSERT INTO ibex_core.memory_lifecycle_outbox
           (org_id, memory_id, revision, event_type)
           VALUES (:org, :id, 2, 'forgotten')""",
        {"org": str(org_id), "id": str(memory_id)},
    )
    command = ForgetMemory(
        org_id=org_id,
        agent_id=agent_id,
        memory_id=memory_id,
        expected_revision=1,
    )
    async with session_factory() as session:
        await session.begin()
        with pytest.raises(IntegrityError):
            await forget_memory_session(session, command)
        await session.rollback()
    revision, tombstoned, status, _ = await _read_lifecycle(
        session_factory, org_id=org_id, memory_id=memory_id
    )
    assert (revision, tombstoned, status) == (1, False, "active")


async def test_stale_forget_mutation_emits_no_outbox_event(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_id, agent_id, memory_id = await seed_org_agent_memory(
        session_factory, content="stale mutation has no event"
    )
    stale_command = ForgetMemory(
        org_id=org_id,
        agent_id=agent_id,
        memory_id=memory_id,
        expected_revision=2,
    )
    async with session_factory() as session:
        await session.begin()
        with pytest.raises(StaleLifecycleError):
            await forget_memory_session(session, stale_command)
        await session.rollback()
    revision, tombstoned, status, _ = await _read_lifecycle(
        session_factory, org_id=org_id, memory_id=memory_id
    )
    assert (revision, tombstoned, status) == (1, False, "active")
    assert await _read_outbox(session_factory, org_id=org_id, memory_id=memory_id) == []


async def test_stale_extraction_session_revision_fails_before_memory_insert(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content="extraction fence parent fixture"
    )
    session_id = uuid4()
    content = "stale session revision must never persist"
    content_hash = f"stale-{uuid4()}"
    await _execute_sql(
        session_factory,
        org_id,
        """INSERT INTO ibex_core.sessions
           (id, org_id, agent_id, status, model, provider)
           VALUES (:id, :org, :agent, 'completed', 'test', 'test')""",
        {"id": str(session_id), "org": str(org_id), "agent": str(agent_id)},
    )
    await _execute_sql(
        session_factory,
        org_id,
        "UPDATE ibex_core.sessions SET status='abandoned' WHERE id=:id AND org_id=:org",
        {"id": str(session_id), "org": str(org_id)},
    )
    command = CreateMemoryCommand(
        org_id=org_id,
        agent_id=agent_id,
        content=content,
        session_id=session_id,
        expected_session_revision=1,
    )
    ctx = WriteContext(
        org_id=org_id,
        agent_id=agent_id,
        content=content,
        content_hash=content_hash,
    )
    orchestrator = MemoryWriteOrchestrator(WritePipeline([]), session_factory)
    with pytest.raises(StaleLifecycleError):
        await orchestrator._persist_active(command, ctx)
    count = await _scalar(
        session_factory,
        org_id,
        "SELECT COUNT(*) FROM ibex_core.memories WHERE org_id=:org AND content_hash=:hash",
        {"org": str(org_id), "hash": content_hash},
    )
    assert count == 0


async def test_expires_at_hides_normal_retrieval_but_tombstone_wins_historical_mode(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    org_id, agent_id, memory_id, query, store = await _seed_memory_with_embedding(
        session_factory, settings, content="soft expiry integration fixture", hotspot=17
    )
    await _execute_sql(
        session_factory,
        org_id,
        "UPDATE ibex_core.memories SET expires_at=:expiry WHERE id=:id AND org_id=:org",
        {
            "expiry": datetime.now(tz=UTC) - timedelta(seconds=1),
            "id": str(memory_id),
            "org": str(org_id),
        },
    )
    common = {
        "org_id": org_id,
        "agent_id": agent_id,
        "query_embedding": query,
        "limit": 5,
        "min_similarity": 0.1,
    }
    ordinary = await store.search(SearchRequest(**common, mode=SearchMode.USER_RETRIEVAL))
    historical = await store.search(
        SearchRequest(**common, mode=SearchMode.HISTORICAL_CONFLICT_CANDIDATES)
    )
    assert ordinary == []
    assert [hit.memory_id for hit in historical] == [memory_id]
    await _execute_sql(
        session_factory,
        org_id,
        """UPDATE ibex_core.memories
           SET status='deleted', deleted_at=NOW(), tombstoned=TRUE
           WHERE id=:id AND org_id=:org""",
        {"id": str(memory_id), "org": str(org_id)},
    )
    assert (
        await store.search(SearchRequest(**common, mode=SearchMode.HISTORICAL_CONFLICT_CANDIDATES))
        == []
    )


async def _after_barrier(barrier: asyncio.Barrier, factory, action):
    """Run ``action(session)`` in its own transaction once both racers arrive."""
    await barrier.wait()
    async with factory() as session, session.begin():
        return await action(session)


async def test_concurrent_supersede_vs_forget_has_one_typed_loser(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_id, agent_id, target_id = await seed_org_agent_memory(
        session_factory, content="concurrent lifecycle target"
    )
    new_memory_id = uuid4()
    await _execute_sql(
        session_factory,
        org_id,
        """INSERT INTO ibex_core.memories
           (id, org_id, agent_id, content, content_hash, content_tokens)
           VALUES (:id, :org, :agent, :content, :hash, 4)""",
        {
            "id": str(new_memory_id),
            "org": str(org_id),
            "agent": str(agent_id),
            "content": "concurrent lifecycle replacement",
            "hash": f"race-{new_memory_id}",
        },
    )

    barrier = asyncio.Barrier(3)
    forget_task = asyncio.create_task(
        _after_barrier(
            barrier,
            session_factory,
            lambda session: forget_memory_session(
                session,
                ForgetMemory(
                    org_id=org_id,
                    agent_id=agent_id,
                    memory_id=target_id,
                    expected_revision=1,
                ),
            ),
        )
    )
    supersede_task = asyncio.create_task(
        _after_barrier(
            barrier,
            session_factory,
            lambda session: apply_supersession_session(
                session,
                SupersedeApply(
                    org_id=org_id,
                    agent_id=agent_id,
                    new_memory_id=new_memory_id,
                    target_memory_id=target_id,
                    expected_revision=1,
                ),
            ),
        )
    )
    await barrier.wait()
    results = await asyncio.gather(forget_task, supersede_task, return_exceptions=True)
    successes = [result for result in results if not isinstance(result, BaseException)]
    failures = [result for result in results if isinstance(result, BaseException)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], StaleLifecycleError)
    revision, tombstoned, status, _ = await _read_lifecycle(
        session_factory, org_id=org_id, memory_id=target_id
    )
    assert revision == 2
    assert (tombstoned and status == "deleted") or (not tombstoned and status == "superseded")
    assert await _read_outbox(session_factory, org_id=org_id, memory_id=target_id) == [
        (2, "forgotten" if tombstoned else "superseded")
    ]


@pytest.mark.asyncio
async def test_forget_erases_content_and_child_labels(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    """P0-08: forget is erasure, not only a visibility tombstone."""
    content = "sentinel-erasure-7f3a91 unforgettable"
    org_id, agent_id, memory_id, _query, _store = await _seed_memory_with_embedding(
        session_factory, settings, content=content, hotspot=12
    )
    fixture = lifecycle_erasure_support.ForgetFixture(
        org_id=org_id,
        agent_id=agent_id,
        memory_id=memory_id,
        other_id=await lifecycle_erasure_support.seed_related_memory(
            session_factory, org_id=org_id, agent_id=agent_id
        ),
        content=content,
        original_hash=await lifecycle_erasure_support.read_content_hash(
            session_factory, org_id=org_id, memory_id=memory_id
        ),
    )
    await lifecycle_erasure_support.seed_forget_state(session_factory, fixture)

    from app.routers.memories import forget_memory

    # Seeding the retention state moves the lifecycle revision on its own.
    revision, _tombstoned, _status, _embedding = await _read_lifecycle(
        session_factory, org_id=org_id, memory_id=memory_id
    )
    token = SimpleNamespace(org_id=org_id, agent_id=agent_id)
    ctx = ForgetMemoryContext(token=token, session_factory=session_factory, cache_writer=None)
    await forget_memory(
        memory_id,
        ForgetMemoryRequest(expected_revision=revision),
        ctx,
    )

    await lifecycle_erasure_support.assert_erased(session_factory, fixture)
    assert await _read_outbox(
        session_factory, org_id=org_id, memory_id=memory_id
    ) == [(revision + 1, "forgotten")]


@pytest.mark.asyncio
async def test_finalize_after_forget_stores_the_erased_marker(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    """A create that loses the race to forget must not resurrect its content."""
    content = "raced create sentinel 91b2"
    org_id, agent_id, memory_id, _query, _store = await _seed_memory_with_embedding(
        session_factory, settings, content=content, hotspot=17
    )
    ledger = PostgresIdempotencyLedger(
        session_factory, session_scope=tenant_scope(session_factory)
    )
    claim = (
        await ledger.claim(
            org_id=org_id,
            agent_id=agent_id,
            key="raced-create",
            request_hash="c" * 64,
        )
    ).claim
    assert claim is not None

    async with session_factory() as session, session.begin():
        await forget_memory_session(
            session,
            ForgetMemory(
                org_id=org_id,
                agent_id=agent_id,
                memory_id=memory_id,
                expected_revision=1,
            ),
        )

    body = json.dumps({"data": {"id": str(memory_id), "content": content}}).encode()
    await ledger.finalize(
        claim,
        status=201,
        response=body,
        prepare=erased_create_prepare(
            memory_id=memory_id, org_id=org_id, body=body
        ),
    )

    rows = await _rows(
        session_factory,
        org_id,
        "SELECT encode(response_payload, 'escape') AS payload"
        " FROM ibex_core.idempotency_ledger"
        " WHERE organization_id = :org AND dedupe_key = 'raced-create'",
        {"org": org_id},
    )
    assert len(rows) == 1
    assert content not in rows[0].payload, "the finalize resurrected erased content"
    assert '"erased":true' in rows[0].payload.replace(" ", "")


async def _forget_in_plain_transaction(factory, *, org_id, agent_id, memory_id) -> None:
    """Forget as a tenant transaction, with no service-account bypass set."""
    async with factory() as session, session.begin():
        await forget_memory_session(
            session,
            ForgetMemory(
                org_id=org_id,
                agent_id=agent_id,
                memory_id=memory_id,
                expected_revision=1,
            ),
        )


@pytest.mark.asyncio
async def test_forget_waits_for_a_finalization_holding_the_sharing_lock(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    """Forget blocks while finalization holds the row, and the key ends erased.

    This is the overlap the ``FOR SHARE`` exists for: without it, forget would
    commit while the finalize transaction is still open, and the finalize could
    then write the body back to the ledger.
    """
    content = "overlap sentinel 5c1f"
    org_id, agent_id, memory_id, _query, _store = await _seed_memory_with_embedding(
        session_factory, settings, content=content, hotspot=19
    )
    ledger = PostgresIdempotencyLedger(
        session_factory, session_scope=tenant_scope(session_factory)
    )
    claim = (
        await ledger.claim(
            org_id=org_id,
            agent_id=agent_id,
            key="overlap-create",
            request_hash="d" * 64,
        )
    ).claim
    assert claim is not None
    body = json.dumps({"data": {"id": str(memory_id), "content": content}}).encode()
    prepare = erased_create_prepare(memory_id=memory_id, org_id=org_id, body=body)

    locked = asyncio.Event()
    release = asyncio.Event()

    async def _hold_the_lock() -> None:
        async with tenant_ledger_session(session_factory, str(org_id)) as session:
            await prepare(session)
            locked.set()
            await release.wait()

    holder = asyncio.create_task(_hold_the_lock())
    try:
        await asyncio.wait_for(locked.wait(), timeout=5.0)
        forget_task = asyncio.create_task(
            _forget_in_plain_transaction(
                session_factory, org_id=org_id, agent_id=agent_id, memory_id=memory_id
            )
        )
        guarded = asyncio.shield(forget_task)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(guarded, timeout=1.0)
        release.set()
        await asyncio.wait_for(holder, timeout=5.0)
        await asyncio.wait_for(forget_task, timeout=10.0)
    finally:
        release.set()
        if not holder.done():
            await holder

    await ledger.finalize(claim, status=201, response=body, prepare=prepare)
    stored = await _rows(
        session_factory,
        org_id,
        "SELECT encode(response_payload, 'escape') AS payload"
        " FROM ibex_core.idempotency_ledger"
        " WHERE organization_id = :org AND dedupe_key = 'overlap-create'",
        {"org": org_id},
    )
    assert len(stored) == 1
    assert content not in stored[0].payload
    assert '"erased":true' in stored[0].payload.replace(" ", "")


async def test_forget_is_refused_while_a_legal_hold_is_active(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    """A legal hold preserves the organization's data: destruction is refused."""
    content = "held-tenant sentinel"
    org_id, agent_id, memory_id, _query, _store = await _seed_memory_with_embedding(
        session_factory, settings, content=content, hotspot=13
    )
    await _execute_sql(
        session_factory,
        org_id,
        "INSERT INTO ibex_core.legal_holds (org_id, reason, set_by)"
        " VALUES (:org, 'integration hold', :actor)",
        {"org": org_id, "actor": str(agent_id)},
    )

    refusal = _forget_in_plain_transaction(
        session_factory, org_id=org_id, agent_id=agent_id, memory_id=memory_id
    )
    with pytest.raises(LegalHoldActiveError):
        await refusal

    rows = await _rows(
        session_factory,
        org_id,
        "SELECT content, tombstoned FROM ibex_core.memories WHERE id=:id AND org_id=:org",
        {"id": memory_id, "org": org_id},
    )
    assert rows[0].content == content
    assert rows[0].tombstoned is False
