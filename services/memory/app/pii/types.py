"""Typed results for the PII stage."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PiiFinding:
    entity_type: str
    start: int
    end: int
    score: float


@dataclass(slots=True)
class PiiProcessResult:
    """Outcome of analyze + confidence routing + optional typed redaction."""

    findings: list[PiiFinding] = field(default_factory=list)
    content: str = ""
    pii_detected: bool = False
    pii_redacted: bool = False
    status: str = "active"
    quarantine_reason: str | None = None
