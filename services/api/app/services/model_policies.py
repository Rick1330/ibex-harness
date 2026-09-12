"""Org model-policy persistence (m4.C.2 / ADR-0075)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from apierror_py import (
    INTERNAL_ERROR,
    MODEL_POLICY_PATTERN_CONFLICT,
    NOT_FOUND,
    VALIDATION_ERROR,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.model_policy_publish import ModelPolicyPublisher, NoopModelPolicyPublisher
from app.pagination import CursorPage, decode_cursor, encode_cursor, page_from_rows
from app.schemas.model_policies import (
    ModelPolicyCreate,
    ModelPolicyPatch,
    ModelPolicyResponse,
)

logger = logging.getLogger(__name__)

_UNIQUE = "org_model_policies_org_pattern_unique"
_NOT_FOUND_MSG = "Model policy not found"

_GET_SQL = """
SELECT id, org_id, model_pattern, allowed, priority, created_at, updated_at
FROM ibex_core.org_model_policies
WHERE id = CAST(:policy_id AS uuid) AND org_id = CAST(:org_id AS uuid)
"""

_LIST_SQL = """
SELECT id, org_id, model_pattern, allowed, priority, created_at, updated_at
FROM ibex_core.org_model_policies
WHERE org_id = CAST(:org_id AS uuid)
  AND (
    CAST(:cursor_priority AS integer) IS NULL
    OR priority > CAST(:cursor_priority AS integer)
    OR (
      priority = CAST(:cursor_priority AS integer)
      AND model_pattern > CAST(:cursor_pattern AS text)
    )
  )
ORDER BY priority ASC, model_pattern ASC
LIMIT :limit
"""

_INSERT_SQL = """
INSERT INTO ibex_core.org_model_policies (org_id, model_pattern, allowed, priority)
VALUES (CAST(:org_id AS uuid), :model_pattern, :allowed, :priority)
RETURNING id, org_id, model_pattern, allowed, priority, created_at, updated_at
"""

_UPDATE_SQL = """
UPDATE ibex_core.org_model_policies
SET model_pattern = COALESCE(:model_pattern, model_pattern),
    allowed = COALESCE(:allowed, allowed),
    priority = COALESCE(:priority, priority),
    updated_at = now()
WHERE id = CAST(:policy_id AS uuid) AND org_id = CAST(:org_id AS uuid)
RETURNING id, org_id, model_pattern, allowed, priority, created_at, updated_at
"""

_DELETE_SQL = """
DELETE FROM ibex_core.org_model_policies
WHERE id = CAST(:policy_id AS uuid) AND org_id = CAST(:org_id AS uuid)
RETURNING id
"""


@dataclass(frozen=True, slots=True)
class WriteDeps:
    publisher: ModelPolicyPublisher | None = None


@dataclass(frozen=True, slots=True)
class PatchArgs:
    org_id: UUID
    policy_id: UUID
    body: ModelPolicyPatch
    deps: WriteDeps


def _row_to_response(row) -> ModelPolicyResponse:
    return ModelPolicyResponse(
        id=row.id if isinstance(row.id, UUID) else UUID(str(row.id)),
        org_id=row.org_id if isinstance(row.org_id, UUID) else UUID(str(row.org_id)),
        model_pattern=str(row.model_pattern),
        allowed=bool(row.allowed),
        priority=int(row.priority),
        created_at=row.created_at,
        updated_at=row.updated_at,
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


def _is_pattern_conflict(exc: IntegrityError) -> bool:
    name = _constraint_name(exc)
    return name == _UNIQUE or _UNIQUE in name


def _raise_write_integrity(exc: IntegrityError) -> None:
    if _is_pattern_conflict(exc):
        raise ApiError(
            code=MODEL_POLICY_PATTERN_CONFLICT,
            message="Model pattern already exists for this organization",
            detail=_UNIQUE,
        ) from exc
    raise ApiError(
        code=INTERNAL_ERROR,
        message="Unable to write model policy",
    ) from exc


async def list_policies(
    session: AsyncSession,
    org_id: UUID,
    *,
    cursor: str | None,
    limit: int,
) -> CursorPage[ModelPolicyResponse]:
    cursor_priority, cursor_pattern = _parse_list_cursor(cursor)
    result = await session.execute(
        text(_LIST_SQL),
        {
            "org_id": str(org_id),
            "cursor_priority": cursor_priority,
            "cursor_pattern": cursor_pattern,
            "limit": limit + 1,
        },
    )
    rows = [_row_to_response(r) for r in result.all()]
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode_cursor(
            {"priority": last.priority, "pattern": last.model_pattern}
        )
    return page_from_rows(rows, limit=limit, next_cursor=next_cursor)


def _parse_list_cursor(cursor: str | None) -> tuple[int | None, str | None]:
    if not cursor:
        return None, None
    try:
        payload = decode_cursor(cursor) or {}
        return int(payload["priority"]), str(payload["pattern"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError(code=VALIDATION_ERROR, message="Invalid cursor") from exc


async def get_policy(
    session: AsyncSession, org_id: UUID, policy_id: UUID
) -> ModelPolicyResponse:
    result = await session.execute(
        text(_GET_SQL),
        {"org_id": str(org_id), "policy_id": str(policy_id)},
    )
    row = result.first()
    if row is None:
        raise ApiError(code=NOT_FOUND, message=_NOT_FOUND_MSG)
    return _row_to_response(row)


async def create_policy(
    session: AsyncSession,
    org_id: UUID,
    body: ModelPolicyCreate,
    *,
    deps: WriteDeps,
) -> ModelPolicyResponse:
    try:
        result = await session.execute(
            text(_INSERT_SQL),
            {
                "org_id": str(org_id),
                "model_pattern": body.model_pattern,
                "allowed": body.allowed,
                "priority": body.priority,
            },
        )
        row = result.first()
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        _raise_write_integrity(exc)
    if row is None:
        raise ApiError(code=INTERNAL_ERROR, message="Unable to create model policy")
    await _publish_best_effort(deps.publisher, org_id)
    return _row_to_response(row)


def _patch_has_fields(body: ModelPolicyPatch) -> bool:
    return body.model_pattern is not None or body.allowed is not None or body.priority is not None


async def patch_policy(session: AsyncSession, args: PatchArgs) -> ModelPolicyResponse:
    body = args.body
    if not _patch_has_fields(body):
        return await get_policy(session, args.org_id, args.policy_id)
    try:
        result = await session.execute(
            text(_UPDATE_SQL),
            {
                "org_id": str(args.org_id),
                "policy_id": str(args.policy_id),
                "model_pattern": body.model_pattern,
                "allowed": body.allowed,
                "priority": body.priority,
            },
        )
        row = result.first()
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        _raise_write_integrity(exc)
    if row is None:
        raise ApiError(code=NOT_FOUND, message=_NOT_FOUND_MSG)
    await _publish_best_effort(args.deps.publisher, args.org_id)
    return _row_to_response(row)


async def delete_policy(
    session: AsyncSession,
    org_id: UUID,
    policy_id: UUID,
    *,
    deps: WriteDeps,
) -> None:
    result = await session.execute(
        text(_DELETE_SQL),
        {"org_id": str(org_id), "policy_id": str(policy_id)},
    )
    if result.first() is None:
        await session.rollback()
        raise ApiError(code=NOT_FOUND, message=_NOT_FOUND_MSG)
    await session.commit()
    await _publish_best_effort(deps.publisher, org_id)


async def _publish_best_effort(
    publisher: ModelPolicyPublisher | None, org_id: UUID
) -> None:
    pub = publisher if publisher is not None else NoopModelPolicyPublisher()
    try:
        await pub.publish_policy_update(str(org_id))
    except Exception as exc:  # noqa: BLE001 — best-effort; PG already committed
        logger.warning(
            "model-policy publish failed org_id=%s error_class=%s",
            org_id,
            type(exc).__name__,
        )
