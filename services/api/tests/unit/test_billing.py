"""Unit tests for billing routes (4.P.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.budget_publish import RecordingBudgetPublisher
from app.pagination import CursorPage, PaginationMeta
from app.schemas.billing import BudgetPeriodResponse, RateCardResponse
from tests.unit.org_user_test_support import (
    ManagedClientOpts,
    bearer_headers,
    managed_org_client,
)


def test_list_rate_cards_ok() -> None:
    org_id = uuid4()
    card = RateCardResponse(
        id=uuid4(),
        org_id=org_id,
        name="default",
        currency="USD",
        status="draft",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    page = CursorPage(
        data=[card],
        pagination=PaginationMeta(has_more=False, next_cursor=None, total_count=1),
    )
    with (
        managed_org_client(ManagedClientOpts(org_id=org_id)) as (client, _, _),
        patch("app.services.billing.list_rate_cards", new=AsyncMock(return_value=page)),
    ):
        resp = client.get(
            f"/v1/organizations/{org_id}/rate-cards", headers=bearer_headers()
        )
    assert resp.status_code == 200
    assert resp.json()["data"][0]["name"] == "default"


def test_create_budget_period_owner_ok() -> None:
    org_id = uuid4()
    start = datetime.now(UTC)
    end = start + timedelta(days=1)
    period = BudgetPeriodResponse(
        id=uuid4(),
        org_id=org_id,
        period_start=start,
        period_end=end,
        cap_cents=1000,
        spent_cents_cached=0,
        enforcement_mode="hard_cap",
        created_at=start,
        updated_at=start,
    )
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
                "period_end": end.isoformat(),
                "cap_cents": 1000,
                "enforcement_mode": "hard_cap",
            },
        )
    assert resp.status_code == 201
    assert resp.json()["cap_cents"] == 1000


def test_usage_query_fails_closed_without_clickhouse() -> None:
    """Unset ClickHouse must not return empty success (fail-loud ledger contract)."""
    org_id = uuid4()
    start = datetime.now(UTC) - timedelta(hours=1)
    end = datetime.now(UTC)
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
