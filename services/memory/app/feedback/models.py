"""Feedback apply command and result models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class FeedbackKind(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class ApplyFeedbackCommand:
    org_id: UUID
    agent_id: UUID
    memory_id: UUID
    feedback: FeedbackKind
    session_id: UUID | None = None
    trace_id: UUID | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class ApplyFeedbackResult:
    memory_id: UUID
    feedback: FeedbackKind
    new_usefulness_score: float
    total_positive_feedback: int
    total_negative_feedback: int
    memory_agent_id: UUID
