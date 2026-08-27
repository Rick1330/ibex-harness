"""Unit tests for ConflictService auto-supersede vs escalate."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class _Snippet:
    content: str
    from_month: int
    until_month: int | None = None
    memory_id: UUID | None = None


def _interval(snippet: _Snippet) -> ValidityInterval:
    until = None if snippet.until_month is None else _dt(snippet.until_month)
    return ValidityInterval(valid_from=_dt(snippet.from_month), valid_until=until)


def _pair(inc: _Snippet, cand: _Snippet) -> tuple[IncomingMemory, CandidateMemory]:
    """Build incoming + candidate from snippets (shared interval helper)."""
    return (
        IncomingMemory(content=inc.content, interval=_interval(inc)),
        CandidateMemory(
            memory_id=cand.memory_id or uuid4(),
            content=cand.content,
            interval=_interval(cand),
        ),
    )


async def _evaluate(
    pair: tuple[IncomingMemory, CandidateMemory],
    *,
    subject: Callable[[str], str] = _subject,
    classifier: object | None = None,
) -> ConflictEvaluation:
    incoming, candidate = pair
    svc = ConflictService(
        Settings(),
        classifier=classifier,  # type: ignore[arg-type]
        subject_extractor=subject,
    )
    return await svc.evaluate(incoming, [candidate])


@pytest.mark.asyncio
async def test_sequential_fact_supersedes_without_llm() -> None:
    """Python (Mar–Jun) → Go (Jun+) same subject: supersedes, zero LLM."""
    classifier = _FixedClassifier(ConflictOutcome.CONTRADICTS)
    old_id = uuid4()
    result = await _evaluate(
        _pair(
            _Snippet("User is switching to Go", 6),
            _Snippet("User prefers Python", 3, until_month=6, memory_id=old_id),
        ),
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
        _pair(_Snippet("User prefers Python", 3), _Snippet("User prefers Go", 3)),
        classifier=classifier,
    )
    assert result.llm_calls == 1
    assert classifier.calls == 1
    assert result.decisions[0].outcome == ConflictOutcome.CONTRADICTS
    assert result.decisions[0].llm_call_made is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("subject_fn", "incoming_text", "candidate_text"),
    [
        (
            lambda text: "python" if "Python" in text else "coffee",
            "User prefers coffee",
            "User prefers Python",
        ),
        (
            lambda text: (
                "user prefer python" if "Python" in text else "user live seattle"
            ),
            "User lives in Seattle",
            "User prefers Python",
        ),
    ],
)
async def test_non_matching_subjects_skip_supersede(
    subject_fn: Callable[[str], str],
    incoming_text: str,
    candidate_text: str,
) -> None:
    result = await _evaluate(
        _pair(
            _Snippet(incoming_text, 6),
            _Snippet(candidate_text, 3, until_month=6),
        ),
        subject=subject_fn,
    )
    assert result.llm_calls == 0
    assert result.decisions[0].outcome == ConflictOutcome.NO_CONFLICT


@pytest.mark.asyncio
async def test_noop_classifier_returns_escalate_pending() -> None:
    clf = NoopConflictClassifier()
    incoming, candidate = _pair(_Snippet("a", 3), _Snippet("b", 3))
    assert await clf.classify(incoming, candidate) == ConflictOutcome.ESCALATE_PENDING
    assert clf.invokes_llm is False


@pytest.mark.asyncio
async def test_noop_escalation_does_not_count_llm_calls() -> None:
    result = await _evaluate(
        _pair(_Snippet("User prefers Python", 3), _Snippet("User prefers Go", 3)),
        classifier=NoopConflictClassifier(),
    )
    assert result.llm_calls == 0
    assert result.decisions[0].outcome == ConflictOutcome.ESCALATE_PENDING
    assert result.decisions[0].llm_call_made is False


@pytest.mark.asyncio
async def test_classifier_supersedes_rewritten_to_pending() -> None:
    result = await _evaluate(
        _pair(_Snippet("a", 3), _Snippet("b", 3)),
        classifier=_FixedClassifier(ConflictOutcome.SUPERSEDES),
    )
    assert result.decisions[0].outcome == ConflictOutcome.ESCALATE_PENDING
