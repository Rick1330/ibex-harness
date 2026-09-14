"""Provisional operator session routes (4.P.0 stub — full identity is 4.P.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from apierror_py import INVALID_TOKEN, SERVICE_DEGRADED
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.auth.client import (
    AuthFailedError,
    AuthUnavailableError,
    TokenValidator,
    ValidateResult,
    parse_authorization_header,
)
from app.config import Settings
from app.deps import get_validator
from app.errors import ApiError
from app.session_stub import (
    SESSION_KIND_ACCESS,
    SESSION_KIND_REFRESH,
    SessionStubError,
    TokenIssueOpts,
    issue_token_opts,
    mint_csrf_token,
    verify_token,
)

router = APIRouter(prefix="/v1/operator/session", tags=["operator-session-provisional"])


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


def _set_http_only_cookie(
    response: Response, *, name: str, value: str, settings: Settings, max_age: int
) -> None:
    secure, samesite = _cookie_security(settings)
    _apply_cookie(
        response,
        CookieParams(
            name=name,
            value=value,
            max_age=max_age,
            httponly=True,
            secure=secure,
            samesite=samesite,
            domain=settings.cookie_domain,
        ),
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


def _mint_token(
    *,
    secret: str,
    settings: Settings,
    org_id: UUID,
    permissions: int,
    subject: str,
    session_kind: str,
    ttl_seconds: int,
) -> str:
    return issue_token_opts(
        TokenIssueOpts(
            secret=secret,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            org_id=org_id,
            permissions=permissions,
            subject=subject,
            session_kind=session_kind,
            ttl_seconds=ttl_seconds,
        )
    )


def _issue_session_pair(
    *,
    secret: str,
    settings: Settings,
    org_id: UUID,
    permissions: int,
    subject: str,
) -> tuple[str, str]:
    access = _mint_token(
        secret=secret,
        settings=settings,
        org_id=org_id,
        permissions=permissions,
        subject=subject,
        session_kind=SESSION_KIND_ACCESS,
        ttl_seconds=settings.jwt_access_token_ttl_seconds,
    )
    refresh = _mint_token(
        secret=secret,
        settings=settings,
        org_id=org_id,
        permissions=permissions,
        subject=subject,
        session_kind=SESSION_KIND_REFRESH,
        ttl_seconds=settings.jwt_refresh_token_ttl_seconds,
    )
    return access, refresh


def _apply_session_cookies(
    response: Response,
    *,
    settings: Settings,
    access: str,
    refresh: str | None,
) -> None:
    _set_http_only_cookie(
        response,
        name=settings.dashboard_session_cookie_name,
        value=access,
        settings=settings,
        max_age=settings.jwt_access_token_ttl_seconds,
    )
    if refresh is not None:
        _set_http_only_cookie(
            response,
            name=settings.dashboard_refresh_cookie_name,
            value=refresh,
            settings=settings,
            max_age=settings.jwt_refresh_token_ttl_seconds,
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
    secret = _require_hmac(settings)
    result = await _validate_pat(validator, body.pat.strip())
    subject = result.user_id or result.token_id or str(result.org_id)
    access, refresh = _issue_session_pair(
        secret=secret,
        settings=settings,
        org_id=result.org_id,
        permissions=result.permissions,
        subject=subject,
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
        raise ApiError(code=INVALID_TOKEN, message="invalid token") from exc
    except AuthUnavailableError as exc:
        raise ApiError(code=SERVICE_DEGRADED, message="auth unavailable") from exc


@router.post("/refresh")
async def refresh_session(request: Request, response: Response) -> dict[str, object]:
    settings = _settings(request)
    _require_operator_enabled(settings)
    secret = _require_hmac(settings)
    raw = request.cookies.get(settings.dashboard_refresh_cookie_name)
    if not raw:
        raise ApiError(code=INVALID_TOKEN, message="missing refresh cookie")
    try:
        claims = verify_token(
            raw,
            secret=secret,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            expect_kind=SESSION_KIND_REFRESH,
        )
    except SessionStubError as exc:
        raise ApiError(code=INVALID_TOKEN, message=str(exc)) from exc
    access = _mint_token(
        secret=secret,
        settings=settings,
        org_id=claims.org_id,
        permissions=claims.permissions,
        subject=claims.sub,
        session_kind=SESSION_KIND_ACCESS,
        ttl_seconds=settings.jwt_access_token_ttl_seconds,
    )
    _apply_session_cookies(response, settings=settings, access=access, refresh=None)
    csrf = _mint_and_set_csrf(response, settings=settings, secret=secret)
    return {
        "status": "ok",
        "provisional": True,
        "org_id": str(claims.org_id),
        "csrf_token": csrf,
    }


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict[str, str]:
    settings = _settings(request)
    for name in (
        settings.dashboard_session_cookie_name,
        settings.dashboard_refresh_cookie_name,
        settings.dashboard_csrf_cookie_name,
    ):
        response.delete_cookie(name, path="/", domain=settings.cookie_domain)
    return {"status": "ok"}


@router.get("/me")
async def me(request: Request) -> dict[str, object]:
    """Prove cookie session works for authenticated API calls."""
    settings = _settings(request)
    _require_operator_enabled(settings)
    secret = _require_hmac(settings)
    raw = request.cookies.get(settings.dashboard_session_cookie_name)
    if not raw:
        return await _me_bearer(request)
    return _me_cookie(raw, settings=settings, secret=secret)


def _me_cookie(raw: str, *, settings: Settings, secret: str) -> dict[str, object]:
    try:
        claims = verify_token(
            raw,
            secret=secret,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            expect_kind=SESSION_KIND_ACCESS,
        )
    except SessionStubError as exc:
        raise ApiError(code=INVALID_TOKEN, message=str(exc)) from exc
    return {
        "auth": "cookie",
        "org_id": str(claims.org_id),
        "sub": claims.sub,
        "provisional": True,
    }


async def _validate_bearer(validator: TokenValidator, bearer: str) -> ValidateResult:
    try:
        return await validator.validate(bearer)
    except AuthFailedError as exc:
        raise ApiError(code=INVALID_TOKEN, message="invalid token") from exc
    except AuthUnavailableError as exc:
        raise ApiError(code=SERVICE_DEGRADED, message="auth unavailable") from exc


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
