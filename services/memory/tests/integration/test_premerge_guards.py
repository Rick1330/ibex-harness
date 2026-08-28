"""Verify HTTP PII fixtures and escalation poll index (integration)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.pii.service import PiiService
from tests.integration.http_pii_fixtures import (
    HTTP_BROKEN_REDIS_WRITE_CONTENT,
    HTTP_DUPLICATE_PAYLOAD_CONTENT,
    HTTP_IDEMPOTENT_WRITE_CONTENT,
    HTTP_NOVEL_WRITE_CONTENT,
    HTTP_REDIS_CACHE_CONTENT,
    HTTP_SEED_CONTENT,
)

pytestmark = pytest.mark.integration

# Future worker poll query (see ADR-0057 / GitHub issue for escalation consumer).
WORKER_POLL_SQL = """
SELECT id, new_memory_id, candidate_memory_id, conflict_type, created_at
FROM ibex_core.memory_conflict_escalations
WHERE org_id = :org_id
  AND status = 'pending'
ORDER BY created_at DESC
LIMIT :limit
"""

_INDEX_NAME = "idx_memory_conflict_escalations_org_status_pending"
_INDEXDEF_SQL = """
SELECT indexdef
FROM pg_indexes
WHERE schemaname = 'ibex_core'
  AND indexname = :index_name
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
        ("broken_redis", HTTP_BROKEN_REDIS_WRITE_CONTENT),
    ):
        result = await pii.process_async(content)
        assert not result.pii_detected, f"{label} fixture flagged PII: {content!r}"


@pytest.mark.asyncio
async def test_escalation_pending_poll_uses_partial_index(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Partial index for worker poll exists with org_id + created_at DESC + pending filter."""
    async with session_factory() as session:
        row = (
            await session.execute(
                text(_INDEXDEF_SQL),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                {"index_name": _INDEX_NAME},
            )
        ).one_or_none()
    assert row is not None, f"missing index {_INDEX_NAME}"
    indexdef = str(row.indexdef)
    assert "(org_id, created_at DESC)" in indexdef, indexdef
    assert "status = 'pending'" in indexdef, indexdef
