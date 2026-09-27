"""Versioned metadata-only DTOs for the first D2 trace read slice."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

EvidenceState = Literal[
    "complete", "partial", "sampled", "late", "redacted", "expired", "deleted", "simulated"
]
FreshnessState = Literal["fresh", "stale", "unknown"]
RetentionState = Literal["active", "expired", "deleted", "unknown"]
TraceStatus = Literal["ok", "error"]


class TraceEvidenceState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completeness: EvidenceState
    sample_decision: str = Field(min_length=1, max_length=32)
    freshness: FreshnessState
    retention: RetentionState
    source: Literal["postgres.evidence_runs"]
    source_watermark: None = None
    observed_at: AwareDatetime


class OperatorTraceListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(min_length=1, max_length=256)
    run_id: UUID
    request_id: str = Field(min_length=1, max_length=256)
    agent_id: UUID | None
    session_id: UUID | None
    checkpoint_id: UUID | None
    status: TraceStatus
    error_code: str | None = Field(default=None, max_length=128)
    started_at: AwareDatetime
    ended_at: AwareDatetime | None
    duration_ms: int | None = Field(default=None, ge=0)
    evidence: TraceEvidenceState


class OperatorTraceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["operator.trace-list.v1"] = "operator.trace-list.v1"
    items: list[OperatorTraceListItem] = Field(max_length=100)
    next_cursor: str | None = Field(default=None, max_length=2048)
    truncated: bool
    observed_at: AwareDatetime
    query_start: AwareDatetime
    query_end: AwareDatetime
    limit: int = Field(ge=1, le=100)


class OperatorTraceDetailResponse(OperatorTraceListItem):
    schema_version: Literal["operator.trace-detail.v1"] = "operator.trace-detail.v1"
    unavailable_sections: tuple[
        Literal["spans", "candidates", "score_explanation", "directives", "tools", "content"], ...
    ]
