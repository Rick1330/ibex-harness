"""Token management request/response schemas."""

from __future__ import annotations

import ipaddress
from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, field_validator

NameStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]


class TokenCreateRequest(BaseModel):
    name: NameStr
    permissions: list[str] = Field(default_factory=list, max_length=64)
    allowed_ips: list[str] | None = Field(default=None, max_length=32)
    expires_at: datetime | None = None
    agent_id: UUID | None = None

    @field_validator("allowed_ips")
    @classmethod
    def _validate_cidrs(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned: list[str] = []
        for raw in value:
            try:
                network = ipaddress.ip_network(raw, strict=False)
            except ValueError as exc:
                msg = f"invalid CIDR: {raw!r}"
                raise ValueError(msg) from exc
            cleaned.append(str(network))
        return cleaned


class TokenCreateResponse(BaseModel):
    id: UUID
    name: str
    token: str
    permissions: list[str]
    prefix: str
    expires_at: datetime | None = None
    created_at: datetime


class TokenResponse(BaseModel):
    id: UUID
    name: str
    permissions: list[str]
    prefix: str
    expires_at: datetime | None = None
    created_at: datetime
    revoked_at: datetime | None = None
    is_revoked: bool = False
