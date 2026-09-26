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
from app.deps import operator_org_session, org_session, require_token
from app.errors import ApiError
from app.operator_session_auth import OperatorSessionAuthorization, require_operator_session
from app.step_up import StepUpAction, enforce_step_up

AdminRoles = frozenset({"owner", "admin"})
OwnerRoles = frozenset({"owner"})
ORG_NOT_FOUND_MSG = "Organization not found"
USER_NOT_FOUND_MSG = "User not found"
AGENT_NOT_FOUND_MSG = "Agent not found"
INSUFFICIENT_PERMISSIONS_MSG = "Insufficient permissions"

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
                message=INSUFFICIENT_PERMISSIONS_MSG,
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


def require_operator_legal_hold_manage() -> Callable[..., OperatorSessionAuthorization]:
    """Require a verified browser session, owner/admin role, permission, and step-up."""

    async def _dep(
        request: Request,
        operator: Annotated[
            OperatorSessionAuthorization, Depends(require_operator_session)
        ],
        session: Annotated[AsyncSession, Depends(operator_org_session)],
    ) -> OperatorSessionAuthorization:
        result = await session.execute(
            text(
                """
                SELECT role
                FROM ibex_core.users
                WHERE id = :user_id AND org_id = :org_id AND deleted_at IS NULL
                """
            ),
            {"user_id": operator.subject, "org_id": str(operator.org_id)},
        )
        role = result.scalar_one_or_none()
        if role is None or str(role) not in AdminRoles:
            raise ApiError(code=INSUFFICIENT_PERMISSIONS, message="Insufficient role")
        if not has_permission(operator.permissions, LEGAL_HOLD_MANAGE):
            raise ApiError(code=INSUFFICIENT_PERMISSIONS, message=INSUFFICIENT_PERMISSIONS_MSG)
        token = ValidateResult(
            org_id=operator.org_id,
            permissions=operator.permissions,
            user_id=operator.subject,
            token_id=operator.session_id,
        )
        await enforce_step_up(
            request,
            token,
            action=StepUpAction(
                required_permission=LEGAL_HOLD_MANAGE,
                action="legal_hold.manage",
                session_id=operator.session_id,
            ),
        )
        return operator

    return _dep


RequireLegalHoldManage = Annotated[
    OperatorSessionAuthorization, Depends(require_operator_legal_hold_manage())
]


def require_legal_hold_manage() -> Callable[..., ValidateResult]:
    """Deprecated PAT helper retained for isolated compatibility tests only.

    No mounted legal-hold mutation route uses this dependency. Browser mutations
    use ``require_operator_legal_hold_manage`` above.
    """

    async def _dep(
        request: Request,
        token: Annotated[
            ValidateResult,
            Depends(require_roles(AdminRoles, required_permission=LEGAL_HOLD_MANAGE)),
        ],
        operator_session: Annotated[
            OperatorSessionAuthorization | None, Depends(_maybe_operator_session)
        ] = None,
    ) -> ValidateResult:
        await enforce_step_up(
            request,
            token,
            action=StepUpAction(
                required_permission=LEGAL_HOLD_MANAGE,
                action="legal_hold.manage",
                session_id=operator_session.session_id if operator_session else None,
            ),
        )
        return token

    return _dep


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


def _assert_operator_bitmap(bitmap: int, required: int) -> None:
    if not has_permission(bitmap, required):
        raise ApiError(code=INSUFFICIENT_PERMISSIONS, message=INSUFFICIENT_PERMISSIONS_MSG)
    if requires_step_up(required):
        raise ApiError(code=INSUFFICIENT_PERMISSIONS, message="Step-up authentication required")


def assert_operator_permission(
    settings: Settings,
    bitmap: int,
    required: int,
) -> None:
    """Check non-step-up operator access; high-impact actions use an async dependency."""
    _assert_operator_feature_enabled(settings)
    _assert_operator_action_enabled(settings, required)
    _assert_operator_bitmap(bitmap, required)


def require_operator_permission(required: int) -> Callable[..., ValidateResult]:
    async def _dep(
        request: Request,
        token: Annotated[ValidateResult, Depends(require_token)],
        operator_session: Annotated[
            OperatorSessionAuthorization | None, Depends(_maybe_operator_session)
        ] = None,
    ) -> ValidateResult:
        needs_step_up = requires_step_up(required)
        settings = _settings(request)
        _assert_operator_feature_enabled(settings)
        _assert_operator_action_enabled(settings, required)
        if not has_permission(token.permissions, required):
            raise ApiError(code=INSUFFICIENT_PERMISSIONS, message=INSUFFICIENT_PERMISSIONS_MSG)
        if needs_step_up:
            await enforce_step_up(
                request,
                token,
                action=StepUpAction(
                    required_permission=required,
                    action=f"operator.permission.{required}",
                    session_id=operator_session.session_id if operator_session else None,
                ),
            )
        return token

    return _dep


async def _maybe_operator_session(
    request: Request,
) -> OperatorSessionAuthorization | None:
    """Validate the operator session only when a step-up proof is presented."""
    if not request.headers.get("X-IBEX-Step-Up"):
        return None
    return await require_operator_session(request)


RequireOperatorMetadataRead = Annotated[
    ValidateResult,
    Depends(require_operator_permission(OPERATOR_METADATA_READ)),
]
