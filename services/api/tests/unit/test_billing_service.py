"""Unit tests for billing service persistence helpers (4.P.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from apierror_py import VALIDATION_ERROR
from sqlalchemy.exc import IntegrityError

from app.budget_publish import RecordingBudgetPublisher
from app.errors import ApiError
from app.schemas.billing import (
    BudgetPeriodCreate,
    PriceRow,
    RateCardCreate,
    RateCardVersionPublish,
)
from app.services import billing as svc


def _card_ns(*, org_id, name="default"):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        org_id=org_id,
        name=name,
        currency="USD",
        status="draft",
        created_at=now,
        updated_at=now,
    )


def _period_ns(*, org_id):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        org_id=org_id,
        period_start=now,
        period_end=now + timedelta(days=1),
        cap_cents=1000,
        spent_cents_cached=0,
        enforcement_mode="hard_cap",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_list_rate_cards_maps_rows() -> None:
    org_id = uuid4()
    row = _card_ns(org_id=org_id)
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=SimpleNamespace(fetchall=lambda: [row])
    )
    out = await svc.list_rate_cards(session, org_id)
    assert len(out.data) == 1
    assert out.data[0].name == "default"
    assert out.data[0].org_id == org_id
    assert out.pagination.has_more is False


@pytest.mark.asyncio
async def test_create_rate_card_publishes() -> None:
    org_id = uuid4()
    row = _card_ns(org_id=org_id)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(first=lambda: row))
    session.commit = AsyncMock()
    pub = RecordingBudgetPublisher()
    out = await svc.create_rate_card(
        session, org_id, RateCardCreate(name="default"), deps=svc.WriteDeps(publisher=pub)
    )
    assert out.name == "default"
    assert pub.published == [str(org_id)]


@pytest.mark.asyncio
async def test_create_rate_card_duplicate_name() -> None:
    org_id = uuid4()
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    session.rollback = AsyncMock()
    with pytest.raises(ApiError) as ei:
        await svc.create_rate_card(
            session, org_id, RateCardCreate(name="default"), deps=svc.WriteDeps()
        )
    assert ei.value.code == VALIDATION_ERROR
    assert "already" in ei.value.message.lower()


@pytest.mark.asyncio
async def test_publish_rate_card_version_for_update() -> None:
    org_id = uuid4()
    card_id = uuid4()
    now = datetime.now(UTC)
    version_row = SimpleNamespace(
        id=uuid4(),
        rate_card_id=card_id,
        org_id=org_id,
        version=2,
        published_at=now,
        prices=[{"provider": "openai", "model_pattern": "*", "input_cents_per_1k": 1, "output_cents_per_1k": 2}],
    )
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(first=lambda: SimpleNamespace(id=card_id)),
            SimpleNamespace(scalar_one=lambda: 2),
            SimpleNamespace(first=lambda: version_row),
            SimpleNamespace(),
        ]
    )
    session.commit = AsyncMock()
    pub = RecordingBudgetPublisher()
    body = RateCardVersionPublish(
        prices=[PriceRow(provider="openai", model_pattern="*", input_cents_per_1k=1, output_cents_per_1k=2)]
    )
    out = await svc.publish_rate_card_version(
        session, org_id, card_id, body, deps=svc.WriteDeps(publisher=pub)
    )
    assert out.version == 2
    assert pub.published == [str(org_id)]
    first_sql = str(session.execute.await_args_list[0].args[0])
    assert "FOR UPDATE" in first_sql


@pytest.mark.asyncio
async def test_publish_rate_card_version_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(first=lambda: None))
    with pytest.raises(ApiError):
        await svc.publish_rate_card_version(
            session,
            uuid4(),
            uuid4(),
            RateCardVersionPublish(
                prices=[PriceRow(provider="o", model_pattern="*", input_cents_per_1k=1, output_cents_per_1k=1)]
            ),
            deps=svc.WriteDeps(),
        )


@pytest.mark.asyncio
async def test_list_and_create_budget_periods() -> None:
    org_id = uuid4()
    row = _period_ns(org_id=org_id)
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(fetchall=lambda: [row]),
            SimpleNamespace(first=lambda: row),
        ]
    )
    session.commit = AsyncMock()
    listed = await svc.list_budget_periods(session, org_id)
    assert listed.data[0].cap_cents == 1000
    start = datetime.now(UTC)
    created = await svc.create_budget_period(
        session,
        org_id,
        BudgetPeriodCreate(
            period_start=start,
            period_end=start + timedelta(days=1),
            cap_cents=1000,
            enforcement_mode="hard_cap",
        ),
        deps=svc.WriteDeps(),
    )
    assert created.enforcement_mode == "hard_cap"


@pytest.mark.asyncio
async def test_create_rate_card_returns_none_row() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(first=lambda: None))
    session.commit = AsyncMock()
    with pytest.raises(ApiError):
        await svc.create_rate_card(
            session, uuid4(), RateCardCreate(name="x"), deps=svc.WriteDeps()
        )


@pytest.mark.asyncio
async def test_publish_best_effort_on_publisher_error() -> None:
    class Boom:
        async def publish_budget_update(self, org_id: str) -> None:
            raise RuntimeError("redis down")

    org_id = uuid4()
    row = _card_ns(org_id=org_id)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(first=lambda: row))
    session.commit = AsyncMock()
    out = await svc.create_rate_card(
        session, org_id, RateCardCreate(name="default"), deps=svc.WriteDeps(publisher=Boom())
    )
    assert out.name == "default"


@pytest.mark.asyncio
async def test_create_budget_period_none_row() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(first=lambda: None))
    session.commit = AsyncMock()
    start = datetime.now(UTC)
    with pytest.raises(ApiError):
        await svc.create_budget_period(
            session,
            uuid4(),
            BudgetPeriodCreate(
                period_start=start,
                period_end=start + timedelta(days=1),
                cap_cents=1,
            ),
            deps=svc.WriteDeps(),
        )
