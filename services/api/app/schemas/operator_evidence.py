"""Tenant-scoped, metadata-only operator evidence summary."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

EvidenceRange = Literal["24h", "7d", "30d"]
EvidenceCompleteness = Literal[
    "complete",
    "partial",
    "sampled",
    "late",
    "redacted",
    "expired",
    "deleted",
    "simulated",
]
EvidenceRunStatus = Literal["ok", "error"]
EvidenceDeliveryStatus = Literal["pending", "in_flight", "delivered", "failed", "poison"]
EvidenceCaptureMode = Literal["none", "metadata_only", "redacted", "full"]


class EvidenceCompletenessCounts(BaseModel):
    """What the capture layer recorded, one bucket per `evidence_runs.completeness`."""

    complete: int = Field(default=0, ge=0)
    partial: int = Field(default=0, ge=0)
    sampled: int = Field(default=0, ge=0)
    late: int = Field(default=0, ge=0)
    redacted: int = Field(default=0, ge=0)
    expired: int = Field(default=0, ge=0)
    deleted: int = Field(default=0, ge=0)
    simulated: int = Field(default=0, ge=0)


class EvidenceStatusCounts(BaseModel):
    """Operation outcome, kept separate from capture completeness.

    Evidence of a failed operation is still complete evidence, so an `error` row
    does not lower the capture count.
    """

    ok: int = Field(default=0, ge=0)
    error: int = Field(default=0, ge=0)


class EvidenceDeliveryCounts(BaseModel):
    """Relay health for the same window, grouped by `evidence_outbox.delivery_status`."""

    pending: int = Field(default=0, ge=0)
    in_flight: int = Field(default=0, ge=0)
    delivered: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    poison: int = Field(default=0, ge=0)


class EvidenceCapturePolicy(BaseModel):
    """The capture policy that applies to the organization.

    `mode` is the effective mode; `None` means no policy row exists and the
    deployment default applies. `scope` names where the winning row applies.
    """

    mode: EvidenceCaptureMode | None = None
    scope: Literal["org", "agent"] | None = None
    agent_overrides: int = Field(default=0, ge=0)


class EvidenceLegalHold(BaseModel):
    """An active hold preserves data; it is not a completeness claim."""

    active: bool
    since: datetime | None = None


class OperatorEvidenceSummary(BaseModel):
    """`operator.evidence.summary.v1`.

    Every field states a fact this service can read. Nothing here is a verdict:
    the contract deliberately does not call a run "certified", because a run row
    holds no digest of its own — the only digest in the plane is
    `evidence_outbox.payload_digest`, per event.
    """

    schema_version: Literal["operator.evidence.summary.v1"] = "operator.evidence.summary.v1"
    range: EvidenceRange
    window_start: datetime
    window_end: datetime
    observed_at: datetime
    runs_total: int = Field(ge=0)
    capture_complete_runs: int = Field(ge=0)
    completeness: EvidenceCompletenessCounts
    statuses: EvidenceStatusCounts
    last_run_at: datetime | None = None
    delivery: EvidenceDeliveryCounts
    oldest_pending_at: datetime | None = None
    last_delivered_at: datetime | None = None
    capture_policy: EvidenceCapturePolicy
    legal_hold: EvidenceLegalHold


class OperatorEvidenceSummaryQuery(BaseModel):
    range: EvidenceRange = "24h"
