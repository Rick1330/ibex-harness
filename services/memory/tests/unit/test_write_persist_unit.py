"""Unit tests for write persist helpers."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.pipeline.context import WriteContext
from app.write.labels import LabelInsert
from app.write.models import CreateMemoryCommand
from app.write.persist import (
    EscalationInsert,
    insert_escalations_session,
    insert_labels_session,
    insert_memory_session,
    reload_memory_session,
)
from tests.unit.memory_test_support import mapping_row, mock_session_returning_row


async def _insert_memory(
    *,
    row,
    command: CreateMemoryCommand,
    ctx: WriteContext,
):
    session = mock_session_returning_row(row)
    return await insert_memory_session(session, command=command, ctx=ctx), session


@pytest.mark.asyncio
async def test_insert_memory_session_maps_row() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    row = mapping_row(org_id=org_id, agent_id=agent_id, metadata='{"k":"v"}')
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
    memory, session = await _insert_memory(row=row, command=command, ctx=ctx)
    assert memory.org_id == org_id
    assert memory.metadata == {"k": "v"}
    assert session.execute.await_count >= 1


@pytest.mark.asyncio
async def test_insert_memory_session_metadata_dict() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    row = mapping_row(org_id=org_id, agent_id=agent_id, metadata={"a": 1})
    command = CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content="x")
    ctx = WriteContext(org_id=org_id, agent_id=agent_id, content="x", status="active")
    memory, _session = await _insert_memory(row=row, command=command, ctx=ctx)
    assert memory.metadata == {"a": 1}


@pytest.mark.asyncio
async def test_insert_memory_session_non_dict_metadata_becomes_empty() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    row = mapping_row(org_id=org_id, agent_id=agent_id, metadata=123)
    command = CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content="x")
    ctx = WriteContext(org_id=org_id, agent_id=agent_id, content="x", status="quarantined")
    memory, _session = await _insert_memory(row=row, command=command, ctx=ctx)
    assert memory.metadata == {}


@pytest.mark.asyncio
async def test_insert_memory_session_persists_visibility_tags_pinned() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    row = mapping_row(
        org_id=org_id,
        agent_id=agent_id,
        metadata='{"visibility":"org","pinned":true,"tags":["a"],"note":"x"}',
    )
    command = CreateMemoryCommand(
        org_id=org_id,
        agent_id=agent_id,
        content="hello",
        visibility="org",
        tags=("a",),
        pinned=True,
        metadata={"note": "x"},
    )
    ctx = WriteContext(org_id=org_id, agent_id=agent_id, content="hello", status="active")
    memory, session = await _insert_memory(row=row, command=command, ctx=ctx)
    assert memory.visibility == "org"
    assert memory.pinned is True
    assert memory.tags == ("a",)
    assert memory.metadata == {"note": "x"}
    params = session.execute.await_args_list[-1].args[1]
    assert '"visibility": "org"' in params["metadata"]
    assert '"pinned": true' in params["metadata"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("insert_fn", "inserts"),
    [
        (insert_escalations_session, []),
        (insert_labels_session, []),
    ],
)
async def test_insert_session_empty_noop(insert_fn, inserts) -> None:
    session = AsyncMock()
    assert await insert_fn(session, inserts) == 0
    session.execute.assert_not_awaited()


async def _assert_single_insert(
    insert_fn: Callable,
    item: object,
    expected_params: dict[str, str],
) -> None:
    session = AsyncMock()
    assert await insert_fn(session, [item]) == 1
    params = session.execute.await_args_list[-1].args[1]
    for key, value in expected_params.items():
        assert params[key] == value


@pytest.mark.asyncio
async def test_insert_escalations_session_inserts() -> None:
    org_id = uuid4()
    await _assert_single_insert(
        insert_escalations_session,
        EscalationInsert(
            org_id=org_id,
            new_memory_id=uuid4(),
            candidate_memory_id=uuid4(),
            conflict_type="escalate_pending",
            subject_key="k",
            reason="r",
        ),
        {"org_id": str(org_id)},
    )


@pytest.mark.asyncio
async def test_insert_labels_session_inserts() -> None:
    org_id = uuid4()
    memory_id = uuid4()
    await _assert_single_insert(
        insert_labels_session,
        LabelInsert(
            org_id=org_id,
            memory_id=memory_id,
            label="factual",
            confidence=0.8,
        ),
        {"label": "factual", "memory_id": str(memory_id)},
    )


@pytest.mark.asyncio
async def test_reload_memory_session_maps_row() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    memory_id = uuid4()
    row = mapping_row(org_id=org_id, agent_id=agent_id, metadata="{}")
    row.id = memory_id
    row.category = "behavioral"
    session = mock_session_returning_row(row)
    memory = await reload_memory_session(session, org_id=org_id, memory_id=memory_id)
    assert memory.id == memory_id
    assert memory.category == "behavioral"
