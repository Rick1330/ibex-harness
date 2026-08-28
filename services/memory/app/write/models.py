"""Write orchestration command and outcome models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.conflict.types import ConflictDecision


class WriteOutcomeKind(StrEnum):
    CREATED = "created"
    QUARANTINED = "quarantined"


@dataclass(frozen=True, slots=True)
class CreateMemoryCommand:
    org_id: UUID
    agent_id: UUID
    content: str
    category: str = "factual"
    confidence: float = 0.80
    session_id: UUID | None = None
    metadata: dict[str, Any] | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None


@dataclass(frozen=True, slots=True)
class MemoryRow:
    id: UUID
    org_id: UUID
    agent_id: UUID
    content: str
    content_tokens: int
    category: str
    confidence: float
    status: str
    source: str
    pii_detected: bool
    pii_redacted: bool
    session_id: UUID | None
    metadata: dict[str, Any]
    retrieval_count: int
    usefulness_score: float
    valid_from: datetime
    valid_until: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class WriteOutcome:
    kind: WriteOutcomeKind
    memory: MemoryRow
    near_duplicate_candidates: tuple[UUID, ...] = ()
    conflict_decisions: tuple[ConflictDecision, ...] = ()
    embedding: tuple[float, ...] | None = None
    embedding_model: str | None = None
