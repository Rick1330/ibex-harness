"""Strict JSON schemas and deterministic stub handlers for MCP memory tools."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.errors import PermissionDeniedError, SchemaError
from app.permissions import MEMORY_READ, MEMORY_WRITE, has_permission
from app.principal import Principal

# Deterministic stub IDs — not a persistence keyspace.
_STUB_NAMESPACE = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
Category = Literal["fact", "preference", "procedure", "context", "other"]

SEARCH_MEMORY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["query"],
    "properties": {
        "query": {"type": "string", "minLength": 1, "maxLength": 2000},
        "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 5},
        "agent_id": {"type": "string", "format": "uuid"},
    },
}

WRITE_MEMORY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["content"],
    "properties": {
        "content": {"type": "string", "minLength": 1, "maxLength": 8000},
        "category": {
            "type": "string",
            "enum": ["fact", "preference", "procedure", "context", "other"],
            "default": "fact",
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0, "default": 0.6},
        "agent_id": {"type": "string", "format": "uuid"},
    },
}


class SearchMemoryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=50)
    agent_id: UUID | None = None


class WriteMemoryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=8000)
    category: Category = Field(default="fact")
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    agent_id: UUID | None = None


def parse_search_args(raw: dict[str, Any] | None) -> SearchMemoryArgs:
    try:
        return SearchMemoryArgs.model_validate(raw or {})
    except ValidationError as exc:
        raise SchemaError(_first_validation_message(exc)) from exc


def parse_write_args(raw: dict[str, Any] | None) -> WriteMemoryArgs:
    try:
        return WriteMemoryArgs.model_validate(raw or {})
    except ValidationError as exc:
        raise SchemaError(_first_validation_message(exc)) from exc


def stub_search_memory(principal: Principal, args: SearchMemoryArgs) -> dict[str, Any]:
    """Org-scoped mock hit. Tenant comes from the principal — never from client args."""
    if not has_permission(principal.permissions, MEMORY_READ):
        raise PermissionDeniedError("search_memory requires MemoryRead")
    memory_id = str(uuid5(_STUB_NAMESPACE, f"{principal.org_id}:search:{args.query}"))
    return {
        "stub": True,
        "org_id": str(principal.org_id),
        "query": args.query,
        "limit": args.limit,
        "results": [
            {
                "memory_id": memory_id,
                "content": "[stub] matching memory",
                "score": 0.91,
                "category": "fact",
            }
        ],
        "source": "mcp_stub",
    }


def stub_write_memory(principal: Principal, args: WriteMemoryArgs) -> dict[str, Any]:
    """Accepted-shape stub. Does not persist; source mirrors future mcp_explicit writes."""
    if not has_permission(principal.permissions, MEMORY_WRITE):
        raise PermissionDeniedError("write_memory requires MemoryWrite")
    memory_id = str(uuid5(_STUB_NAMESPACE, f"{principal.org_id}:write:{args.content}"))
    return {
        "stub": True,
        "org_id": str(principal.org_id),
        "memory_id": memory_id,
        "accepted": True,
        "category": args.category,
        "confidence": args.confidence,
        "source": "mcp_explicit",
        "persisted": False,
    }


def _first_validation_message(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "invalid tool arguments"
    err = errors[0]
    loc = ".".join(str(part) for part in err.get("loc", ()))
    msg = err.get("msg", "invalid")
    return f"{loc}: {msg}" if loc else str(msg)
