"""Integration tests for memory feedback ledger + ranking (3.5.E.3 option a)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.feedback.models import ApplyFeedbackCommand, FeedbackKind
from app.feedback.service import MemoryFeedbackService
from app.main import create_app
from app.permissions import MEMORY_READ, MEMORY_WRITE
from app.vectorstore.pgvector_store import PgVectorStore
from tests.integration.conftest import with_service_org
from tests.integration.find_similar_support import (
    InsertScoredMemoryParams,
    insert_scored_memory,
    upsert_embedding,
)
from tests.integration.security.seed import (
    OrgSeed,
    seed_org_agent,
    seed_second_agent_same_org,
)

pytestmark = pytest.mark.integration

OWNER_TOKEN = "feedback-owner"
AGENT_B_TOKEN = "feedback-agent-b"
AGENT_C_TOKEN = "feedback-agent-c"
SEARCH_TOKEN = "feedback-search"


class _StubEmbed:
    async def embed(self, texts: list[str], *, org_id: UUID) -> object:
        from types import SimpleNamespace

        from tests.integration.conftest import zero_embedding

        return SimpleNamespace(
            vectors=[zero_embedding(hotspot=3) for _ in texts],
            model_id="test",
            dimensions=1024,
            backend="stub",
        )

    async def aclose(self) -> None:
        return None


async def _seed_ranked_pair(
    session_factory: async_sessionmaker[AsyncSession],
    store: PgVectorStore,
) -> tuple[OrgSeed, UUID, UUID, UUID]:
    org = await seed_org_agent(
        session_factory,
        slug_prefix="fb-e2e",
        content="feedback boosted dark mode preference memory",
    )
    agent_b = await seed_second_agent_same_org(
        session_factory,
        org_id=org.org_id,
        user_id=org.user_id,
        slug_prefix="fb-e2e",
    )
    agent_c = await seed_second_agent_same_org(
        session_factory,
        org_id=org.org_id,
        user_id=org.user_id,
        slug_prefix="fb-e2e-c",
    )
    control_id = await insert_scored_memory(
        session_factory,
        InsertScoredMemoryParams(
            org_id=org.org_id,
            agent_id=org.agent_id,
            content="control dark mode preference memory default usefulness",
            category="factual",
            valid_from=datetime.now(tz=UTC),
            confidence=0.85,
            usefulness_score=0.50,
        ),
    )
    await upsert_embedding(store, org_id=org.org_id, memory_id=org.memory_id, hotspot=3)
    await upsert_embedding(store, org_id=org.org_id, memory_id=control_id, hotspot=3)
    return org, agent_b, agent_c, control_id


def _e2e_tokens(org: OrgSeed, agent_b: UUID, agent_c: UUID) -> dict[str, ValidateResult]:
    return {
        OWNER_TOKEN: ValidateResult(
            org_id=org.org_id,
            permissions=MEMORY_WRITE | MEMORY_READ,
            agent_id=org.agent_id,
        ),
        AGENT_B_TOKEN: ValidateResult(
            org_id=org.org_id, permissions=MEMORY_WRITE, agent_id=agent_b
        ),
        AGENT_C_TOKEN: ValidateResult(
            org_id=org.org_id, permissions=MEMORY_WRITE, agent_id=agent_c
        ),
        SEARCH_TOKEN: ValidateResult(
            org_id=org.org_id, permissions=MEMORY_READ, agent_id=org.agent_id
        ),
    }


async def _post_three_positives(client: AsyncClient, memory_id: UUID) -> dict:
    last_body: dict = {}
    for token in (OWNER_TOKEN, AGENT_B_TOKEN, AGENT_C_TOKEN):
        response = await client.post(
            f"/v1/memories/{memory_id}/feedback",
            headers={"Authorization": f"Bearer {token}"},
            json={"feedback": "positive"},
        )
        assert response.status_code == 200, response.text
        last_body = response.json()["data"]
    return last_body


async def _assert_db_usefulness(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    org_id: UUID,
    memory_id: UUID,
    expected: float,
) -> None:
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_id)
        row = (
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    "SELECT usefulness_score FROM ibex_core.memories "
                    "WHERE id = :id AND org_id = :org"
                ),
                {"id": str(memory_id), "org": str(org_id)},
            )
        ).one()
    assert float(row.usefulness_score) == pytest.approx(expected)


@pytest.mark.asyncio
async def test_feedback_upsert_replaces_same_agent_vote(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org = await seed_org_agent(
        session_factory, slug_prefix="fb-upsert", content="feedback target memory"
    )
    service = MemoryFeedbackService(session_factory)
    first = await service.apply(
        ApplyFeedbackCommand(
            org_id=org.org_id,
            agent_id=org.agent_id,
            memory_id=org.memory_id,
            feedback=FeedbackKind.POSITIVE,
        )
    )
    assert first.total_positive_feedback == 1
    assert first.total_negative_feedback == 0
    assert first.new_usefulness_score == pytest.approx(0.67)
    second = await service.apply(
        ApplyFeedbackCommand(
            org_id=org.org_id,
            agent_id=org.agent_id,
            memory_id=org.memory_id,
            feedback=FeedbackKind.NEGATIVE,
        )
    )
    assert second.total_positive_feedback == 0
    assert second.total_negative_feedback == 1
    assert second.new_usefulness_score == pytest.approx(0.33)


@pytest.mark.asyncio
async def test_concurrent_feedback_from_distinct_agents(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """FOR UPDATE serializes concurrent votes so both agents are counted."""
    org = await seed_org_agent(
        session_factory, slug_prefix="fb-race", content="concurrent feedback memory"
    )
    agent_b = await seed_second_agent_same_org(
        session_factory,
        org_id=org.org_id,
        user_id=org.user_id,
        slug_prefix="fb-race",
    )
    service = MemoryFeedbackService(session_factory)

    async def _vote(agent_id: UUID) -> object:
        return await service.apply(
            ApplyFeedbackCommand(
                org_id=org.org_id,
                agent_id=agent_id,
                memory_id=org.memory_id,
                feedback=FeedbackKind.POSITIVE,
            )
        )

    first, second = await asyncio.gather(_vote(org.agent_id), _vote(agent_b))
    totals = {first.total_positive_feedback, second.total_positive_feedback}
    assert 2 in totals
    winner = first if first.total_positive_feedback == 2 else second
    assert winner.total_negative_feedback == 0
    assert winner.new_usefulness_score == pytest.approx(0.60)


@pytest.mark.asyncio
async def test_feedback_cross_org_returns_404(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    org_a = await seed_org_agent(
        session_factory, slug_prefix="fb-a", content="org a memory"
    )
    org_b = await seed_org_agent(
        session_factory, slug_prefix="fb-b", content="org b memory"
    )
    validator = StaticTokenValidator(
        {
            OWNER_TOKEN: ValidateResult(
                org_id=org_b.org_id,
                permissions=MEMORY_WRITE,
                agent_id=org_b.agent_id,
            )
        }
    )
    app = create_app(settings=settings, validator=validator)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/v1/memories/{org_a.memory_id}/feedback",
                headers={"Authorization": f"Bearer {OWNER_TOKEN}"},
                json={"feedback": "positive"},
            )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_neutral_does_not_change_pn_counts(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org = await seed_org_agent(
        session_factory, slug_prefix="fb-neutral", content="neutral vote memory"
    )
    service = MemoryFeedbackService(session_factory)
    result = await service.apply(
        ApplyFeedbackCommand(
            org_id=org.org_id,
            agent_id=org.agent_id,
            memory_id=org.memory_id,
            feedback=FeedbackKind.NEUTRAL,
        )
    )
    assert result.total_positive_feedback == 0
    assert result.total_negative_feedback == 0
    assert result.new_usefulness_score == pytest.approx(0.50)


@pytest.mark.asyncio
async def test_e2e_three_agents_positive_raises_rank(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: PgVectorStore,
) -> None:
    """Option (a): three distinct agents each upsert positive once → 0.80, ranks above control."""
    org, agent_b, agent_c, control_id = await _seed_ranked_pair(session_factory, store)
    search_settings = settings.model_copy(
        update={"embedding_api_token": SecretStr("test-embed-token")}
    )
    app = create_app(
        settings=search_settings,
        validator=StaticTokenValidator(_e2e_tokens(org, agent_b, agent_c)),
    )
    async with app.router.lifespan_context(app):
        app.state.memory.embedding_client = _StubEmbed()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            last_body = await _post_three_positives(client, org.memory_id)
            assert last_body["new_usefulness_score"] == pytest.approx(0.80)
            assert last_body["total_positive_feedback"] == 3
            await _assert_db_usefulness(
                session_factory,
                org_id=org.org_id,
                memory_id=org.memory_id,
                expected=0.80,
            )
            search = await client.post(
                "/v1/memories/search",
                headers={"Authorization": f"Bearer {SEARCH_TOKEN}"},
                json={
                    "agent_id": str(org.agent_id),
                    "query": "dark mode preference",
                    "limit": 5,
                    "min_similarity": 0.0,
                },
            )
            assert search.status_code == 200, search.text
            ids = [hit["memory"]["id"] for hit in search.json()["data"]["results"]]
            assert str(org.memory_id) in ids
            assert str(control_id) in ids
            assert ids.index(str(org.memory_id)) < ids.index(str(control_id))
