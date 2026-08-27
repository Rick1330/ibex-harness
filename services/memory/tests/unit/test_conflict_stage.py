"""ConflictStage wiring after near-dup."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
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


async def _run_conflict(
    *,
    load: CandidateLoader,
    enabled: bool = True,
    agent_id: object = _MISSING,
    candidates: list[UUID] | None = None,
    valid_from: datetime | None | object = _MISSING,
    classifier: object | None = None,
    subject: str = "x",
    content: str = "x",
) -> WriteContext:
    resolved_agent: UUID | None
    if agent_id is _MISSING:
        resolved_agent = uuid4()
    else:
        resolved_agent = agent_id  # type: ignore[assignment]
    resolved_valid_from: datetime | None
    if valid_from is _MISSING:
        resolved_valid_from = _dt(6)
    else:
        resolved_valid_from = valid_from  # type: ignore[assignment]
    svc = ConflictService(
        Settings(),
        classifier=classifier,  # type: ignore[arg-type]
        subject_extractor=lambda _: subject,
    )
    pipe = WritePipeline(
        [ConflictStage(svc, load_candidates=load, enabled=enabled)]
    )
    return await pipe.run(
        WriteContext(
            org_id=uuid4(),
            agent_id=resolved_agent,
            content=content,
            near_duplicate_candidates=candidates or [],
            valid_from=resolved_valid_from,
        )
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("enabled", "candidates", "agent_id", "load", "expect_error"),
    [
        (False, [uuid4()], _MISSING, _refuse_load, None),
        (True, [], _MISSING, _refuse_load, None),
        (True, [uuid4()], _MISSING, _empty_load, None),
        (True, [uuid4()], None, _refuse_load, "agent_id_required"),
    ],
)
async def test_conflict_stage_early_exits(
    enabled: bool,
    candidates: list[UUID],
    agent_id: object,
    load: CandidateLoader,
    expect_error: str | None,
) -> None:
    ctx = await _run_conflict(
        load=load,
        enabled=enabled,
        agent_id=agent_id,
        candidates=candidates,
    )
    assert ctx.conflict_decisions == []
    if expect_error is None:
        assert ctx.stop is False
    else:
        assert ctx.stop is True
        assert ctx.error == expect_error


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

    ctx = await _run_conflict(
        load=load,
        candidates=[old_id],
        subject="pref",
        content="User is switching to Go",
        valid_from=_dt(6),
    )
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

    ctx = await _run_conflict(
        load=load,
        candidates=[cand],
        classifier=_Cls(),
        subject="pref",
        content="User prefers Go",
        valid_from=None,
    )
    assert ctx.conflict_llm_calls == 1
    assert ctx.conflict_decisions[0].outcome == ConflictOutcome.UNRELATED
    assert ctx.conflict_decisions[0].notes == "missing_validity"
