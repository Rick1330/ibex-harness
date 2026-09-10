"""Org-scoped rate-limit override routes (m4.B.2)."""

from __future__ import annotations

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


def _default_rpm(request: Request) -> int:
    settings = request.app.state.api.settings
    if settings is None:
        return 60
    return int(settings.rate_limit_default_rpm)


def _counter(request: Request) -> RedisRateLimitCounter:
    counter = getattr(request.app.state.api, "rate_limit_counter", None)
    if counter is not None:
        return counter  # type: ignore[no-any-return]
    settings = request.app.state.api.settings
    redis_url = settings.redis_url if settings is not None else None
    return RedisRateLimitCounter(redis_url)


def _publisher(request: Request):
    pub = getattr(request.app.state.api, "rate_limit_config_publisher", None)
    if pub is not None:
        return pub
    return NoopRateLimitConfigPublisher()


@router.get("/{org_id}/rate-limits")
async def get_rate_limits(
    org_id: UUID,
    token: Annotated[ValidateResult, Depends(require_token)],
    session: Annotated[AsyncSession, Depends(org_session)],
    request: Request,
) -> RateLimitsResponse:
    assert_path_org(token.org_id, org_id)
    return await rate_limit_service.get_rate_limits(
        session,
        org_id,
        platform_default_rpm=_default_rpm(request),
        counter=_counter(request),
    )


@router.patch("/{org_id}/rate-limits")
async def patch_rate_limits(
    org_id: UUID,
    body: RateLimitsPatchRequest,
    token: RequireOrgSettings,
    session: Annotated[AsyncSession, Depends(org_session)],
    request: Request,
) -> RateLimitsResponse:
    assert_path_org(token.org_id, org_id)
    return await rate_limit_service.patch_rate_limits(
        session,
        org_id,
        body,
        platform_default_rpm=_default_rpm(request),
        counter=_counter(request),
        publisher=_publisher(request),
    )
