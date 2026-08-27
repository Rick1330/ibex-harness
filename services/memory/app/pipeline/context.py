"""In-memory write context shared across pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.conflict.types import ConflictDecision
from app.pii.types import PiiFinding


@dataclass(slots=True)
class WriteContext:
    org_id: UUID
    content: str
    agent_id: UUID | None = None
    status: str = "active"
    pii_detected: bool = False
    pii_redacted: bool = False
    findings: list[PiiFinding] = field(default_factory=list)
    quarantine_reason: str | None = None
    embedding: list[float] | None = None
    content_hash: str | None = None
    is_exact_duplicate: bool = False
    existing_memory_id: UUID | None = None
    near_duplicate_candidates: list[UUID] = field(default_factory=list)
    # World-time validity for conflict stage (ADR-0047 / ADR-0056).
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    conflict_decisions: list[ConflictDecision] = field(default_factory=list)
    conflict_llm_calls: int = 0
    pending_supersede_targets: list[UUID] = field(default_factory=list)
    stop: bool = False
    error: str | None = None
