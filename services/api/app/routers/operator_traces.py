"""Authenticated, metadata-only D2 operator trace reads."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from authclient.permissions import OPERATOR_METADATA_READ
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz import assert_operator_permission
from app.config import Settings
from app.deps import operator_org_session
from app.operator_session_auth import OperatorSessionAuthorization, require_operator_session
from app.schemas.operator_traces import OperatorTraceDetailResponse, OperatorTraceListResponse
from app.services.operator_traces import get_operator_trace, list_operator_traces

router = APIRouter(prefix="/v1/operator/traces", tags=["operator-traces"])
OperatorSession = Annotated[OperatorSessionAuthorization, Depends(require_operator_session)]
OperatorSessionDatabase = Annotated[AsyncSession, Depends(operator_org_session)]


def require_trace_read_session(request: Request, operator: OperatorSession) -> OperatorSessionAuthorization:
    assert_operator_permission(request.app.state.settings, operator.permissions, OPERATOR_METADATA_READ)
    return operator


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("")
async def operator_trace_list(
    response: Response,
    operator: Annotated[OperatorSessionAuthorization, Depends(require_trace_read_session)],
    session: OperatorSessionDatabase,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    status: Annotated[Literal["ok", "error"] | None, Query()] = None,
    started_after: Annotated[datetime | None, Query()] = None,
    started_before: Annotated[datetime | None, Query()] = None,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> OperatorTraceListResponse:
    result = await list_operator_traces(
        session,
        _settings(request),
        operator,
        query_start=started_after,
        query_end=started_before,
        status=status,
        limit=limit,
        cursor=cursor,
    )
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/{trace_id}")
async def operator_trace_detail(
    trace_id: str,
    response: Response,
    operator: Annotated[OperatorSessionAuthorization, Depends(require_trace_read_session)],
    session: OperatorSessionDatabase,
) -> OperatorTraceDetailResponse:
    result = await get_operator_trace(session, operator, trace_id=trace_id)
    response.headers["Cache-Control"] = "no-store"
    return result
