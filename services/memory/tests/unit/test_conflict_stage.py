"""ConflictStage wiring after near-dup."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.config import Settings
from app.conflict.intervals import ValidityInterval
from app.conflict.service import ConflictService
from app.conflict.types import (
    CandidateMemory,
    ConflictOutcome,
)
from app.pipeline import ConflictStage, WriteContext, WritePipeline

CandidateLoader = Callable[[UUID, Sequence[UUID]], Awaitable[list[CandidateMemory]]]
_MISSING = object()


def _dt(month: int) -> datetime:
    return datetime(2026, month, 1, tzinfo=UTC)


async def _refuse_load(_org: UUID, _ids: object) -> list[CandidateMemory]:
    raise AssertionError("should not load")


async def _empty_load(_org: UUID, _ids: object) -> list[CandidateMemory]:
    return []


def _stage(load: CandidateLoader) -> SimpleNamespace:
    """Mutable fixture bag — avoids multi-arg helpers CodeScene rejects."""
    return SimpleNamespace(
        load=load,
        enabled=True,
        agent_id=_MISSING,
        candidates=[],
        valid_from=_MISSING,
        classifier=None,
        subject="x",
        content="x",
    )


def _early(
    enabled: bool,
    load: CandidateLoader,
    candidates: tuple[UUID, ...],
    expect: object = None,
) -> SimpleNamespace:
    """expect is None (ok), str error code, or (agent_id, error) tuple."""
    agent_id: object = _MISSING
    expect_error: str | None = None
    if isinstance(expect, tuple):
        agent_id, expect_error = expect
    elif isinstance(expect, str):
        expect_error = expect
    return SimpleNamespace(
        enabled=enabled,
        load=load,
        candidates=candidates,
        agent_id=agent_id,
        expect_error=expect_error,
    )


async def _run_conflict(case: SimpleNamespace) -> WriteContext:
    resolved_agent: UUID | None
    if case.agent_id is _MISSING:
        resolved_agent = uuid4()
    else:
        resolved_agent = case.agent_id
    resolved_valid_from: datetime | None
    if case.valid_from is _MISSING:
        resolved_valid_from = _dt(6)
    else:
        resolved_valid_from = case.valid_from
    svc = ConflictService(
        Settings(),
        classifier=case.classifier,  # type: ignore[arg-type]
        subject_extractor=lambda _: case.subject,
    )
    pipe = WritePipeline(
        [ConflictStage(svc, load_candidates=case.load, enabled=case.enabled)]
    )
    return await pipe.run(
        WriteContext(
            org_id=uuid4(),
            agent_id=resolved_agent,
            content=case.content,
            near_duplicate_candidates=list(case.candidates),
            valid_from=resolved_valid_from,
        )
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        _early(False, _refuse_load, (uuid4(),)),
        _early(True, _refuse_load, ()),
        _early(True, _empty_load, (uuid4(),)),
        _early(True, _refuse_load, (uuid4(),), expect=(None, "agent_id_required")),
    ],
)
async def test_conflict_stage_early_exits(case: SimpleNamespace) -> None:
    stage = _stage(case.load)
    stage.enabled = case.enabled
    stage.agent_id = case.agent_id
    stage.candidates = list(case.candidates)
    ctx = await _run_conflict(stage)
    assert ctx.conflict_decisions == []
    if case.expect_error is None:
        assert ctx.stop is False
    else:
        assert ctx.stop is True
        assert ctx.error == case.expect_error


@pytest.mark.asyncio
async def test_conflict_stage_records_supersede_targets() -> None:
    old_id = uuid4()

    async def load(_org: UUID, ids: object) -> list[CandidateMemory]:
        assert list(ids) == [old_id]
        return [
            CandidateMemory(
                memory_id=old_id,
                content="User prefers Python",
                interval=ValidityInterval(valid_from=_dt(3), valid_until=_dt(6)),
            )
        ]

    stage = _stage(load)
    stage.candidates = [old_id]
    stage.subject = "pref"
    stage.content = "User is switching to Go"
    stage.valid_from = _dt(6)
    ctx = await _run_conflict(stage)
    assert ctx.pending_supersede_targets == [old_id]
    assert ctx.conflict_llm_calls == 0
    assert ctx.conflict_decisions[0].outcome == ConflictOutcome.SUPERSEDES


@pytest.mark.asyncio
async def test_conflict_stage_missing_valid_from_escalates() -> None:
    cand = uuid4()

    class _Cls:
        invokes_llm = True

        async def classify(self, incoming, candidate):
            del incoming, candidate
            return ConflictOutcome.UNRELATED

    async def load(_org: UUID, _ids: object) -> list[CandidateMemory]:
        return [
            CandidateMemory(
                memory_id=cand,
                content="User prefers Python",
                interval=ValidityInterval(valid_from=_dt(3), valid_until=None),
            )
        ]

    stage = _stage(load)
    stage.candidates = [cand]
    stage.classifier = _Cls()
    stage.subject = "pref"
    stage.content = "User prefers Go"
    stage.valid_from = None
    ctx = await _run_conflict(stage)
    assert ctx.conflict_llm_calls == 1
    assert ctx.conflict_decisions[0].outcome == ConflictOutcome.UNRELATED
    assert ctx.conflict_decisions[0].notes == "missing_validity"
