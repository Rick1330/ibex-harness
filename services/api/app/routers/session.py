"""Provisional operator session routes (4.P.0 stub — full identity is 4.P.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from apierror_py import INVALID_TOKEN, SERVICE_DEGRADED
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from app.auth.client import (
    AuthFailedError,
    AuthUnavailableError,
    TokenValidator,
    ValidateResult,
    parse_authorization_header,
)
from app.auth.session_refresh import (
    issue_operator_session,
    refresh_operator_session,
    revoke_operator_session,
    validate_operator_session,
)
from app.config import Settings
from app.deps import get_validator
from app.errors import ApiError, ResponseOpts, envelope_response
from app.reqid import require_current
from app.session_stub import (
    SESSION_KIND_ACCESS,
    SESSION_KIND_REFRESH,
    SessionClaims,
    SessionStubError,
    TokenIssueOpts,
    TokenVerifyOpts,
    issue_token_opts,
    mint_csrf_token,
    peek_token_alg,
    verify_token_opts,
)

router = APIRouter(prefix="/v1/operator/session", tags=["operator-session-provisional"])

_AUTH_UNAVAILABLE = "auth unavailable"
_ALG_RS256 = "RS256"
_INVALID_TOKEN_MESSAGE = INVALID_TOKEN.lower().replace("_", " ")


class LoginBody(BaseModel):
    """Exchange a PAT for provisional session cookies. PAT must not be stored in the browser."""

    pat: str = Field(min_length=8, max_length=4096)


@dataclass(frozen=True, slots=True)
class CookieParams:
    name: str
    value: str
    max_age: int
    httponly: bool
    secure: bool
    samesite: str
    domain: str | None


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _require_operator_enabled(settings: Settings) -> None:
    if not settings.operator_feature_enabled:
        raise ApiError(
            code=SERVICE_DEGRADED,
            message="operator feature disabled",
            detail="IBEX_OPERATOR_FEATURE_ENABLED=false",
        )


def _require_hmac(settings: Settings) -> str:
    if settings.environment != "development":
        raise ApiError(
            code=SERVICE_DEGRADED,
            message="provisional HMAC operator sessions are disabled outside development",
        )
    if not settings.jwt_hmac_secret:
        raise ApiError(
            code=SERVICE_DEGRADED,
            message="provisional session signing secret not configured",
            detail="set JWT_HMAC_SECRET for 4.P.0 stub",
        )
    return settings.jwt_hmac_secret


def _cookie_security(settings: Settings) -> tuple[bool, str]:
    samesite = settings.cookie_samesite
    secure = settings.cookie_secure or samesite == "none"
    return secure, samesite


def _apply_cookie(response: Response, params: CookieParams) -> None:
    response.set_cookie(
        key=params.name,
        value=params.value,
        max_age=params.max_age,
        httponly=params.httponly,
        secure=params.secure,
        samesite=params.samesite,
        domain=params.domain,
        path="/",
    )


def _http_only_params(name: str, value: str, max_age: int, settings: Settings) -> CookieParams:
    secure, samesite = _cookie_security(settings)
    return CookieParams(
        name=name,
        value=value,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite=samesite,
        domain=settings.cookie_domain,
    )


def _set_csrf_cookie(response: Response, *, csrf: str, settings: Settings) -> None:
    secure, samesite = _cookie_security(settings)
    # Readable by JS (double-submit); TTL matches refresh so CSRF survives access rotation.
    response.set_cookie(  # NOSONAR python:S3330 — CSRF double-submit must be JS-readable
        key=settings.dashboard_csrf_cookie_name,
        value=csrf,
        max_age=settings.jwt_refresh_token_ttl_seconds,
        httponly=False,
        secure=secure,
        samesite=samesite,
        domain=settings.cookie_domain,
        path="/",
    )


@dataclass(frozen=True, slots=True)
class _SessionPrincipal:
    secret: str
    settings: Settings
    org_id: UUID
    permissions: int
    subject: str


def _mint_access(principal: _SessionPrincipal) -> str:
    return issue_token_opts(
        TokenIssueOpts(
            secret=principal.secret,
            issuer=principal.settings.jwt_issuer,
            audience=principal.settings.jwt_audience,
            org_id=principal.org_id,
            permissions=principal.permissions,
            subject=principal.subject,
            session_kind=SESSION_KIND_ACCESS,
            ttl_seconds=principal.settings.jwt_access_token_ttl_seconds,
        )
    )


def _mint_refresh(principal: _SessionPrincipal) -> str:
    return issue_token_opts(
        TokenIssueOpts(
            secret=principal.secret,
            issuer=principal.settings.jwt_issuer,
            audience=principal.settings.jwt_audience,
            org_id=principal.org_id,
            permissions=principal.permissions,
            subject=principal.subject,
            session_kind=SESSION_KIND_REFRESH,
            ttl_seconds=principal.settings.jwt_refresh_token_ttl_seconds,
        )
    )


def _issue_session_pair(principal: _SessionPrincipal) -> tuple[str, str]:
    return _mint_access(principal), _mint_refresh(principal)


def _apply_session_cookies(
    response: Response,
    *,
    settings: Settings,
    access: str,
    refresh: str | None,
) -> None:
    _apply_cookie(
        response,
        _http_only_params(
            settings.dashboard_session_cookie_name,
            access,
            settings.jwt_access_token_ttl_seconds,
            settings,
        ),
    )
    if refresh is not None:
        _apply_cookie(
            response,
            _http_only_params(
                settings.dashboard_refresh_cookie_name,
                refresh,
                settings.jwt_refresh_token_ttl_seconds,
                settings,
            ),
        )


def _mint_and_set_csrf(response: Response, *, settings: Settings, secret: str) -> str:
    csrf_secret = settings.dashboard_csrf_secret or secret
    csrf = mint_csrf_token(secret=csrf_secret)
    _set_csrf_cookie(response, csrf=csrf, settings=settings)
    return csrf


@router.post("/login")
async def login(
    body: LoginBody,
    request: Request,
    response: Response,
    validator: Annotated[TokenValidator, Depends(get_validator)],
) -> dict[str, object]:
    """PROVISIONAL: PAT → HttpOnly access+refresh cookies. 4.P.1 moves issuance to auth."""
    settings = _settings(request)
    _require_operator_enabled(settings)
    result = await _validate_pat(validator, body.pat.strip())
    if settings.environment != "development":
        return await _login_via_auth(response, settings, result, body.pat.strip())
    return _login_via_hmac(response, settings, result)


async def _login_via_auth(
    response: Response, settings: Settings, result: ValidateResult, pat: str
) -> dict[str, object]:
    try:
        pair = await issue_operator_session(
            auth_grpc_addr=settings.auth_grpc_addr,
            service_token=settings.auth_service_token or "",
            pat=pat,
            timeout_seconds=max(settings.auth_timeout_ms / 1000.0, 0.2),
        )
    except AuthFailedError as exc:
        raise ApiError(code=INVALID_TOKEN, message=_INVALID_TOKEN_MESSAGE) from exc
    except AuthUnavailableError as exc:
        raise ApiError(code=SERVICE_DEGRADED, message=_AUTH_UNAVAILABLE) from exc
    _apply_session_cookies(
        response, settings=settings, access=pair.access_token, refresh=pair.refresh_token
    )
    csrf = _mint_and_set_csrf(
        response, settings=settings, secret=settings.dashboard_csrf_secret or ""
    )
    return {"status": "ok", "provisional": False, "org_id": str(result.org_id), "csrf_token": csrf}


def _login_via_hmac(
    response: Response, settings: Settings, result: ValidateResult
) -> dict[str, object]:
    secret = _require_hmac(settings)
    subject = result.user_id or result.token_id or str(result.org_id)
    access, refresh = _issue_session_pair(
        _SessionPrincipal(
            secret=secret,
            settings=settings,
            org_id=result.org_id,
            permissions=result.permissions,
            subject=subject,
        )
    )
    _apply_session_cookies(response, settings=settings, access=access, refresh=refresh)
    csrf = _mint_and_set_csrf(response, settings=settings, secret=secret)
    return {
        "status": "ok",
        "provisional": True,
        "org_id": str(result.org_id),
        "csrf_token": csrf,
        "warning": "4.P.0 provisional session stub; 4.P.1 replaces issuance with services/auth",
    }


async def _validate_pat(validator: TokenValidator, pat: str) -> ValidateResult:
    try:
        return await validator.validate(pat)
    except AuthFailedError as exc:
        raise ApiError(code=INVALID_TOKEN, message=_INVALID_TOKEN_MESSAGE) from exc
    except AuthUnavailableError as exc:
        raise ApiError(code=SERVICE_DEGRADED, message=_AUTH_UNAVAILABLE) from exc


def _auth_owned_refresh(alg: str, settings: Settings) -> bool:
    # RS256 refresh is always Auth-owned (even when HMAC is also configured).
    # Non-HS256 headers with public keys also go to Auth (matches verify_token_opts).
    return alg == _ALG_RS256 or (bool(settings.jwt_public_keys_pem) and alg != "HS256")


async def _refresh_via_auth(
    *, response: Response, settings: Settings, refresh_token: str
) -> dict[str, object]:
    if not settings.jwt_public_keys_pem:
        raise ApiError(code=SERVICE_DEGRADED, message="session public keys not configured")
    try:
        pair = await refresh_operator_session(
            auth_grpc_addr=settings.auth_grpc_addr,
            service_token=settings.auth_service_token or "",
            refresh_token=refresh_token,
        )
    except AuthFailedError as exc:
        raise ApiError(code=INVALID_TOKEN, message="invalid refresh token") from exc
    except AuthUnavailableError as exc:
        raise ApiError(code=SERVICE_DEGRADED, message=_AUTH_UNAVAILABLE) from exc
    _apply_session_cookies(
        response, settings=settings, access=pair.access_token, refresh=pair.refresh_token
    )
    csrf = ""
    if settings.dashboard_csrf_secret:
        csrf = mint_csrf_token(secret=settings.dashboard_csrf_secret)
        _set_csrf_cookie(response, csrf=csrf, settings=settings)
    return {
        "status": "ok",
        "provisional": False,
        "csrf_token": csrf,
    }


def _refresh_via_hmac(
    *, response: Response, settings: Settings, refresh_token: str
) -> dict[str, object]:
    secret = _require_hmac(settings)
    try:
        claims = verify_token_opts(
            refresh_token,
            TokenVerifyOpts(
                secret=secret,
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
                expect_kind=SESSION_KIND_REFRESH,
                public_keys_pem=settings.jwt_public_keys_pem,
                key_id=settings.jwt_key_id,
            ),
        )
    except SessionStubError as exc:
        raise ApiError(code=INVALID_TOKEN, message=str(exc)) from exc
    access = _mint_access(
        _SessionPrincipal(
            secret=secret,
            settings=settings,
            org_id=claims.org_id,
            permissions=claims.permissions,
            subject=claims.sub,
        )
    )
    _apply_session_cookies(response, settings=settings, access=access, refresh=None)
    csrf = _mint_and_set_csrf(response, settings=settings, secret=secret)
    return {
        "status": "ok",
        "provisional": True,
        "org_id": str(claims.org_id),
        "csrf_token": csrf,
    }


@router.post("/refresh")
async def refresh_session(request: Request, response: Response) -> dict[str, object]:
    settings = _settings(request)
    _require_operator_enabled(settings)
    raw = request.cookies.get(settings.dashboard_refresh_cookie_name)
    if not raw:
        raise ApiError(code=INVALID_TOKEN, message="missing refresh cookie")
    if settings.environment != "development":
        return await _refresh_via_auth(response=response, settings=settings, refresh_token=raw)
    try:
        alg = peek_token_alg(raw)
    except SessionStubError as exc:
        raise ApiError(code=INVALID_TOKEN, message=str(exc)) from exc
    if _auth_owned_refresh(alg, settings):
        return await _refresh_via_auth(response=response, settings=settings, refresh_token=raw)
    return _refresh_via_hmac(response=response, settings=settings, refresh_token=raw)


@router.post("/logout")
async def logout(request: Request) -> Response:
    settings = _settings(request)
    if settings.environment != "development":
        auth_error = await _logout_via_auth(request, settings)
        if auth_error is not None:
            return auth_error
    success = JSONResponse(
        {"status": "ok"},
        headers={"X-Request-ID": require_current()},
    )
    _clear_session_cookies(success, settings)
    return success


async def _logout_via_auth(request: Request, settings: Settings) -> Response | None:
    raw_access = request.cookies.get(settings.dashboard_session_cookie_name)
    raw_refresh = request.cookies.get(settings.dashboard_refresh_cookie_name)
    access_claims = _logout_claims(raw_access, settings=settings, kind=SESSION_KIND_ACCESS)
    refresh_claims = _logout_claims(raw_refresh, settings=settings, kind=SESSION_KIND_REFRESH)
    if access_claims is None and refresh_claims is None:
        return _logout_error(settings, INVALID_TOKEN, "no valid session proof")
    if _logout_proofs_mismatch(access_claims, refresh_claims):
        return _logout_error(settings, INVALID_TOKEN, "session proofs do not match")
    claims = access_claims if access_claims is not None else refresh_claims
    if claims is None:
        return _logout_error(settings, INVALID_TOKEN, "no valid session proof")
    try:
        await revoke_operator_session(
            auth_grpc_addr=settings.auth_grpc_addr,
            service_token=settings.auth_service_token or "",
            session_id=claims.session_id,
            family_id=claims.family_id or "",
            access_jti=access_claims.jti if access_claims else "",
            access_token=raw_access if access_claims else "",
            refresh_token=raw_refresh if refresh_claims else "",
            timeout_seconds=max(settings.auth_timeout_ms / 1000.0, 0.2),
        )
    except AuthFailedError:
        return _logout_error(settings, INVALID_TOKEN, "invalid session")
    except AuthUnavailableError:
        return _logout_error(settings, SERVICE_DEGRADED, _AUTH_UNAVAILABLE)
    return None


def _logout_proofs_mismatch(
    access_claims: SessionClaims | None, refresh_claims: SessionClaims | None
) -> bool:
    return bool(
        access_claims
        and refresh_claims
        and (
            access_claims.session_id != refresh_claims.session_id
            or access_claims.family_id != refresh_claims.family_id
        )
    )


def _logout_error(settings: Settings, code: str, message: str) -> Response:
    error = envelope_response(code=code, message=message, opts=ResponseOpts(settings=settings))
    _clear_session_cookies(error, settings)
    return error


def _logout_claims(raw: str | None, *, settings: Settings, kind: str) -> SessionClaims | None:
    """Return locally verified logout claims, treating stale/malformed cookies independently."""
    if not raw:
        return None
    try:
        return verify_token_opts(
            raw,
            TokenVerifyOpts(
                secret=None,
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
                expect_kind=kind,
                public_keys_pem=settings.jwt_public_keys_pem,
                key_id=settings.jwt_key_id,
            ),
        )
    except SessionStubError:
        return None


def _clear_session_cookies(response: Response, settings: Settings) -> None:
    """Delete all operator-session cookies using the same path/domain attributes."""
    secure, samesite = _cookie_security(settings)
    for name in (
        settings.dashboard_session_cookie_name,
        settings.dashboard_refresh_cookie_name,
        settings.dashboard_csrf_cookie_name,
    ):
        response.delete_cookie(
            name,
            path="/",
            domain=settings.cookie_domain,
            secure=secure,
            httponly=name != settings.dashboard_csrf_cookie_name,
            samesite=samesite,
        )


@router.get("/me")
async def me(request: Request) -> dict[str, object]:
    """Prove cookie session works for authenticated API calls."""
    settings = _settings(request)
    _require_operator_enabled(settings)
    if settings.environment != "development" and not settings.jwt_public_keys_pem:
        raise ApiError(
            code=SERVICE_DEGRADED,
            message="session public keys not configured",
            detail="set DASHBOARD_JWT_PUBLIC_KEYS_PEM",
        )
    if (
        settings.environment == "development"
        and not settings.jwt_hmac_secret
        and not settings.jwt_public_keys_pem
    ):
        raise ApiError(
            code=SERVICE_DEGRADED,
            message="session signing secret not configured",
            detail="set JWT_HMAC_SECRET and/or DASHBOARD_JWT_PUBLIC_KEYS_PEM",
        )
    raw = request.cookies.get(settings.dashboard_session_cookie_name)
    if not raw:
        return await _me_bearer(request)
    if settings.environment != "development":
        return await _me_auth(raw, settings)
    secret = settings.jwt_hmac_secret if settings.environment == "development" else None
    return _me_cookie(raw, settings=settings, secret=secret)


async def _me_auth(raw: str, settings: Settings) -> dict[str, object]:
    try:
        claims = await validate_operator_session(
            auth_grpc_addr=settings.auth_grpc_addr,
            service_token=settings.auth_service_token or "",
            access_token=raw,
            timeout_seconds=max(settings.auth_timeout_ms / 1000.0, 0.2),
        )
    except AuthFailedError as exc:
        raise ApiError(code=INVALID_TOKEN, message="invalid session") from exc
    except AuthUnavailableError as exc:
        raise ApiError(code=SERVICE_DEGRADED, message=_AUTH_UNAVAILABLE) from exc
    return {"auth": "cookie", "org_id": claims.org_id, "sub": claims.subject, "provisional": False}


def _me_cookie(raw: str, *, settings: Settings, secret: str | None) -> dict[str, object]:
    try:
        claims = verify_token_opts(
            raw,
            TokenVerifyOpts(
                secret=secret,
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
                expect_kind=SESSION_KIND_ACCESS,
                public_keys_pem=settings.jwt_public_keys_pem,
                key_id=settings.jwt_key_id,
            ),
        )
    except SessionStubError as exc:
        raise ApiError(code=INVALID_TOKEN, message=str(exc)) from exc
    return {
        "auth": "cookie",
        "org_id": str(claims.org_id),
        "sub": claims.sub,
        "provisional": claims.verify_method != "RS256",
    }


async def _validate_bearer(validator: TokenValidator, bearer: str) -> ValidateResult:
    try:
        return await validator.validate(bearer)
    except AuthFailedError as exc:
        raise ApiError(code=INVALID_TOKEN, message=_INVALID_TOKEN_MESSAGE) from exc
    except AuthUnavailableError as exc:
        raise ApiError(code=SERVICE_DEGRADED, message=_AUTH_UNAVAILABLE) from exc


async def _me_bearer(request: Request) -> dict[str, object]:
    try:
        bearer = parse_authorization_header(request.headers.get("Authorization"))
    except AuthFailedError as exc:
        raise ApiError(code=INVALID_TOKEN, message="missing session cookie") from exc
    validator = request.app.state.api.validator
    if validator is None:
        raise ApiError(code=SERVICE_DEGRADED, message="validator unavailable")
    result = await _validate_bearer(validator, bearer)
    return {
        "auth": "bearer",
        "org_id": str(result.org_id),
        "provisional": False,
    }
