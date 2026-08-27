"""In-memory write context shared across pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

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
    stop: bool = False
    error: str | None = None
