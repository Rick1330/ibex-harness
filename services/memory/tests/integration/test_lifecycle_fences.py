"""Provisional GAP-007 lifecycle fence integration tests (real PostgreSQL required)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.conflict.persist import apply_supersession_session
from app.conflict.types import SupersedeApply
from app.exceptions import LegalHoldActiveError, StaleLifecycleError
from app.lifecycle import (
    ForgetMemory,
    forget_memory_session,
)
from app.pipeline.context import WriteContext
from app.pipeline.write import WritePipeline
from app.schemas.memories import ForgetMemoryRequest
from app.vectorstore.base import SearchMode, SearchRequest, UpsertRequest
from app.vectorstore.pgvector_store import PgVectorStore
from app.write.models import CreateMemoryCommand
from app.write.orchestrator import MemoryWriteOrchestrator
from tests.integration.conftest import seed_org_agent_memory, with_service_org, zero_embedding

pytestmark = pytest.mark.integration


@asynccontextmanager
async def _service_session(factory, org_id):
    async with factory() as session, session.begin():
        await with_service_org(session, org_id)
        yield session


async def _execute_sql(factory, org_id, statement: str, params: dict) -> None:
    async with _service_session(factory, org_id) as session:
        await session.execute(text(statement), params)


async def _scalar(factory, org_id, statement: str, params: dict):
    async with _service_session(factory, org_id) as session:
        return await session.scalar(text(statement), params)


async def _rows(factory, org_id, statement: str, params: dict) -> list:
    async with _service_session(factory, org_id) as session:
        return (await session.execute(text(statement), params)).all()


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
    response = await forget_memory(
        memory_id,
        ForgetMemoryRequest(expected_revision=1),
        token,
        session_factory,
        None,
    )
    assert response.data.memory_id == memory_id
    assert response.data.revision == 2
    assert response.data.tombstoned is True

    with pytest.raises(HTTPException) as stale:
        await forget_memory(
            memory_id,
            ForgetMemoryRequest(expected_revision=1),
            token,
            session_factory,
            None,
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


async def _forget_after(
    barrier: asyncio.Barrier,
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id,
    agent_id,
    memory_id,
):
    await barrier.wait()
    async with factory() as session, session.begin():
        return await forget_memory_session(
            session,
            ForgetMemory(
                org_id=org_id,
                agent_id=agent_id,
                memory_id=memory_id,
                expected_revision=1,
            ),
        )


async def _supersede_after(
    barrier: asyncio.Barrier,
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id,
    agent_id,
    new_memory_id,
    target_id,
) -> None:
    await barrier.wait()
    async with factory() as session, session.begin():
        await apply_supersession_session(
            session,
            SupersedeApply(
                org_id=org_id,
                agent_id=agent_id,
                new_memory_id=new_memory_id,
                target_memory_id=target_id,
                expected_revision=1,
            ),
        )


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
        _forget_after(
            barrier, session_factory, org_id=org_id, agent_id=agent_id, memory_id=target_id
        )
    )
    supersede_task = asyncio.create_task(
        _supersede_after(
            barrier,
            session_factory,
            org_id=org_id,
            agent_id=agent_id,
            new_memory_id=new_memory_id,
            target_id=target_id,
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


async def _seed_finalized_create(
    factory, *, org_id, agent_id, created: tuple[str, str]
) -> None:
    """Store a finalized idempotent create response that carries the content."""
    memory_id, content = created
    await _execute_sql(
        factory,
        org_id,
        """INSERT INTO ibex_core.idempotency_ledger
           (organization_id, agent_id, dedupe_key, request_hash, state,
            status_code, response_payload)
           VALUES (:org, :agent, 'forget-erasure', repeat('a', 64), 'finalized',
                   201, convert_to(:payload, 'UTF8'))""",
        {
            "org": org_id,
            "agent": agent_id,
            "payload": '{"data":{"id":"%s","content":"%s"}}' % (memory_id, content),
        },
    )


async def _seed_near_duplicate(factory, *, org_id, agent_id, forgotten_id: str) -> None:
    """Another create's response lists the forgotten id; it must survive the scrub."""
    await _execute_sql(
        factory,
        org_id,
        """INSERT INTO ibex_core.idempotency_ledger
           (organization_id, agent_id, dedupe_key, request_hash, state,
            status_code, response_payload)
           VALUES (:org, :agent, 'other-create', repeat('b', 64), 'finalized', 201,
                   convert_to(:payload, 'UTF8'))""",
        {
            "org": org_id,
            "agent": agent_id,
            "payload": (
                '{"data":{"id":"%s","content":"other create content"},'
                '"meta":{"deduplication":{"similar_memories":["%s"]}}}'
                % ("11111111-1111-1111-1111-111111111111", forgotten_id)
            ),
        },
    )


async def _assert_content_erased(factory, *, org_id, memory_id, content: str) -> None:
    rows = await _rows(
        factory,
        org_id,
        """SELECT content, content_tokens, metadata::text AS metadata_text,
                  pii_detected, pii_redacted
           FROM ibex_core.memories WHERE id=:id AND org_id=:org""",
        {"id": memory_id, "org": org_id},
    )
    row = rows[0]
    assert content not in row.content
    assert row.content == "[forgotten]"
    assert int(row.content_tokens) == 0
    assert row.metadata_text == "{}"
    assert row.pii_detected is False
    assert row.pii_redacted is False

    labels = await _scalar(
        factory,
        org_id,
        "SELECT count(*) FROM ibex_core.memory_labels WHERE memory_id=:id AND org_id=:org",
        {"id": memory_id, "org": org_id},
    )
    assert labels == 0
    ledger = await _rows(
        factory,
        org_id,
        "SELECT dedupe_key, encode(response_payload, 'escape') AS payload"
        " FROM ibex_core.idempotency_ledger"
        " WHERE organization_id = :org AND dedupe_key = 'forget-erasure'",
        {"org": org_id},
    )
    assert len(ledger) == 1, "the create's idempotency row must survive the scrub"
    assert content not in ledger[0].payload, "the idempotent response still holds the content"
    assert '"erased":true' in ledger[0].payload.replace(" ", "")

    untouched = await _rows(
        factory,
        org_id,
        "SELECT encode(response_payload, 'escape') AS payload"
        " FROM ibex_core.idempotency_ledger"
        " WHERE organization_id = :org AND dedupe_key = 'other-create'",
        {"org": org_id},
    )
    assert len(untouched) == 1, "another create's ledger row must not be scrubbed"
    assert "other create content" in untouched[0].payload


@pytest.mark.asyncio
async def test_forget_erases_content_and_child_labels(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    """P0-08: forget is erasure, not only a visibility tombstone."""
    content = "sentinel-erasure-7f3a91 unforgettable"
    org_id, agent_id, memory_id, _query, _store = await _seed_memory_with_embedding(
        session_factory, settings, content=content, hotspot=12
    )
    await _execute_sql(
        session_factory,
        org_id,
        "INSERT INTO ibex_core.memory_labels (memory_id, org_id, label)"
        " VALUES (:id, :org, 'factual')",
        {"id": memory_id, "org": org_id},
    )
    await _seed_finalized_create(
        session_factory,
        org_id=org_id,
        agent_id=agent_id,
        created=(memory_id, content),
    )
    await _seed_near_duplicate(
        session_factory, org_id=org_id, agent_id=agent_id, forgotten_id=memory_id
    )

    from app.routers.memories import forget_memory

    token = SimpleNamespace(org_id=org_id, agent_id=agent_id)
    await forget_memory(
        memory_id,
        ForgetMemoryRequest(expected_revision=1),
        token,
        session_factory,
        None,
    )

    await _assert_content_erased(
        session_factory, org_id=org_id, memory_id=memory_id, content=content
    )
    assert await _read_outbox(
        session_factory, org_id=org_id, memory_id=memory_id
    ) == [(2, "forgotten")]


@pytest.mark.asyncio
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

    with pytest.raises(LegalHoldActiveError):
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

    rows = await _rows(
        session_factory,
        org_id,
        "SELECT content, tombstoned FROM ibex_core.memories WHERE id=:id AND org_id=:org",
        {"id": memory_id, "org": org_id},
    )
    assert rows[0].content == content
    assert rows[0].tombstoned is False
