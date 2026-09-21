"""Unit tests for billing routes (4.P.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.budget_publish import NoopBudgetPublisher, RecordingBudgetPublisher
from app.pagination import CursorPage, PaginationMeta
from app.routers.billing import _budget_publisher_from_request
from app.schemas.billing import (
    BudgetPeriodCreate,
    BudgetPeriodResponse,
    RateCardResponse,
    RateCardVersionResponse,
    UsageQueryRequest,
)
from tests.unit.org_user_test_support import (
    ManagedClientOpts,
    bearer_headers,
    managed_org_client,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _card(org_id) -> RateCardResponse:
    ts = _now()
    return RateCardResponse(
        id=uuid4(),
        org_id=org_id,
        name="default",
        currency="USD",
        status="draft",
        created_at=ts,
        updated_at=ts,
    )


def _period(org_id, *, start: datetime | None = None) -> BudgetPeriodResponse:
    start = start or _now()
    return BudgetPeriodResponse(
        id=uuid4(),
        org_id=org_id,
        period_start=start,
        period_end=start + timedelta(days=1),
        cap_cents=1000,
        spent_cents_cached=0,
        enforcement_mode="hard_cap",
        created_at=start,
        updated_at=start,
    )


def _page(item: Any) -> CursorPage:
    return CursorPage(
        data=[item],
        pagination=PaginationMeta(has_more=False, next_cursor=None, total_count=1),
    )


@pytest.mark.parametrize(
    "case",
    [
        {
            "patch": "app.services.billing.list_rate_cards",
            "method": "get",
            "suffix": "/rate-cards",
            "json": None,
            "status": 200,
            "key": "name",
            "val": "default",
            "mock": lambda org_id: _page(_card(org_id)),
        },
        {
            "patch": "app.services.billing.create_rate_card",
            "method": "post",
            "suffix": "/rate-cards",
            "json": {"name": "default", "currency": "USD"},
            "status": 201,
            "key": "name",
            "val": "default",
            "mock": lambda org_id: _card(org_id),
        },
        {
            "patch": "app.services.billing.list_budget_periods",
            "method": "get",
            "suffix": "/budget-periods",
            "json": None,
            "status": 200,
            "key": "cap_cents",
            "val": 1000,
            "mock": lambda org_id: _page(_period(org_id)),
        },
    ],
)
def test_billing_list_create_happy_paths(case: dict[str, Any]) -> None:
    org_id = uuid4()
    with (
        managed_org_client(ManagedClientOpts(org_id=org_id)) as (client, _, _),
        patch(case["patch"], new=AsyncMock(return_value=case["mock"](org_id))),
    ):
        path = f"/v1/organizations/{org_id}{case['suffix']}"
        call = getattr(client, case["method"])
        headers = bearer_headers()
        if case["json"] is None:
            resp = call(path, headers=headers)
        else:
            resp = call(path, headers=headers, json=case["json"])
    assert resp.status_code == case["status"]
    payload = resp.json()
    row = payload["data"][0] if "data" in payload else payload
    assert row[case["key"]] == case["val"]


def test_publish_rate_card_version_ok() -> None:
    org_id = uuid4()
    card_id = uuid4()
    version = RateCardVersionResponse(
        id=uuid4(),
        rate_card_id=card_id,
        org_id=org_id,
        version=1,
        published_at=_now(),
        prices=[
            {
                "provider": "openai",
                "model_pattern": "*",
                "input_cents_per_1k": 1,
                "output_cents_per_1k": 2,
            }
        ],
    )
    with (
        managed_org_client(ManagedClientOpts(org_id=org_id)) as (client, _, _),
        patch(
            "app.services.billing.publish_rate_card_version",
            new=AsyncMock(return_value=version),
        ),
    ):
        resp = client.post(
            f"/v1/organizations/{org_id}/rate-cards/{card_id}/versions",
            headers=bearer_headers(),
            json={
                "prices": [
                    {
                        "provider": "openai",
                        "model_pattern": "*",
                        "input_cents_per_1k": 1,
                        "output_cents_per_1k": 2,
                    }
                ]
            },
        )
    assert resp.status_code == 201
    assert resp.json()["version"] == 1


def test_create_budget_period_owner_ok() -> None:
    org_id = uuid4()
    start = _now()
    period = _period(org_id, start=start)
    pub = RecordingBudgetPublisher()
    with (
        managed_org_client(ManagedClientOpts(org_id=org_id)) as (client, _, _),
        patch(
            "app.services.billing.create_budget_period",
            new=AsyncMock(return_value=period),
        ),
    ):
        client.app.state.api.budget_publisher = pub
        resp = client.post(
            f"/v1/organizations/{org_id}/budget-periods",
            headers=bearer_headers(),
            json={
                "period_start": start.isoformat(),
                "period_end": (start + timedelta(days=1)).isoformat(),
                "cap_cents": 1000,
                "enforcement_mode": "hard_cap",
            },
        )
    assert resp.status_code == 201
    assert resp.json()["cap_cents"] == 1000


def test_budget_publisher_from_request_falls_back_to_noop() -> None:
    req = MagicMock()
    req.app.state.api = None
    assert isinstance(_budget_publisher_from_request(req), NoopBudgetPublisher)
    req.app.state.api = SimpleNamespace(budget_publisher=None)
    assert isinstance(_budget_publisher_from_request(req), NoopBudgetPublisher)


def test_usage_query_fails_closed_without_clickhouse() -> None:
    """Unset ClickHouse must not return empty success (fail-loud ledger contract)."""
    org_id = uuid4()
    start = _now() - timedelta(hours=1)
    end = _now()
    with managed_org_client(ManagedClientOpts(org_id=org_id)) as (client, _, _):
        resp = client.post(
            f"/v1/organizations/{org_id}/usage/query",
            headers=bearer_headers(),
            json={
                "shape": "org_time_aggregate",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": 100,
            },
        )
    assert resp.status_code == 503
    body = resp.json()
    assert "ClickHouse" in body.get("error", {}).get("message", "") or "ClickHouse" in str(
        body
    )


@pytest.mark.parametrize(
    ("factory", "kwargs"),
    [
        (
            BudgetPeriodCreate,
            {
                "period_start": datetime(2026, 1, 2, tzinfo=UTC),
                "period_end": datetime(2026, 1, 1, tzinfo=UTC),
                "cap_cents": 1,
            },
        ),
        (
            UsageQueryRequest,
            {
                "shape": "org_time_aggregate",
                "start": datetime(2026, 1, 2, tzinfo=UTC),
                "end": datetime(2026, 1, 1, tzinfo=UTC),
            },
        ),
    ],
)
def test_schema_rejects_inverted_time_windows(factory: Any, kwargs: dict) -> None:
    with pytest.raises(ValidationError):
        factory(**kwargs)
