"""Tenant-scoped read repositories for the operator gateway.

Every query filters on ``org_id`` explicitly (defense in depth) in addition to
the RLS GUC bound by ``app.db.session_with_org``. Cross-tenant resources return
``NotFoundError`` (404), never ``permission_denied``, to avoid existence leaks.
Only metadata columns are selected — never memory content, prompts, or raw
evidence payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from mcp_gateway import NotFoundError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.tracing import get_tracer


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value)


def _uuid_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    return str(value)


async def _execute(session: AsyncSession, operation: str, statement: Any, params: dict[str, Any]):  # type: ignore[no-untyped-def]
    with get_tracer().start_as_current_span(f"postgres.{operation}") as span:
        span.set_attribute("db.system", "postgresql")
        span.set_attribute("db.operation", operation)
        return await session.execute(statement, params)


async def get_session(session: AsyncSession, *, org_id: UUID, session_id: UUID) -> dict[str, Any]:
    result = await _execute(
        session,
        "get_session",
        text(
            "SELECT id, status, model, provider, agent_id, turn_count, "
            "total_input_tokens, total_output_tokens, created_at, updated_at, "
            "completed_at FROM ibex_core.sessions "
            "WHERE org_id = :org_id AND id = :session_id AND deleted_at IS NULL "
            "LIMIT 1"
        ),
        {"org_id": str(org_id), "session_id": str(session_id)},
    )
    row = result.mappings().first()
    if row is None:
        raise NotFoundError("session not found")
    return {
        "session_id": _uuid_or_none(row["id"]),
        "status": row["status"],
        "model": row["model"],
        "provider": row["provider"],
        "agent_id": _uuid_or_none(row["agent_id"]),
        "turn_count": int(row["turn_count"]),
        "total_input_tokens": int(row["total_input_tokens"]),
        "total_output_tokens": int(row["total_output_tokens"]),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
        "completed_at": _iso(row["completed_at"]),
    }


async def get_run(session: AsyncSession, *, org_id: UUID, run_id: UUID) -> dict[str, Any]:
    result = await _execute(
        session,
        "get_run",
        text(
            "SELECT id, trace_id, request_id, status, error_code, completeness, "
            "capture_mode, sample_decision, schema_version, agent_id, session_id, "
            "started_at, ended_at FROM ibex_core.evidence_runs "
            "WHERE org_id = :org_id AND id = :run_id LIMIT 1"
        ),
        {"org_id": str(org_id), "run_id": str(run_id)},
    )
    row = result.mappings().first()
    if row is None:
        raise NotFoundError("run not found")
    return _run_row(row)


@dataclass(frozen=True, slots=True)
class EvidenceFilters:
    trace_id: str | None = None
    session_id: UUID | None = None
    request_id: str | None = None
    error_code: str | None = None
    status: str | None = None


async def query_evidence(
    session: AsyncSession,
    *,
    org_id: UUID,
    filters: EvidenceFilters,
    limit: int,
) -> dict[str, Any]:
    result = await _execute(
        session,
        "query_evidence",
        text(
            "SELECT id, trace_id, request_id, status, error_code, completeness, "
            "capture_mode, sample_decision, schema_version, agent_id, session_id, "
            "started_at, ended_at FROM ibex_core.evidence_runs "
            "WHERE org_id = :org_id "
            "AND (CAST(:trace_id AS text) IS NULL "
            "OR trace_id = CAST(:trace_id AS text)) "
            "AND (CAST(:session_id AS uuid) IS NULL "
            "OR session_id = CAST(:session_id AS uuid)) "
            "AND (CAST(:request_id AS text) IS NULL "
            "OR request_id = CAST(:request_id AS text)) "
            "AND (CAST(:error_code AS text) IS NULL "
            "OR error_code = CAST(:error_code AS text)) "
            "AND (CAST(:status AS text) IS NULL "
            "OR (CAST(:status AS text) = 'ok' AND status = 'ok') "
            "OR (CAST(:status AS text) = 'error' AND status <> 'ok')) "
            "ORDER BY started_at DESC, id DESC LIMIT :limit"
        ),
        {
            "org_id": str(org_id),
            "trace_id": filters.trace_id,
            "session_id": str(filters.session_id) if filters.session_id is not None else None,
            "request_id": filters.request_id,
            "error_code": filters.error_code,
            "status": filters.status,
            "limit": limit + 1,
        },
    )
    rows = result.mappings().all()
    truncated = len(rows) > limit
    selected = rows[:limit]
    return {
        "runs": [_run_row(row) for row in selected],
        "count": len(selected),
        "truncated": truncated,
    }


async def get_budget_periods(
    session: AsyncSession,
    *,
    org_id: UUID,
    active_only: bool,
    limit: int,
) -> dict[str, Any]:
    result = await _execute(
        session,
        "get_budget_periods",
        text(
            "SELECT id, period_start, period_end, cap_cents, spent_cents_cached, "
            "enforcement_mode FROM ibex_billing.budget_periods "
            "WHERE org_id = :org_id "
            "AND (NOT CAST(:active_only AS boolean) "
            "OR (period_start <= NOW() AND period_end > NOW())) "
            "ORDER BY period_start DESC LIMIT :limit"
        ),
        {"org_id": str(org_id), "active_only": active_only, "limit": limit + 1},
    )
    rows = result.mappings().all()
    truncated = len(rows) > limit
    selected = rows[:limit]
    return {
        "periods": [
            {
                "period_id": _uuid_or_none(row["id"]),
                "period_start": _iso(row["period_start"]),
                "period_end": _iso(row["period_end"]),
                "cap_cents": int(row["cap_cents"]),
                "spent_cents_cached": int(row["spent_cents_cached"]),
                "enforcement_mode": row["enforcement_mode"],
            }
            for row in selected
        ],
        "count": len(selected),
        "truncated": truncated,
    }


def _run_row(row: Any) -> dict[str, Any]:
    return {
        "run_id": _uuid_or_none(row["id"]),
        "trace_id": row["trace_id"],
        "request_id": row["request_id"],
        "status": row["status"],
        "error_code": row["error_code"],
        "completeness": row["completeness"],
        "capture_mode": row["capture_mode"],
        "sample_decision": row["sample_decision"],
        "schema_version": row["schema_version"],
        "agent_id": _uuid_or_none(row["agent_id"]),
        "session_id": _uuid_or_none(row["session_id"]),
        "started_at": _iso(row["started_at"]),
        "ended_at": _iso(row["ended_at"]),
    }
