"""Unit tests for conflict type validation."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.conflict.intervals import ValidityInterval
from app.conflict.types import CandidateMemory, IncomingMemory


def _interval() -> ValidityInterval:
    return ValidityInterval(valid_from=datetime(2026, 3, 1, tzinfo=UTC))


@pytest.mark.parametrize("confidence", [0.0, 1.0, 0.5])
def test_candidate_confidence_boundaries(confidence: float) -> None:
    row = CandidateMemory(
        memory_id=uuid4(),
        content="x",
        interval=_interval(),
        confidence=confidence,
    )
    assert row.confidence == confidence


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_candidate_confidence_rejects_out_of_range(confidence: float) -> None:
    memory_id = uuid4()
    interval = _interval()
    with pytest.raises(ValueError, match="confidence"):
        CandidateMemory(
            memory_id=memory_id,
            content="x",
            interval=interval,
            confidence=confidence,
        )


@pytest.mark.parametrize("confidence", [0.0, 1.0])
def test_incoming_confidence_boundaries(confidence: float) -> None:
    row = IncomingMemory(content="x", interval=_interval(), confidence=confidence)
    assert row.confidence == confidence


@pytest.mark.parametrize("confidence", [-1.0, 2.0])
def test_incoming_confidence_rejects_out_of_range(confidence: float) -> None:
    interval = _interval()
    with pytest.raises(ValueError, match="confidence"):
        IncomingMemory(content="x", interval=interval, confidence=confidence)
