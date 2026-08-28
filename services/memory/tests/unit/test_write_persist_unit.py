"""Unit tests for write persist helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.pipeline.context import WriteContext
from app.write.models import CreateMemoryCommand
from app.write.persist import (
    EscalationInsert,
    insert_escalations_session,
    insert_memory_session,
)


def _mapping_row(**overrides):
    org_id = uuid4()
    agent_id = uuid4()
    now = datetime.now(tz=UTC)
    base = {
        "id": uuid4(),
        "org_id": org_id,
        "agent_id": agent_id,
        "content": "hello world",
        "content_tokens": 2,
        "category": "factual",
        "confidence": 0.8,
        "status": "active",
        "source": "user_provided",
        "pii_detected": False,
        "pii_redacted": False,
        "session_id": None,
        "metadata": "{}",
        "retrieval_count": 0,
        "usefulness_score": 0.5,
        "valid_from": now,
        "valid_until": None,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_insert_memory_session_maps_row() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    row = _mapping_row(org_id=org_id, agent_id=agent_id, metadata='{"k":"v"}')
    session = AsyncMock()
    result = MagicMock()
    result.one.return_value = row
    session.execute = AsyncMock(return_value=result)

    command = CreateMemoryCommand(
        org_id=org_id,
        agent_id=agent_id,
        content="hello world",
        metadata={"k": "v"},
    )
    ctx = WriteContext(
        org_id=org_id,
        agent_id=agent_id,
        content="hello world",
        status="active",
        content_hash="hash",
    )
    memory = await insert_memory_session(session, command=command, ctx=ctx)
    assert memory.org_id == org_id
    assert memory.metadata == {"k": "v"}
    assert session.execute.await_count >= 1


@pytest.mark.asyncio
async def test_insert_memory_session_metadata_dict() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    row = _mapping_row(org_id=org_id, agent_id=agent_id, metadata={"a": 1})
    session = AsyncMock()
    result = MagicMock()
    result.one.return_value = row
    session.execute = AsyncMock(return_value=result)

    command = CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content="x")
    ctx = WriteContext(org_id=org_id, agent_id=agent_id, content="x", status="active")
    memory = await insert_memory_session(session, command=command, ctx=ctx)
    assert memory.metadata == {"a": 1}


@pytest.mark.asyncio
async def test_insert_memory_session_non_dict_metadata_becomes_empty() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    row = _mapping_row(org_id=org_id, agent_id=agent_id, metadata=123)
    session = AsyncMock()
    result = MagicMock()
    result.one.return_value = row
    session.execute = AsyncMock(return_value=result)

    command = CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content="x")
    ctx = WriteContext(org_id=org_id, agent_id=agent_id, content="x", status="quarantined")
    memory = await insert_memory_session(session, command=command, ctx=ctx)
    assert memory.metadata == {}


@pytest.mark.asyncio
async def test_insert_escalations_session_empty_noop() -> None:
    session = AsyncMock()
    await insert_escalations_session(session, [])
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_insert_escalations_session_inserts() -> None:
    org_id = uuid4()
    session = AsyncMock()
    item = EscalationInsert(
        org_id=org_id,
        new_memory_id=uuid4(),
        candidate_memory_id=uuid4(),
        conflict_type="escalate_pending",
        subject_key="k",
        reason="r",
    )
    await insert_escalations_session(session, [item])
    assert session.execute.await_count >= 1
    params = session.execute.await_args_list[-1].args[1]
    assert params["org_id"] == str(org_id)
