"""Org capture-policy persistence (4.P.3)."""

from __future__ import annotations

from uuid import UUID

from apierror_py import CAPTURE_POLICY_CONFLICT, NOT_FOUND
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.schemas.capture_policies import (
    CapturePolicyCreate,
    CapturePolicyPatch,
    CapturePolicyResponse,
)

_NOT_FOUND = "Capture policy not found"
_DEFAULT_MODE = "metadata_only"


def _row(r) -> CapturePolicyResponse:
    return CapturePolicyResponse(
        id=r["id"],
        org_id=r["org_id"],
        agent_id=r["agent_id"],
        mode=r["mode"],
        priority=r["priority"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


async def list_policies(session: AsyncSession, org_id: UUID) -> list[CapturePolicyResponse]:
    result = await session.execute(
        text(
            """
            SELECT id, org_id, agent_id, mode, priority, created_at, updated_at
            FROM ibex_core.org_capture_policies
            WHERE org_id = :org_id
            ORDER BY priority ASC, created_at ASC
            """
        ),
        {"org_id": str(org_id)},
    )
    return [_row(m) for m in result.mappings().all()]


async def resolve_mode(
    session: AsyncSession, org_id: UUID, agent_id: UUID | None = None
) -> str:
    result = await session.execute(
        text(
            """
            SELECT mode FROM ibex_core.org_capture_policies
            WHERE org_id = :org_id
              AND (
                    (:agent_id IS NULL AND agent_id IS NULL)
                 OR (agent_id IS NOT DISTINCT FROM CAST(:agent_id AS uuid))
                 OR agent_id IS NULL
              )
            ORDER BY
                CASE WHEN agent_id IS NOT NULL THEN 0 ELSE 1 END,
                priority ASC
            LIMIT 1
            """
        ),
        {
            "org_id": str(org_id),
            "agent_id": str(agent_id) if agent_id else None,
        },
    )
    row = result.first()
    return str(row[0]) if row else _DEFAULT_MODE


async def create_policy(
    session: AsyncSession, org_id: UUID, body: CapturePolicyCreate
) -> CapturePolicyResponse:
    try:
        result = await session.execute(
            text(
                """
                INSERT INTO ibex_core.org_capture_policies (org_id, agent_id, mode, priority)
                VALUES (:org_id, :agent_id, :mode, :priority)
                RETURNING id, org_id, agent_id, mode, priority, created_at, updated_at
                """
            ),
            {
                "org_id": str(org_id),
                "agent_id": str(body.agent_id) if body.agent_id else None,
                "mode": body.mode,
                "priority": body.priority,
            },
        )
    except Exception as exc:
        if "org_capture_policies_org_agent_unique" in str(exc):
            raise ApiError(code=CAPTURE_POLICY_CONFLICT, message="Capture policy already exists") from exc
        raise
    row = result.mappings().first()
    await session.commit()
    assert row is not None
    return _row(row)


async def patch_policy(
    session: AsyncSession, org_id: UUID, policy_id: UUID, body: CapturePolicyPatch
) -> CapturePolicyResponse:
    current = await get_policy(session, org_id, policy_id)
    mode = body.mode if body.mode is not None else current.mode
    priority = body.priority if body.priority is not None else current.priority
    result = await session.execute(
        text(
            """
            UPDATE ibex_core.org_capture_policies
            SET mode = :mode, priority = :priority
            WHERE id = :id AND org_id = :org_id
            RETURNING id, org_id, agent_id, mode, priority, created_at, updated_at
            """
        ),
        {
            "id": str(policy_id),
            "org_id": str(org_id),
            "mode": mode,
            "priority": priority,
        },
    )
    row = result.mappings().first()
    if row is None:
        raise ApiError(code=NOT_FOUND, message=_NOT_FOUND)
    await session.commit()
    return _row(row)


async def get_policy(
    session: AsyncSession, org_id: UUID, policy_id: UUID
) -> CapturePolicyResponse:
    result = await session.execute(
        text(
            """
            SELECT id, org_id, agent_id, mode, priority, created_at, updated_at
            FROM ibex_core.org_capture_policies
            WHERE id = :id AND org_id = :org_id
            """
        ),
        {"id": str(policy_id), "org_id": str(org_id)},
    )
    row = result.mappings().first()
    if row is None:
        raise ApiError(code=NOT_FOUND, message=_NOT_FOUND)
    return _row(row)


async def delete_policy(session: AsyncSession, org_id: UUID, policy_id: UUID) -> None:
    result = await session.execute(
        text(
            """
            DELETE FROM ibex_core.org_capture_policies
            WHERE id = :id AND org_id = :org_id
            RETURNING id
            """
        ),
        {"id": str(policy_id), "org_id": str(org_id)},
    )
    if result.first() is None:
        raise ApiError(code=NOT_FOUND, message=_NOT_FOUND)
    await session.commit()
