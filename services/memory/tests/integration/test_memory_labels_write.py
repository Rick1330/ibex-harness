"""Integration tests for multi-label memory write path (milestone 3.C.4)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.main import create_app
from app.permissions import MEMORY_WRITE
from app.write.labels import MemoryLabelInput
from app.write.models import CreateMemoryCommand, WriteOutcomeKind
from tests.integration.conftest import seed_org_agent_memory, with_service_org
from tests.integration.http_pii_fixtures import HTTP_NOVEL_WRITE_CONTENT
from tests.integration.write_orchestrator_support import (
    EmbedProbe,
    OrchestratorTestDeps,
    QuarantinePii,
    build_orchestrator,
    ensure_pii_ready,
)

pytestmark = pytest.mark.integration

TOKEN = "test-memory-labels-token"


@dataclass(frozen=True, slots=True)
class LabelRow:
    label: str
    confidence: float


async def _with_org_rls(session: AsyncSession, org_id: UUID) -> None:
    await session.execute(
        text("SET LOCAL ROLE ibex_app"),
    )  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    await session.execute(
        text("SELECT set_config('app.is_service_account', 'false', true)"),
    )  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    await session.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(org_id)},
    )  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text


async def _fetch_memory_labels(
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id: UUID,
    memory_id: UUID,
) -> list[LabelRow]:
    async with factory() as session:
        await with_service_org(session, org_id)
        rows = (
            await session.execute(
                text(
                    """
                    SELECT label, confidence::float8 AS confidence
                    FROM ibex_core.memory_labels
                    WHERE memory_id = :memory_id AND org_id = :org_id
                    ORDER BY label
                    """
                ),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                {"memory_id": str(memory_id), "org_id": str(org_id)},
            )
        ).all()
    return [LabelRow(label=str(row.label), confidence=float(row.confidence)) for row in rows]


async def _fetch_memory_category(
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id: UUID,
    memory_id: UUID,
) -> str:
    async with factory() as session:
        await with_service_org(session, org_id)
        row = (
            await session.execute(
                text(
                    """
                    SELECT category FROM ibex_core.memories
                    WHERE id = :memory_id AND org_id = :org_id
                    """
                ),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                {"memory_id": str(memory_id), "org_id": str(org_id)},
            )
        ).one()
    return str(row.category)


async def _count_rows(
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id: UUID,
    memory_id: UUID | None = None,
) -> tuple[int, int]:
    async with factory() as session:
        await with_service_org(session, org_id)
        mem_params: dict[str, str] = {"org_id": str(org_id)}
        label_params: dict[str, str] = {"org_id": str(org_id)}
        mem_sql = "SELECT COUNT(*) FROM ibex_core.memories WHERE org_id = :org_id"
        label_sql = "SELECT COUNT(*) FROM ibex_core.memory_labels WHERE org_id = :org_id"
        if memory_id is not None:
            mem_sql += " AND id = :memory_id"
            label_sql += " AND memory_id = :memory_id"
            mem_params["memory_id"] = str(memory_id)
            label_params["memory_id"] = str(memory_id)
        mem_count = int(
            (await session.execute(text(mem_sql), mem_params)).scalar_one()
        )
        label_count = int(
            (await session.execute(text(label_sql), label_params)).scalar_one()
        )
    return mem_count, label_count


@pytest.mark.asyncio
async def test_orchestrator_writes_multiple_labels_and_syncs_category(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> None:
    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content="seed for multi-label"
    )
    orch = build_orchestrator(OrchestratorTestDeps(session_factory, settings, store))
    await ensure_pii_ready(orch)
    outcome = await orch.create(
        CreateMemoryCommand(
            org_id=org_id,
            agent_id=agent_id,
            content="User prefers concise summaries for technical docs",
            labels=(
                MemoryLabelInput(label="preference", confidence=0.9),
                MemoryLabelInput(label="factual", confidence=0.7),
            ),
        )
    )
    assert outcome.kind == WriteOutcomeKind.CREATED
    labels = await _fetch_memory_labels(
        session_factory, org_id=org_id, memory_id=outcome.memory.id
    )
    assert len(labels) == 2
    category = await _fetch_memory_category(
        session_factory, org_id=org_id, memory_id=outcome.memory.id
    )
    assert category == "preference"
    assert outcome.memory.category == "preference"


@pytest.mark.asyncio
async def test_orchestrator_legacy_single_label_from_scalar(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> None:
    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content="seed for legacy label"
    )
    orch = build_orchestrator(OrchestratorTestDeps(session_factory, settings, store))
    await ensure_pii_ready(orch)
    outcome = await orch.create(
        CreateMemoryCommand(
            org_id=org_id,
            agent_id=agent_id,
            content="Weekly planning happens on Monday mornings",
            category="episodic",
            confidence=0.82,
        )
    )
    labels = await _fetch_memory_labels(
        session_factory, org_id=org_id, memory_id=outcome.memory.id
    )
    assert len(labels) == 1
    assert labels[0].label == "episodic"
    assert labels[0].confidence == pytest.approx(0.82)
    assert outcome.memory.category == "episodic"


@pytest.mark.asyncio
async def test_orchestrator_confidence_tie_break_label_asc(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> None:
    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content="seed for tie break"
    )
    orch = build_orchestrator(OrchestratorTestDeps(session_factory, settings, store))
    await ensure_pii_ready(orch)
    outcome = await orch.create(
        CreateMemoryCommand(
            org_id=org_id,
            agent_id=agent_id,
            content="Team standups follow a fixed agenda template",
            labels=(
                MemoryLabelInput(label="factual", confidence=0.8),
                MemoryLabelInput(label="behavioral", confidence=0.8),
            ),
        )
    )
    category = await _fetch_memory_category(
        session_factory, org_id=org_id, memory_id=outcome.memory.id
    )
    assert category == "behavioral"
    assert outcome.memory.category == "behavioral"


@pytest.mark.asyncio
async def test_orchestrator_quarantine_path_inserts_labels(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> None:
    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content="seed for quarantine labels"
    )
    deps = OrchestratorTestDeps(session_factory, settings, store, pii=QuarantinePii())
    orch = build_orchestrator(deps)
    await ensure_pii_ready(orch)
    outcome = await orch.create(
        CreateMemoryCommand(
            org_id=org_id,
            agent_id=agent_id,
            content="Contact Jordan",
            labels=(MemoryLabelInput(label="factual", confidence=0.9),),
        )
    )
    assert outcome.kind == WriteOutcomeKind.QUARANTINED
    labels = await _fetch_memory_labels(
        session_factory, org_id=org_id, memory_id=outcome.memory.id
    )
    assert len(labels) == 1


@pytest.mark.asyncio
async def test_memory_labels_rls_cross_org_isolation(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> None:
    org_a, agent_a, _ = await seed_org_agent_memory(session_factory, content="org a seed")
    org_b, _agent_b, _ = await seed_org_agent_memory(session_factory, content="org b seed")
    orch = build_orchestrator(OrchestratorTestDeps(session_factory, settings, store))
    await ensure_pii_ready(orch)
    outcome_a = await orch.create(
        CreateMemoryCommand(
            org_id=org_a,
            agent_id=agent_a,
            content="Org A confidential preference",
            labels=(MemoryLabelInput(label="preference", confidence=0.9),),
        )
    )
    async with session_factory() as session, session.begin():
        await _with_org_rls(session, org_b)
        count = (
            await session.execute(
                text(
                    """
                    SELECT COUNT(*) FROM ibex_core.memory_labels
                    WHERE memory_id = :memory_id
                    """
                ),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                {"memory_id": str(outcome_a.memory.id)},
            )
        ).scalar_one()
    assert int(count) == 0


@pytest.mark.asyncio
async def test_memory_labels_cascade_delete(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> None:
    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content="seed for cascade"
    )
    orch = build_orchestrator(OrchestratorTestDeps(session_factory, settings, store))
    await ensure_pii_ready(orch)
    outcome = await orch.create(
        CreateMemoryCommand(
            org_id=org_id,
            agent_id=agent_id,
            content="Temporary note for cascade proof",
            labels=(
                MemoryLabelInput(label="factual", confidence=0.8),
                MemoryLabelInput(label="episodic", confidence=0.6),
            ),
        )
    )
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_id)
        await session.execute(
            text(
                "DELETE FROM ibex_core.memories WHERE id = :id AND org_id = :org_id"
            ),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            {"id": str(outcome.memory.id), "org_id": str(org_id)},
        )
    mem_count, label_count = await _count_rows(
        session_factory, org_id=org_id, memory_id=outcome.memory.id
    )
    assert mem_count == 0
    assert label_count == 0


@pytest.mark.asyncio
async def test_http_post_multi_label(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> None:
    probe = EmbedProbe()
    orch = build_orchestrator(
        OrchestratorTestDeps(session_factory, settings, store, embed=probe)
    )
    await ensure_pii_ready(orch)
    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content="http multi-label seed"
    )
    validator = StaticTokenValidator(
        {TOKEN: ValidateResult(org_id=org_id, permissions=MEMORY_WRITE, agent_id=agent_id)}
    )
    app = create_app(settings=settings, validator=validator)
    async with app.router.lifespan_context(app):
        app.state.memory.write_orchestrator = orch
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/memories",
                headers={"Authorization": f"Bearer {TOKEN}"},
                json={
                    "agent_id": str(agent_id),
                    "content": HTTP_NOVEL_WRITE_CONTENT,
                    "labels": [
                        {"label": "procedural", "confidence": 0.85},
                        {"label": "factual", "confidence": 0.7},
                    ],
                },
            )
    assert response.status_code == 201
    memory_id = UUID(response.json()["data"]["id"])
    assert response.json()["data"]["category"] == "procedural"
    labels = await _fetch_memory_labels(
        session_factory, org_id=org_id, memory_id=memory_id
    )
    assert len(labels) == 2


@pytest.mark.asyncio
async def test_http_post_legacy_without_labels(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> None:
    probe = EmbedProbe()
    orch = build_orchestrator(
        OrchestratorTestDeps(session_factory, settings, store, embed=probe)
    )
    await ensure_pii_ready(orch)
    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content="http legacy label seed"
    )
    validator = StaticTokenValidator(
        {TOKEN: ValidateResult(org_id=org_id, permissions=MEMORY_WRITE, agent_id=agent_id)}
    )
    app = create_app(settings=settings, validator=validator)
    async with app.router.lifespan_context(app):
        app.state.memory.write_orchestrator = orch
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/memories",
                headers={"Authorization": f"Bearer {TOKEN}"},
                json={
                    "agent_id": str(agent_id),
                    "content": "Legacy scalar category write path",
                    "category": "preference",
                    "confidence": 0.88,
                },
            )
    assert response.status_code == 201
    memory_id = UUID(response.json()["data"]["id"])
    labels = await _fetch_memory_labels(
        session_factory, org_id=org_id, memory_id=memory_id
    )
    assert len(labels) == 1
    assert labels[0].label == "preference"


@pytest.mark.asyncio
async def test_orchestrator_label_insert_failure_rolls_back_memory(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> None:
    from unittest.mock import AsyncMock, patch

    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content="rollback seed"
    )
    orch = build_orchestrator(OrchestratorTestDeps(session_factory, settings, store))
    await ensure_pii_ready(orch)

    before_mem, before_labels = await _count_rows(session_factory, org_id=org_id)
    with (
        patch(
            "app.write.orchestrator.insert_labels_session",
            AsyncMock(side_effect=RuntimeError("label insert failed")),
        ),
        pytest.raises(RuntimeError, match="label insert failed"),
    ):
        await orch.create(
            CreateMemoryCommand(
                org_id=org_id,
                agent_id=agent_id,
                content=f"rollback probe {uuid4().hex}",
            )
        )
    after_mem, after_labels = await _count_rows(session_factory, org_id=org_id)
    assert after_mem == before_mem
    assert after_labels == before_labels
