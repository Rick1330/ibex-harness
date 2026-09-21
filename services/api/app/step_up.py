"""Step-up token verification for high-impact operator routes."""

from __future__ import annotations

from typing import Annotated

from apierror_py import INSUFFICIENT_PERMISSIONS
from fastapi import Depends, Request

from app.config import Settings
from app.errors import ApiError
from app.session_stub import (
    SESSION_KIND_STEP_UP,
    SessionClaims,
    SessionStubError,
    TokenVerifyOpts,
    verify_token_opts,
)

STEP_UP_HEADER = "X-IBEX-Step-Up"
_STEP_UP_REQUIRED = "Step-up authentication required"


def _settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def _deny_step_up() -> ApiError:
    return ApiError(code=INSUFFICIENT_PERMISSIONS, message=_STEP_UP_REQUIRED)


def _verify_step_up_token(raw: str, settings: Settings) -> SessionClaims:
    try:
        return verify_token_opts(
            raw.strip(),
            TokenVerifyOpts(
                secret=settings.jwt_hmac_secret,
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
                expect_kind=SESSION_KIND_STEP_UP,
                public_keys_pem=settings.jwt_public_keys_pem,
            ),
        )
    except SessionStubError as exc:
        raise _deny_step_up() from exc


def _assert_step_up_binds_session(request: Request, claims: SessionClaims) -> None:
    # Binding is mandatory whenever a step-up header is presented. Missing
    # request.state session attrs is a caller/wiring bug — fail closed (do not skip).
    _assert_step_up_org(request, claims)
    _assert_step_up_sub(request, claims)


def _assert_step_up_org(request: Request, claims: SessionClaims) -> None:
    session_org = getattr(request.state, "ibex_session_org_id", None)
    if session_org is None:
        raise _deny_step_up()
    if str(claims.org_id) == str(session_org):
        return
    raise _deny_step_up()


def _assert_step_up_sub(request: Request, claims: SessionClaims) -> None:
    session_sub = getattr(request.state, "ibex_session_sub", None)
    if session_sub is None:
        raise _deny_step_up()
    if claims.sub and str(claims.sub) == str(session_sub):
        return
    raise _deny_step_up()


def require_step_up_header(request: Request) -> None:
    """Validate X-IBEX-Step-Up when present; set request.state.ibex_step_up_ok."""
    raw = request.headers.get(STEP_UP_HEADER)
    if not raw:
        request.state.ibex_step_up_ok = False
        return
    claims = _verify_step_up_token(raw, _settings(request))
    _assert_step_up_binds_session(request, claims)
    request.state.ibex_step_up_ok = True
    request.state.ibex_step_up_jti = claims.jti


RequireStepUpProbe = Annotated[None, Depends(require_step_up_header)]
