"""Unit tests for ConflictService auto-supersede vs escalate."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.config import Settings
from app.conflict.classifier import NoopConflictClassifier
from app.conflict.intervals import ValidityInterval
from app.conflict.service import ConflictService
from app.conflict.types import (
    CandidateMemory,
    ConflictEvaluation,
    ConflictOutcome,
    IncomingMemory,
)


def _dt(month: int) -> datetime:
    return datetime(2026, month, 1, tzinfo=UTC)


def _subject(_: str) -> str:
    return "preference language"


class _FixedClassifier:
    invokes_llm = True

    def __init__(self, outcome: ConflictOutcome) -> None:
        self.outcome = outcome
        self.calls = 0

    async def classify(self, incoming, candidate):
        del incoming, candidate
        self.calls += 1
        return self.outcome


def _incoming(
    content: str,
    *,
    from_month: int,
    until_month: int | None = None,
) -> IncomingMemory:
    until = None if until_month is None else _dt(until_month)
    return IncomingMemory(
        content=content,
        interval=ValidityInterval(valid_from=_dt(from_month), valid_until=until),
    )


def _candidate(
    content: str,
    *,
    from_month: int,
    until_month: int | None = None,
    memory_id: UUID | None = None,
) -> CandidateMemory:
    until = None if until_month is None else _dt(until_month)
    return CandidateMemory(
        memory_id=memory_id or uuid4(),
        content=content,
        interval=ValidityInterval(valid_from=_dt(from_month), valid_until=until),
    )


async def _evaluate(
    *,
    incoming: IncomingMemory,
    candidates: list[CandidateMemory],
    subject: Callable[[str], str] = _subject,
    classifier: object | None = None,
) -> ConflictEvaluation:
    svc = ConflictService(
        Settings(),
        classifier=classifier,  # type: ignore[arg-type]
        subject_extractor=subject,
    )
    return await svc.evaluate(incoming, candidates)


@pytest.mark.asyncio
async def test_sequential_fact_supersedes_without_llm() -> None:
    """Python (Mar–Jun) → Go (Jun+) same subject: supersedes, zero LLM."""
    classifier = _FixedClassifier(ConflictOutcome.CONTRADICTS)
    old_id = uuid4()
    result = await _evaluate(
        incoming=_incoming("User is switching to Go", from_month=6),
        candidates=[
            _candidate(
                "User prefers Python",
                from_month=3,
                until_month=6,
                memory_id=old_id,
            )
        ],
        classifier=classifier,
    )
    assert result.llm_calls == 0
    assert classifier.calls == 0
    assert result.decisions[0].outcome == ConflictOutcome.SUPERSEDES
    assert result.supersede_targets == [old_id]


@pytest.mark.asyncio
async def test_overlapping_intervals_escalate_to_classifier() -> None:
    classifier = _FixedClassifier(ConflictOutcome.CONTRADICTS)
    result = await _evaluate(
        incoming=_incoming("User prefers Python", from_month=3),
        candidates=[_candidate("User prefers Go", from_month=3)],
        classifier=classifier,
    )
    assert result.llm_calls == 1
    assert classifier.calls == 1
    assert result.decisions[0].outcome == ConflictOutcome.CONTRADICTS
    assert result.decisions[0].llm_call_made is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("subject_fn", "incoming_text", "candidate_text", "expected"),
    [
        (
            lambda text: "python" if "Python" in text else "coffee",
            "User prefers coffee",
            "User prefers Python",
            ConflictOutcome.NO_CONFLICT,
        ),
        (
            lambda text: (
                "user prefer python" if "Python" in text else "user live seattle"
            ),
            "User lives in Seattle",
            "User prefers Python",
            ConflictOutcome.NO_CONFLICT,
        ),
    ],
)
async def test_non_matching_subjects_skip_supersede(
    subject_fn: Callable[[str], str],
    incoming_text: str,
    candidate_text: str,
    expected: ConflictOutcome,
) -> None:
    result = await _evaluate(
        incoming=_incoming(incoming_text, from_month=6),
        candidates=[
            _candidate(candidate_text, from_month=3, until_month=6),
        ],
        subject=subject_fn,
    )
    assert result.llm_calls == 0
    assert result.decisions[0].outcome == expected


@pytest.mark.asyncio
async def test_noop_classifier_returns_escalate_pending() -> None:
    clf = NoopConflictClassifier()
    incoming = _incoming("a", from_month=3)
    candidate = _candidate("b", from_month=3)
    assert await clf.classify(incoming, candidate) == ConflictOutcome.ESCALATE_PENDING
    assert clf.invokes_llm is False


@pytest.mark.asyncio
async def test_noop_escalation_does_not_count_llm_calls() -> None:
    result = await _evaluate(
        incoming=_incoming("User prefers Python", from_month=3),
        candidates=[_candidate("User prefers Go", from_month=3)],
        classifier=NoopConflictClassifier(),
    )
    assert result.llm_calls == 0
    assert result.decisions[0].outcome == ConflictOutcome.ESCALATE_PENDING
    assert result.decisions[0].llm_call_made is False


@pytest.mark.asyncio
async def test_classifier_supersedes_rewritten_to_pending() -> None:
    result = await _evaluate(
        incoming=_incoming("a", from_month=3),
        candidates=[_candidate("b", from_month=3)],
        classifier=_FixedClassifier(ConflictOutcome.SUPERSEDES),
    )
    assert result.decisions[0].outcome == ConflictOutcome.ESCALATE_PENDING
