"""Verify HTTP PII fixtures and escalation poll index (integration)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.pii.service import PiiService
from tests.integration.conftest import with_service_org
from tests.integration.http_pii_fixtures import (
    HTTP_DUPLICATE_PAYLOAD_CONTENT,
    HTTP_IDEMPOTENT_WRITE_CONTENT,
    HTTP_NOVEL_WRITE_CONTENT,
    HTTP_REDIS_CACHE_CONTENT,
    HTTP_SEED_CONTENT,
)

pytestmark = pytest.mark.integration

WORKER_POLL_SQL = """
SELECT id, new_memory_id, candidate_memory_id, conflict_type, created_at
FROM ibex_core.memory_conflict_escalations
WHERE org_id = :org_id
  AND status = 'pending'
ORDER BY created_at DESC
LIMIT :limit
"""


@pytest.mark.asyncio
async def test_http_fixture_strings_presidio_clean(settings: Settings) -> None:
    """Guard: HTTP fixtures must stay PII-clean under the real Presidio pipeline."""
    pii = PiiService(settings)
    await pii.ensure_ready()
    for label, content in (
        ("seed", HTTP_SEED_CONTENT),
        ("novel", HTTP_NOVEL_WRITE_CONTENT),
        ("duplicate", HTTP_DUPLICATE_PAYLOAD_CONTENT),
        ("redis", HTTP_REDIS_CACHE_CONTENT),
        ("idempotent", HTTP_IDEMPOTENT_WRITE_CONTENT),
    ):
        result = await pii.process_async(content)
        assert not result.pii_detected, f"{label} fixture flagged PII: {content!r}"


@pytest.mark.asyncio
async def test_escalation_pending_poll_uses_partial_index(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """EXPLAIN: worker poll query should use idx_memory_conflict_escalations_org_status_pending."""
    org_id = uuid4()
    async with session_factory() as session:
        await with_service_org(session, org_id)
        plan = (
            await session.execute(
                text("EXPLAIN (FORMAT TEXT) " + WORKER_POLL_SQL),
                {"org_id": str(org_id), "limit": 50},
            )
        ).all()
    plan_text = "\n".join(row[0] for row in plan)
    assert "idx_memory_conflict_escalations_org_status_pending" in plan_text, plan_text
