"""Authenticated, metadata-only D2 operator trace reads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from authclient.permissions import OPERATOR_METADATA_READ
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz import assert_operator_permission
from app.config import Settings
from app.deps import operator_org_session
from app.operator_session_auth import OperatorSessionAuthorization, require_operator_session
from app.schemas.operator_traces import (
    OperatorTraceDetailResponse,
    OperatorTraceListQuery,
    OperatorTraceListResponse,
)
from app.services.operator_traces import get_operator_trace, list_operator_traces

router = APIRouter(prefix="/v1/operator/traces", tags=["operator-traces"])
OperatorSession = Annotated[OperatorSessionAuthorization, Depends(require_operator_session)]
OperatorSessionDatabase = Annotated[AsyncSession, Depends(operator_org_session)]


@dataclass(frozen=True)
class TraceListContext:
    session: AsyncSession
    settings: Settings


def require_trace_read_session(request: Request, operator: OperatorSession) -> OperatorSessionAuthorization:
    assert_operator_permission(request.app.state.settings, operator.permissions, OPERATOR_METADATA_READ)
    return operator


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def trace_list_context(
    request: Request,
    session: OperatorSessionDatabase,
) -> TraceListContext:
    return TraceListContext(session=session, settings=_settings(request))


trace_list_context.__route_inventory_security__ = False


@router.get("")
async def operator_trace_list(
    response: Response,
    operator: Annotated[OperatorSessionAuthorization, Depends(require_trace_read_session)],
    context: Annotated[TraceListContext, Depends(trace_list_context)],
    query: Annotated[OperatorTraceListQuery, Query()],
) -> OperatorTraceListResponse:
    result = await list_operator_traces(
        context.session,
        context.settings,
        operator,
        query_start=query.started_after,
        query_end=query.started_before,
        status=query.status,
        limit=query.limit,
        cursor=query.cursor,
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
