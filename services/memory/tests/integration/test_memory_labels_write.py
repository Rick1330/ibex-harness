"""Integration tests for multi-label memory write path (milestone 3.C.4)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.write.labels import MemoryLabelInput
from app.write.models import CreateMemoryCommand, WriteOutcomeKind
from tests.integration.conftest import seed_org_agent_memory, with_service_org
from tests.integration.http_pii_fixtures import HTTP_NOVEL_WRITE_CONTENT
from tests.integration.memory_labels_write_support import (
    LABEL_HTTP_TOKEN,
    HttpLabelCase,
    OrchestratorLabelCase,
    count_label_rows,
    fetch_memory_category,
    fetch_memory_labels,
    labels_http_client,
    run_orchestrator_label_write,
    with_org_rls,
)
from tests.integration.write_orchestrator_support import (
    OrchestratorTestDeps,
    build_orchestrator,
    ensure_pii_ready,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        OrchestratorLabelCase(
            seed_content="seed for multi-label",
            content="User prefers concise summaries for technical docs",
            labels=(
                MemoryLabelInput(label="preference", confidence=0.9),
                MemoryLabelInput(label="factual", confidence=0.7),
            ),
            expected_category="preference",
            expected_label_count=2,
        ),
        OrchestratorLabelCase(
            seed_content="seed for legacy label",
            content="Weekly planning happens on Monday mornings",
            category="episodic",
            confidence=0.82,
            expected_category="episodic",
            expected_label_count=1,
            expected_label="episodic",
            expected_label_confidence=0.82,
        ),
        OrchestratorLabelCase(
            seed_content="seed for tie break",
            content="Team standups follow a fixed agenda template",
            labels=(
                MemoryLabelInput(label="factual", confidence=0.8),
                MemoryLabelInput(label="behavioral", confidence=0.8),
            ),
            expected_category="behavioral",
        ),
        OrchestratorLabelCase(
            seed_content="seed for quarantine labels",
            content="Contact Jordan",
            labels=(MemoryLabelInput(label="factual", confidence=0.9),),
            expected_kind=WriteOutcomeKind.QUARANTINED,
            expected_label_count=1,
            quarantine=True,
        ),
    ],
)
async def test_orchestrator_label_write_paths(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
    case: OrchestratorLabelCase,
) -> None:
    outcome, org_id, _agent_id = await run_orchestrator_label_write(
        session_factory, settings, store, case
    )
    assert outcome.kind == case.expected_kind
    if case.expected_label_count is not None:
        labels = await fetch_memory_labels(
            session_factory, org_id=org_id, memory_id=outcome.memory.id
        )
        assert len(labels) == case.expected_label_count
        if case.expected_label is not None:
            assert labels[0].label == case.expected_label
        if case.expected_label_confidence is not None:
            assert labels[0].confidence == pytest.approx(case.expected_label_confidence)
    if case.expected_category is not None:
        category = await fetch_memory_category(
            session_factory, org_id=org_id, memory_id=outcome.memory.id
        )
        assert category == case.expected_category
        assert outcome.memory.category == case.expected_category


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
        await with_org_rls(session, org_b)
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
    outcome, org_id, _agent_id = await run_orchestrator_label_write(
        session_factory,
        settings,
        store,
        OrchestratorLabelCase(
            seed_content="seed for cascade",
            content="Temporary note for cascade proof",
            labels=(
                MemoryLabelInput(label="factual", confidence=0.8),
                MemoryLabelInput(label="episodic", confidence=0.6),
            ),
            expected_label_count=2,
        ),
    )
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_id)
        await session.execute(
            text(
                "DELETE FROM ibex_core.memories WHERE id = :id AND org_id = :org_id"
            ),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            {"id": str(outcome.memory.id), "org_id": str(org_id)},
        )
    mem_count, label_count = await count_label_rows(
        session_factory, org_id=org_id, memory_id=outcome.memory.id
    )
    assert mem_count == 0
    assert label_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        HttpLabelCase(
            seed_content="http multi-label seed",
            payload={
                "content": HTTP_NOVEL_WRITE_CONTENT,
                "labels": [
                    {"label": "procedural", "confidence": 0.85},
                    {"label": "factual", "confidence": 0.7},
                ],
            },
            expected_category="procedural",
            expected_label_count=2,
        ),
        HttpLabelCase(
            seed_content="http legacy label seed",
            payload={
                "content": "Legacy scalar category write path",
                "category": "preference",
                "confidence": 0.88,
            },
            expected_category="preference",
            expected_label_count=1,
            expected_primary_label="preference",
        ),
    ],
)
async def test_http_post_labels(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
    case: HttpLabelCase,
) -> None:
    async with labels_http_client(
        session_factory, settings, store, seed_content=case.seed_content
    ) as (client, org_id, agent_id):
        response = await client.post(
            "/v1/memories",
            headers={"Authorization": f"Bearer {LABEL_HTTP_TOKEN}"},
            json={"agent_id": str(agent_id), **case.payload},
        )
    assert response.status_code == 201
    memory_id = response.json()["data"]["id"]
    if case.expected_category is not None:
        assert response.json()["data"]["category"] == case.expected_category
    labels = await fetch_memory_labels(
        session_factory, org_id=org_id, memory_id=memory_id
    )
    assert len(labels) == case.expected_label_count
    if case.expected_primary_label is not None:
        assert labels[0].label == case.expected_primary_label


@pytest.mark.asyncio
async def test_orchestrator_label_insert_failure_rolls_back_memory(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> None:
    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content="rollback seed"
    )
    orch = build_orchestrator(OrchestratorTestDeps(session_factory, settings, store))
    await ensure_pii_ready(orch)

    before_mem, before_labels = await count_label_rows(session_factory, org_id=org_id)
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
    after_mem, after_labels = await count_label_rows(session_factory, org_id=org_id)
    assert after_mem == before_mem
    assert after_labels == before_labels
