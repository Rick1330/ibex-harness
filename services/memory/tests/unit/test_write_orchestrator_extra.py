"""Additional orchestrator unit tests for coverage."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.clients.embedding import EmbeddingUnavailableError
from app.exceptions import DuplicateMemoryError, EmbeddingServiceError
from app.pipeline.context import WriteContext
from app.write.errors import is_active_content_hash_violation
from app.write.models import CreateMemoryCommand, MemoryRow, WriteOutcomeKind
from app.write.orchestrator import MemoryWriteOrchestrator, _is_embedding_failure


class _Pipe:
    async def run(self, ctx: WriteContext) -> WriteContext:
        return ctx


@pytest.mark.asyncio
async def test_orchestrator_embedding_failure_mapped() -> None:
    orch = MemoryWriteOrchestrator(_Pipe(), MagicMock())

    async def _boom(_ctx: WriteContext) -> WriteContext:
        raise EmbeddingUnavailableError("down")

    orch._pipeline.run = _boom  # type: ignore[method-assign]
    with pytest.raises(EmbeddingServiceError):
        await orch.create(
            CreateMemoryCommand(org_id=uuid4(), agent_id=uuid4(), content="x")
        )


@pytest.mark.asyncio
async def test_orchestrator_active_persist_integrity_race() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    existing = uuid4()
    ctx = WriteContext(
        org_id=org_id,
        agent_id=agent_id,
        content="race content here",
        content_hash="hash123",
        status="active",
    )

    async def _run(_c: WriteContext) -> WriteContext:
        return ctx

    orch = MemoryWriteOrchestrator(_Pipe(), MagicMock())
    orch._pipeline.run = _run  # type: ignore[method-assign]

    exc = IntegrityError("insert", {}, Exception("dup"))
    orig = MagicMock()
    orig.sqlstate = "23505"
    orig.constraint_name = "idx_memories_org_agent_content_hash_active"
    exc.orig = orig

    mock_session = MagicMock()
    mock_begin = MagicMock()
    mock_begin.__aenter__ = AsyncMock(return_value=mock_session)
    mock_begin.__aexit__ = AsyncMock(return_value=None)
    mock_session.begin = MagicMock(return_value=mock_begin)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    mock_factory = MagicMock(return_value=mock_cm)

    orch._factory = mock_factory

    with (
        patch(
            "app.write.orchestrator.insert_memory_session",
            AsyncMock(side_effect=exc),
        ),
        patch(
            "app.write.orchestrator.find_active_by_content_hash",
            AsyncMock(return_value=existing),
        ),
        patch(
            "app.write.orchestrator.increment_retrieval_count",
            AsyncMock(return_value=1),
        ),
    ):
        with pytest.raises(DuplicateMemoryError) as err:
            await orch.create(
                CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content=ctx.content)
            )
        assert err.value.existing_id == existing


def test_is_embedding_failure_names() -> None:
    assert _is_embedding_failure(EmbeddingUnavailableError("x")) is True
    assert _is_embedding_failure(RuntimeError("x")) is False


def test_is_active_content_hash_violation_asyncpg_message() -> None:
    exc = IntegrityError("insert", {}, Exception("dup"))
    orig = MagicMock()
    orig.sqlstate = None
    orig.pgcode = "23505"
    orig.constraint_name = ""
    orig.diag = None
    orig.detail = ""
    orig.__str__ = lambda self: (
        'duplicate key value violates unique constraint '
        '"idx_memories_org_agent_content_hash_active"'
    )
    exc.orig = orig
    assert is_active_content_hash_violation(exc) is True


def test_is_active_content_hash_violation_content_hash_key() -> None:
    exc = IntegrityError("insert", {}, Exception("dup"))
    orig = MagicMock()
    orig.sqlstate = "23505"
    orig.constraint_name = ""
    orig.diag = None
    orig.detail = ""
    orig.__str__ = lambda self: (
        "Key (org_id, agent_id, content_hash)=(...) already exists."
    )
    exc.orig = orig
    assert is_active_content_hash_violation(exc) is True


def test_is_active_content_hash_detail_fallback() -> None:
    exc = IntegrityError("stmt", {}, Exception("dup"))
    orig = MagicMock()
    orig.sqlstate = "23505"
    orig.constraint_name = ""
    orig.diag = None
    orig.detail = "idx_memories_org_agent_content_hash_active violated"
    exc.orig = orig
    assert is_active_content_hash_violation(exc) is True


@pytest.mark.asyncio
async def test_orchestrator_active_persist_with_supersession_and_after_commit() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    target_id = uuid4()
    ctx = WriteContext(
        org_id=org_id,
        agent_id=agent_id,
        content="new fact about project",
        content_hash="hash456",
        status="active",
        embedding=[0.1] * 8,
        pending_supersede_targets=[target_id],
        conflict_decisions=[],
    )

    async def _run(_c: WriteContext) -> WriteContext:
        return ctx

    mock_session = MagicMock()
    mock_begin = MagicMock()
    mock_begin.__aenter__ = AsyncMock(return_value=mock_session)
    mock_begin.__aexit__ = AsyncMock(return_value=None)
    mock_session.begin = MagicMock(return_value=mock_begin)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    mock_factory = MagicMock(return_value=mock_cm)

    after_commit = AsyncMock()
    orch = MemoryWriteOrchestrator(_Pipe(), mock_factory, after_commit=after_commit)
    orch._pipeline.run = _run  # type: ignore[method-assign]

    fake_row = MemoryRow(
        id=uuid4(),
        org_id=org_id,
        agent_id=agent_id,
        content=ctx.content,
        content_tokens=4,
        category="factual",
        confidence=0.8,
        status="active",
        source="user_provided",
        pii_detected=False,
        pii_redacted=False,
        session_id=None,
        metadata={},
        retrieval_count=0,
        usefulness_score=0.5,
        valid_from=datetime.now(tz=UTC),
        valid_until=None,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )

    with (
        patch("app.write.orchestrator.insert_memory_session", AsyncMock(return_value=fake_row)),
        patch("app.write.orchestrator.apply_supersession_session", AsyncMock()) as supersede,
        patch("app.write.orchestrator.insert_escalations_session", AsyncMock()),
    ):
        outcome = await orch.create(
            CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content=ctx.content)
        )
        assert outcome.kind == WriteOutcomeKind.CREATED
        assert outcome.embedding_model == "bge-m3"
        supersede.assert_awaited_once()
        after_commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_orchestrator_exact_duplicate_missing_id_raises() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    ctx = WriteContext(
        org_id=org_id,
        agent_id=agent_id,
        content="dup",
        is_exact_duplicate=True,
        existing_memory_id=None,
    )

    async def _run(_c: WriteContext) -> WriteContext:
        return ctx

    orch = MemoryWriteOrchestrator(_Pipe(), MagicMock())
    orch._pipeline.run = _run  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="existing_memory_id"):
        await orch.create(
            CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content="dup")
        )


@pytest.mark.asyncio
async def test_orchestrator_race_without_existing_raises() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    orch = MemoryWriteOrchestrator(_Pipe(), MagicMock())
    with patch(
        "app.write.orchestrator.find_active_by_content_hash",
        AsyncMock(return_value=None),
    ), pytest.raises(RuntimeError, match="unique violation"):
        await orch._handle_hash_race(
            CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content="x"),
            "hash",
        )


@pytest.mark.asyncio
async def test_orchestrator_re_raises_non_hash_integrity() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    ctx = WriteContext(
        org_id=org_id,
        agent_id=agent_id,
        content="content here",
        content_hash="h",
        status="active",
    )

    async def _run(_c: WriteContext) -> WriteContext:
        return ctx

    mock_session = MagicMock()
    mock_begin = MagicMock()
    mock_begin.__aenter__ = AsyncMock(return_value=mock_session)
    mock_begin.__aexit__ = AsyncMock(return_value=None)
    mock_session.begin = MagicMock(return_value=mock_begin)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    orch = MemoryWriteOrchestrator(_Pipe(), MagicMock(return_value=mock_cm))
    orch._pipeline.run = _run  # type: ignore[method-assign]

    exc = IntegrityError("insert", {}, Exception("other"))
    orig = MagicMock()
    orig.sqlstate = "23503"
    exc.orig = orig

    with patch(
        "app.write.orchestrator.insert_memory_session",
        AsyncMock(side_effect=exc),
    ), pytest.raises(IntegrityError):
        await orch.create(
            CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content=ctx.content)
        )
