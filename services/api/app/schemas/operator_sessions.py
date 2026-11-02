"""Metadata-only operator session read models.

The session projection omits message hashes, provider request ids, and ``org_id``.
Message content is not stored for checkpoints, so it cannot be exposed here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

SessionStatus = Literal["active", "completed", "abandoned", "error"]
EvidenceCompleteness = Literal[
    "complete", "partial", "sampled", "late", "redacted", "expired", "deleted", "simulated"
]
EvidenceStatus = Literal["ok", "error"]

MAX_SESSION_TURNS = 500


class SessionTurnEvidence(BaseModel):
    trace_id: str = Field(min_length=1, max_length=256)
    run_id: UUID
    completeness: EvidenceCompleteness
    status: EvidenceStatus
    error_code: str | None = Field(default=None, max_length=128)
    started_at: datetime
    ended_at: datetime | None = None


class OperatorSessionTurn(BaseModel):
    id: UUID
    turn_index: int = Field(ge=0)
    request_id: str = Field(min_length=1, max_length=256)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    # The proxy bounds a model name at MaxModelNameLength (256) and stores it
    # unchanged, so a narrower projection would turn a saved session into a 500.
    model: str = Field(min_length=1, max_length=256)
    provider: str = Field(min_length=1, max_length=64)
    latency_ms: int = Field(ge=0)
    is_streaming: bool
    is_complete: bool
    created_at: datetime
    trace: SessionTurnEvidence | None = None


class OperatorSession(BaseModel):
    id: UUID
    agent_id: UUID
    external_id: str | None = Field(default=None, max_length=128)
    status: SessionStatus
    model: str = Field(min_length=1, max_length=256)
    provider: str = Field(min_length=1, max_length=64)
    directive_version_id: UUID | None = None
    turn_count: int = Field(ge=0)
    total_input_tokens: int = Field(ge=0)
    total_output_tokens: int = Field(ge=0)
    total_latency_ms: int = Field(ge=0)
    last_extracted_turn: int = Field(ge=0)
    lifecycle_revision: int = Field(ge=1)
    evidence_fence_version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class OperatorSessionDetail(OperatorSession):
    turns: list[OperatorSessionTurn] = Field(
        default_factory=list, max_length=MAX_SESSION_TURNS
    )
    turns_truncated: bool = False


class OperatorSessionListQuery(BaseModel):
    agent_id: UUID | None = None
    status: SessionStatus | None = None
    cursor: str | None = Field(default=None, max_length=2048)
    limit: int = Field(default=50, ge=1, le=100)
