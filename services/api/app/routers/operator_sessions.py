"""Authenticated, metadata-only operator session routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz import require_operator_metadata_session
from app.deps import operator_org_session
from app.operator_session_auth import OperatorSessionAuthorization
from app.pagination import CursorPage
from app.schemas.operator_sessions import (
    OperatorSession,
    OperatorSessionDetail,
    OperatorSessionListQuery,
)
from app.services import operator_sessions as session_service
from app.services.operator_sessions import ListSessionsArgs, SessionListFilters

router = APIRouter(prefix="/v1/operator/sessions", tags=["operator-sessions"])

OperatorSessionAuth = Annotated[
    OperatorSessionAuthorization,
    Depends(require_operator_metadata_session),
]
OperatorSessionDatabase = Annotated[AsyncSession, Depends(operator_org_session)]


@router.get("")
async def operator_session_list(
    operator: OperatorSessionAuth,
    session: OperatorSessionDatabase,
    query: Annotated[OperatorSessionListQuery, Query()],
) -> CursorPage[OperatorSession]:
    page = await session_service.list_operator_sessions(
        session,
        ListSessionsArgs(
            org_id=operator.org_id,
            cursor=query.cursor,
            limit=query.limit,
            filters=SessionListFilters(
                agent_id=query.agent_id,
                status=query.status,
            ),
        ),
    )
    return CursorPage[OperatorSession](data=page.data, pagination=page.pagination)


@router.get("/{session_id}")
async def operator_session_detail(
    session_id: UUID,
    operator: OperatorSessionAuth,
    session: OperatorSessionDatabase,
) -> OperatorSessionDetail:
    return await session_service.get_operator_session(
        session, operator.org_id, session_id
    )
