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
class BillingRouteCtx:
    org_id: UUID
    session: AsyncSession
    publisher: BudgetPublisher


def _budget_publisher_from_request(request: Request) -> BudgetPublisher:
    api = getattr(request.app.state, "api", None)
    pub = getattr(api, "budget_publisher", None) if api is not None else None
    if pub is not None:
        return pub  # type: ignore[no-any-return]
    return NoopBudgetPublisher()


def _billing_read_ctx(
    request: Request,
    org_id: UUID,
    token: Annotated[ValidateResult, Depends(require_token)],
    session: Annotated[AsyncSession, Depends(org_session)],
) -> BillingRouteCtx:
    assert_path_org(token.org_id, org_id)
    return BillingRouteCtx(
        org_id=org_id,
        session=session,
        publisher=_budget_publisher_from_request(request),
    )


def _billing_write_ctx(
    request: Request,
    org_id: UUID,
    token: RequireOrgSettings,
    session: Annotated[AsyncSession, Depends(org_session)],
) -> BillingRouteCtx:
    assert_path_org(token.org_id, org_id)
    return BillingRouteCtx(
        org_id=org_id,
        session=session,
        publisher=_budget_publisher_from_request(request),
    )


@router.get("/{org_id}/rate-cards")
async def list_rate_cards(
    ctx: Annotated[BillingRouteCtx, Depends(_billing_read_ctx)],
    query: Annotated[ListQuery, Query()],
) -> CursorPage[RateCardResponse]:
    return await billing_service.list_rate_cards(
        ctx.session, ctx.org_id, cursor=query.cursor, limit=query.limit
    )


@router.post("/{org_id}/rate-cards", status_code=status.HTTP_201_CREATED)
async def create_rate_card(
    body: RateCardCreate,
    ctx: Annotated[BillingRouteCtx, Depends(_billing_write_ctx)],
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
    ctx: Annotated[BillingRouteCtx, Depends(_billing_write_ctx)],
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
    ctx: Annotated[BillingRouteCtx, Depends(_billing_read_ctx)],
    query: Annotated[ListQuery, Query()],
) -> CursorPage[BudgetPeriodResponse]:
    return await billing_service.list_budget_periods(
        ctx.session, ctx.org_id, cursor=query.cursor, limit=query.limit
    )


@router.post("/{org_id}/budget-periods", status_code=status.HTTP_201_CREATED)
async def create_budget_period(
    body: BudgetPeriodCreate,
    ctx: Annotated[BillingRouteCtx, Depends(_billing_write_ctx)],
) -> BudgetPeriodResponse:
    return await billing_service.create_budget_period(
        ctx.session, ctx.org_id, body, deps=billing_service.WriteDeps(publisher=ctx.publisher)
    )
