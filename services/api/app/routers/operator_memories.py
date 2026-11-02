"""Authenticated, metadata-only operator memory routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz import require_operator_metadata_session
from app.deps import operator_org_session
from app.operator_session_auth import OperatorSessionAuthorization
from app.pagination import CursorPage
from app.schemas.operator_memories import OperatorMemory, OperatorMemoryListQuery
from app.services import operator_memories as memory_service
from app.services.operator_memories import ListMemoriesArgs, MemoryListFilters

router = APIRouter(prefix="/v1/operator/memories", tags=["operator-memories"])

OperatorSession = Annotated[
    OperatorSessionAuthorization,
    Depends(require_operator_metadata_session),
]
OperatorSessionDatabase = Annotated[AsyncSession, Depends(operator_org_session)]


@router.get("")
async def operator_memory_list(
    operator: OperatorSession,
    session: OperatorSessionDatabase,
    query: Annotated[OperatorMemoryListQuery, Query()],
) -> CursorPage[OperatorMemory]:
    page = await memory_service.list_operator_memories(
        session,
        ListMemoriesArgs(
            org_id=operator.org_id,
            cursor=query.cursor,
            limit=query.limit,
            filters=MemoryListFilters(
                agent_id=query.agent_id,
                session_id=query.session_id,
                status=query.status,
                category=query.category,
            ),
        ),
    )
    return CursorPage[OperatorMemory](
        data=page.data,
        pagination=page.pagination,
    )


@router.get("/{memory_id}")
async def operator_memory_detail(
    memory_id: UUID,
    operator: OperatorSession,
    session: OperatorSessionDatabase,
) -> OperatorMemory:
    return await memory_service.get_operator_memory(
        session, operator.org_id, memory_id
    )
