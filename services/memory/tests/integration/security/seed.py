"""Seed helpers for memory security integration tests (m3.E.1)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.conftest import with_service_org

SHARED_ISO_SEARCH_CONTENT = "tenant isolation probe prefers concise technical summaries"
SHARED_ISO_QUERY_TEXT = "concise technical summaries"


def require_postgres_dsn() -> str:
    dsn = os.getenv("POSTGRES_TEST_DSN") or os.getenv("IBEX_MEMORY_DATABASE_URL")
    if not dsn:
        msg = "POSTGRES_TEST_DSN or IBEX_MEMORY_DATABASE_URL required for security integration tests"
        raise RuntimeError(msg)
    return dsn


def require_redis_url() -> str:
    url = os.getenv("REDIS_URL") or os.getenv("IBEX_MEMORY_REDIS_URL")
    if not url:
        pytest.skip("REDIS_URL required for security integration tests")
    return url


@dataclass(frozen=True, slots=True)
class OrgSeed:
    org_id: UUID
    user_id: UUID
    agent_id: UUID
    memory_id: UUID
    slug: str


async def _insert_organization(
    session: AsyncSession,
    *,
    org_id: UUID,
    slug: str,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.organizations (id, name, slug)
            VALUES (:id, :name, :slug)
            """
        ),
        {"id": str(org_id), "name": f"Org {slug}", "slug": slug},
    )


async def _insert_user(
    session: AsyncSession,
    *,
    org_id: UUID,
    user_id: UUID,
    slug: str,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.users (id, org_id, email, name)
            VALUES (:id, :org_id, :email, :name)
            """
        ),
        {
            "id": str(user_id),
            "org_id": str(org_id),
            "email": f"{slug}@example.com",
            "name": "User",
        },
    )


async def _insert_agent(
    session: AsyncSession,
    *,
    org_id: UUID,
    user_id: UUID,
    agent_id: UUID,
    name: str = "Agent",
    slug: str | None = None,
) -> None:
    resolved_slug = slug or f"agent-{agent_id.hex[:8]}"
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.agents (id, org_id, created_by, name, slug)
            VALUES (:id, :org_id, :created_by, :name, :slug)
            """
        ),
        {
            "id": str(agent_id),
            "org_id": str(org_id),
            "created_by": str(user_id),
            "name": name,
            "slug": resolved_slug,
        },
    )


async def _insert_memory(
    session: AsyncSession,
    *,
    org_id: UUID,
    agent_id: UUID,
    memory_id: UUID,
    content: str,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.memories (
                id, org_id, agent_id, content, content_hash, content_tokens
            ) VALUES (
                :id, :org_id, :agent_id, :content, :hash, :tokens
            )
            """
        ),
        {
            "id": str(memory_id),
            "org_id": str(org_id),
            "agent_id": str(agent_id),
            "content": content,
            "hash": f"hash-{memory_id.hex}",
            "tokens": max(1, len(content.split())),
        },
    )


async def seed_org_agent(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    slug_prefix: str,
    content: str,
    agent_id: UUID | None = None,
) -> OrgSeed:
    org_id = uuid4()
    user_id = uuid4()
    resolved_agent_id = agent_id or uuid4()
    memory_id = uuid4()
    slug = f"{slug_prefix}-{org_id.hex[:8]}"
    async with session_factory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.is_service_account', 'true', true)"),
        )
        await with_service_org(session, org_id)
        await _insert_organization(session, org_id=org_id, slug=slug)
        await _insert_user(session, org_id=org_id, user_id=user_id, slug=slug)
        await _insert_agent(
            session,
            org_id=org_id,
            user_id=user_id,
            agent_id=resolved_agent_id,
        )
        await _insert_memory(
            session,
            org_id=org_id,
            agent_id=resolved_agent_id,
            memory_id=memory_id,
            content=content,
        )
    return OrgSeed(
        org_id=org_id,
        user_id=user_id,
        agent_id=resolved_agent_id,
        memory_id=memory_id,
        slug=slug,
    )


async def seed_second_agent_same_org(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    org_id: UUID,
    user_id: UUID,
    slug_prefix: str,
) -> UUID:
    agent_id = uuid4()
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_id)
        await _insert_agent(
            session,
            org_id=org_id,
            user_id=user_id,
            agent_id=agent_id,
            name="Agent B",
            slug=f"{slug_prefix}-b-{agent_id.hex[:8]}",
        )
    return agent_id


@dataclass(frozen=True, slots=True)
class TwoOrgSeed:
    org_a: OrgSeed
    org_b: OrgSeed


async def seed_two_orgs(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    shared_content: str = SHARED_ISO_SEARCH_CONTENT,
) -> TwoOrgSeed:
    org_a = await seed_org_agent(
        session_factory, slug_prefix="iso-org-a", content=shared_content
    )
    org_b = await seed_org_agent(
        session_factory, slug_prefix="iso-org-b", content=shared_content
    )
    return TwoOrgSeed(org_a=org_a, org_b=org_b)
