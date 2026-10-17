"""Provisional GAP-007 lifecycle fence integration tests (real PostgreSQL required)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.conflict.persist import apply_supersession_session
from app.conflict.types import SupersedeApply
from app.exceptions import StaleLifecycleError
from app.lifecycle import forget_memory_session, require_extraction_session
from app.schemas.memories import ForgetMemoryRequest
from app.vectorstore.base import SearchMode, SearchRequest, UpsertRequest
from app.vectorstore.pgvector_store import PgVectorStore
from tests.integration.conftest import seed_org_agent_memory, with_service_org, zero_embedding

pytestmark = pytest.mark.integration


async def _read_lifecycle(
    factory: async_sessionmaker[AsyncSession], *, org_id, memory_id
) -> tuple[int, bool, str, object]:
    async with factory() as session, session.begin():
        await with_service_org(session, org_id)
        row = (
            await session.execute(
                text(
                    """SELECT lifecycle_revision, tombstoned, status, embedding
                       FROM ibex_core.memories WHERE id=:id AND org_id=:org"""
                ),
                {"id": str(memory_id), "org": str(org_id)},
            )
        ).one()
    return int(row.lifecycle_revision), bool(row.tombstoned), str(row.status), row.embedding


async def test_forget_http_scope_revision_and_tombstone_vector_fence(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    org_id, agent_id, memory_id = await seed_org_agent_memory(
        session_factory, content="forget lifecycle integration fixture"
    )
    query = zero_embedding(hotspot=11)
    store = PgVectorStore(session_factory, settings)
    await store.upsert(
        UpsertRequest(
            memory_id=memory_id,
            org_id=org_id,
            embedding=query,
            embedding_model="test",
            expected_revision=1,
        )
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

    from fastapi import HTTPException

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
    with pytest.raises(LookupError):
        await store.delete(memory_id=memory_id, org_id=org_id, expected_revision=2)
    with pytest.raises(LookupError):
        await store.upsert(
            UpsertRequest(
                memory_id=memory_id,
                org_id=org_id,
                embedding=query,
                embedding_model="test",
                expected_revision=1,
            )
        )
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

    async with session_factory() as session, session.begin():
        await with_service_org(session, org_id)
        events = (
            await session.execute(
                text(
                    """SELECT revision, event_type FROM ibex_core.memory_lifecycle_outbox
                       WHERE org_id=:org AND memory_id=:id"""
                ),
                {"org": str(org_id), "id": str(memory_id)},
            )
        ).all()
    assert [(int(row.revision), row.event_type) for row in events] == [(2, "forgotten")]


async def test_forget_outbox_failure_rolls_back_tombstone(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_id, agent_id, memory_id = await seed_org_agent_memory(
        session_factory, content="outbox atomic rollback fixture"
    )
    # Force the exact revision's unique key to conflict after the mutation executes.
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_id)
        await session.execute(
            text(
                """INSERT INTO ibex_core.memory_lifecycle_outbox
                   (org_id, memory_id, revision, event_type)
                   VALUES (:org, :id, 2, 'forgotten')"""
            ),
            {"org": str(org_id), "id": str(memory_id)},
        )
    with pytest.raises(IntegrityError):
        async with session_factory() as session, session.begin():
            await forget_memory_session(
                session,
                org_id=org_id,
                agent_id=agent_id,
                memory_id=memory_id,
                expected_revision=1,
            )
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
    with pytest.raises(StaleLifecycleError):
        async with session_factory() as session, session.begin():
            await forget_memory_session(
                session,
                org_id=org_id,
                agent_id=agent_id,
                memory_id=memory_id,
                expected_revision=2,
            )
    revision, tombstoned, status, _ = await _read_lifecycle(
        session_factory, org_id=org_id, memory_id=memory_id
    )
    assert (revision, tombstoned, status) == (1, False, "active")
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_id)
        count = await session.scalar(
            text(
                "SELECT COUNT(*) FROM ibex_core.memory_lifecycle_outbox "
                "WHERE org_id=:org AND memory_id=:id"
            ),
            {"org": str(org_id), "id": str(memory_id)},
        )
    assert count == 0


async def test_stale_extraction_session_revision_fails_before_memory_insert(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content="extraction fence parent fixture"
    )
    session_id = uuid4()
    content = f"stale extraction must not persist {uuid4()}"
    content_hash = f"stale-{uuid4()}"
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_id)
        await session.execute(
            text(
                """INSERT INTO ibex_core.sessions
                   (id, org_id, agent_id, status, model, provider)
                   VALUES (:id, :org, :agent, 'completed', 'test', 'test')"""
            ),
            {"id": str(session_id), "org": str(org_id), "agent": str(agent_id)},
        )
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_id)
        await session.execute(
            text("UPDATE ibex_core.sessions SET status='abandoned' WHERE id=:id AND org_id=:org"),
            {"id": str(session_id), "org": str(org_id)},
        )
    with pytest.raises(StaleLifecycleError):
        async with session_factory() as session, session.begin():
            await require_extraction_session(
                session,
                org_id=org_id,
                agent_id=agent_id,
                session_id=session_id,
                expected_revision=1,
            )
            await session.execute(
                text(
                    """INSERT INTO ibex_core.memories
                       (org_id, agent_id, content, content_hash, content_tokens)
                       VALUES (:org, :agent, :content, :hash, 4)"""
                ),
                {
                    "org": str(org_id),
                    "agent": str(agent_id),
                    "content": content,
                    "hash": content_hash,
                },
            )
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_id)
        count = await session.scalar(
            text(
                "SELECT COUNT(*) FROM ibex_core.memories WHERE org_id=:org AND content_hash=:hash"
            ),
            {"org": str(org_id), "hash": content_hash},
        )
    assert count == 0


async def test_expires_at_hides_normal_retrieval_but_tombstone_wins_historical_mode(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    org_id, agent_id, memory_id = await seed_org_agent_memory(
        session_factory, content="soft expiry integration fixture"
    )
    query = zero_embedding(hotspot=17)
    store = PgVectorStore(session_factory, settings)
    await store.upsert(
        UpsertRequest(
            memory_id=memory_id,
            org_id=org_id,
            embedding=query,
            embedding_model="test",
            expected_revision=1,
        )
    )
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_id)
        await session.execute(
            text("UPDATE ibex_core.memories SET expires_at=:expiry WHERE id=:id AND org_id=:org"),
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
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_id)
        await session.execute(
            text(
                """UPDATE ibex_core.memories
                   SET status='deleted', deleted_at=NOW(), tombstoned=TRUE
                   WHERE id=:id AND org_id=:org"""
            ),
            {"id": str(memory_id), "org": str(org_id)},
        )
    assert (
        await store.search(SearchRequest(**common, mode=SearchMode.HISTORICAL_CONFLICT_CANDIDATES))
        == []
    )


async def test_concurrent_supersede_vs_forget_has_one_typed_loser(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    import asyncio

    org_id, agent_id, target_id = await seed_org_agent_memory(
        session_factory, content="concurrent lifecycle target"
    )
    new_memory_id = uuid4()
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_id)
        await session.execute(
            text(
                """INSERT INTO ibex_core.memories
                   (id, org_id, agent_id, content, content_hash, content_tokens)
                   VALUES (:id, :org, :agent, :content, :hash, 4)"""
            ),
            {
                "id": str(new_memory_id),
                "org": str(org_id),
                "agent": str(agent_id),
                "content": "concurrent lifecycle replacement",
                "hash": f"race-{new_memory_id}",
            },
        )

    barrier = asyncio.Barrier(3)

    async def _forget():
        await barrier.wait()
        async with session_factory() as session, session.begin():
            return await forget_memory_session(
                session, org_id=org_id, agent_id=agent_id, memory_id=target_id, expected_revision=1
            )

    async def _supersede():
        await barrier.wait()
        async with session_factory() as session, session.begin():
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

    forget_task = asyncio.create_task(_forget())
    supersede_task = asyncio.create_task(_supersede())
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
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_id)
        events = (
            await session.execute(
                text(
                    "SELECT revision, event_type FROM ibex_core.memory_lifecycle_outbox WHERE org_id=:org AND memory_id=:id"
                ),
                {"org": str(org_id), "id": str(target_id)},
            )
        ).all()
    assert [(int(row.revision), row.event_type) for row in events] == [
        (2, "forgotten" if tombstoned else "superseded")
    ]
