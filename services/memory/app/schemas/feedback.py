"""POST /v1/memories/{memory_id}/feedback request and response schemas."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

FeedbackLiteral = Literal["positive", "negative", "neutral"]


class RecordFeedbackRequest(BaseModel):
    feedback: FeedbackLiteral
    session_id: UUID | None = None
    trace_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


class RecordFeedbackData(BaseModel):
    memory_id: UUID
    feedback: FeedbackLiteral
    new_usefulness_score: float
    total_positive_feedback: int
    total_negative_feedback: int


class RecordFeedbackResponse(BaseModel):
    data: RecordFeedbackData
