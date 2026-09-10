"""Org-scoped rate-limit override routes (m4.B.2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.client import ValidateResult
from app.authz import RequireOrgSettings, assert_path_org
from app.deps import org_session, require_token
from app.rate_limit_publish import NoopRateLimitConfigPublisher, RedisRateLimitCounter
from app.schemas.rate_limits import RateLimitsPatchRequest, RateLimitsResponse
from app.services import rate_limits as rate_limit_service

router = APIRouter(prefix="/v1/organizations", tags=["rate-limits"])


@dataclass(frozen=True, slots=True)
class _RateLimitCtx:
    org_id: UUID
    session: AsyncSession
    platform_default_rpm: int
    counter: RedisRateLimitCounter
    publisher: object


def _api_state(request: Request):
    return getattr(request.app.state, "api", None)


def _default_rpm(request: Request) -> int:
    settings = getattr(_api_state(request), "settings", None)
    if settings is None:
        return 60
    return int(settings.rate_limit_default_rpm)


def _counter(request: Request) -> RedisRateLimitCounter:
    state = _api_state(request)
    counter = getattr(state, "rate_limit_counter", None)
    if counter is not None:
        return counter  # type: ignore[no-any-return]
    settings = getattr(state, "settings", None)
    redis_url = settings.redis_url if settings is not None else None
    return RedisRateLimitCounter(redis_url)


def _publisher(request: Request):
    pub = getattr(_api_state(request), "rate_limit_config_publisher", None)
    if pub is not None:
        return pub
    return NoopRateLimitConfigPublisher()


def _make_ctx(
    request: Request, org_id: UUID, token_org_id: UUID, session: AsyncSession
) -> _RateLimitCtx:
    assert_path_org(token_org_id, org_id)
    return _RateLimitCtx(
        org_id=org_id,
        session=session,
        platform_default_rpm=_default_rpm(request),
        counter=_counter(request),
        publisher=_publisher(request),
    )


def _rate_limit_read_ctx(
    request: Request,
    org_id: UUID,
    token: Annotated[ValidateResult, Depends(require_token)],
    session: Annotated[AsyncSession, Depends(org_session)],
) -> _RateLimitCtx:
    return _make_ctx(request, org_id, token.org_id, session)


def _rate_limit_write_ctx(
    request: Request,
    org_id: UUID,
    token: RequireOrgSettings,
    session: Annotated[AsyncSession, Depends(org_session)],
) -> _RateLimitCtx:
    return _make_ctx(request, org_id, token.org_id, session)


@router.get("/{org_id}/rate-limits")
async def get_rate_limits(
    ctx: Annotated[_RateLimitCtx, Depends(_rate_limit_read_ctx)],
) -> RateLimitsResponse:
    return await rate_limit_service.get_rate_limits(
        ctx.session,
        ctx.org_id,
        platform_default_rpm=ctx.platform_default_rpm,
        counter=ctx.counter,
    )


@router.patch("/{org_id}/rate-limits")
async def patch_rate_limits(
    body: RateLimitsPatchRequest,
    ctx: Annotated[_RateLimitCtx, Depends(_rate_limit_write_ctx)],
) -> RateLimitsResponse:
    return await rate_limit_service.patch_rate_limits(
        ctx.session,
        ctx.org_id,
        body,
        deps=rate_limit_service.PatchDeps(
            platform_default_rpm=ctx.platform_default_rpm,
            counter=ctx.counter,
            publisher=ctx.publisher,  # type: ignore[arg-type]
        ),
    )
