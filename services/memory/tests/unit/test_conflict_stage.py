"""ConflictStage wiring after near-dup."""

from __future__ import annotations

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


def _dt(month: int) -> datetime:
    return datetime(2026, month, 1, tzinfo=UTC)


@pytest.mark.asyncio
async def test_conflict_stage_disabled_skips() -> None:
    svc = ConflictService(Settings(), subject_extractor=lambda _: "x")

    async def load(_org: UUID, _ids: object) -> list[CandidateMemory]:
        raise AssertionError("should not load")

    pipe = WritePipeline(
        [ConflictStage(svc, load_candidates=load, enabled=False)]
    )
    ctx = await pipe.run(
        WriteContext(
            org_id=uuid4(),
            agent_id=uuid4(),
            content="x",
            near_duplicate_candidates=[uuid4()],
            valid_from=_dt(6),
        )
    )
    assert ctx.conflict_decisions == []


@pytest.mark.asyncio
async def test_conflict_stage_skips_without_candidates() -> None:
    svc = ConflictService(Settings(), subject_extractor=lambda _: "x")

    async def load(_org: UUID, _ids: object) -> list[CandidateMemory]:
        raise AssertionError("should not load")

    pipe = WritePipeline([ConflictStage(svc, load_candidates=load)])
    ctx = await pipe.run(WriteContext(org_id=uuid4(), content="x", agent_id=uuid4()))
    assert ctx.conflict_decisions == []


@pytest.mark.asyncio
async def test_conflict_stage_records_supersede_targets() -> None:
    old_id = uuid4()
    svc = ConflictService(
        Settings(),
        subject_extractor=lambda _: "pref",
    )

    async def load(_org: UUID, ids: object) -> list[CandidateMemory]:
        assert list(ids) == [old_id]
        return [
            CandidateMemory(
                memory_id=old_id,
                content="User prefers Python",
                interval=ValidityInterval(valid_from=_dt(3), valid_until=_dt(6)),
            )
        ]

    pipe = WritePipeline([ConflictStage(svc, load_candidates=load)])
    ctx = await pipe.run(
        WriteContext(
            org_id=uuid4(),
            agent_id=uuid4(),
            content="User is switching to Go",
            near_duplicate_candidates=[old_id],
            valid_from=_dt(6),
        )
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

    svc = ConflictService(
        Settings(), classifier=_Cls(), subject_extractor=lambda _: "pref"
    )

    async def load(_org: UUID, _ids: object) -> list[CandidateMemory]:
        return [
            CandidateMemory(
                memory_id=cand,
                content="User prefers Python",
                interval=ValidityInterval(valid_from=_dt(3), valid_until=None),
            )
        ]

    pipe = WritePipeline([ConflictStage(svc, load_candidates=load)])
    ctx = await pipe.run(
        WriteContext(
            org_id=uuid4(),
            agent_id=uuid4(),
            content="User prefers Go",
            near_duplicate_candidates=[cand],
            valid_from=None,
        )
    )
    assert ctx.conflict_llm_calls == 1
    assert ctx.conflict_decisions[0].outcome == ConflictOutcome.UNRELATED
    assert ctx.conflict_decisions[0].notes == "missing_validity"


@pytest.mark.asyncio
async def test_conflict_stage_empty_load_noop() -> None:
    svc = ConflictService(Settings(), subject_extractor=lambda _: "x")

    async def load(_org: UUID, _ids: object) -> list[CandidateMemory]:
        return []

    pipe = WritePipeline([ConflictStage(svc, load_candidates=load)])
    ctx = await pipe.run(
        WriteContext(
            org_id=uuid4(),
            agent_id=uuid4(),
            content="x",
            near_duplicate_candidates=[uuid4()],
            valid_from=_dt(6),
        )
    )
    assert ctx.conflict_decisions == []


@pytest.mark.asyncio
async def test_conflict_stage_requires_agent_id() -> None:
    svc = ConflictService(Settings(), subject_extractor=lambda _: "x")

    async def load(_org: UUID, _ids: object) -> list[CandidateMemory]:
        raise AssertionError("should not load")

    pipe = WritePipeline([ConflictStage(svc, load_candidates=load)])
    ctx = await pipe.run(
        WriteContext(
            org_id=uuid4(),
            content="x",
            near_duplicate_candidates=[uuid4()],
            valid_from=_dt(6),
        )
    )
    assert ctx.stop is True
    assert ctx.error == "agent_id_required"
