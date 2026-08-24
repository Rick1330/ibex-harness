"""API request/response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(default="ok", examples=["ok"])


class ReadyResponse(BaseModel):
    status: str = Field(default="ready", examples=["ready"])
    profile: str
    model_id: str
    dimensions: int
    backend: str


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class EmbedRequest(BaseModel):
    texts: list[str] = Field(..., description="Text batch to embed (1..64 items)")


class EmbedResponse(BaseModel):
    vectors: list[list[float]]
    model_id: str
    dimensions: int
    backend: str
