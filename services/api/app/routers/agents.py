"""Agent management routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.client import ValidateResult
from app.authz import RequireOrgSettings
from app.deps import org_session, require_token
from app.pagination import CursorPage
from app.schemas.agents import (
    AgentCreate,
    AgentListQuery,
    AgentPatch,
    AgentResponse,
)
from app.services import agents as agent_service
from app.services.agents import AgentListFilters, ListAgentsArgs

router = APIRouter(prefix="/v1/agents", tags=["agents"])


def _optional_user_uuid(raw: str | None) -> UUID | None:
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


@dataclass(frozen=True)
class _AgentListCtx:
    org_id: UUID
    session: AsyncSession
    query: AgentListQuery


def _agent_list_ctx(
    token: Annotated[ValidateResult, Depends(require_token)],
    session: Annotated[AsyncSession, Depends(org_session)],
    query: Annotated[AgentListQuery, Query()],
) -> _AgentListCtx:
    return _AgentListCtx(org_id=token.org_id, session=session, query=query)


@router.get("")
async def list_agents(
    ctx: Annotated[_AgentListCtx, Depends(_agent_list_ctx)],
) -> CursorPage[AgentResponse]:
    return await agent_service.list_agents(
        ctx.session,
        ListAgentsArgs(
            org_id=ctx.org_id,
            cursor=ctx.query.cursor,
            limit=ctx.query.limit,
            filters=AgentListFilters(
                status=ctx.query.status,
                tags=ctx.query.tags,
                search=ctx.query.search,
            ),
        ),
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: AgentCreate,
    token: RequireOrgSettings,
    session: Annotated[AsyncSession, Depends(org_session)],
) -> AgentResponse:
    created_by = _optional_user_uuid(token.user_id)
    return await agent_service.create_agent(
        session,
        agent_service.CreateAgentArgs(
            org_id=token.org_id, body=body, created_by=created_by
        ),
    )


@router.get("/{agent_id}")
async def get_agent(
    agent_id: UUID,
    token: Annotated[ValidateResult, Depends(require_token)],
    session: Annotated[AsyncSession, Depends(org_session)],
) -> AgentResponse:
    return await agent_service.get_agent(session, token.org_id, agent_id)


@router.patch("/{agent_id}")
async def patch_agent(
    agent_id: UUID,
    body: AgentPatch,
    token: RequireOrgSettings,
    session: Annotated[AsyncSession, Depends(org_session)],
) -> AgentResponse:
    return await agent_service.patch_agent(session, token.org_id, agent_id, body)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_agent(
    agent_id: UUID,
    token: RequireOrgSettings,
    session: Annotated[AsyncSession, Depends(org_session)],
) -> Response:
    await agent_service.soft_delete_agent(session, token.org_id, agent_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _lifecycle(
    agent_id: UUID,
    action: Literal["activate", "pause", "archive"],
    token: RequireOrgSettings,
    session: AsyncSession,
) -> AgentResponse:
    return await agent_service.set_agent_status(session, token.org_id, agent_id, action)


@router.post("/{agent_id}/activate")
async def activate_agent(
    agent_id: UUID,
    token: RequireOrgSettings,
    session: Annotated[AsyncSession, Depends(org_session)],
) -> AgentResponse:
    return await _lifecycle(agent_id, "activate", token, session)


@router.post("/{agent_id}/pause")
async def pause_agent(
    agent_id: UUID,
    token: RequireOrgSettings,
    session: Annotated[AsyncSession, Depends(org_session)],
) -> AgentResponse:
    return await _lifecycle(agent_id, "pause", token, session)


@router.post("/{agent_id}/archive")
async def archive_agent(
    agent_id: UUID,
    token: RequireOrgSettings,
    session: Annotated[AsyncSession, Depends(org_session)],
) -> AgentResponse:
    return await _lifecycle(agent_id, "archive", token, session)
