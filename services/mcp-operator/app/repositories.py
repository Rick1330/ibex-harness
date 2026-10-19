"""Tenant-scoped read repositories for the operator gateway.

Every query filters on ``org_id`` explicitly (defense in depth) in addition to
the RLS GUC bound by ``app.db.session_with_org``. Cross-tenant resources return
``NotFoundError`` (404), never ``permission_denied``, to avoid existence leaks.
Only metadata columns are selected — never memory content, prompts, or raw
evidence payloads.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from mcp_gateway import NotFoundError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_SESSION_COLUMNS = (
    "id, status, model, provider, agent_id, turn_count, "
    "total_input_tokens, total_output_tokens, created_at, updated_at, completed_at"
)

_RUN_COLUMNS = (
    "id, trace_id, request_id, status, error_code, completeness, capture_mode, "
    "sample_decision, schema_version, agent_id, session_id, started_at, ended_at"
)

_BUDGET_COLUMNS = "id, period_start, period_end, cap_cents, spent_cents_cached, enforcement_mode"


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


async def get_session(session: AsyncSession, *, org_id: UUID, session_id: UUID) -> dict[str, Any]:
    result = await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            f"SELECT {_SESSION_COLUMNS} FROM ibex_core.sessions "  # nosec B608 - module constants, bound params
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
    result = await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            f"SELECT {_RUN_COLUMNS} FROM ibex_core.evidence_runs "  # nosec B608 - module constants, bound params
            "WHERE org_id = :org_id AND id = :run_id LIMIT 1"
        ),
        {"org_id": str(org_id), "run_id": str(run_id)},
    )
    row = result.mappings().first()
    if row is None:
        raise NotFoundError("run not found")
    return _run_row(row)


async def query_evidence(
    session: AsyncSession,
    *,
    org_id: UUID,
    trace_id: str | None,
    session_id: UUID | None,
    request_id: str | None,
    error_code: str | None,
    status: str | None,
    limit: int,
) -> dict[str, Any]:
    clauses = ["org_id = :org_id"]
    params: dict[str, Any] = {"org_id": str(org_id), "limit": limit + 1}
    if trace_id is not None:
        clauses.append("trace_id = :trace_id")
        params["trace_id"] = trace_id
    if session_id is not None:
        clauses.append("session_id = :session_id")
        params["session_id"] = str(session_id)
    if request_id is not None:
        clauses.append("request_id = :request_id")
        params["request_id"] = request_id
    if error_code is not None:
        clauses.append("error_code = :error_code")
        params["error_code"] = error_code
    if status == "ok":
        clauses.append("status = 'ok'")
    elif status == "error":
        clauses.append("status <> 'ok'")
    where = " AND ".join(clauses)
    result = await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            f"SELECT {_RUN_COLUMNS} FROM ibex_core.evidence_runs "  # nosec B608 - fixed clauses, bound params
            f"WHERE {where} ORDER BY started_at DESC, id DESC LIMIT :limit"
        ),
        params,
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
    clauses = ["org_id = :org_id"]
    params: dict[str, Any] = {"org_id": str(org_id), "limit": limit + 1}
    if active_only:
        clauses.append("period_start <= NOW() AND period_end > NOW()")
    where = " AND ".join(clauses)
    result = await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            f"SELECT {_BUDGET_COLUMNS} FROM ibex_billing.budget_periods "  # nosec B608 - fixed clauses, bound params
            f"WHERE {where} ORDER BY period_start DESC LIMIT :limit"
        ),
        params,
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
