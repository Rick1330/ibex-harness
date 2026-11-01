"""Authenticated, read-only operator agent routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz import require_operator_metadata_session
from app.deps import operator_org_session
from app.operator_session_auth import OperatorSessionAuthorization
from app.pagination import CursorPage
from app.schemas.agents import AgentListQuery
from app.schemas.operator_agents import OperatorAgent
from app.services import agents as agent_service
from app.services.agents import AgentListFilters, ListAgentsArgs

router = APIRouter(prefix="/v1/operator/agents", tags=["operator-agents"])

OperatorSession = Annotated[
    OperatorSessionAuthorization,
    Depends(require_operator_metadata_session),
]
OperatorSessionDatabase = Annotated[AsyncSession, Depends(operator_org_session)]


@router.get("")
async def operator_agent_list(
    operator: OperatorSession,
    session: OperatorSessionDatabase,
    query: Annotated[AgentListQuery, Query()],
) -> CursorPage[OperatorAgent]:
    page = await agent_service.list_agents(
        session,
        ListAgentsArgs(
            org_id=operator.org_id,
            cursor=query.cursor,
            limit=query.limit,
            filters=AgentListFilters(
                status=query.status,
                tags=query.tags,
                search=query.search,
            ),
        ),
    )
    return CursorPage[OperatorAgent](
        data=[OperatorAgent.from_agent(agent) for agent in page.data],
        pagination=page.pagination,
    )


@router.get("/{agent_id}")
async def operator_agent_detail(
    agent_id: UUID,
    operator: OperatorSession,
    session: OperatorSessionDatabase,
) -> OperatorAgent:
    agent = await agent_service.get_agent(session, operator.org_id, agent_id)
    return OperatorAgent.from_agent(agent)
