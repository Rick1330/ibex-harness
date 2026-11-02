"""Authenticated, metadata-only operator directive routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz import require_operator_metadata_session
from app.deps import operator_org_session
from app.operator_session_auth import OperatorSessionAuthorization
from app.pagination import CursorPage
from app.schemas.operator_directives import (
    OperatorDirectiveDetail,
    OperatorDirectiveDetailQuery,
    OperatorDirectiveListQuery,
    OperatorDirectiveSummary,
)
from app.services import operator_directives as directive_service
from app.services.operator_directives import DirectiveDetailArgs, DirectiveListArgs

router = APIRouter(prefix="/v1/operator/directives", tags=["operator-directives"])

OperatorSessionAuth = Annotated[
    OperatorSessionAuthorization,
    Depends(require_operator_metadata_session),
]
OperatorSessionDatabase = Annotated[AsyncSession, Depends(operator_org_session)]


@router.get("")
async def operator_directive_list(
    operator: OperatorSessionAuth,
    session: OperatorSessionDatabase,
    query: Annotated[OperatorDirectiveListQuery, Query()],
) -> CursorPage[OperatorDirectiveSummary]:
    return await directive_service.list_operator_directives(
        session,
        DirectiveListArgs(
            org_id=operator.org_id,
            state=query.state,
            agent_id=query.agent_id,
            cursor=query.cursor,
            limit=query.limit,
        ),
    )


@router.get("/{directive_id}")
async def operator_directive_detail(
    directive_id: UUID,
    operator: OperatorSessionAuth,
    session: OperatorSessionDatabase,
    query: Annotated[OperatorDirectiveDetailQuery, Query()],
) -> OperatorDirectiveDetail:
    return await directive_service.get_operator_directive(
        session,
        DirectiveDetailArgs(
            org_id=operator.org_id,
            directive_id=directive_id,
            usage_range=query.range,
        ),
    )
