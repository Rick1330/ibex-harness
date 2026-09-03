"""Extraction output schema v2 (milestone 3.5.B.1 / ADR-0063).

Maps onto the live memory write-path ``labels[]`` contract (ADR-0048 / 3.C.4):
each category is ``{label, confidence}`` with the same five-value enum as
``ibex_core.memory_labels``. Temporal fields mirror ``memories_valid_interval_chk``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Same CHECK constraint values as infra/migrations/postgres/000015 and
# services/memory/app/write/labels.py VALID_LABELS — keep in sync.
VALID_LABELS = frozenset(
    {"factual", "preference", "behavioral", "episodic", "procedural"}
)
MemoryLabelName = Literal[
    "factual", "preference", "behavioral", "episodic", "procedural"
]

CONTENT_MIN_LENGTH = 5
CONTENT_MAX_LENGTH = 10_000
CONTENT_MAX_BYTES = 10_000  # memories_content_max: octet_length(content) <= 10000
MAX_CATEGORIES_PER_MEMORY = 3
MAX_MEMORIES_PER_TURN = 10


class ExtractedMemoryLabel(BaseModel):
    """One category assignment — shape-compatible with MemoryLabelSchema / labels[]."""

    label: MemoryLabelName
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractedMemory(BaseModel):
    """One extracted memory candidate for a conversation turn."""

    content: str = Field(min_length=CONTENT_MIN_LENGTH, max_length=CONTENT_MAX_LENGTH)
    categories: list[ExtractedMemoryLabel] = Field(
        min_length=1, max_length=MAX_CATEGORIES_PER_MEMORY
    )
    confidence: float = Field(ge=0.0, le=1.0)
    valid_from: datetime | None = None
    valid_until: datetime | None = None

    @field_validator("content")
    @classmethod
    def content_utf8_byte_limit(cls, value: str) -> str:
        encoded_len = len(value.encode("utf-8"))
        if encoded_len > CONTENT_MAX_BYTES:
            raise ValueError(
                f"content exceeds {CONTENT_MAX_BYTES} UTF-8 bytes "
                f"(got {encoded_len}; matches memories_content_max)"
            )
        return value

    @field_validator("categories")
    @classmethod
    def categories_unique_and_known(
        cls, value: list[ExtractedMemoryLabel]
    ) -> list[ExtractedMemoryLabel]:
        seen: set[str] = set()
        for item in value:
            if item.label not in VALID_LABELS:
                raise ValueError(f"unknown category label: {item.label!r}")
            if item.label in seen:
                raise ValueError(f"duplicate category label: {item.label!r}")
            seen.add(item.label)
        return value

    @model_validator(mode="after")
    def valid_interval_matches_db(self) -> ExtractedMemory:
        """Mirror memories_valid_interval_chk: valid_until IS NULL OR valid_until > valid_from."""
        start = self.valid_from
        end = self.valid_until
        if start is None or end is None:
            return self
        if (start.tzinfo is None) != (end.tzinfo is None):
            raise ValueError(
                "valid_from and valid_until must both be timezone-aware or both naive"
            )
        if end <= start:
            raise ValueError(
                "valid_until must be greater than valid_from "
                "(matches memories_valid_interval_chk)"
            )
        return self


class ExtractionResult(BaseModel):
    """Structured LLM extraction output for one turn (B.1)."""

    memories: list[ExtractedMemory] = Field(default_factory=list)

    @field_validator("memories")
    @classmethod
    def cap_per_turn(cls, value: list[ExtractedMemory]) -> list[ExtractedMemory]:
        if len(value) > MAX_MEMORIES_PER_TURN:
            raise ValueError(
                f"at most {MAX_MEMORIES_PER_TURN} memories per turn "
                f"(got {len(value)})"
            )
        return value


class TurnExtraction(BaseModel):
    """Extraction for one turn index inside a session batch (B.2)."""

    turn_index: int = Field(ge=0)
    memories: list[ExtractedMemory] = Field(default_factory=list)

    @field_validator("memories")
    @classmethod
    def cap_per_turn(cls, value: list[ExtractedMemory]) -> list[ExtractedMemory]:
        if len(value) > MAX_MEMORIES_PER_TURN:
            raise ValueError(
                f"at most {MAX_MEMORIES_PER_TURN} memories per turn "
                f"(got {len(value)})"
            )
        return value


class BatchExtractionResult(BaseModel):
    """Session-close batch extraction keyed by turn_index."""

    turns: list[TurnExtraction] = Field(default_factory=list)

    @field_validator("turns")
    @classmethod
    def unique_turn_indexes(cls, value: list[TurnExtraction]) -> list[TurnExtraction]:
        seen: set[int] = set()
        for item in value:
            if item.turn_index in seen:
                raise ValueError(f"duplicate turn_index: {item.turn_index}")
            seen.add(item.turn_index)
        return value
