"""Role + permission bitmap authorization for management endpoints."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from apierror_py import INSUFFICIENT_PERMISSIONS, NOT_FOUND
from authclient.permissions import ORG_SETTINGS_WRITE, USER_MANAGE, has_permission
from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.client import ValidateResult
from app.deps import org_session, require_token
from app.errors import ApiError

AdminRoles = frozenset({"owner", "admin"})
OwnerRoles = frozenset({"owner"})
ORG_NOT_FOUND_MSG = "Organization not found"
USER_NOT_FOUND_MSG = "User not found"
AGENT_NOT_FOUND_MSG = "Agent not found"


async def load_caller_role(
    token: Annotated[ValidateResult, Depends(require_token)],
    session: Annotated[AsyncSession, Depends(org_session)],
) -> str:
    if not token.user_id:
        raise ApiError(
            code=INSUFFICIENT_PERMISSIONS,
            message="User-scoped token required",
        )
    result = await session.execute(
        text(
            """
            SELECT role
            FROM ibex_core.users
            WHERE id = :user_id AND org_id = :org_id AND deleted_at IS NULL
            """
        ),
        {"user_id": token.user_id, "org_id": str(token.org_id)},
    )
    role = result.scalar_one_or_none()
    if role is None:
        raise ApiError(code=NOT_FOUND, message=USER_NOT_FOUND_MSG)
    return str(role)


def require_roles(
    allowed: frozenset[str],
    *,
    required_permission: int,
) -> Callable[..., ValidateResult]:
    def _dep(
        token: Annotated[ValidateResult, Depends(require_token)],
        role: Annotated[str, Depends(load_caller_role)],
    ) -> ValidateResult:
        if role not in allowed:
            raise ApiError(
                code=INSUFFICIENT_PERMISSIONS,
                message="Insufficient role",
            )
        if not has_permission(token.permissions, required_permission):
            raise ApiError(
                code=INSUFFICIENT_PERMISSIONS,
                message="Insufficient permissions",
            )
        return token

    return _dep


RequireUserManage = Annotated[
    ValidateResult,
    Depends(require_roles(AdminRoles, required_permission=USER_MANAGE)),
]
RequireOrgSettings = Annotated[
    ValidateResult,
    Depends(require_roles(AdminRoles, required_permission=ORG_SETTINGS_WRITE)),
]
RequireOwnerOrgSettings = Annotated[
    ValidateResult,
    Depends(require_roles(OwnerRoles, required_permission=ORG_SETTINGS_WRITE)),
]


def assert_path_org(token_org: UUID, path_org: UUID) -> None:
    if token_org != path_org:
        # Anti-enumeration: do not reveal whether the org exists elsewhere.
        raise ApiError(code=NOT_FOUND, message=ORG_NOT_FOUND_MSG)
