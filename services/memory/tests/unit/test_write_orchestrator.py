"""Unit tests for write orchestrator and error helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.exceptions import DuplicateMemoryError, ValidationError
from app.pipeline.context import WriteContext
from app.write.errors import is_active_content_hash_violation
from app.write.models import CreateMemoryCommand, WriteOutcomeKind
from app.write.orchestrator import MemoryWriteOrchestrator
from tests.unit.memory_test_support import sample_memory_row


class _StopPipeline:
    async def run(self, ctx: WriteContext) -> WriteContext:
        return ctx


class _Orig:
    def __init__(self, *, sqlstate: str, constraint_name: str = "") -> None:
        self.sqlstate = sqlstate
        self.constraint_name = constraint_name


def test_is_active_content_hash_violation_true() -> None:
    exc = IntegrityError("stmt", {}, Exception("dup"))
    exc.orig = _Orig(  # type: ignore[attr-defined]
        sqlstate="23505",
        constraint_name="idx_memories_org_agent_content_hash_active",
    )
    assert is_active_content_hash_violation(exc) is True


def test_is_active_content_hash_violation_false_wrong_code() -> None:
    exc = IntegrityError("stmt", {}, Exception("other"))
    exc.orig = _Orig(sqlstate="23503")  # type: ignore[attr-defined]
    assert is_active_content_hash_violation(exc) is False


@pytest.mark.asyncio
async def test_orchestrator_raises_validation_error() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    orch = MemoryWriteOrchestrator(_StopPipeline(), AsyncMock())
    ctx = WriteContext(org_id=org_id, agent_id=agent_id, content="x", error="content_empty")

    async def _run(_ctx: WriteContext) -> WriteContext:
        return ctx

    orch._pipeline = _StopPipeline()
    orch._pipeline.run = _run  # type: ignore[method-assign]

    with pytest.raises(ValidationError):
        await orch.create(
            CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content="")
        )


@pytest.mark.asyncio
async def test_orchestrator_exact_duplicate_raises_without_insert() -> None:
    existing = uuid4()
    org_id = uuid4()
    agent_id = uuid4()
    orch = MemoryWriteOrchestrator(_StopPipeline(), AsyncMock())
    ctx = WriteContext(
        org_id=org_id,
        agent_id=agent_id,
        content="dup",
        is_exact_duplicate=True,
        existing_memory_id=existing,
        stop=True,
    )

    async def _run(_ctx: WriteContext) -> WriteContext:
        return ctx

    orch._pipeline = _StopPipeline()
    orch._pipeline.run = _run  # type: ignore[method-assign]

    with patch("app.write.orchestrator.insert_memory_session", AsyncMock()) as insert_mock:
        with pytest.raises(DuplicateMemoryError) as exc_info:
            await orch.create(
                CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content="dup")
            )
        insert_mock.assert_not_awaited()
        assert exc_info.value.existing_id == existing


@pytest.mark.asyncio
async def test_orchestrator_quarantine_persists_without_active_path() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    mock_session = MagicMock()
    mock_begin = MagicMock()
    mock_begin.__aenter__ = AsyncMock(return_value=mock_session)
    mock_begin.__aexit__ = AsyncMock(return_value=None)
    mock_session.begin = MagicMock(return_value=mock_begin)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    mock_factory = MagicMock(return_value=mock_cm)

    orch = MemoryWriteOrchestrator(_StopPipeline(), mock_factory)
    ctx = WriteContext(
        org_id=org_id,
        agent_id=agent_id,
        content="Contact Jordan",
        status="quarantined",
        pii_detected=True,
        content_hash="abc123",
        stop=True,
    )

    async def _run(_ctx: WriteContext) -> WriteContext:
        return ctx

    orch._pipeline = _StopPipeline()
    orch._pipeline.run = _run  # type: ignore[method-assign]

    fake_row = sample_memory_row(
        org_id=org_id,
        agent_id=agent_id,
        content=ctx.content,
        content_tokens=2,
        status="quarantined",
        pii_detected=True,
    )
    with (
        patch(
            "app.write.orchestrator.insert_memory_session",
            AsyncMock(return_value=fake_row),
        ) as insert_mock,
        patch("app.write.orchestrator.insert_labels_session", AsyncMock(return_value=1)),
        patch("app.write.orchestrator.reload_memory_session", AsyncMock(return_value=fake_row)),
    ):
        outcome = await orch.create(
            CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content=ctx.content)
        )
        insert_mock.assert_awaited_once()
        assert outcome.kind == WriteOutcomeKind.QUARANTINED
