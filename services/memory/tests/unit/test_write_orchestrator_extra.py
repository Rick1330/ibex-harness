"""Additional orchestrator unit tests for coverage."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from prometheus_client import REGISTRY
from sqlalchemy.exc import IntegrityError

from app.clients.embedding import EmbeddingUnavailableError
from app.conflict.types import ConflictDecision, ConflictOutcome
from app.exceptions import DuplicateMemoryError, EmbeddingServiceError, ValidationError
from app.pipeline.context import WriteContext
from app.write.errors import is_active_content_hash_violation
from app.write.models import CreateMemoryCommand, WriteOutcomeKind
from app.write.orchestrator import MemoryWriteOrchestrator, _is_embedding_failure
from tests.unit.memory_test_support import (
    HashViolationOpts,
    LabelViolationOpts,
    hash_violation_integrity_error,
    label_violation_integrity_error,
    mock_async_session_factory,
    sample_memory_row,
)


class _Pipe:
    async def run(self, ctx: WriteContext) -> WriteContext:
        return ctx


def _counter_value(name: str) -> float:
    value = REGISTRY.get_sample_value(name)
    return float(value) if value is not None else 0.0


@pytest.mark.asyncio
async def test_orchestrator_embedding_failure_mapped() -> None:
    orch = MemoryWriteOrchestrator(_Pipe(), MagicMock())

    async def _boom(_ctx: WriteContext) -> WriteContext:
        raise EmbeddingUnavailableError("down")

    orch._pipeline.run = _boom  # type: ignore[method-assign]
    cmd = CreateMemoryCommand(org_id=uuid4(), agent_id=uuid4(), content="x")
    with pytest.raises(EmbeddingServiceError):
        await orch.create(cmd)


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
    exc = hash_violation_integrity_error(
        HashViolationOpts(constraint_name="idx_memories_org_agent_content_hash_active")
    )

    mock_factory = mock_async_session_factory()
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
        cmd = CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content=ctx.content)
        with pytest.raises(DuplicateMemoryError) as err:
            await orch.create(cmd)
        assert err.value.existing_id == existing


def test_is_embedding_failure_names() -> None:
    assert _is_embedding_failure(EmbeddingUnavailableError("x")) is True
    assert _is_embedding_failure(RuntimeError("x")) is False


@pytest.mark.parametrize(
    "opts",
    [
        HashViolationOpts(
            sqlstate=None,
            pgcode="23505",
            message=(
                'duplicate key value violates unique constraint '
                '"idx_memories_org_agent_content_hash_active"'
            ),
        ),
        HashViolationOpts(
            message="Key (org_id, agent_id, content_hash)=(...) already exists."
        ),
        HashViolationOpts(detail="idx_memories_org_agent_content_hash_active violated"),
    ],
)
def test_is_active_content_hash_violation_variants(opts: HashViolationOpts) -> None:
    exc = hash_violation_integrity_error(opts)
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

    mock_factory = mock_async_session_factory()
    after_commit = AsyncMock()
    orch = MemoryWriteOrchestrator(_Pipe(), mock_factory, after_commit=after_commit)
    orch._pipeline.run = _run  # type: ignore[method-assign]

    fake_row = sample_memory_row(
        org_id=org_id,
        agent_id=agent_id,
        content=ctx.content,
        content_tokens=4,
    )

    with (
        patch("app.write.orchestrator.insert_memory_session", AsyncMock(return_value=fake_row)),
        patch("app.write.orchestrator.insert_labels_session", AsyncMock(return_value=1)),
        patch("app.write.orchestrator.reload_memory_session", AsyncMock(return_value=fake_row)),
        patch("app.write.orchestrator.apply_supersession_session", AsyncMock()) as supersede,
        patch("app.write.orchestrator.insert_escalations_session", AsyncMock(return_value=0)),
    ):
        outcome = await orch.create(
            CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content=ctx.content)
        )
        assert outcome.kind == WriteOutcomeKind.CREATED
        assert outcome.embedding_model == "bge-m3"
        supersede.assert_awaited_once()
        after_commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_orchestrator_escalations_metric_increments_after_commit() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    candidate_id = uuid4()
    ctx = WriteContext(
        org_id=org_id,
        agent_id=agent_id,
        content="escalation metric probe",
        content_hash="hash-esc",
        status="active",
        embedding=[0.1] * 8,
        conflict_decisions=[
            ConflictDecision(
                candidate_id=candidate_id,
                outcome=ConflictOutcome.ESCALATE_PENDING,
                llm_call_made=False,
                subject_key="k",
                notes="n",
            ),
        ],
    )

    async def _run(_c: WriteContext) -> WriteContext:
        return ctx

    mock_factory = mock_async_session_factory()
    orch = MemoryWriteOrchestrator(_Pipe(), mock_factory)
    orch._pipeline.run = _run  # type: ignore[method-assign]

    fake_row = sample_memory_row(
        org_id=org_id,
        agent_id=agent_id,
        content=ctx.content,
        content_tokens=4,
    )
    escalation_count = 2
    before = _counter_value("ibex_memory_conflict_escalations_inserted_total")

    with (
        patch("app.write.orchestrator.insert_memory_session", AsyncMock(return_value=fake_row)),
        patch("app.write.orchestrator.insert_labels_session", AsyncMock(return_value=1)),
        patch("app.write.orchestrator.reload_memory_session", AsyncMock(return_value=fake_row)),
        patch(
            "app.write.orchestrator.insert_escalations_session",
            AsyncMock(return_value=escalation_count),
        ),
    ):
        outcome = await orch.create(
            CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content=ctx.content)
        )

    assert outcome.kind == WriteOutcomeKind.CREATED
    after = _counter_value("ibex_memory_conflict_escalations_inserted_total")
    assert after == before + escalation_count


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
    cmd = CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content="dup")
    with pytest.raises(RuntimeError, match="existing_memory_id"):
        await orch.create(cmd)


@pytest.mark.asyncio
async def test_orchestrator_race_without_existing_raises() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    orch = MemoryWriteOrchestrator(_Pipe(), MagicMock())
    cmd = CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content="x")
    with (
        patch(
            "app.write.orchestrator.find_active_by_content_hash",
            AsyncMock(return_value=None),
        ),
        pytest.raises(RuntimeError, match="unique violation"),
    ):
        await orch._handle_hash_race(cmd, "hash")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("patch_target", "side_effect", "expected_exc", "field_code"),
    [
        (
            "insert_memory_session",
            IntegrityError("insert", {}, Exception("other")),
            IntegrityError,
            None,
        ),
        (
            "insert_labels_session",
            label_violation_integrity_error(),
            ValidationError,
            "duplicate_label",
        ),
        (
            "insert_labels_session",
            label_violation_integrity_error(LabelViolationOpts(constraint_name="other_fk")),
            IntegrityError,
            None,
        ),
    ],
)
async def test_orchestrator_active_integrity_errors(
    patch_target: str,
    side_effect: BaseException,
    expected_exc: type[BaseException],
    field_code: str | None,
) -> None:
    org_id = uuid4()
    agent_id = uuid4()
    content = f"integrity probe {patch_target}"
    ctx = WriteContext(
        org_id=org_id,
        agent_id=agent_id,
        content=content,
        content_hash="hash-active-integrity",
        status="active",
    )

    async def _run(_c: WriteContext) -> WriteContext:
        return ctx

    fake_row = sample_memory_row(org_id=org_id, agent_id=agent_id, content=content)
    orch = MemoryWriteOrchestrator(_Pipe(), mock_async_session_factory())
    orch._pipeline.run = _run  # type: ignore[method-assign]

    if patch_target == "insert_memory_session":
        if isinstance(side_effect, IntegrityError):
            orig = MagicMock()
            orig.sqlstate = "23503"
            side_effect.orig = orig
        patches = {patch_target: AsyncMock(side_effect=side_effect)}
    else:
        patches = {
            "insert_memory_session": AsyncMock(return_value=fake_row),
            patch_target: AsyncMock(side_effect=side_effect),
        }

    cmd = CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content=content)
    with (
        patch.multiple("app.write.orchestrator", **patches),
        pytest.raises(expected_exc) as err,
    ):
        await orch.create(cmd)
    if field_code is not None:
        assert err.value.field_code == field_code


def test_raise_duplicate_label_error_maps_pkey() -> None:
    orch = MemoryWriteOrchestrator(_Pipe(), MagicMock())
    exc = label_violation_integrity_error()
    with pytest.raises(ValidationError) as err:
        orch._raise_duplicate_label_error(exc)
    assert err.value.field_code == "duplicate_label"
    assert err.value.field == "labels"


def test_raise_duplicate_label_error_reraises_other() -> None:
    orch = MemoryWriteOrchestrator(_Pipe(), MagicMock())
    exc = IntegrityError("insert", {}, Exception("other"))
    orig = MagicMock()
    orig.constraint_name = "other_constraint"
    exc.orig = orig
    with pytest.raises(IntegrityError):
        orch._raise_duplicate_label_error(exc)
