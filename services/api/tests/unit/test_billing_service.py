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
async def test_list_rate_cards_invalid_cursor() -> None:
    session = AsyncMock()
    with pytest.raises(ApiError) as ei:
        await svc.list_rate_cards(session, uuid4(), cursor="not-a-cursor")
    assert ei.value.code == VALIDATION_ERROR
    assert "cursor" in ei.value.message.lower()


@pytest.mark.asyncio
async def test_list_rate_cards_paginates_with_next_cursor() -> None:
    from app.pagination import encode_cursor

    org_id = uuid4()
    rows = [_card_ns(org_id=org_id, name=f"card-{i}") for i in range(3)]
    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(fetchall=lambda: rows))
    cursor = encode_cursor({"name": "card-0"})
    out = await svc.list_rate_cards(session, org_id, cursor=cursor, limit=2)
    assert len(out.data) == 2
    assert out.pagination.has_more is True
    assert out.pagination.next_cursor is not None
    bind = session.execute.await_args.args[1]
    assert bind["cursor_name"] == "card-0"


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
    body = RateCardCreate(name="default")
    deps = svc.WriteDeps()
    with pytest.raises(ApiError) as ei:
        await svc.create_rate_card(session, org_id, body, deps=deps)
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
        session,
        svc.PublishRateCardVersionInput(org_id=org_id, card_id=card_id, body=body),
        deps=svc.WriteDeps(publisher=pub),
    )
    assert out.version == 2
    assert pub.published == [str(org_id)]
    first_sql = str(session.execute.await_args_list[0].args[0])
    assert "FOR UPDATE" in first_sql


@pytest.mark.asyncio
async def test_publish_rate_card_version_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(first=lambda: None))
    body = RateCardVersionPublish(
        prices=[PriceRow(provider="o", model_pattern="*", input_cents_per_1k=1, output_cents_per_1k=1)]
    )
    deps = svc.WriteDeps()
    inp = svc.PublishRateCardVersionInput(org_id=uuid4(), card_id=uuid4(), body=body)
    with pytest.raises(ApiError):
        await svc.publish_rate_card_version(session, inp, deps=deps)


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
    body = RateCardCreate(name="x")
    deps = svc.WriteDeps()
    with pytest.raises(ApiError):
        await svc.create_rate_card(session, uuid4(), body, deps=deps)


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
    body = BudgetPeriodCreate(
        period_start=start,
        period_end=start + timedelta(days=1),
        cap_cents=1,
    )
    deps = svc.WriteDeps()
    with pytest.raises(ApiError):
        await svc.create_budget_period(session, uuid4(), body, deps=deps)


def test_parse_budget_period_cursor_ok() -> None:
    from app.pagination import encode_cursor

    start = datetime(2026, 1, 1, tzinfo=UTC)
    pid = str(uuid4())
    cursor = encode_cursor({"period_start": start.isoformat(), "id": pid})
    got_start, got_id = svc._parse_budget_period_cursor(cursor)
    assert got_start == start
    assert got_id == pid


def test_parse_budget_period_cursor_invalid() -> None:
    with pytest.raises(ApiError) as ei:
        svc._parse_budget_period_cursor("not-a-cursor")
    assert ei.value.code == VALIDATION_ERROR


def test_parse_budget_period_cursor_naive_rejected() -> None:
    from app.pagination import encode_cursor

    cursor = encode_cursor(
        {"period_start": "2026-01-01T00:00:00", "id": str(uuid4())}
    )
    with pytest.raises(ApiError):
        svc._parse_budget_period_cursor(cursor)


@pytest.mark.asyncio
async def test_list_budget_periods_with_cursor_and_page() -> None:
    org_id = uuid4()
    from app.pagination import encode_cursor

    rows = [_period_ns(org_id=org_id) for _ in range(3)]
    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(fetchall=lambda: rows))
    cursor = encode_cursor(
        {"period_start": rows[0].period_start.isoformat(), "id": str(rows[0].id)}
    )
    out = await svc.list_budget_periods(session, org_id, cursor=cursor, limit=2)
    assert len(out.data) == 2
    assert out.pagination.has_more is True
    assert out.pagination.next_cursor is not None


@pytest.mark.asyncio
async def test_publish_insert_returns_none() -> None:
    org_id = uuid4()
    card_id = uuid4()
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(first=lambda: SimpleNamespace(id=card_id)),
            SimpleNamespace(scalar_one=lambda: 1),
            SimpleNamespace(first=lambda: None),
        ]
    )
    body = RateCardVersionPublish(
        prices=[PriceRow(provider="o", model_pattern="*", input_cents_per_1k=1, output_cents_per_1k=1)]
    )
    inp = svc.PublishRateCardVersionInput(org_id=org_id, card_id=card_id, body=body)
    deps = svc.WriteDeps()
    with pytest.raises(ApiError):
        await svc.publish_rate_card_version(session, inp, deps=deps)
