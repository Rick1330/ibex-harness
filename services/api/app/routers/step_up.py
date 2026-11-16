"""Step-up proof issuance (S02): the only way to obtain an X-IBEX-Step-Up token."""

from __future__ import annotations

from typing import Annotated

from apierror_py import (
    INSUFFICIENT_PERMISSIONS,
    INVALID_REQUEST,
    INVALID_TOKEN,
    MISSING_TOKEN,
    RATE_LIMITED,
    SERVICE_DEGRADED,
)
from authclient.permissions import ORG_SETTINGS_WRITE
from fastapi import APIRouter, Depends, Request

from app.auth.client import (
    AuthFailedError,
    AuthUnavailableError,
    ValidateResult,
    parse_authorization_header,
)
from app.auth.session_refresh import (
    AuthRPC,
    CreateStepUpParams,
    IssuedStepUp,
    StepUpAttemptLimitError,
    create_step_up,
)
from app.authz import assert_permission
from app.config import Settings
from app.deps import require_token
from app.errors import ApiError
from app.schemas.step_up import StepUpRequest, StepUpResponse
from app.step_up import bearer_binding

router = APIRouter(prefix="/v1/auth", tags=["auth"])

# The actions a proof may be minted for. A proof is bound to its action, so this
# registry is the closed set the API is willing to vouch for; AuthService records
# the same action in the token it signs.
_STEP_UP_ACTIONS: dict[str, int] = {"org.delete": ORG_SETTINGS_WRITE}

_INVALID_CODE = "invalid step-up code"
_AUTH_UNAVAILABLE = "auth unavailable"
_USER_SCOPED = "User-scoped token required"


def _step_up_permission(action: str) -> int:
    permission = _STEP_UP_ACTIONS.get(action)
    if permission is None:
        raise ApiError(code=INVALID_REQUEST, message="unsupported step-up action")
    return permission


def _assert_user_caller(token: ValidateResult) -> None:
    """Refuse a userless bearer here, before AuthService has to.

    AuthService's ``CreateStepUpToken`` asserts the caller is the user named in
    the request and refuses a caller with no user id. Every action this route
    vouches for is owner-role gated, and that gate already requires a user, so a
    userless PAT could never use the proof it asked for. Asking AuthService
    anyway would report its refusal as an "invalid step-up code" 401; this says
    what is actually wrong, in the same words ``load_caller_role`` uses.
    """
    if not token.user_id:
        raise ApiError(code=INSUFFICIENT_PERMISSIONS, message=_USER_SCOPED)


def _bearer_token(request: Request) -> str:
    """Return the raw bearer credential to forward to AuthService.

    ``require_token`` has already validated the same header, so a failure here
    means the request was rewritten between the two reads; it fails closed with
    the same 401 rather than calling AuthService without a caller identity.
    """
    try:
        return parse_authorization_header(request.headers.get("Authorization"))
    except AuthFailedError as exc:
        raise ApiError(code=MISSING_TOKEN, message="missing bearer token") from exc


async def _issue_proof(
    settings: Settings, params: CreateStepUpParams, pat: str
) -> IssuedStepUp:
    # No service credential: AuthService asserts the caller is the user named in
    # the request, so the call carries the caller's own PAT and nothing else.
    rpc = AuthRPC(
        settings.auth_grpc_addr,
        "",
        max(settings.auth_timeout_ms / 1000.0, 0.2),
        settings.auth_grpc_ca_file or "",
    )
    try:
        return await create_step_up(rpc, params, pat=pat)
    except StepUpAttemptLimitError as exc:
        raise ApiError(code=RATE_LIMITED, message="step-up attempt limit exceeded") from exc
    except AuthFailedError as exc:
        raise ApiError(code=INVALID_TOKEN, message=_INVALID_CODE) from exc
    except AuthUnavailableError as exc:
        raise ApiError(code=SERVICE_DEGRADED, message=_AUTH_UNAVAILABLE) from exc


@router.post("/step-up")
async def create_step_up_proof(
    body: StepUpRequest,
    request: Request,
    token: Annotated[ValidateResult, Depends(require_token)],
) -> StepUpResponse:
    """Mint a short-lived proof for one action, bound to the bearer's own identity.

    The caller must already hold the permission the action needs; the proof only
    proves a second factor was presented just now, never a grant the caller did
    not have. Only a user-scoped bearer can obtain one: the sole registered
    action, ``org.delete``, is owner-role gated, and AuthService issues no proof
    for a caller with no user.
    """
    permission = _step_up_permission(body.action)
    assert_permission(token.permissions, permission)
    _assert_user_caller(token)
    binding = bearer_binding(token, getattr(request.state, "ibex_session_id", None))
    issued = await _issue_proof(
        request.app.state.settings,
        CreateStepUpParams(
            subject=binding.subject,
            org_id=str(token.org_id),
            session_id=binding.session_id,
            action=body.action,
            code=body.code,
        ),
        _bearer_token(request),
    )
    return StepUpResponse(token=issued.token, expires_at=issued.expires_at)
