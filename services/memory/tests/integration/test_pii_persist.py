"""Integration: PII flags and quarantined status persist with org_id scoping."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.pii.persist import MemoryPiiUpdate, update_memory_pii_flags
from app.pii.service import PiiService
from app.pipeline import PiiStage, ValidateStage, WriteContext, WritePipeline
from tests.integration.conftest import seed_org_agent_memory

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_pii_flags_persist_after_pipeline(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    raw = "Contact refunds via billing@example.com or +1-212-555-0182"
    org_id, _agent_id, memory_id = await seed_org_agent_memory(
        session_factory, content=raw
    )
    pii = PiiService(settings)
    pipe = WritePipeline([ValidateStage(settings), PiiStage(pii)])
    ctx = await pipe.run(WriteContext(org_id=org_id, content=raw))

    await update_memory_pii_flags(
        session_factory,
        MemoryPiiUpdate(
            org_id=org_id,
            memory_id=memory_id,
            content=ctx.content,
            status=ctx.status,
            pii_detected=ctx.pii_detected,
            pii_redacted=ctx.pii_redacted,
        ),
    )

    async with session_factory() as session:
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.is_service_account', 'true', true)"
            )
        )
        row = (
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    """
                    SELECT content, status, pii_detected, pii_redacted
                    FROM ibex_core.memories
                    WHERE id = :id AND org_id = :org_id
                    """
                ),
                {"id": str(memory_id), "org_id": str(org_id)},
            )
        ).one()

    assert row.pii_detected is True
    assert row.status in {"active", "quarantined"}
    if row.status == "active":
        assert row.pii_redacted is True
        assert "billing@example.com" not in row.content
    else:
        assert row.pii_redacted is False


@pytest.mark.asyncio
async def test_cross_tenant_update_does_not_touch_other_org(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_a, _, mem_a = await seed_org_agent_memory(session_factory, content="a@example.com")
    org_b, _, _mem_b = await seed_org_agent_memory(session_factory, content="b@example.com")

    update = MemoryPiiUpdate(
        org_id=org_b,
        memory_id=mem_a,
        content="[EMAIL_ADDRESS]",
        status="active",
        pii_detected=True,
        pii_redacted=True,
    )
    with pytest.raises(RuntimeError, match="expected 1 row"):
        await update_memory_pii_flags(session_factory, update)

    async with session_factory() as session:
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.is_service_account', 'true', true)"
            )
        )
        content = (
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    "SELECT content FROM ibex_core.memories WHERE id = :id AND org_id = :org"
                ),
                {"id": str(mem_a), "org": str(org_a)},
            )
        ).scalar_one()
    assert content == "a@example.com"
