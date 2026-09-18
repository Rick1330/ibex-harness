"""Billing rate-card and budget-period routes (4.P.4)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.client import ValidateResult
from app.authz import RequireOrgSettings, assert_path_org
from app.budget_publish import BudgetPublisher, NoopBudgetPublisher
from app.deps import org_session, require_token
from app.pagination import CursorPage, ListQuery
from app.schemas.billing import (
    BudgetPeriodCreate,
    BudgetPeriodResponse,
    RateCardCreate,
    RateCardResponse,
    RateCardVersionPublish,
    RateCardVersionResponse,
)
from app.services import billing as billing_service

router = APIRouter(prefix="/v1/organizations", tags=["billing"])


@dataclass(frozen=True, slots=True)
class _Ctx:
    org_id: UUID
    session: AsyncSession
    publisher: BudgetPublisher


def _api_state(request: Request):
    return getattr(request.app.state, "api", None)


def _publisher(request: Request) -> BudgetPublisher:
    pub = getattr(_api_state(request), "budget_publisher", None)
    if pub is not None:
        return pub  # type: ignore[no-any-return]
    return NoopBudgetPublisher()


def _make_ctx(
    request: Request, org_id: UUID, token_org_id: UUID, session: AsyncSession
) -> _Ctx:
    assert_path_org(token_org_id, org_id)
    return _Ctx(org_id=org_id, session=session, publisher=_publisher(request))


def _read_ctx(
    request: Request,
    org_id: UUID,
    token: Annotated[ValidateResult, Depends(require_token)],
    session: Annotated[AsyncSession, Depends(org_session)],
) -> _Ctx:
    return _make_ctx(request, org_id, token.org_id, session)


def _write_ctx(
    request: Request,
    org_id: UUID,
    token: RequireOrgSettings,
    session: Annotated[AsyncSession, Depends(org_session)],
) -> _Ctx:
    return _make_ctx(request, org_id, token.org_id, session)


@router.get("/{org_id}/rate-cards")
async def list_rate_cards(
    ctx: Annotated[_Ctx, Depends(_read_ctx)],
    query: Annotated[ListQuery, Query()],
) -> CursorPage[RateCardResponse]:
    return await billing_service.list_rate_cards(
        ctx.session, ctx.org_id, cursor=query.cursor, limit=query.limit
    )


@router.post("/{org_id}/rate-cards", status_code=status.HTTP_201_CREATED)
async def create_rate_card(
    body: RateCardCreate,
    ctx: Annotated[_Ctx, Depends(_write_ctx)],
) -> RateCardResponse:
    return await billing_service.create_rate_card(
        ctx.session, ctx.org_id, body, deps=billing_service.WriteDeps(publisher=ctx.publisher)
    )


@router.post(
    "/{org_id}/rate-cards/{card_id}/versions",
    status_code=status.HTTP_201_CREATED,
)
async def publish_rate_card_version(
    card_id: UUID,
    body: RateCardVersionPublish,
    ctx: Annotated[_Ctx, Depends(_write_ctx)],
) -> RateCardVersionResponse:
    return await billing_service.publish_rate_card_version(
        ctx.session,
        ctx.org_id,
        card_id,
        body,
        deps=billing_service.WriteDeps(publisher=ctx.publisher),
    )


@router.get("/{org_id}/budget-periods")
async def list_budget_periods(
    ctx: Annotated[_Ctx, Depends(_read_ctx)],
    query: Annotated[ListQuery, Query()],
) -> CursorPage[BudgetPeriodResponse]:
    return await billing_service.list_budget_periods(
        ctx.session, ctx.org_id, cursor=query.cursor, limit=query.limit
    )


@router.post("/{org_id}/budget-periods", status_code=status.HTTP_201_CREATED)
async def create_budget_period(
    body: BudgetPeriodCreate,
    ctx: Annotated[_Ctx, Depends(_write_ctx)],
) -> BudgetPeriodResponse:
    return await billing_service.create_budget_period(
        ctx.session, ctx.org_id, body, deps=billing_service.WriteDeps(publisher=ctx.publisher)
    )
