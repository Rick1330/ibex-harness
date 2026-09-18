"""Rate-card and budget-period persistence (4.P.4)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from uuid import UUID

from apierror_py import INTERNAL_ERROR, NOT_FOUND, VALIDATION_ERROR
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.budget_publish import BudgetPublisher, NoopBudgetPublisher
from app.errors import ApiError
from app.pagination import CursorPage, decode_cursor, encode_cursor, page_from_rows
from app.schemas.billing import (
    BudgetPeriodCreate,
    BudgetPeriodResponse,
    RateCardCreate,
    RateCardResponse,
    RateCardVersionPublish,
    RateCardVersionResponse,
)

logger = logging.getLogger(__name__)

_NOT_FOUND_CARD = "Rate card not found"
_NOT_FOUND_PERIOD = "Budget period not found"


@dataclass(frozen=True, slots=True)
class WriteDeps:
    publisher: BudgetPublisher | None = None


async def _publish(deps: WriteDeps, org_id: UUID) -> None:
    pub = deps.publisher or NoopBudgetPublisher()
    try:
        await pub.publish_budget_update(str(org_id))
    except (OSError, RuntimeError, TimeoutError) as exc:
        logger.warning("budget publish failed: %s", exc)


def _card_row(row) -> RateCardResponse:
    return RateCardResponse(
        id=UUID(str(row.id)),
        org_id=UUID(str(row.org_id)),
        name=str(row.name),
        currency=str(row.currency),
        status=str(row.status),  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _period_row(row) -> BudgetPeriodResponse:
    return BudgetPeriodResponse(
        id=UUID(str(row.id)),
        org_id=UUID(str(row.org_id)),
        period_start=row.period_start,
        period_end=row.period_end,
        cap_cents=int(row.cap_cents),
        spent_cents_cached=int(row.spent_cents_cached),
        enforcement_mode=str(row.enforcement_mode),  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def list_rate_cards(
    session: AsyncSession, org_id: UUID, *, cursor: str | None = None, limit: int = 50
) -> CursorPage[RateCardResponse]:
    cursor_name: str | None = None
    if cursor:
        try:
            payload = decode_cursor(cursor) or {}
            cursor_name = str(payload["name"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ApiError(code=VALIDATION_ERROR, message="invalid cursor") from exc
    result = await session.execute(
        text(
            """
            SELECT id, org_id, name, currency, status, created_at, updated_at
            FROM ibex_billing.rate_cards
            WHERE org_id = CAST(:org_id AS uuid)
              AND (CAST(:cursor_name AS text) IS NULL OR name > CAST(:cursor_name AS text))
            ORDER BY name ASC
            LIMIT :limit
            """
        ),
        {"org_id": str(org_id), "cursor_name": cursor_name, "limit": limit + 1},
    )
    rows = [_card_row(r) for r in result.fetchall()]
    next_cursor = None
    if len(rows) > limit:
        next_cursor = encode_cursor({"name": rows[limit - 1].name})
    return page_from_rows(rows, limit=limit, next_cursor=next_cursor)


async def create_rate_card(
    session: AsyncSession, org_id: UUID, body: RateCardCreate, *, deps: WriteDeps
) -> RateCardResponse:
    try:
        result = await session.execute(
            text(
                """
                INSERT INTO ibex_billing.rate_cards (org_id, name, currency, status)
                VALUES (CAST(:org_id AS uuid), :name, :currency, 'draft')
                RETURNING id, org_id, name, currency, status, created_at, updated_at
                """
            ),
            {"org_id": str(org_id), "name": body.name, "currency": body.currency},
        )
        row = result.first()
        if row is None:
            raise ApiError(code=INTERNAL_ERROR, message="Unable to create rate card")
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError(code=VALIDATION_ERROR, message="Rate card name already exists") from exc
    await _publish(deps, org_id)
    return _card_row(row)


async def publish_rate_card_version(
    session: AsyncSession,
    org_id: UUID,
    card_id: UUID,
    body: RateCardVersionPublish,
    *,
    deps: WriteDeps,
) -> RateCardVersionResponse:
    existing = await session.execute(
        text(
            """
            SELECT id FROM ibex_billing.rate_cards
            WHERE id = CAST(:card_id AS uuid) AND org_id = CAST(:org_id AS uuid)
            FOR UPDATE
            """
        ),
        {"card_id": str(card_id), "org_id": str(org_id)},
    )
    if existing.first() is None:
        raise ApiError(code=NOT_FOUND, message=_NOT_FOUND_CARD)

    next_ver = await session.execute(
        text(
            """
            SELECT COALESCE(MAX(version), 0) + 1 AS v
            FROM ibex_billing.rate_card_versions
            WHERE rate_card_id = CAST(:card_id AS uuid)
            """
        ),
        {"card_id": str(card_id)},
    )
    version = int(next_ver.scalar_one())
    prices_json = json.dumps([p.model_dump() for p in body.prices])
    result = await session.execute(
        text(
            """
            INSERT INTO ibex_billing.rate_card_versions
                (rate_card_id, org_id, version, prices)
            VALUES (
                CAST(:card_id AS uuid), CAST(:org_id AS uuid), :version, CAST(:prices AS jsonb)
            )
            RETURNING id, rate_card_id, org_id, version, published_at, prices
            """
        ),
        {
            "card_id": str(card_id),
            "org_id": str(org_id),
            "version": version,
            "prices": prices_json,
        },
    )
    row = result.first()
    if row is None:
        raise ApiError(code=INTERNAL_ERROR, message="Unable to publish rate card version")
    await session.execute(
        text(
            """
            UPDATE ibex_billing.rate_cards
            SET status = 'published', updated_at = now()
            WHERE id = CAST(:card_id AS uuid) AND org_id = CAST(:org_id AS uuid)
            """
        ),
        {"card_id": str(card_id), "org_id": str(org_id)},
    )
    await session.commit()
    await _publish(deps, org_id)
    prices = row.prices if isinstance(row.prices, list) else json.loads(row.prices)
    return RateCardVersionResponse(
        id=UUID(str(row.id)),
        rate_card_id=UUID(str(row.rate_card_id)),
        org_id=UUID(str(row.org_id)),
        version=int(row.version),
        published_at=row.published_at,
        prices=prices,
    )


async def list_budget_periods(
    session: AsyncSession, org_id: UUID, *, cursor: str | None = None, limit: int = 50
) -> CursorPage[BudgetPeriodResponse]:
    cursor_start = None
    cursor_id = None
    if cursor:
        try:
            payload = decode_cursor(cursor) or {}
            cursor_start = payload["period_start"]
            cursor_id = str(payload["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ApiError(code=VALIDATION_ERROR, message="invalid cursor") from exc
    result = await session.execute(
        text(
            """
            SELECT id, org_id, period_start, period_end, cap_cents, spent_cents_cached,
                   enforcement_mode, created_at, updated_at
            FROM ibex_billing.budget_periods
            WHERE org_id = CAST(:org_id AS uuid)
              AND (
                CAST(:cursor_start AS timestamptz) IS NULL
                OR period_start < CAST(:cursor_start AS timestamptz)
                OR (
                  period_start = CAST(:cursor_start AS timestamptz)
                  AND id::text > CAST(:cursor_id AS text)
                )
              )
            ORDER BY period_start DESC, id ASC
            LIMIT :limit
            """
        ),
        {
            "org_id": str(org_id),
            "cursor_start": cursor_start,
            "cursor_id": cursor_id,
            "limit": limit + 1,
        },
    )
    rows = [_period_row(r) for r in result.fetchall()]
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode_cursor(
            {"period_start": last.period_start.isoformat(), "id": str(last.id)}
        )
    return page_from_rows(rows, limit=limit, next_cursor=next_cursor)


async def create_budget_period(
    session: AsyncSession, org_id: UUID, body: BudgetPeriodCreate, *, deps: WriteDeps
) -> BudgetPeriodResponse:
    result = await session.execute(
        text(
            """
            INSERT INTO ibex_billing.budget_periods
                (org_id, period_start, period_end, cap_cents, enforcement_mode)
            VALUES (
                CAST(:org_id AS uuid), :period_start, :period_end, :cap_cents, :mode
            )
            RETURNING id, org_id, period_start, period_end, cap_cents, spent_cents_cached,
                      enforcement_mode, created_at, updated_at
            """
        ),
        {
            "org_id": str(org_id),
            "period_start": body.period_start,
            "period_end": body.period_end,
            "cap_cents": body.cap_cents,
            "mode": body.enforcement_mode,
        },
    )
    row = result.first()
    if row is None:
        raise ApiError(code=INTERNAL_ERROR, message="Unable to create budget period")
    await session.commit()
    await _publish(deps, org_id)
    return _period_row(row)
