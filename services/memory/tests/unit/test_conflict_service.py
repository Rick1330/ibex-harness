"""Unit tests for ConflictService auto-supersede vs escalate."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.config import Settings
from app.conflict.classifier import NoopConflictClassifier
from app.conflict.intervals import ValidityInterval
from app.conflict.service import ConflictService
from app.conflict.types import (
    CandidateMemory,
    ConflictOutcome,
    IncomingMemory,
)


def _dt(month: int) -> datetime:
    return datetime(2026, month, 1, tzinfo=UTC)


def _subject(_: str) -> str:
    return "preference language"


class _FixedClassifier:
    def __init__(self, outcome: ConflictOutcome) -> None:
        self.outcome = outcome
        self.calls = 0

    async def classify(self, incoming, candidate):
        del incoming, candidate
        self.calls += 1
        return self.outcome


@pytest.mark.asyncio
async def test_sequential_fact_supersedes_without_llm() -> None:
    """Python (Mar–Jun) → Go (Jun+) same subject: supersedes, zero LLM."""
    classifier = _FixedClassifier(ConflictOutcome.CONTRADICTS)
    svc = ConflictService(
        Settings(),
        classifier=classifier,
        subject_extractor=_subject,
    )
    old_id = uuid4()
    incoming = IncomingMemory(
        content="User is switching to Go",
        interval=ValidityInterval(valid_from=_dt(6), valid_until=None),
    )
    candidates = [
        CandidateMemory(
            memory_id=old_id,
            content="User prefers Python",
            interval=ValidityInterval(valid_from=_dt(3), valid_until=_dt(6)),
        )
    ]
    result = await svc.evaluate(incoming, candidates)
    assert result.llm_calls == 0
    assert classifier.calls == 0
    assert result.decisions[0].outcome == ConflictOutcome.SUPERSEDES
    assert result.supersede_targets == [old_id]


@pytest.mark.asyncio
async def test_overlapping_intervals_escalate_to_classifier() -> None:
    classifier = _FixedClassifier(ConflictOutcome.CONTRADICTS)
    svc = ConflictService(
        Settings(),
        classifier=classifier,
        subject_extractor=_subject,
    )
    cand_id = uuid4()
    incoming = IncomingMemory(
        content="User prefers Python",
        interval=ValidityInterval(valid_from=_dt(3), valid_until=None),
    )
    candidates = [
        CandidateMemory(
            memory_id=cand_id,
            content="User prefers Go",
            interval=ValidityInterval(valid_from=_dt(3), valid_until=None),
        )
    ]
    result = await svc.evaluate(incoming, candidates)
    assert result.llm_calls == 1
    assert classifier.calls == 1
    assert result.decisions[0].outcome == ConflictOutcome.CONTRADICTS
    assert result.decisions[0].llm_call_made is True


@pytest.mark.asyncio
async def test_distinct_subject_no_conflict_when_non_overlapping() -> None:
    svc = ConflictService(
        Settings(),
        subject_extractor=lambda text: "python" if "Python" in text else "coffee",
    )
    incoming = IncomingMemory(
        content="User prefers coffee",
        interval=ValidityInterval(valid_from=_dt(6), valid_until=None),
    )
    candidates = [
        CandidateMemory(
            memory_id=uuid4(),
            content="User prefers Python",
            interval=ValidityInterval(valid_from=_dt(3), valid_until=_dt(6)),
        )
    ]
    result = await svc.evaluate(incoming, candidates)
    assert result.llm_calls == 0
    assert result.decisions[0].outcome == ConflictOutcome.NO_CONFLICT


@pytest.mark.asyncio
async def test_noop_classifier_returns_escalate_pending() -> None:
    clf = NoopConflictClassifier()
    incoming = IncomingMemory(
        content="a",
        interval=ValidityInterval(valid_from=_dt(3), valid_until=None),
    )
    candidate = CandidateMemory(
        memory_id=uuid4(),
        content="b",
        interval=ValidityInterval(valid_from=_dt(3), valid_until=None),
    )
    assert await clf.classify(incoming, candidate) == ConflictOutcome.ESCALATE_PENDING


@pytest.mark.asyncio
async def test_classifier_supersedes_rewritten_to_pending() -> None:
    classifier = _FixedClassifier(ConflictOutcome.SUPERSEDES)
    svc = ConflictService(
        Settings(),
        classifier=classifier,
        subject_extractor=_subject,
    )
    incoming = IncomingMemory(
        content="a",
        interval=ValidityInterval(valid_from=_dt(3), valid_until=None),
    )
    candidates = [
        CandidateMemory(
            memory_id=uuid4(),
            content="b",
            interval=ValidityInterval(valid_from=_dt(3), valid_until=None),
        )
    ]
    result = await svc.evaluate(incoming, candidates)
    assert result.decisions[0].outcome == ConflictOutcome.ESCALATE_PENDING
