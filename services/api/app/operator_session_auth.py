"""Shared operator access-cookie validation for protected API routes."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from apierror_py import INVALID_TOKEN, SERVICE_DEGRADED
from fastapi import Request

from app.auth.client import AuthFailedError, AuthUnavailableError
from app.auth.session_refresh import AuthRPC, ValidatedSession, validate_operator_session
from app.config import Settings
from app.errors import ApiError
from app.session_stub import (
    SESSION_KIND_ACCESS,
    SessionStubError,
    TokenVerifyOpts,
    verify_token_opts,
)


@dataclass(frozen=True, slots=True)
class OperatorSessionAuthorization:
    """Minimal AuthService-verified identity and grants needed by routes."""

    org_id: UUID
    permissions: int
    session_id: str
    subject: str = ""


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _access_cookie(request: Request, settings: Settings) -> str:
    raw = request.cookies.get(settings.dashboard_session_cookie_name)
    if not raw:
        raise ApiError(code=INVALID_TOKEN, message="missing session cookie")
    return raw


def _require_operator_feature(settings: Settings) -> None:
    if not settings.operator_feature_enabled:
        raise ApiError(code=SERVICE_DEGRADED, message="operator feature disabled")
    if not settings.jwt_hmac_secret and not settings.jwt_public_keys_pem:
        raise ApiError(code=SERVICE_DEGRADED, message="session verification key not configured")


def _verified_local_session(raw: str, settings: Settings) -> OperatorSessionAuthorization:
    try:
        claims = verify_token_opts(
            raw,
            TokenVerifyOpts(
                secret=settings.jwt_hmac_secret,
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
                expect_kind=SESSION_KIND_ACCESS,
                public_keys_pem=settings.jwt_public_keys_pem,
                key_id=settings.jwt_key_id,
            ),
        )
    except SessionStubError as exc:
        raise ApiError(code=INVALID_TOKEN, message=str(exc)) from exc
    if not isinstance(claims.org_id, UUID):
        raise ApiError(code=INVALID_TOKEN, message="missing org context in session")
    return OperatorSessionAuthorization(
        org_id=claims.org_id,
        permissions=claims.permissions,
        session_id=claims.session_id,
        subject=claims.sub,
    )


async def require_operator_session(request: Request) -> OperatorSessionAuthorization:
    """Verify the identity and live session state before any protected work.

    Development accepts a locally signed operator token because its HMAC issuer
    is deliberately process-local. Staging and production delegate signature,
    identity, expiry, and revocation checks to AuthService on every request.
    """
    settings = _settings(request)
    _require_operator_feature(settings)
    raw = _access_cookie(request, settings)
    if settings.environment == "development":
        authorization = _verified_local_session(raw, settings)
    else:
        claims = await _validate_remote_session(raw, settings)
        authorization = _authorization_from_validated(claims)
    if not authorization.subject:
        raise ApiError(code=INVALID_TOKEN, message="missing session subject")
    request.state.ibex_session_org_id = str(authorization.org_id)
    request.state.ibex_session_sub = authorization.subject
    request.state.ibex_session_id = authorization.session_id
    return authorization


async def _validate_remote_session(raw: str, settings: Settings) -> ValidatedSession:
    try:
        return await validate_operator_session(
            AuthRPC(
                settings.auth_grpc_addr,
                settings.auth_service_token or "",
                max(settings.auth_timeout_ms / 1000.0, 0.2),
            ),
            access_token=raw,
        )
    except AuthFailedError as exc:
        raise ApiError(code=INVALID_TOKEN, message="invalid session") from exc
    except (AuthUnavailableError, ValueError) as exc:
        # ValueError here denotes an invalid/untrusted configured gRPC target.
        raise ApiError(code=SERVICE_DEGRADED, message="auth unavailable") from exc


def _parse_session_org_id(raw: str) -> UUID:
    try:
        return UUID(raw)
    except (TypeError, ValueError) as exc:
        raise ApiError(code=INVALID_TOKEN, message="missing org context in session") from exc


def _require_complete_session_claims(claims: ValidatedSession) -> None:
    for value in (claims.subject, claims.session_id, claims.jti):
        if not value:
            raise ApiError(code=INVALID_TOKEN, message="incomplete session claims")


def _authorization_from_validated(claims: ValidatedSession) -> OperatorSessionAuthorization:
    _require_complete_session_claims(claims)
    return OperatorSessionAuthorization(
        org_id=_parse_session_org_id(claims.org_id),
        permissions=claims.permissions,
        session_id=claims.session_id,
        subject=claims.subject,
    )
