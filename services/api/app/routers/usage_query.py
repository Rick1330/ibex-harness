"""Usage query routes (4.P.4)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.auth.client import ValidateResult
from app.authz import assert_path_org
from app.deps import require_token
from app.schemas.billing import UsageQueryRequest, UsageQueryResponse
from app.services import usage_query as usage_query_service

router = APIRouter(prefix="/v1/organizations", tags=["usage"])


def _settings(request: Request):
    return getattr(request.app.state, "settings", None) or getattr(
        getattr(request.app.state, "api", None), "settings", None
    )


@router.post("/{org_id}/usage/query")
async def query_usage(
    org_id: UUID,
    body: UsageQueryRequest,
    request: Request,
    token: Annotated[ValidateResult, Depends(require_token)],
) -> UsageQueryResponse:
    assert_path_org(token.org_id, org_id)
    settings = _settings(request)
    redis_url = getattr(settings, "redis_url", None) if settings else None
    ch_url = getattr(settings, "clickhouse_http_url", None) if settings else None
    return await usage_query_service.execute_usage_query(
        org_id=org_id,
        body=body,
        redis_url=redis_url,
        clickhouse_url=ch_url,
    )
