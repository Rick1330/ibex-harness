"""Read-only operator tools: typed specs + tenant-scoped dispatcher.

Four tools, one per scope (D3/D5): ``session.get``, ``run.get``,
``evidence.query``, ``budget.get``. All return redacted metadata only — never
memory content, prompts, or raw evidence payloads (D6). The dispatcher opens its
own tenant-scoped session so a denied call never touches the database.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Literal
from uuid import UUID

from mcp_gateway import (
    BackendUnavailableError,
    Scope,
    ToolContext,
    ToolRegistry,
    ToolSpec,
)
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import repositories
from app.db import session_with_org
from app.dependency_metrics import DB_DURATION, DB_ERRORS
from app.tracing import get_tracer

TOOL_VERSION = "1.0.0"
TOOL_TIMEOUT_MS = 2_000
EVIDENCE_MAX_LIMIT = 100
BUDGET_MAX_LIMIT = 50

_SESSION_PROPERTIES: dict[str, Any] = {
    "session_id": {"type": "string"},
    "status": {"type": "string"},
    "model": {"type": ["string", "null"]},
    "provider": {"type": ["string", "null"]},
    "agent_id": {"type": ["string", "null"]},
    "turn_count": {"type": "integer"},
    "total_input_tokens": {"type": "integer"},
    "total_output_tokens": {"type": "integer"},
    "created_at": {"type": ["string", "null"]},
    "updated_at": {"type": ["string", "null"]},
    "completed_at": {"type": ["string", "null"]},
}

_RUN_PROPERTIES: dict[str, Any] = {
    "run_id": {"type": "string"},
    "trace_id": {"type": ["string", "null"]},
    "request_id": {"type": ["string", "null"]},
    "status": {"type": "string"},
    "error_code": {"type": ["string", "null"]},
    "completeness": {"type": ["string", "null"]},
    "capture_mode": {"type": ["string", "null"]},
    "sample_decision": {"type": ["string", "null"]},
    "schema_version": {"type": ["string", "null"]},
    "agent_id": {"type": ["string", "null"]},
    "session_id": {"type": ["string", "null"]},
    "started_at": {"type": ["string", "null"]},
    "ended_at": {"type": ["string", "null"]},
}

_EVIDENCE_ITEM_PROPERTIES: dict[str, Any] = {
    "run_id": {"type": "string"},
    "trace_id": {"type": ["string", "null"]},
    "request_id": {"type": ["string", "null"]},
    "status": {"type": "string"},
    "error_code": {"type": ["string", "null"]},
    "completeness": {"type": ["string", "null"]},
    "capture_mode": {"type": ["string", "null"]},
    "started_at": {"type": ["string", "null"]},
    "ended_at": {"type": ["string", "null"]},
}

_PERIOD_PROPERTIES: dict[str, Any] = {
    "period_id": {"type": "string"},
    "period_start": {"type": ["string", "null"]},
    "period_end": {"type": ["string", "null"]},
    "cap_cents": {"type": "integer"},
    "spent_cents_cached": {"type": "integer"},
    "enforcement_mode": {"type": ["string", "null"]},
}


def _object_schema(properties: Mapping[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": dict(properties),
        "required": required,
        "additionalProperties": False,
    }


class SessionGetArgs(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: UUID = Field(description="Session UUID within the caller's org")


class RunGetArgs(BaseModel):
    model_config = {"extra": "forbid"}

    run_id: UUID = Field(description="Evidence run UUID within the caller's org")


class EvidenceQueryArgs(BaseModel):
    model_config = {"extra": "forbid"}

    trace_id: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"^\S+$")
    session_id: UUID | None = None
    request_id: str | None = Field(default=None, max_length=128)
    error_code: str | None = Field(default=None, max_length=64)
    status: Literal["ok", "error"] | None = None
    limit: int = Field(default=25, ge=1, le=EVIDENCE_MAX_LIMIT)


class BudgetGetArgs(BaseModel):
    model_config = {"extra": "forbid"}

    active_only: bool = True
    limit: int = Field(default=20, ge=1, le=BUDGET_MAX_LIMIT)


def build_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            ToolSpec(
                name="session.get",
                version=TOOL_VERSION,
                scope=Scope.OPERATOR_READ,
                description="Return redacted metadata for one session in the caller's org.",
                args_model=SessionGetArgs,
                output_schema=_object_schema(
                    _SESSION_PROPERTIES,
                    [
                        "session_id",
                        "status",
                        "turn_count",
                        "total_input_tokens",
                        "total_output_tokens",
                    ],
                ),
                timeout_ms=TOOL_TIMEOUT_MS,
                row_limit=1,
            ),
            ToolSpec(
                name="run.get",
                version=TOOL_VERSION,
                scope=Scope.RUNS_READ,
                description="Return redacted metadata for one evidence run in the caller's org.",
                args_model=RunGetArgs,
                output_schema=_object_schema(
                    _RUN_PROPERTIES, ["run_id", "status", "trace_id", "request_id"]
                ),
                timeout_ms=TOOL_TIMEOUT_MS,
                row_limit=1,
            ),
            ToolSpec(
                name="evidence.query",
                version=TOOL_VERSION,
                scope=Scope.EVIDENCE_READ,
                description="List redacted evidence-run metadata in the caller's org.",
                args_model=EvidenceQueryArgs,
                output_schema=_object_schema(
                    {
                        "runs": {
                            "type": "array",
                            "items": _object_schema(
                                _EVIDENCE_ITEM_PROPERTIES, ["run_id", "status"]
                            ),
                        },
                        "count": {"type": "integer"},
                        "truncated": {"type": "boolean"},
                    },
                    ["runs", "count", "truncated"],
                ),
                timeout_ms=TOOL_TIMEOUT_MS,
                row_limit=EVIDENCE_MAX_LIMIT,
            ),
            ToolSpec(
                name="budget.get",
                version=TOOL_VERSION,
                scope=Scope.BUDGET_READ,
                description="Return billing budget periods for the caller's org (cached cents).",
                args_model=BudgetGetArgs,
                output_schema=_object_schema(
                    {
                        "periods": {
                            "type": "array",
                            "items": _object_schema(
                                _PERIOD_PROPERTIES,
                                ["period_id", "cap_cents", "spent_cents_cached"],
                            ),
                        },
                        "count": {"type": "integer"},
                        "truncated": {"type": "boolean"},
                    },
                    ["periods", "count", "truncated"],
                ),
                timeout_ms=TOOL_TIMEOUT_MS,
                row_limit=BUDGET_MAX_LIMIT,
            ),
        ]
    )


_Handler = Callable[[AsyncSession, ToolContext, Mapping[str, Any]], Awaitable[Mapping[str, Any]]]


async def _session_get(
    session: AsyncSession, ctx: ToolContext, args: Mapping[str, Any]
) -> Mapping[str, Any]:
    return await repositories.get_session(session, org_id=ctx.org_id, session_id=args["session_id"])


async def _run_get(
    session: AsyncSession, ctx: ToolContext, args: Mapping[str, Any]
) -> Mapping[str, Any]:
    return await repositories.get_run(session, org_id=ctx.org_id, run_id=args["run_id"])


async def _evidence_query(
    session: AsyncSession, ctx: ToolContext, args: Mapping[str, Any]
) -> Mapping[str, Any]:
    return await repositories.query_evidence(
        session,
        org_id=ctx.org_id,
        trace_id=args.get("trace_id"),
        session_id=args.get("session_id"),
        request_id=args.get("request_id"),
        error_code=args.get("error_code"),
        status=args.get("status"),
        limit=args["limit"],
    )


async def _budget_get(
    session: AsyncSession, ctx: ToolContext, args: Mapping[str, Any]
) -> Mapping[str, Any]:
    return await repositories.get_budget_periods(
        session,
        org_id=ctx.org_id,
        active_only=args["active_only"],
        limit=args["limit"],
    )


def build_handlers() -> dict[str, _Handler]:
    return {
        "session.get": _session_get,
        "run.get": _run_get,
        "evidence.query": _evidence_query,
        "budget.get": _budget_get,
    }


class ToolDispatcher:
    """Opens a tenant-scoped session per call and runs the matching handler."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        handlers: Mapping[str, _Handler] | None = None,
    ) -> None:
        self._factory = session_factory
        self._handlers = dict(handlers or build_handlers())

    async def __call__(self, ctx: ToolContext, args: Mapping[str, Any]) -> Mapping[str, Any]:
        handler = self._handlers.get(ctx.spec.name)
        if handler is None:  # pragma: no cover - registry/dispatcher drift guard
            raise BackendUnavailableError(f"no handler for tool {ctx.spec.name!r}")
        tool = ctx.spec.name
        started = time.perf_counter()
        try:
            with get_tracer().start_as_current_span("db.read", attributes={"tool": tool}):
                async with session_with_org(self._factory, str(ctx.org_id)) as session:
                    return await handler(session, ctx, args)
        except SQLAlchemyError as exc:
            DB_ERRORS.labels(tool=tool).inc()
            raise BackendUnavailableError("database unavailable") from exc
        finally:
            DB_DURATION.labels(tool=tool).observe(time.perf_counter() - started)


__all__ = [
    "BudgetGetArgs",
    "EvidenceQueryArgs",
    "RunGetArgs",
    "SessionGetArgs",
    "ToolDispatcher",
    "build_handlers",
    "build_registry",
]
