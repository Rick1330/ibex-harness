"""Role + permission bitmap authorization for management endpoints."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from apierror_py import INSUFFICIENT_PERMISSIONS, NOT_FOUND, SERVICE_DEGRADED
from authclient.permissions import (
    LEGAL_HOLD_MANAGE,
    OPERATOR_DELETE,
    OPERATOR_EXPORT,
    OPERATOR_METADATA_READ,
    OPERATOR_RAW_READ,
    OPERATOR_REPLAY,
    ORG_SETTINGS_WRITE,
    SECRET_USE,
    USER_MANAGE,
    has_permission,
    requires_step_up,
)
from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.client import ValidateResult
from app.config import Settings
from app.deps import org_session, require_token
from app.errors import ApiError

AdminRoles = frozenset({"owner", "admin"})
OwnerRoles = frozenset({"owner"})
ORG_NOT_FOUND_MSG = "Organization not found"
USER_NOT_FOUND_MSG = "User not found"
AGENT_NOT_FOUND_MSG = "Agent not found"

_KILL_SWITCH_BY_PERM: dict[int, str] = {
    OPERATOR_RAW_READ: "operator_allow_raw_read",
    OPERATOR_EXPORT: "operator_allow_export",
    OPERATOR_DELETE: "operator_allow_delete",
    OPERATOR_REPLAY: "operator_allow_replay",
    SECRET_USE: "operator_allow_secret_use",
}


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


def require_legal_hold_manage() -> Callable[..., ValidateResult]:
    """Owner/admin + LegalHoldManage + step-up (4.P.3)."""

    def _dep(
        request: Request,
        token: Annotated[
            ValidateResult,
            Depends(require_roles(AdminRoles, required_permission=LEGAL_HOLD_MANAGE)),
        ],
    ) -> ValidateResult:
        step_up_ok = bool(getattr(request.state, "ibex_step_up_ok", False))
        if requires_step_up(LEGAL_HOLD_MANAGE) and not step_up_ok:
            raise ApiError(
                code=INSUFFICIENT_PERMISSIONS,
                message="Step-up authentication required",
            )
        return token

    return _dep


RequireLegalHoldManage = Annotated[ValidateResult, Depends(require_legal_hold_manage())]


def assert_path_org(token_org: UUID, path_org: UUID) -> None:
    if token_org != path_org:
        # Anti-enumeration: do not reveal whether the org exists elsewhere.
        raise ApiError(code=NOT_FOUND, message=ORG_NOT_FOUND_MSG)


def _settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def _assert_operator_feature_enabled(settings: Settings) -> None:
    if not settings.operator_feature_enabled:
        raise ApiError(code=SERVICE_DEGRADED, message="Operator feature disabled")


def _assert_operator_action_enabled(settings: Settings, required: int) -> None:
    attr = _KILL_SWITCH_BY_PERM.get(required)
    if attr is not None and not bool(getattr(settings, attr, False)):
        raise ApiError(code=INSUFFICIENT_PERMISSIONS, message="Action disabled by policy")


def _assert_operator_bitmap(bitmap: int, required: int, *, step_up_ok: bool) -> None:
    if not has_permission(bitmap, required):
        raise ApiError(code=INSUFFICIENT_PERMISSIONS, message="Insufficient permissions")
    if requires_step_up(required) and not step_up_ok:
        raise ApiError(code=INSUFFICIENT_PERMISSIONS, message="Step-up authentication required")


def assert_operator_permission(
    settings: Settings,
    bitmap: int,
    required: int,
    *,
    step_up_ok: bool = False,
) -> None:
    """Deny-by-default operator action gate (bitmap + kill switch + step-up)."""
    _assert_operator_feature_enabled(settings)
    _assert_operator_action_enabled(settings, required)
    _assert_operator_bitmap(bitmap, required, step_up_ok=step_up_ok)


def require_operator_permission(required: int) -> Callable[..., ValidateResult]:
    def _dep(
        request: Request,
        token: Annotated[ValidateResult, Depends(require_token)],
    ) -> ValidateResult:
        step_up_ok = bool(getattr(request.state, "ibex_step_up_ok", False))
        assert_operator_permission(
            _settings(request), token.permissions, required, step_up_ok=step_up_ok
        )
        return token

    return _dep


RequireOperatorMetadataRead = Annotated[
    ValidateResult,
    Depends(require_operator_permission(OPERATOR_METADATA_READ)),
]
