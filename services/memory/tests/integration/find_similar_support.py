"""Shared helpers for find_similar integration tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.main import create_app
from app.permissions import MEMORY_READ
from app.read.repository import MemoryReadRepository
from app.vectorstore.base import UpsertRequest
from app.vectorstore.pgvector_store import PgVectorStore
from tests.integration.conftest import seed_org_agent_memory, with_service_org, zero_embedding

SEARCH_HTTP_TOKEN = "test-memory-search-token"
PLAN_SEED_ROWS = 10_000
PLAN_GIN_QUERY_MARKER = "zin-gate-unique-fts-marker"


@dataclass(frozen=True, slots=True)
class SeededAgent:
    org_id: UUID
    agent_id: UUID


@dataclass(frozen=True, slots=True)
class InsertActiveMemoryParams:
    org_id: UUID
    agent_id: UUID
    content: str
    confidence: float = 0.85
    status: str = "active"


@dataclass(frozen=True, slots=True)
class SeedAgentMemoriesParams:
    count: int
    content_prefix: str
    hotspot: int = 0


@dataclass(frozen=True, slots=True)
class PlanSeed:
    seeded: SeededAgent
    query_vec: list[float]
    gin_query_text: str


class _StubEmbed:
    async def embed(self, texts: list[str], org_id: UUID) -> object:
        from types import SimpleNamespace

        return SimpleNamespace(
            vectors=[zero_embedding(hotspot=3) for _ in texts],
            model_id="test",
            dimensions=1024,
            backend="stub",
        )

    async def aclose(self) -> None:
        return None


async def insert_active_memory(
    session_factory: async_sessionmaker[AsyncSession],
    params: InsertActiveMemoryParams,
) -> UUID:
    memory_id = uuid4()
    async with session_factory() as session, session.begin():
        await with_service_org(session, params.org_id)
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                """
                INSERT INTO ibex_core.memories (
                    id, org_id, agent_id, content, content_hash, content_tokens,
                    confidence, status
                ) VALUES (
                    :id, :org_id, :agent_id, :content, :hash, :tokens,
                    :confidence, :status
                )
                """
            ),
            {
                "id": str(memory_id),
                "org_id": str(params.org_id),
                "agent_id": str(params.agent_id),
                "content": params.content,
                "hash": f"hash-{memory_id.hex}",
                "tokens": max(1, len(params.content.split())),
                "confidence": params.confidence,
                "status": params.status,
            },
        )
    return memory_id


async def upsert_embedding(
    store: PgVectorStore,
    *,
    org_id: UUID,
    memory_id: UUID,
    hotspot: int,
) -> list[float]:
    embedding = zero_embedding(hotspot=hotspot)
    await store.upsert(
        UpsertRequest(
            memory_id=memory_id,
            org_id=org_id,
            embedding=embedding,
            embedding_model="test",
        )
    )
    return embedding


async def seed_agent_with_memories(
    session_factory: async_sessionmaker[AsyncSession],
    store: PgVectorStore,
    params: SeedAgentMemoriesParams,
) -> tuple[SeededAgent, list[UUID], list[float]]:
    org_id, agent_id, first_id = await seed_org_agent_memory(
        session_factory, content=f"{params.content_prefix} seed"
    )
    memory_ids = [first_id]
    query_vec = await upsert_embedding(
        store, org_id=org_id, memory_id=first_id, hotspot=params.hotspot
    )
    for index in range(1, params.count):
        memory_id = await insert_active_memory(
            session_factory,
            InsertActiveMemoryParams(
                org_id=org_id,
                agent_id=agent_id,
                content=f"{params.content_prefix} memory {index} preference dark mode",
            ),
        )
        await upsert_embedding(store, org_id=org_id, memory_id=memory_id, hotspot=params.hotspot)
        memory_ids.append(memory_id)
    return SeededAgent(org_id=org_id, agent_id=agent_id), memory_ids, query_vec


async def bulk_seed_for_plans(
    session_factory: async_sessionmaker[AsyncSession],
    store: PgVectorStore,
) -> PlanSeed:
    async with session_factory() as session, session.begin():
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.is_service_account', 'true', true)"
            )
        )
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "TRUNCATE ibex_core.memories CASCADE"
            )
        )
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT pg_stat_reset()"
            )
        )
    seeded, _, query_vec = await seed_agent_with_memories(
        session_factory,
        store,
        SeedAgentMemoriesParams(
            count=PLAN_SEED_ROWS,
            content_prefix="plan gate",
            hotspot=3,
        ),
    )
    for index in range(5):
        await insert_active_memory(
            session_factory,
            InsertActiveMemoryParams(
                org_id=seeded.org_id,
                agent_id=seeded.agent_id,
                content=f"{PLAN_GIN_QUERY_MARKER} selective fts plan gate memory {index}",
            ),
        )
    async with session_factory() as session, session.begin():
        await with_service_org(session, seeded.org_id)
        await session.execute(
            text("ANALYZE ibex_core.memories")  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        )
    return PlanSeed(
        seeded=seeded,
        query_vec=query_vec,
        gin_query_text=PLAN_GIN_QUERY_MARKER,
    )


def build_read_repository(
    session_factory: async_sessionmaker[AsyncSession],
    store: PgVectorStore,
    settings: Settings,
) -> MemoryReadRepository:
    return MemoryReadRepository(session_factory, store, settings)


@asynccontextmanager
async def search_http_client(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: PgVectorStore,
    *,
    org_id: UUID,
) -> AsyncIterator[AsyncClient]:
    search_settings = settings.model_copy(
        update={"embedding_api_token": SecretStr("test-embed-token")},
    )
    validator = StaticTokenValidator(
        {
            SEARCH_HTTP_TOKEN: ValidateResult(
                org_id=org_id,
                permissions=MEMORY_READ,
            )
        }
    )
    app = create_app(settings=search_settings, validator=validator)
    async with app.router.lifespan_context(app):
        app.state.memory.embedding_client = _StubEmbed()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client
