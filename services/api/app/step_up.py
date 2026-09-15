"""Step-up token verification for high-impact operator routes."""

from __future__ import annotations

from typing import Annotated

from apierror_py import INSUFFICIENT_PERMISSIONS
from fastapi import Depends, Request

from app.config import Settings
from app.errors import ApiError
from app.session_stub import (
    SESSION_KIND_STEP_UP,
    SessionStubError,
    TokenVerifyOpts,
    verify_token_opts,
)

STEP_UP_HEADER = "X-IBEX-Step-Up"


def _settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


async def require_step_up_header(request: Request) -> None:
    """Validate X-IBEX-Step-Up when present; set request.state.ibex_step_up_ok."""
    settings = _settings(request)
    raw = request.headers.get(STEP_UP_HEADER)
    if not raw:
        request.state.ibex_step_up_ok = False
        return
    try:
        claims = verify_token_opts(
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
        raise ApiError(
            code=INSUFFICIENT_PERMISSIONS,
            message="Step-up authentication required",
        ) from exc
    session_org = getattr(request.state, "ibex_session_org_id", None)
    session_sub = getattr(request.state, "ibex_session_sub", None)
    if session_org is not None and str(claims.org_id) != str(session_org):
        raise ApiError(code=INSUFFICIENT_PERMISSIONS, message="Step-up authentication required")
    if session_sub is not None and (not claims.sub or str(claims.sub) != str(session_sub)):
        raise ApiError(code=INSUFFICIENT_PERMISSIONS, message="Step-up authentication required")
    request.state.ibex_step_up_ok = True
    request.state.ibex_step_up_jti = claims.jti


RequireStepUpProbe = Annotated[None, Depends(require_step_up_header)]
