"""User request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

EmailAddress = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=320, pattern=r"^[^@]+@[^@]+\.[^@]+$"),
]

UserRole = Literal["owner", "admin", "member", "viewer"]
InviteRole = Literal["admin", "member", "viewer"]


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    email: EmailAddress
    name: str
    role: UserRole
    status: str
    created_at: datetime
    updated_at: datetime
    invite_token: str | None = None


class UserCreate(BaseModel):
    email: EmailAddress
    name: str = Field(min_length=1, max_length=200)
    role: InviteRole = "member"


class UserPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role: UserRole | None = None
