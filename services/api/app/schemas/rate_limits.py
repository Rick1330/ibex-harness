"""Rate-limit override request/response schemas (RPM only)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

RPM = Annotated[int, Field(ge=1, le=1_000_000)]


class AgentRateLimitOverride(BaseModel):
    agent_id: UUID
    requests_per_minute: RPM | None = Field(
        default=None,
        description="Per-agent RPM; null clears the override",
    )


class RateLimitsPatchRequest(BaseModel):
    requests_per_minute: RPM | None = Field(
        default=None,
        description="Org-level RPM; omit to leave unchanged; use agent clears separately",
    )
    clear_org_override: bool = Field(
        default=False,
        description="When true, delete the org-level override row (revert to platform default)",
    )
    agent_overrides: list[AgentRateLimitOverride] = Field(default_factory=list)


class AgentRateLimitView(BaseModel):
    agent_id: UUID
    requests_per_minute: int
    source: str  # "override" | "default"


class RateLimitsResponse(BaseModel):
    org_id: UUID
    requests_per_minute: int
    source: str  # "override" | "default"
    platform_default_rpm: int
    current_minute_requests: int
    agent_overrides: list[AgentRateLimitView] = Field(default_factory=list)
