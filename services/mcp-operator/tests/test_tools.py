"""Operator tool registry and tenant-scoped dispatcher."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import pytest
from mcp_gateway import BackendUnavailableError, Scope, ToolContext
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app import tools
from app.tools import (
    BudgetGetArgs,
    EvidenceQueryArgs,
    SessionGetArgs,
    ToolDispatcher,
    build_handlers,
    build_registry,
)
from tests.fixtures import AGENT, ORG, RUN_ID, SESSION_ID

_SENTINEL = object()


def _ctx(name: str) -> ToolContext:
    registry = build_registry()
    spec = registry.get(name)
    assert spec is not None
    from mcp_gateway import GatewayPrincipal

    return ToolContext(
        principal=GatewayPrincipal(org_id=ORG, permissions=0, agent_id=AGENT),
        spec=spec,
        request_id="req-1",
    )


def test_registry_has_four_read_only_tools() -> None:
    registry = build_registry()
    assert tuple(spec.name for spec in registry.specs()) == (
        "budget.get",
        "evidence.query",
        "run.get",
        "session.get",
    )
    expected = {
        "session.get": Scope.OPERATOR_READ,
        "run.get": Scope.RUNS_READ,
        "evidence.query": Scope.EVIDENCE_READ,
        "budget.get": Scope.BUDGET_READ,
    }
    for spec in registry.specs():
        assert spec.scope == expected[spec.name]
        assert spec.input_schema["additionalProperties"] is False


def test_args_models_reject_unknown_and_bounds() -> None:
    with pytest.raises(ValidationError):
        SessionGetArgs(session_id=str(SESSION_ID), extra="x")
    with pytest.raises(ValidationError):
        EvidenceQueryArgs(limit=0)
    with pytest.raises(ValidationError):
        EvidenceQueryArgs(limit=tools.EVIDENCE_MAX_LIMIT + 1)
    with pytest.raises(ValidationError):
        BudgetGetArgs(limit=tools.BUDGET_MAX_LIMIT + 1)


def test_evidence_query_trace_id_is_opaque_and_bounded() -> None:
    opaque = "4bf92f3577b34da6a3ce929d0e0e4736"
    assert EvidenceQueryArgs(trace_id=opaque).trace_id == opaque
    dashed = "4bf92f35-77b3-4da6-a3ce-929d0e0e4736"
    assert EvidenceQueryArgs(trace_id=dashed).trace_id == dashed
    with pytest.raises(ValidationError):
        EvidenceQueryArgs(trace_id="has space")
    with pytest.raises(ValidationError):
        EvidenceQueryArgs(trace_id="x" * 129)


@pytest.mark.asyncio
async def test_dispatcher_routes_session_get_to_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    @asynccontextmanager
    async def fake_session(factory: Any, org_id: str):
        captured["org_id"] = org_id
        yield _SENTINEL

    async def fake_get_session(session: Any, *, org_id: UUID, session_id: UUID) -> dict[str, Any]:
        captured["session"] = session
        captured["called_org"] = org_id
        captured["session_id"] = session_id
        return {"session_id": str(session_id)}

    monkeypatch.setattr(tools, "session_with_org", fake_session)
    monkeypatch.setattr(tools.repositories, "get_session", fake_get_session)

    dispatcher = ToolDispatcher(session_factory=object())  # type: ignore[arg-type]
    result = await dispatcher(_ctx("session.get"), {"session_id": SESSION_ID})

    assert result == {"session_id": str(SESSION_ID)}
    assert captured["org_id"] == str(ORG)
    assert captured["called_org"] == ORG
    assert captured["session"] is _SENTINEL


@pytest.mark.asyncio
async def test_dispatcher_maps_sqlalchemy_error_to_backend_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @asynccontextmanager
    async def failing_session(factory: Any, org_id: str):
        raise OperationalError("SELECT 1", {}, Exception("db down"))
        yield  # pragma: no cover

    monkeypatch.setattr(tools, "session_with_org", failing_session)

    dispatcher = ToolDispatcher(session_factory=object())  # type: ignore[arg-type]
    ctx = _ctx("run.get")
    with pytest.raises(BackendUnavailableError):
        await dispatcher(ctx, {"run_id": RUN_ID})


@pytest.mark.asyncio
async def test_dispatcher_rejects_unknown_tool() -> None:
    dispatcher = ToolDispatcher(session_factory=object())  # type: ignore[arg-type]
    ctx = _ctx("session.get")
    dispatcher._handlers.pop("session.get")  # type: ignore[attr-defined]
    with pytest.raises(BackendUnavailableError):
        await dispatcher(ctx, {"session_id": SESSION_ID})


def test_handlers_cover_every_registered_tool() -> None:
    assert set(build_handlers()) == {spec.name for spec in build_registry().specs()}


def test_scope_for_each_tool_is_distinct() -> None:
    scopes = {spec.scope for spec in build_registry().specs()}
    assert len(scopes) == 4
