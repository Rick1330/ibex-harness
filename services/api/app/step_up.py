"""Step-up token verification for high-impact operator routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from apierror_py import INSUFFICIENT_PERMISSIONS, SERVICE_DEGRADED
from fastapi import Depends, Request

from app.auth.client import ValidateResult
from app.auth.errors import AuthFailedError, AuthUnavailableError
from app.auth.session_refresh import AuthRPC, ConsumeStepUpParams, consume_step_up
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


@dataclass(frozen=True, slots=True)
class StepUpAction:
    """Action binding for enforce_step_up."""

    required_permission: int
    action: str
    session_id: str | None = None


@dataclass(frozen=True, slots=True)
class _StepUpProof:
    raw: str
    settings: Settings
    token: ValidateResult
    subject: str
    session_id: str
    action: str
    required_permission: int


def _settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def _deny_step_up() -> ApiError:
    return ApiError(code=INSUFFICIENT_PERMISSIONS, message=_STEP_UP_REQUIRED)


def _verify_step_up_token(raw: str, settings: Settings) -> SessionClaims:
    try:
        return verify_token_opts(
            raw.strip(),
            TokenVerifyOpts(
                secret=settings.jwt_hmac_secret if settings.environment == "development" else None,
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
                expect_kind=SESSION_KIND_STEP_UP,
                public_keys_pem=settings.jwt_public_keys_pem,
                key_id=settings.jwt_key_id,
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


def _resolve_step_up_proof(
    request: Request, token: ValidateResult, spec: StepUpAction
) -> _StepUpProof:
    raw = request.headers.get(STEP_UP_HEADER)
    if not raw:
        raise _deny_step_up()
    subject = token.user_id or token.token_id
    session_id = spec.session_id or getattr(request.state, "ibex_session_id", None)
    if not subject or not session_id:
        raise _deny_step_up()
    return _StepUpProof(
        raw=raw,
        settings=_settings(request),
        token=token,
        subject=subject,
        session_id=session_id,
        action=spec.action,
        required_permission=spec.required_permission,
    )


async def enforce_step_up(
    request: Request,
    token: ValidateResult,
    *,
    action: StepUpAction,
) -> None:
    """Verify and atomically consume the action-bound step-up immediately before mutation."""
    proof = _resolve_step_up_proof(request, token, action)
    if str(proof.settings.environment) not in {"staging", "production"}:
        _enforce_local_step_up(proof)
    else:
        await _enforce_auth_step_up(proof)
    request.state.ibex_step_up_ok = True
    request.state.ibex_step_up_action = action.action


def _identity_matches(proof: _StepUpProof, claims: SessionClaims) -> bool:
    return (
        claims.sub == proof.subject
        and str(claims.org_id) == str(proof.token.org_id)
        and claims.session_id == proof.session_id
    )


def _action_matches(proof: _StepUpProof, claims: SessionClaims) -> bool:
    return (
        claims.action == proof.action
        and claims.permissions & proof.required_permission == proof.required_permission
    )


def _enforce_local_step_up(proof: _StepUpProof) -> None:
    claims = _verify_step_up_token(proof.raw, proof.settings)
    if not _identity_matches(proof, claims) or not _action_matches(proof, claims):
        raise _deny_step_up()


async def _enforce_auth_step_up(proof: _StepUpProof) -> None:
    rpc = AuthRPC(
        proof.settings.auth_grpc_addr,
        proof.settings.auth_service_token or "",
        max(proof.settings.auth_timeout_ms / 1000.0, 0.2),
    )
    params = ConsumeStepUpParams(
        proof.raw,
        proof.subject,
        str(proof.token.org_id),
        proof.session_id,
        proof.action,
        proof.required_permission,
    )
    try:
        await consume_step_up(rpc, params)
    except AuthFailedError as exc:
        raise _deny_step_up() from exc
    except AuthUnavailableError as exc:
        raise ApiError(code=SERVICE_DEGRADED, message="auth unavailable") from exc
