"""Step-up proof issuance schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class StepUpRequest(BaseModel):
    """What the caller asks to elevate to, and the TOTP code proving it can.

    The org, subject, and session the proof binds to are never read from here:
    they come from the verified bearer token.
    """

    action: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=6, max_length=64)


class StepUpResponse(BaseModel):
    token: str
    expires_at: datetime | None = None
