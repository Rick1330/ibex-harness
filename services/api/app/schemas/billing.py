"""Billing / usage schemas for milestone 4.P.4."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, field_validator

Cents = Annotated[int, Field(ge=0)]
EnforcementMode = Literal["alert_only", "hard_cap"]
RateCardStatus = Literal["draft", "published", "archived"]
UsageShape = Literal[
    "org_time_aggregate",
    "agent_session_breakdown",
    "request_point_lookup",
    "fallback_attribution",
    "tool_correlation",
]


class PriceRow(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    model_pattern: str = Field(min_length=1, max_length=256)
    input_cents_per_1k: Cents
    output_cents_per_1k: Cents


class RateCardCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    currency: str = Field(default="USD", min_length=3, max_length=8)


class RateCardResponse(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    currency: str
    status: RateCardStatus
    created_at: datetime
    updated_at: datetime


class RateCardVersionPublish(BaseModel):
    prices: list[PriceRow] = Field(min_length=1, max_length=256)


class RateCardVersionResponse(BaseModel):
    id: UUID
    rate_card_id: UUID
    org_id: UUID
    version: int
    published_at: datetime
    prices: list[dict[str, Any]]


class BudgetPeriodCreate(BaseModel):
    period_start: AwareDatetime
    period_end: AwareDatetime
    cap_cents: Cents
    enforcement_mode: EnforcementMode = "alert_only"

    @field_validator("period_end")
    @classmethod
    def _window(cls, end: datetime, info) -> datetime:
        start = info.data.get("period_start")
        if start is not None and end <= start:
            raise ValueError("period_end must be after period_start")
        return end


class BudgetPeriodResponse(BaseModel):
    id: UUID
    org_id: UUID
    period_start: datetime
    period_end: datetime
    cap_cents: int
    spent_cents_cached: int
    enforcement_mode: EnforcementMode
    created_at: datetime
    updated_at: datetime


class UsageQueryRequest(BaseModel):
    shape: UsageShape
    start: AwareDatetime
    end: AwareDatetime
    agent_id: UUID | None = None
    request_id: str | None = Field(default=None, max_length=128)
    limit: int | None = Field(default=None, ge=1, le=10_000)

    @field_validator("end")
    @classmethod
    def _range(cls, end: datetime, info) -> datetime:
        start = info.data.get("start")
        if start is not None and end <= start:
            raise ValueError("end must be after start")
        return end


class UsageQueryResponse(BaseModel):
    shape: UsageShape
    org_id: UUID
    rows: list[dict[str, Any]]
    completeness: str = "partial"
    truncated: bool = False
