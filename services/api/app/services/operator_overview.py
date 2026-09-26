"""Tenant-bound, read-only data service for the D1 operator Overview."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from apierror_py import NOT_FOUND, SERVICE_DEGRADED
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.operator_session_auth import OperatorSessionAuthorization
from app.schemas.operator_overview import (
    OperatorContextResponse,
    OperatorOverviewCounts,
    OperatorOverviewResponse,
)

_ORG_NOT_FOUND = "Operator organization not found"
_OVERVIEW_UNAVAILABLE = "Operator overview data is temporarily unavailable"
_SET_D1_QUERY_TIMEOUT = text("SET LOCAL statement_timeout = '3000ms'")
_ALLOWED_ROLES = frozenset({"owner", "admin", "member", "viewer"})

_READ_D1_SUMMARY = text(
    """
    SELECT
        o.id AS org_id,
        o.name AS org_name,
        o.slug AS org_slug,
        o.status AS org_status,
        (
            SELECT u.role
            FROM ibex_core.users AS u
            WHERE u.id = CAST(:subject_id AS uuid)
              AND u.org_id = o.id
              AND u.deleted_at IS NULL
            LIMIT 1
        ) AS role,
        (
            SELECT COUNT(*)
            FROM ibex_core.users AS u
            WHERE u.org_id = o.id
              AND u.deleted_at IS NULL
              AND u.status = 'active'
        ) AS active_users,
        (
            SELECT COUNT(*)
            FROM ibex_core.agents AS a
            WHERE a.org_id = o.id
              AND a.deleted_at IS NULL
        ) AS agents,
        (
            SELECT COUNT(*)
            FROM ibex_core.agents AS a
            WHERE a.org_id = o.id
              AND a.deleted_at IS NULL
              AND a.status = 'active'
        ) AS active_agents
    FROM ibex_core.organizations AS o
    WHERE o.id = CAST(:org_id AS uuid)
      AND o.deleted_at IS NULL
    LIMIT 1
    """
)


def _verified_role(value: object) -> str | None:
    return value if isinstance(value, str) and value in _ALLOWED_ROLES else None


def _parse_subject_id(raw: str) -> UUID | None:
    try:
        return UUID(raw)
    except (TypeError, ValueError):
        return None


async def _fetch_d1_row(
    session: AsyncSession, authorization: OperatorSessionAuthorization
) -> Any:
    subject_id = _parse_subject_id(authorization.subject)
    # The operator session dependency has already opened a transaction and
    # bound the verified organization/RLS GUCs. SET LOCAL cannot leak to a
    # later pooled request and bounds database work below the DAL deadline.
    try:
        await session.execute(_SET_D1_QUERY_TIMEOUT)
        result = await session.execute(
            _READ_D1_SUMMARY,
            {
                "org_id": str(authorization.org_id),
                "subject_id": str(subject_id) if subject_id else None,
            },
        )
        return result.mappings().first()
    except SQLAlchemyError as exc:
        raise ApiError(code=SERVICE_DEGRADED, message=_OVERVIEW_UNAVAILABLE) from exc


def _require_bound_org_id(row: Any, authorization: OperatorSessionAuthorization) -> UUID:
    try:
        row_org_id = UUID(str(row["org_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError(code=SERVICE_DEGRADED, message=_OVERVIEW_UNAVAILABLE) from exc
    if row_org_id != authorization.org_id:
        # Defense in depth: never trust a tenant row that violates the bound
        # query/RLS contract, and do not reveal that another org exists.
        raise ApiError(code=NOT_FOUND, message=_ORG_NOT_FOUND)
    return row_org_id


def _build_d1_responses(
    authorization: OperatorSessionAuthorization, row: Any
) -> tuple[OperatorContextResponse, OperatorOverviewResponse]:
    observed_at = datetime.now(UTC)
    context = OperatorContextResponse(
        org_id=authorization.org_id,
        role=_verified_role(row["role"]),
        org_name=row["org_name"],
        org_slug=row["org_slug"],
        org_status=row["org_status"],
        observed_at=observed_at,
    )
    overview = OperatorOverviewResponse(
        org_id=authorization.org_id,
        org_name=row["org_name"],
        org_slug=row["org_slug"],
        org_status=row["org_status"],
        counts=OperatorOverviewCounts(
            active_users=int(row["active_users"]),
            agents=int(row["agents"]),
            active_agents=int(row["active_agents"]),
        ),
        observed_at=observed_at,
    )
    return context, overview


async def get_operator_d1_read_model(
    session: AsyncSession,
    authorization: OperatorSessionAuthorization,
) -> tuple[OperatorContextResponse, OperatorOverviewResponse]:
    """Read only minimal org metadata and bounded counts under the session's RLS scope."""
    row = await _fetch_d1_row(session, authorization)
    if row is None:
        raise ApiError(code=NOT_FOUND, message=_ORG_NOT_FOUND)
    _require_bound_org_id(row, authorization)
    return _build_d1_responses(authorization, row)
