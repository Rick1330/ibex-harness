"""Versioned metadata-only DTOs for the 4.D.2 operator trace read plane."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

EvidenceState = Literal[
    "complete", "partial", "sampled", "late", "redacted", "expired", "deleted", "simulated"
]
FreshnessState = Literal["fresh", "stale", "unknown"]
RetentionState = Literal["expired", "deleted", "unknown"]
TraceStatus = Literal["ok", "error"]
PublicationState = Literal["published", "partial", "pending", "failed", "poison", "unavailable"]
QueryGrammarVersion = Literal["operator.trace-query.v1"]
UnavailableSection = Literal[
    "spans", "candidates", "score_explanation", "directives", "tools", "content", "events", "assembly"
]


class TraceEvidenceState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(min_length=1, max_length=64)
    capture_mode: str = Field(min_length=1, max_length=32)
    completeness: EvidenceState
    sample_decision: str = Field(min_length=1, max_length=32)
    freshness: FreshnessState
    retention: RetentionState
    source: Literal["postgres.evidence_runs"]
    source_watermark: str = Field(min_length=1, max_length=128)
    publication_state: PublicationState
    ingestion_lag_ms: int | None = Field(default=None, ge=0)
    policy_version: Literal["operator.trace-read.v1"] = "operator.trace-read.v1"
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
    query_grammar_version: QueryGrammarVersion = "operator.trace-query.v1"
    items: list[OperatorTraceListItem] = Field(max_length=100)
    next_cursor: str | None = Field(default=None, max_length=2048)
    truncated: bool
    matched_count: int | None = Field(default=None, ge=0)
    returned_count: int = Field(ge=0, le=100)
    observed_at: AwareDatetime
    query_start: AwareDatetime
    query_end: AwareDatetime
    limit: int = Field(ge=1, le=100)


class OperatorTraceListQuery(BaseModel):
    """Allowlisted Explore query grammar (operator.trace-query.v1)."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=50, ge=1, le=100)
    status: TraceStatus | None = None
    started_after: AwareDatetime | None = None
    started_before: AwareDatetime | None = None
    cursor: str | None = Field(default=None, max_length=2048)
    trace_id: str | None = Field(default=None, min_length=1, max_length=256)
    request_id: str | None = Field(default=None, min_length=1, max_length=256)
    run_id: UUID | None = None
    session_id: UUID | None = None
    error_code: str | None = Field(default=None, min_length=1, max_length=128)
    completeness: EvidenceState | None = None
    capture_mode: str | None = Field(default=None, min_length=1, max_length=32)


class OperatorTraceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    span_id: str = Field(min_length=1, max_length=64)
    parent_span_id: str | None = Field(default=None, max_length=64)
    operation_kind: str = Field(min_length=1, max_length=128)
    status: str = Field(min_length=1, max_length=32)
    error_code: str | None = Field(default=None, max_length=128)
    started_at: AwareDatetime
    ended_at: AwareDatetime | None


class OperatorTraceAssemblyMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget_calculation_ms: int = Field(ge=0)
    directive_load_ms: int = Field(ge=0)
    hot_memory_retrieval_ms: int = Field(ge=0)
    cold_memory_retrieval_ms: int = Field(ge=0)
    ranking_ms: int = Field(ge=0)
    packing_ms: int = Field(ge=0)
    formatting_ms: int = Field(ge=0)
    total_ms: int = Field(ge=0)
    candidates_evaluated: int = Field(ge=0)


class OperatorTraceCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: UUID
    retrieval_rank: int = Field(ge=0)
    final_rank: int | None = Field(default=None, ge=0)
    delta_rank: int | None = None
    category: str | None = Field(default=None, max_length=64)
    token_estimate: int | None = Field(default=None, ge=0)
    exclusion: str = Field(min_length=1, max_length=32)
    score_schema: str = Field(min_length=1, max_length=64)
    composite_score: float | None = None


class OperatorTraceDirectiveSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    directive_version_id: UUID | None = None
    content_hash: str | None = Field(default=None, max_length=128)
    schema_version: str = Field(min_length=1, max_length=64)


class OperatorTraceToolAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1, max_length=128)
    status: str = Field(min_length=1, max_length=32)
    error_code: str | None = Field(default=None, max_length=128)
    started_at: AwareDatetime | None = None
    ended_at: AwareDatetime | None = None


class OperatorTraceDetailResponse(OperatorTraceListItem):
    schema_version: Literal["operator.trace-detail.v1"] = "operator.trace-detail.v1"
    unavailable_sections: tuple[UnavailableSection, ...]
    spans: list[OperatorTraceSpan] = Field(default_factory=list, max_length=500)
    assembly: OperatorTraceAssemblyMetrics | None = None
    candidates: list[OperatorTraceCandidate] = Field(default_factory=list, max_length=500)
    directive: OperatorTraceDirectiveSnapshot | None = None
    tools: list[OperatorTraceToolAudit] = Field(default_factory=list, max_length=200)
    score_schema_note: str | None = Field(
        default=None,
        max_length=256,
        description="Present when score rows exist but interim_v1 forbids waterfall rendering.",
    )
