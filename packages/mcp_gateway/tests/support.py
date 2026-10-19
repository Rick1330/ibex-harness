"""Shared test fixtures/helpers for mcp_gateway unit tests."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class SampleArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str


class MissingRequiredArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str
    other: str


SAMPLE_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["resource_id", "status"],
    "properties": {
        "resource_id": {"type": "string"},
        "status": {"type": "string"},
        "detail": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "id": {"type": "string"},
                "content": {"type": "string"},
            },
        },
        "tags": {
            "type": "array",
            "items": {"type": "object", "properties": {"name": {"type": "string"}}},
        },
    },
}
