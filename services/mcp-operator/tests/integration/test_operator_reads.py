"""Operator read isolation against live PostgreSQL (RLS + explicit org filter)."""

from __future__ import annotations

import pytest
from mcp_gateway import GatewayPrincipal, NotFoundError, ToolContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db import create_session_factory, session_with_org
from app.tools import ToolDispatcher, build_registry
from tests.integration.conftest import Seeded

pytestmark = pytest.mark.integration


def _ctx(name: str, org: object, permissions: int) -> ToolContext:
    spec = build_registry().get(name)
    assert spec is not None
    return ToolContext(
        principal=GatewayPrincipal(org_id=org, permissions=permissions),  # type: ignore[arg-type]
        spec=spec,
        request_id="req-it",
    )


@pytest.mark.asyncio
async def test_session_get_returns_own_org_row(dispatcher: ToolDispatcher, seeded: Seeded) -> None:
    ctx = _ctx("session.get", seeded.org_a, 1 << 19)
    payload = await dispatcher(ctx, {"session_id": seeded.session_a})
    assert payload["session_id"] == str(seeded.session_a)
    assert payload["status"] == "active"


@pytest.mark.asyncio
async def test_session_get_cross_tenant_is_not_found(
    dispatcher: ToolDispatcher, seeded: Seeded
) -> None:
    ctx = _ctx("session.get", seeded.org_a, 1 << 19)
    with pytest.raises(NotFoundError):
        await dispatcher(ctx, {"session_id": seeded.session_b})


@pytest.mark.asyncio
async def test_evidence_query_is_org_scoped(dispatcher: ToolDispatcher, seeded: Seeded) -> None:
    ctx = _ctx("evidence.query", seeded.org_a, 1 << 38)
    payload = await dispatcher(ctx, {"limit": 50})
    run_ids = {item["run_id"] for item in payload["runs"]}
    assert str(seeded.run_a) in run_ids
    assert str(seeded.run_b) not in run_ids


@pytest.mark.asyncio
async def test_evidence_query_preserves_opaque_trace_id(
    dispatcher: ToolDispatcher, seeded: Seeded
) -> None:
    ctx = _ctx("evidence.query", seeded.org_b, 1 << 38)
    payload = await dispatcher(ctx, {"trace_id": seeded.trace_b, "limit": 10})
    assert [item["run_id"] for item in payload["runs"]] == [str(seeded.run_b)]
    assert payload["runs"][0]["trace_id"] == seeded.trace_b


@pytest.mark.asyncio
async def test_run_get_cross_tenant_is_not_found(
    dispatcher: ToolDispatcher, seeded: Seeded
) -> None:
    ctx = _ctx("run.get", seeded.org_b, 1 << 24)
    with pytest.raises(NotFoundError):
        await dispatcher(ctx, {"run_id": seeded.run_a})

    own = _ctx("run.get", seeded.org_b, 1 << 24)
    payload = await dispatcher(own, {"run_id": seeded.run_b})
    assert payload["run_id"] == str(seeded.run_b)
    assert payload["trace_id"] == seeded.trace_b


@pytest.mark.asyncio
async def test_budget_get_is_org_scoped(dispatcher: ToolDispatcher, seeded: Seeded) -> None:
    ctx = _ctx("budget.get", seeded.org_a, 1 << 33)
    payload = await dispatcher(ctx, {"active_only": True, "limit": 10})
    assert payload["count"] == 1
    assert payload["periods"][0]["cap_cents"] == 5000


@pytest.mark.asyncio
async def test_budget_periods_rls_is_org_scoped(
    operator_engine: AsyncEngine, seeded: Seeded
) -> None:
    factory = create_session_factory(operator_engine)
    async with session_with_org(factory, str(seeded.org_a)) as session:
        rows = (
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    "SELECT org_id, cap_cents FROM ibex_billing.budget_periods"
                )
            )
        ).all()
    assert [(str(row.org_id), row.cap_cents) for row in rows] == [(str(seeded.org_a), 5000)]
