"""Strict read-only response contracts for the D1 operator shell."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

OperatorRole = Literal["owner", "admin", "member", "viewer"]


class OperatorContextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["operator.context.v1"] = "operator.context.v1"
    org_id: UUID
    role: OperatorRole | None
    org_name: str = Field(min_length=1, max_length=200)
    org_slug: str = Field(min_length=1, max_length=100)
    org_status: str = Field(min_length=1, max_length=32)
    observed_at: AwareDatetime


class OperatorOverviewCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_users: int = Field(ge=0)
    agents: int = Field(ge=0)
    active_agents: int = Field(ge=0)


class OperatorOverviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["operator.overview.v1"] = "operator.overview.v1"
    org_id: UUID
    org_name: str = Field(min_length=1, max_length=200)
    org_slug: str = Field(min_length=1, max_length=100)
    org_status: str = Field(min_length=1, max_length=32)
    counts: OperatorOverviewCounts
    observed_at: AwareDatetime
    completeness: Literal["complete"] = "complete"


class OperatorD1ReadModel(BaseModel):
    """Internal composition model; never exposes organization settings or secrets."""

    model_config = ConfigDict(extra="forbid")

    context: OperatorContextResponse
    overview: OperatorOverviewResponse
    observed_at: datetime
