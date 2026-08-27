"""Conflict detection result types (m3.C.3 / ADR-0056)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.conflict.intervals import ValidityInterval


class ConflictOutcome(StrEnum):
    SUPERSEDES = "supersedes"
    CONTRADICTS = "contradicts"
    NEAR_DUPLICATE = "near_duplicate"
    UNRELATED = "unrelated"
    NO_CONFLICT = "no_conflict"
    ESCALATE_PENDING = "escalate_pending"


@dataclass(frozen=True, slots=True)
class CandidateMemory:
    memory_id: UUID
    content: str
    interval: ValidityInterval
    confidence: float = 0.80


@dataclass(frozen=True, slots=True)
class IncomingMemory:
    content: str
    interval: ValidityInterval
    memory_id: UUID | None = None
    confidence: float = 0.80


@dataclass(frozen=True, slots=True)
class ConflictDecision:
    candidate_id: UUID
    outcome: ConflictOutcome
    llm_call_made: bool
    subject_key: str
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ConflictEvaluation:
    decisions: list[ConflictDecision] = field(default_factory=list)
    llm_calls: int = 0

    @property
    def supersede_targets(self) -> list[UUID]:
        return [
            d.candidate_id
            for d in self.decisions
            if d.outcome == ConflictOutcome.SUPERSEDES
        ]


@dataclass(frozen=True, slots=True)
class SupersedeApply:
    org_id: UUID
    new_memory_id: UUID
    target_memory_id: UUID
    confidence: float = 0.90
    closed_at: datetime | None = None
