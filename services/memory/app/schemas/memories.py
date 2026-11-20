"""POST /v1/memories request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.limits import MAX_LABELS, MAX_TAGS, validate_memory_metadata, validate_tags

_CATEGORIES = Literal["factual", "preference", "behavioral", "episodic", "procedural"]
_VISIBILITY = Literal["agent", "org", "session"]


class MemoryLabelSchema(BaseModel):
    label: _CATEGORIES
    confidence: float = Field(ge=0.0, le=1.0)


class CreateMemoryRequest(BaseModel):
    agent_id: UUID
    content: str = Field(min_length=1, max_length=10_000)
    category: _CATEGORIES = "factual"
    confidence: float = Field(default=0.80, ge=0.0, le=1.0)
    labels: list[MemoryLabelSchema] | None = Field(default=None, max_length=MAX_LABELS)
    session_id: UUID | None = None
    visibility: _VISIBILITY = "agent"
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS)
    metadata: dict[str, Any] | None = None
    pinned: bool = False
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    expires_at: datetime | None = None
    expected_session_revision: int | None = Field(default=None, ge=1, le=2**63 - 1)

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, value: list[str]) -> list[str]:
        return validate_tags(value)

    @model_validator(mode="after")
    def _validate_metadata_and_interval(self) -> CreateMemoryRequest:
        validate_memory_metadata(self.metadata)
        if self.session_id is not None and self.expected_session_revision is None:
            raise ValueError("expected_session_revision is required when session_id is set")
        if self.session_id is None and self.expected_session_revision is not None:
            raise ValueError("expected_session_revision requires session_id")
        start = self.valid_from
        end = self.valid_until
        if start is None or end is None:
            return self
        if (start.tzinfo is None) != (end.tzinfo is None):
            raise ValueError("valid_from and valid_until must both be timezone-aware or both naive")
        if end <= start:
            raise ValueError(
                "valid_until must be greater than valid_from (matches memories_valid_interval_chk)"
            )
        return self


class MemoryData(BaseModel):
    id: UUID
    agent_id: UUID
    org_id: UUID
    content: str
    content_tokens: int
    category: str
    confidence: float
    source: str
    status: str
    visibility: str = "agent"
    pinned: bool = False
    tags: list[str] = Field(default_factory=list)
    retrieval_count: int
    usefulness_score: float
    pii_detected: bool
    session_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    lifecycle_revision: int = 1


class DeduplicationMeta(BaseModel):
    is_duplicate: bool = False
    similar_memories: list[UUID] = Field(default_factory=list)


class CreateMemoryMeta(BaseModel):
    deduplication: DeduplicationMeta = Field(default_factory=DeduplicationMeta)
    processing_time_ms: int
    message: str | None = None


class CreateMemoryResponse(BaseModel):
    data: MemoryData
    meta: CreateMemoryMeta


class QuarantineMemoryData(BaseModel):
    id: UUID
    status: Literal["quarantined"]
    lifecycle_revision: int = 1
    pii_detected: bool = True
    #: ``pii_low_confidence`` or ``prompt_injection_heuristic``; derived from the
    #: persisted row, never stored as a column.
    quarantine_reason: str | None = None


class QuarantineMemoryResponse(BaseModel):
    data: QuarantineMemoryData
    meta: dict[str, str]


class ForgetMemoryRequest(BaseModel):
    expected_revision: int = Field(ge=1, le=2**63 - 1)


class ForgetMemoryData(BaseModel):
    memory_id: UUID
    revision: int
    tombstoned: Literal[True] = True


ErasureStoreState = Literal["pending", "verified", "failed", "not_applicable"]
ErasureJobState = Literal["pending", "partial", "complete", "failed"]


class ErasureStores(BaseModel):
    """Per-store erasure proof for the revision this response describes.

    ``not_applicable`` means the memory had no copy recorded in that store — it
    is never a substitute for ``verified``, and never a report of an unreachable
    store.

    ClickHouse is deliberately absent. The per-memory consumer can only prove a
    store whose copies are recorded in ``memory_artifact_refs``, and nothing
    records a per-memory ClickHouse locator, so an absent ref there means "not
    checked", not "no copy". Reporting a store this response cannot speak for
    would either over-claim (``not_applicable``/``verified``) or read as work
    still queued (``pending``) that will never happen. ClickHouse evidence is
    erased by the org-deletion saga, which proves absence org-wide.

    ``cache`` and ``cache_hot`` are the two Redis structures that can hold a
    memory after a write. They are separate because their purge verbs differ: the
    object entry is deleted, the hot sorted set loses one member. A ``failed``
    cache receipt is outstanding work the worker sweep retries, not a report of a
    completed forget.

    A ``verified`` receipt proves the addresses its proof covered, not the whole
    store. When the response's job ``state`` is ``failed``, no store is reported
    ``verified``: the consumer keeps an earlier ``verified`` receipt rather than
    downgrade a proof over an outage, and this field stops presenting it as the
    store's current state. The downgrade is deliberately coarse, so while
    ``state`` is ``failed`` this map is a **lower bound**: a store reported
    ``failed`` may in fact be proven for every address this revision records.
    ``state`` is the only authority on whether the erasure settled.
    """

    objectstore: ErasureStoreState = "pending"
    session_event: ErasureStoreState = "pending"
    cache: ErasureStoreState = "pending"
    cache_hot: ErasureStoreState = "pending"



class ErasureStatus(BaseModel):
    """Whether the memory's copies outside PostgreSQL are proven gone.

    ``pending`` is the honest answer while the consumer has not run yet, which is
    the normal state immediately after a forget. ``failed`` is terminal: at least
    one store did not confirm erasure before the deadline, so ``state`` is the
    only authority on whether the erasure settled; ``stores.*`` is a lower bound
    while it is ``failed`` — see :class:`ErasureStores`.
    """

    state: ErasureJobState = "pending"
    stores: ErasureStores = Field(default_factory=ErasureStores)


class ForgetMemoryResponse(BaseModel):
    data: ForgetMemoryData
    erasure: ErasureStatus = Field(default_factory=ErasureStatus)
