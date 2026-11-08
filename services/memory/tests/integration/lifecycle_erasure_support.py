"""Fixture helpers for the memory lifecycle/erasure integration tests.

Forget must destroy every copy of a memory's content, so the erasure test needs a
row carrying non-default metadata, PII flags, retrieval state and lifecycle
pointers, plus a feedback vote, relationships and conflict escalations on both
endpoints, and the idempotent create responses that store the body. Seeding and
asserting that in the test module made it the largest file in the suite; it
lives here instead, with one fixture object instead of long argument lists.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from tests.integration.conftest import with_service_org


@asynccontextmanager
async def service_session(factory, org_id):
    """A transaction that sees every tenant (the service-account bypass)."""
    async with factory() as session, session.begin():
        await with_service_org(session, org_id)
        yield session


async def execute_sql(factory, org_id, statement: str, params: dict) -> None:
    """Run one statement in a service-account transaction for ``org_id``."""
    async with service_session(factory, org_id) as session:
        await session.execute(text(statement), params)


async def fetch_scalar(factory, org_id, statement: str, params: dict):
    """Return the first column of the first row, or None."""
    async with service_session(factory, org_id) as session:
        return await session.scalar(text(statement), params)


async def fetch_rows(factory, org_id, statement: str, params: dict) -> list:
    """Return every row of the statement."""
    async with service_session(factory, org_id) as session:
        return (await session.execute(text(statement), params)).all()


@dataclass(frozen=True, slots=True)
class ForgetFixture:
    """The rows a forget must erase, and the values the assertions compare against."""

    org_id: UUID
    agent_id: UUID
    memory_id: UUID
    other_id: str
    content: str
    original_hash: str


async def read_content_hash(factory, *, org_id, memory_id) -> str:
    """Read the memory's content hash so the assertion can prove it changed."""
    return await fetch_scalar(
        factory,
        org_id,
        "SELECT content_hash FROM ibex_core.memories WHERE id=:id AND org_id=:org",
        {"id": memory_id, "org": org_id},
    )


async def seed_related_memory(factory, *, org_id, agent_id) -> str:
    """A second memory the target points at and relates to."""
    other_id = str(uuid4())
    await execute_sql(
        factory,
        org_id,
        "INSERT INTO ibex_core.memories"
        " (id, org_id, agent_id, content, content_hash, content_tokens)"
        " VALUES (:id, :org, :agent, 'related memory content', :hash, 3)",
        {"id": other_id, "org": org_id, "agent": agent_id, "hash": f"hash-{other_id}"},
    )
    return other_id


_RETENTION_UPDATE_SQL = """
    UPDATE ibex_core.memories
    SET metadata = '{"topic":"retention","note":"sentinel-metadata"}'::jsonb,
        pii_detected = TRUE, pii_redacted = TRUE,
        retrieval_count = 17, last_retrieved_at = NOW(),
        superseded_by = :other, merged_into = :other,
        usefulness_score = 0.93
    WHERE id = :id AND org_id = :org
"""

_CHILD_ROWS_SQL = (
    (
        "INSERT INTO ibex_core.memory_labels (memory_id, org_id, label)"
        " VALUES (:id, :org, 'factual')"
    ),
    (
        "INSERT INTO ibex_core.memory_feedback (org_id, memory_id, agent_id, feedback, notes)"
        " VALUES (:org, :id, :agent, 'positive', 'sentinel feedback')"
    ),
    (
        "INSERT INTO ibex_core.memory_relationships"
        " (org_id, source_memory_id, target_memory_id, relationship_type, resolution_notes)"
        " VALUES (:org, :id, :other, 'supersedes', 'sentinel outbound')"
    ),
    (
        "INSERT INTO ibex_core.memory_relationships"
        " (org_id, source_memory_id, target_memory_id, relationship_type, resolution_notes)"
        " VALUES (:org, :other, :id, 'derived_from', 'sentinel inbound')"
    ),
    (
        "INSERT INTO ibex_core.memory_conflict_escalations"
        " (org_id, new_memory_id, candidate_memory_id, conflict_type, reason)"
        " VALUES (:org, :id, :other, 'contradicts', 'sentinel escalation')"
    ),
    (
        "INSERT INTO ibex_core.memory_conflict_escalations"
        " (org_id, new_memory_id, candidate_memory_id, conflict_type, reason)"
        " VALUES (:org, :other, :id, 'contradicts', 'sentinel candidate')"
    ),
)

_LEDGER_INSERT_SQL = """INSERT INTO ibex_core.idempotency_ledger
       (organization_id, agent_id, dedupe_key, request_hash, state,
        status_code, response_payload)
       VALUES (:org, :agent, :key, :hash, 'finalized', 201,
               convert_to(:payload, 'UTF8'))"""


def _fixture_params(fixture: ForgetFixture) -> dict:
    """Bind every id the seed statements share."""
    return {
        "id": fixture.memory_id,
        "org": fixture.org_id,
        "agent": fixture.agent_id,
        "other": fixture.other_id,
    }


async def seed_forget_state(factory, fixture: ForgetFixture) -> None:
    """Give the target every kind of state and copy forget must destroy."""
    params = _fixture_params(fixture)
    await execute_sql(factory, fixture.org_id, _RETENTION_UPDATE_SQL, params)
    for statement in _CHILD_ROWS_SQL:
        await execute_sql(factory, fixture.org_id, statement, params)
    await _seed_ledger(factory, fixture)


async def _seed_ledger(factory, fixture: ForgetFixture) -> None:
    """The finalized create (carries the body) and a near-duplicate that must survive."""
    await execute_sql(
        factory,
        fixture.org_id,
        _LEDGER_INSERT_SQL,
        {
            "org": fixture.org_id,
            "agent": fixture.agent_id,
            "key": "forget-erasure",
            "hash": "a" * 64,
            "payload": json.dumps(
                {"data": {"id": str(fixture.memory_id), "content": fixture.content}}
            ),
        },
    )
    await execute_sql(
        factory,
        fixture.org_id,
        _LEDGER_INSERT_SQL,
        {
            "org": fixture.org_id,
            "agent": fixture.agent_id,
            "key": "other-create",
            "hash": "b" * 64,
            "payload": json.dumps(
                {
                    "data": {
                        "id": "11111111-1111-1111-1111-111111111111",
                        "content": "other create content",
                    },
                    "meta": {
                        "deduplication": {"similar_memories": [str(fixture.memory_id)]}
                    },
                }
            ),
        },
    )


_ERASED_ROW_SQL = """
    SELECT content, content_hash, content_tokens, metadata::text AS metadata_text,
           pii_detected, pii_redacted, retrieval_count, last_retrieved_at,
           superseded_by, merged_into, usefulness_score
    FROM ibex_core.memories WHERE id=:id AND org_id=:org
"""

_CHILD_COUNT_SQL = (
    ("SELECT count(*) FROM ibex_core.memory_labels"
     " WHERE memory_id=:id AND org_id=:org"),
    ("SELECT count(*) FROM ibex_core.memory_feedback"
     " WHERE memory_id=:id AND org_id=:org"),
    ("SELECT count(*) FROM ibex_core.memory_relationships"
     " WHERE org_id=:org AND (source_memory_id=:id OR target_memory_id=:id)"),
    ("SELECT count(*) FROM ibex_core.memory_conflict_escalations"
     " WHERE org_id=:org AND (new_memory_id=:id OR candidate_memory_id=:id)"),
)


async def assert_erased(factory, fixture: ForgetFixture) -> None:
    """Assert the row lost its content and every child row and ledger copy is gone."""
    params = {"id": fixture.memory_id, "org": fixture.org_id}
    row = (await fetch_rows(factory, fixture.org_id, _ERASED_ROW_SQL, params))[0]
    assert fixture.content not in row.content
    assert row.content == "[forgotten]"
    assert fixture.original_hash not in row.content_hash, "the content hash must not survive"
    assert len(row.content_hash) == 64
    assert int(row.content_tokens) == 0
    assert row.metadata_text == "{}"
    assert row.pii_detected is False
    assert row.pii_redacted is False
    assert int(row.retrieval_count) == 0
    assert row.last_retrieved_at is None
    assert row.superseded_by is None and row.merged_into is None
    assert float(row.usefulness_score) == pytest.approx(0.50)
    for statement in _CHILD_COUNT_SQL:
        assert await fetch_scalar(factory, fixture.org_id, statement, params) == 0
    await _assert_ledger_scrubbed(factory, fixture)


async def _assert_ledger_scrubbed(factory, fixture: ForgetFixture) -> None:
    """The create's ledger copy is the marker; another create's copy survives."""
    scrubbed = await fetch_rows(
        factory,
        fixture.org_id,
        "SELECT encode(response_payload, 'escape') AS payload"
        " FROM ibex_core.idempotency_ledger"
        " WHERE organization_id = :org AND dedupe_key = 'forget-erasure'",
        {"org": fixture.org_id},
    )
    assert len(scrubbed) == 1, "the create's idempotency row must survive the scrub"
    assert fixture.content not in scrubbed[0].payload
    assert '"erased":true' in scrubbed[0].payload.replace(" ", "")

    untouched = await fetch_rows(
        factory,
        fixture.org_id,
        "SELECT encode(response_payload, 'escape') AS payload"
        " FROM ibex_core.idempotency_ledger"
        " WHERE organization_id = :org AND dedupe_key = 'other-create'",
        {"org": fixture.org_id},
    )
    assert len(untouched) == 1, "another create's ledger row must not be scrubbed"
    assert "other create content" in untouched[0].payload
