"""Dedup result types for the write pipeline (m3.C.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DedupResult:
    """Outcome of exact + near-duplicate checks (conflict handling is 3.C.3)."""

    is_exact_duplicate: bool
    existing_memory_id: UUID | None = None
    near_duplicate_candidates: list[UUID] = field(default_factory=list)
    content_hash: str | None = None
