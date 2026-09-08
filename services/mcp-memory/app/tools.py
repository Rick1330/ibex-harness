"""Strict JSON schemas and real memory-HTTP tool handlers (3.5.E.2).

Idempotency for write_memory (content-hash, not turn/ordinal):

  X-Idempotency-Key = sha256(f"{org_id}:{agent_id}:{normalize(content)}").hexdigest()

where normalize = Unicode NFC + strip ends only. Content is NOT lowercased —
case is semantically meaningful and lowercasing would falsely merge distinct
writes. Memory still fingerprints POST|/v1/memories|{body}; this key only needs
to be stable per logical MCP write (same spirit as worker memory_idempotency_key).

Fail-closed: memory timeouts / transport / ≥400 become MCPServiceError so
FastMCP returns CallToolResult(isError=true). HTTP 200 with zero hits is success.
"""

from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Awaitable, Callable
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.access_token import require_access_token
from app.agent_verifier import AgentVerifier
from app.clients.memory import (
    FeedbackResult,
    MemoryHttpClient,
    MemoryHttpError,
    MemoryHttpTimeout,
    SearchHit,
)
from app.errors import (
    AuthFailedError,
    BackendRejectedError,
    BackendUnavailableError,
    MCPServiceError,
    PermissionDeniedError,
    SchemaError,
)
from app.permissions import MEMORY_READ, MEMORY_WRITE, has_permission
from app.principal import Principal

Category = Literal["factual", "preference", "behavioral", "episodic", "procedural"]
FeedbackKind = Literal["positive", "negative", "neutral"]
MCP_SOURCE = "mcp_explicit"

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
            "enum": ["factual", "preference", "behavioral", "episodic", "procedural"],
            "default": "factual",
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0, "default": 0.6},
        "agent_id": {"type": "string", "format": "uuid"},
    },
}

RECORD_FEEDBACK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["memory_id", "feedback"],
    "properties": {
        "memory_id": {"type": "string", "format": "uuid"},
        "feedback": {
            "type": "string",
            "enum": ["positive", "negative", "neutral"],
        },
        "session_id": {"type": "string", "format": "uuid"},
        "trace_id": {"type": "string", "format": "uuid"},
        "notes": {"type": "string", "maxLength": 2000},
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
    category: Category = Field(default="factual")
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    agent_id: UUID | None = None


class RecordFeedbackArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: UUID
    feedback: FeedbackKind
    session_id: UUID | None = None
    trace_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


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


def parse_feedback_args(raw: dict[str, Any] | None) -> RecordFeedbackArgs:
    try:
        return RecordFeedbackArgs.model_validate(raw or {})
    except ValidationError as exc:
        raise SchemaError(_first_validation_message(exc)) from exc


def resolve_tool_agent_id(principal: Principal, requested: UUID | None) -> UUID:
    """Prefer principal.agent_id; else tool arg; else reject. Never cross-agent."""
    if principal.agent_id is not None:
        if requested is not None and requested != principal.agent_id:
            raise PermissionDeniedError("token is not authorized for the requested agent")
        return principal.agent_id
    if requested is None:
        raise SchemaError("agent_id is required when the token is not agent-scoped")
    return requested


def normalize_write_content(content: str) -> str:
    """NFC + strip only — do not lowercase (case is meaningful for memory text)."""
    return unicodedata.normalize("NFC", content).strip()


def write_idempotency_key(*, org_id: UUID, agent_id: UUID, content: str) -> str:
    material = f"{org_id}:{agent_id}:{normalize_write_content(content)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


async def search_memory(
    principal: Principal,
    args: SearchMemoryArgs,
    client: MemoryHttpClient | None,
    agent_verifier: AgentVerifier | None = None,
) -> dict[str, Any]:
    """Org-scoped search via memory HTTP. Tenant from principal + forwarded bearer."""
    _require_permission(principal, MEMORY_READ, "search_memory requires MemoryRead")
    agent_id = resolve_tool_agent_id(principal, args.agent_id)
    mem = _require_client(client)
    token = require_access_token()
    await _verify_agent_active(
        agent_verifier, bearer=token, org_id=principal.org_id, agent_id=agent_id
    )
    hits = await _call_memory(
        lambda: mem.search_memories(
            token=token,
            agent_id=agent_id,
            query=args.query,
            limit=args.limit,
        )
    )
    return {
        "org_id": str(principal.org_id),
        "agent_id": str(agent_id),
        "query": args.query,
        "limit": args.limit,
        "results": [_hit_dict(hit) for hit in hits],
    }


async def write_memory(
    principal: Principal,
    args: WriteMemoryArgs,
    client: MemoryHttpClient | None,
    agent_verifier: AgentVerifier | None = None,
) -> dict[str, Any]:
    """Persist via memory write pipeline with metadata.mcp_source=mcp_explicit."""
    _require_permission(principal, MEMORY_WRITE, "write_memory requires MemoryWrite")
    agent_id = resolve_tool_agent_id(principal, args.agent_id)
    mem = _require_client(client)
    token = require_access_token()
    await _verify_agent_active(
        agent_verifier, bearer=token, org_id=principal.org_id, agent_id=agent_id
    )
    idem = write_idempotency_key(
        org_id=principal.org_id, agent_id=agent_id, content=args.content
    )
    payload = {
        "agent_id": str(agent_id),
        "content": args.content,
        "category": args.category,
        "confidence": args.confidence,
        "metadata": {"mcp_source": MCP_SOURCE},
    }
    created = await _call_memory(
        lambda: mem.create_memory(token=token, payload=payload, idempotency_key=idem)
    )
    return {
        "org_id": str(principal.org_id),
        "memory_id": created.memory_id,
        "accepted": True,
        "category": created.category,
        "confidence": created.confidence,
        "mcp_source": MCP_SOURCE,
        "source": created.source,
        "persisted": True,
        "status": created.status,
        "metadata": created.metadata,
    }


async def record_feedback(
    principal: Principal,
    args: RecordFeedbackArgs,
    client: MemoryHttpClient | None,
) -> dict[str, Any]:
    """Record usefulness feedback via memory HTTP. Requires MemoryWrite."""
    _require_permission(principal, MEMORY_WRITE, "record_feedback requires MemoryWrite")
    mem = _require_client(client)
    token = require_access_token()
    body: dict[str, Any] = {"feedback": args.feedback}
    if args.session_id is not None:
        body["session_id"] = str(args.session_id)
    if args.trace_id is not None:
        body["trace_id"] = str(args.trace_id)
    if args.notes is not None:
        body["notes"] = args.notes
    recorded: FeedbackResult = await _call_memory(
        lambda: mem.record_feedback(token=token, memory_id=args.memory_id, body=body)
    )
    return {
        "org_id": str(principal.org_id),
        "memory_id": recorded.memory_id,
        "feedback": recorded.feedback,
        "new_usefulness_score": recorded.new_usefulness_score,
        "total_positive_feedback": recorded.total_positive_feedback,
        "total_negative_feedback": recorded.total_negative_feedback,
    }


def _require_permission(principal: Principal, bit: int, message: str) -> None:
    if not has_permission(principal.permissions, bit):
        raise PermissionDeniedError(message)


async def _verify_agent_active(
    verifier: AgentVerifier | None,
    *,
    bearer: str,
    org_id: UUID,
    agent_id: UUID,
) -> None:
    """Fail closed when verifier missing; active agents pass through unchanged."""
    if verifier is None:
        raise BackendUnavailableError("agent verifier is not configured")
    await verifier.verify(bearer=bearer, org_id=org_id, agent_id=agent_id)


def _require_client(client: MemoryHttpClient | None) -> MemoryHttpClient:
    if client is None:
        raise BackendUnavailableError("IBEX_MEMORY_HTTP_URL is not configured")
    return client


async def _call_memory[T](op: Callable[[], Awaitable[T]]) -> T:
    try:
        return await op()
    except MemoryHttpTimeout as exc:
        raise BackendUnavailableError(str(exc)) from exc
    except MemoryHttpError as exc:
        raise _map_memory_http_error(exc) from exc


def _hit_dict(hit: SearchHit) -> dict[str, Any]:
    return {
        "memory_id": hit.memory_id,
        "content": hit.content,
        "score": hit.score,
        "category": hit.category,
        "rank": hit.rank,
        "source": hit.source,
    }


def _map_memory_http_error(exc: MemoryHttpError) -> MCPServiceError:
    status = exc.status_code
    if status == 401:
        return AuthFailedError(str(exc))
    if status == 403:
        return PermissionDeniedError(str(exc))
    if status is not None and status >= 500:
        return BackendUnavailableError(str(exc))
    if status is not None and 400 <= status < 500:
        return BackendRejectedError(str(exc), code="backend_rejected")
    return BackendUnavailableError(str(exc))


def _first_validation_message(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "invalid tool arguments"
    err = errors[0]
    loc = ".".join(str(part) for part in err.get("loc", ()))
    msg = err.get("msg", "invalid")
    return f"{loc}: {msg}" if loc else str(msg)
