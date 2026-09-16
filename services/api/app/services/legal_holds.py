"""Legal hold persistence (4.P.3)."""

from __future__ import annotations

from uuid import UUID

from apierror_py import LEGAL_HOLD_SCOPE_CONFLICT, NOT_FOUND, VALIDATION_ERROR
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.schemas.legal_holds import LegalHoldCreate, LegalHoldResponse

_NOT_FOUND = "Legal hold not found"
_SCOPE_UNIQUE = "legal_holds_one_active_per_scope"


def _row(r) -> LegalHoldResponse:
    return LegalHoldResponse(
        id=r["id"],
        org_id=r["org_id"],
        scope=r["scope"],
        reason=r["reason"],
        set_by=r["set_by"],
        cleared_by=r["cleared_by"],
        created_at=r["created_at"],
        cleared_at=r["cleared_at"],
    )


def _constraint_name(exc: IntegrityError) -> str:
    orig = getattr(exc, "orig", None)
    name = getattr(orig, "constraint_name", None)
    if name:
        return str(name)
    diag = getattr(orig, "diag", None)
    if diag is not None:
        diag_name = getattr(diag, "constraint_name", None)
        if diag_name:
            return str(diag_name)
    return str(orig or exc)


def _is_scope_conflict(exc: IntegrityError) -> bool:
    name = _constraint_name(exc)
    return name == _SCOPE_UNIQUE or _SCOPE_UNIQUE in name


async def list_active_holds(session: AsyncSession, org_id: UUID) -> list[LegalHoldResponse]:
    result = await session.execute(
        text(
            """
            SELECT id, org_id, scope, reason, set_by, cleared_by, created_at, cleared_at
            FROM ibex_core.legal_holds
            WHERE org_id = :org_id AND cleared_at IS NULL
            ORDER BY created_at DESC
            """
        ),
        {"org_id": str(org_id)},
    )
    return [_row(m) for m in result.mappings().all()]


async def set_hold(
    session: AsyncSession,
    org_id: UUID,
    body: LegalHoldCreate,
    *,
    set_by: UUID,
) -> LegalHoldResponse:
    if not set_by:
        raise ApiError(code=VALIDATION_ERROR, message="User-scoped token required")
    try:
        result = await session.execute(
            text(
                """
                INSERT INTO ibex_core.legal_holds (org_id, scope, reason, set_by)
                VALUES (:org_id, :scope, :reason, :set_by)
                RETURNING id, org_id, scope, reason, set_by, cleared_by, created_at, cleared_at
                """
            ),
            {
                "org_id": str(org_id),
                "scope": body.scope,
                "reason": body.reason,
                "set_by": str(set_by),
            },
        )
        row = result.mappings().first()
        if row is None:
            raise ApiError(code=VALIDATION_ERROR, message="Legal hold insert returned no row")
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if _is_scope_conflict(exc):
            raise ApiError(
                code=LEGAL_HOLD_SCOPE_CONFLICT,
                message="Active legal hold already exists for scope",
            ) from exc
        raise
    return _row(row)


async def clear_hold(
    session: AsyncSession,
    org_id: UUID,
    hold_id: UUID,
    *,
    cleared_by: UUID,
) -> LegalHoldResponse:
    result = await session.execute(
        text(
            """
            UPDATE ibex_core.legal_holds
            SET cleared_at = NOW(), cleared_by = :cleared_by
            WHERE id = :hold_id AND org_id = :org_id AND cleared_at IS NULL
            RETURNING id, org_id, scope, reason, set_by, cleared_by, created_at, cleared_at
            """
        ),
        {
            "hold_id": str(hold_id),
            "org_id": str(org_id),
            "cleared_by": str(cleared_by),
        },
    )
    row = result.mappings().first()
    if row is None:
        raise ApiError(code=NOT_FOUND, message=_NOT_FOUND)
    await session.commit()
    return _row(row)
