"""Shared helpers for memory label write integration tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

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
from tests.integration.write_orchestrator_support import (
    EmbedProbe,
    OrchestratorTestDeps,
    QuarantinePii,
    build_orchestrator,
    ensure_pii_ready,
)

LABEL_HTTP_TOKEN = "test-memory-labels-token"


@dataclass(frozen=True, slots=True)
class HttpLabelCase:
    seed_content: str
    payload: Mapping[str, object]
    expected_category: str | None
    expected_label_count: int
    expected_primary_label: str | None = None


@dataclass(frozen=True, slots=True)
class OrchestratorLabelCase:
    seed_content: str
    content: str
    expected_kind: WriteOutcomeKind = WriteOutcomeKind.CREATED
    labels: tuple[MemoryLabelInput, ...] | None = None
    category: str = "factual"
    confidence: float = 0.8
    expected_category: str | None = None
    expected_label_count: int | None = None
    expected_label: str | None = None
    expected_label_confidence: float | None = None
    quarantine: bool = False


@dataclass(frozen=True, slots=True)
class LabelRow:
    label: str
    confidence: float


async def run_orchestrator_label_write(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
    case: OrchestratorLabelCase,
):
    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content=case.seed_content
    )
    pii = QuarantinePii() if case.quarantine else None
    deps = OrchestratorTestDeps(session_factory, settings, store, pii=pii)
    orch = build_orchestrator(deps)
    await ensure_pii_ready(orch)
    command = CreateMemoryCommand(
        org_id=org_id,
        agent_id=agent_id,
        content=case.content,
        category=case.category,
        confidence=case.confidence,
        labels=case.labels or (),
    )
    outcome = await orch.create(command)
    return outcome, org_id, agent_id


@asynccontextmanager
async def labels_http_client(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
    *,
    seed_content: str,
) -> AsyncIterator[tuple[AsyncClient, UUID, UUID]]:
    probe = EmbedProbe()
    orch = build_orchestrator(
        OrchestratorTestDeps(session_factory, settings, store, embed=probe)
    )
    await ensure_pii_ready(orch)
    org_id, agent_id, _ = await seed_org_agent_memory(session_factory, content=seed_content)
    validator = StaticTokenValidator(
        {
            LABEL_HTTP_TOKEN: ValidateResult(
                org_id=org_id, permissions=MEMORY_WRITE, agent_id=agent_id
            )
        }
    )
    app = create_app(settings=settings, validator=validator)
    async with app.router.lifespan_context(app):
        app.state.memory.write_orchestrator = orch
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, org_id, agent_id


async def with_org_rls(session: AsyncSession, org_id: UUID) -> None:
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


async def service_query(
    factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    sql: str,
    params: dict[str, str],
):
    async with factory() as session:
        await with_service_org(session, org_id)
        return await session.execute(
            text(sql),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            params,
        )


async def fetch_memory_labels(
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id: UUID,
    memory_id: UUID,
) -> list[LabelRow]:
    rows = (
        await service_query(
            factory,
            org_id,
            """
            SELECT label, confidence::float8 AS confidence
            FROM ibex_core.memory_labels
            WHERE memory_id = :memory_id AND org_id = :org_id
            ORDER BY label
            """,
            {"memory_id": str(memory_id), "org_id": str(org_id)},
        )
    ).all()
    return [LabelRow(label=str(row.label), confidence=float(row.confidence)) for row in rows]


async def fetch_memory_category(
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id: UUID,
    memory_id: UUID,
) -> str:
    row = (
        await service_query(
            factory,
            org_id,
            """
            SELECT category FROM ibex_core.memories
            WHERE id = :memory_id AND org_id = :org_id
            """,
            {"memory_id": str(memory_id), "org_id": str(org_id)},
        )
    ).one()
    return str(row.category)


async def count_label_rows(
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
        mem_count = int((await session.execute(text(mem_sql), mem_params)).scalar_one())
        label_count = int(
            (await session.execute(text(label_sql), label_params)).scalar_one()
        )
    return mem_count, label_count
