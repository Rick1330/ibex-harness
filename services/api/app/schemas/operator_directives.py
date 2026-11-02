"""Tenant-scoped, metadata-only operator directive reads.

Directive *content* is deliberately absent. `directive_versions.content` is the
operator's instruction text, and `AGENTS.md` forbids exposing it by default; a
content/diff read model needs its own contract and the stronger
`OPERATOR_REDACTED_READ` bit.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.pagination import PaginationMeta

DirectiveInjectionMode = Literal["system_first", "system_append", "user_prepend"]
DirectiveStateFilter = Literal["all", "active", "inactive"]
DirectiveUsageRange = Literal["24h", "7d", "30d"]


class OperatorDirectiveSummary(BaseModel):
    """One row per agent directive; `active_version_num` is the live pointer."""

    id: UUID
    agent_id: UUID
    agent_name: str
    agent_slug: str
    is_active: bool
    injection_mode: DirectiveInjectionMode
    active_version_num: int | None = None
    version_count: int = Field(ge=0)
    last_version_at: datetime | None = None
    updated_at: datetime


class OperatorDirectiveVersion(BaseModel):
    """A version's identity, never its instruction text.

    `content_digest` is a 12-character prefix of the stored SHA-256: enough to
    see that two versions differ, not a verifier for the content itself.
    """

    version_num: int = Field(ge=1)
    content_digest: str = Field(min_length=1, max_length=64)
    content_bytes: int = Field(ge=1)
    created_by: UUID | None = None
    created_at: datetime
    is_live: bool


class OperatorDirectiveUsage(BaseModel):
    """Sessions that resolved to a version in the window, from the evidence snapshot."""

    version_num: int = Field(ge=1)
    sessions: int = Field(ge=0)
    last_session_at: datetime | None = None


class OperatorDirectiveDetail(OperatorDirectiveSummary):
    """`version_count` is the true total, not the size of `versions`.

    The list carries the newest `VERSIONS_LIMIT` versions plus the pointed
    version when it is older than that window, so a rollback stays visible on a
    long history. `versions_truncated` says the timeline is partial.
    """

    versions: list[OperatorDirectiveVersion] = Field(default_factory=list)
    versions_truncated: bool = False
    usage: list[OperatorDirectiveUsage] = Field(default_factory=list)
    # The table lists at most USAGE_LIMIT versions by session count; the total is
    # exact, so a truncated table never understates the window.
    usage_truncated: bool = False
    usage_total_sessions: int = Field(default=0, ge=0)
    usage_range: DirectiveUsageRange
    usage_window_start: datetime
    observed_at: datetime
    # True when the pointer names a version that is not in `versions`, which can
    # only happen if the two reads disagree; the UI must not guess a live version.
    active_version_missing: bool = False


class OperatorDirectivePage(BaseModel):
    """One keyset page plus the read time relative ages are measured against."""

    data: list[OperatorDirectiveSummary]
    pagination: PaginationMeta
    observed_at: datetime


class OperatorDirectiveListQuery(BaseModel):
    state: DirectiveStateFilter = "all"
    agent_id: UUID | None = None
    cursor: str | None = Field(default=None, max_length=2048)
    limit: int = Field(default=50, ge=1, le=100)


class OperatorDirectiveDetailQuery(BaseModel):
    range: DirectiveUsageRange = "7d"
