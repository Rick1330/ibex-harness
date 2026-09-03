"""Worker extraction package — schema contract and prompt v2 (3.5.B.1)."""

from __future__ import annotations

from app.extraction.prompt_v2 import EXTRACTION_SYSTEM_PROMPT_V2
from app.extraction.schema import (
    CONTENT_MAX_BYTES,
    CONTENT_MAX_LENGTH,
    CONTENT_MIN_LENGTH,
    MAX_CATEGORIES_PER_MEMORY,
    MAX_MEMORIES_PER_TURN,
    VALID_LABELS,
    ExtractedMemory,
    ExtractedMemoryLabel,
    ExtractionResult,
    MemoryLabelName,
)

__all__ = [
    "CONTENT_MAX_BYTES",
    "CONTENT_MAX_LENGTH",
    "CONTENT_MIN_LENGTH",
    "EXTRACTION_SYSTEM_PROMPT_V2",
    "MAX_CATEGORIES_PER_MEMORY",
    "MAX_MEMORIES_PER_TURN",
    "VALID_LABELS",
    "ExtractedMemory",
    "ExtractedMemoryLabel",
    "ExtractionResult",
    "MemoryLabelName",
]
