"""Tenant-scoped, metadata-only deletion evidence for the operator surface.

This contract answers the three questions a deletion record exists for — what was
tombstoned, did every store confirm the erasure, and is the audit chain intact —
without reading a single payload, hold reason, or memory body.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DeletionRange = Literal["24h", "7d", "30d"]
TombstoneEvent = Literal["forgotten", "expired", "purged"]
ErasureStatus = Literal["pending", "running", "succeeded", "failed", "hold_blocked"]
DeletionStore = Literal["postgres", "clickhouse", "redis", "objectstore"]
ReceiptStatus = Literal["pending", "verified", "failed", "not_applicable"]

JOBS_LIMIT = 20


class TombstoneEventCounts(BaseModel):
    forgotten: int = Field(default=0, ge=0)
    expired: int = Field(default=0, ge=0)
    purged: int = Field(default=0, ge=0)


class TombstoneSummary(BaseModel):
    """What was tombstoned in the window, and whether propagation finished."""

    events: TombstoneEventCounts
    # Lifecycle outbox rows for deletion events that have not been delivered.
    pending: int = Field(default=0, ge=0)
    oldest_pending_at: datetime | None = None
    last_event_at: datetime | None = None
    # The current visibility fence, independent of the window.
    tombstoned_memories: int = Field(default=0, ge=0)


class ErasureStatusCounts(BaseModel):
    pending: int = Field(default=0, ge=0)
    running: int = Field(default=0, ge=0)
    succeeded: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    hold_blocked: int = Field(default=0, ge=0)


class StoreReceipt(BaseModel):
    store: DeletionStore
    status: ReceiptStatus
    verified_absent_at: datetime | None = None


class ErasureJob(BaseModel):
    id: str
    status: ErasureStatus
    created_at: datetime
    finished_at: datetime | None = None
    receipts: list[StoreReceipt] = Field(default_factory=list)


class AuditChainSummary(BaseModel):
    """Structural continuity of `privacy_audit_ledger`, not content verification.

    `continuity_ok` means `seq` has no gaps and every `prev_hash` equals the
    previous `row_hash`. Re-deriving `row_hash` from the payload is the CLI
    verifier's job; doing it here would duplicate the canonicalisation.
    """

    entries: int = Field(default=0, ge=0)
    first_seq: int | None = None
    last_seq: int | None = None
    continuity_ok: bool = True
    broken_at_seq: int | None = None
    last_row_hash: str | None = None


class OperatorEvidenceDeletions(BaseModel):
    schema_version: Literal["operator.evidence.deletions.v1"] = "operator.evidence.deletions.v1"
    range: DeletionRange
    window_start: datetime
    window_end: datetime
    observed_at: datetime
    tombstones: TombstoneSummary
    erasures: ErasureStatusCounts
    jobs: list[ErasureJob] = Field(default_factory=list)
    jobs_truncated: bool = False
    audit: AuditChainSummary


class OperatorEvidenceDeletionsQuery(BaseModel):
    range: DeletionRange = "24h"
