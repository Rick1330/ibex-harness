"""Mounted-route contract tests for the operator agent projection."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from apierror_py import NOT_FOUND
from authclient.permissions import OPERATOR_METADATA_READ

from app.auth.client import StaticTokenValidator, ValidateResult
from app.deps import operator_org_session
from app.errors import ApiError
from app.pagination import CursorPage, PaginationMeta
from app.schemas.agents import AgentResponse
from tests.unit.operator.conftest import create_operator_app

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
PAT = "ibex_pat_operator_agents"


def _agent(org_id: object, **overrides: object) -> AgentResponse:
    data: dict[str, object] = {
        "id": uuid4(),
        "org_id": org_id,
        "slug": "support-triage",
        "name": "Support triage",
        "description": "Triage inbound support",
        "status": "active",
        "default_provider": "openai",
        "default_model": "gpt-4.1",
        "config": {"secret": "must-not-leak"},
        "metadata": {"internal": "must-not-leak"},
        "tags": ["support"],
        "total_sessions": 12,
        "total_memories": 34,
        "total_tokens_used": 5600,
        "last_active_at": NOW,
        "created_at": NOW,
        "updated_at": NOW,
    }
    data.update(overrides)
    return AgentResponse.model_validate(data)


def _validator(org_id: object, permissions: int = OPERATOR_METADATA_READ) -> StaticTokenValidator:
    return StaticTokenValidator(
        {PAT: ValidateResult(org_id=org_id, permissions=permissions, user_id="u1")}
    )


def _login(client: object) -> None:
    response = client.post("/v1/operator/session/login", json={"pat": PAT})  # type: ignore[attr-defined]
    assert response.status_code == 200


def test_operator_agent_list_requires_a_verified_session() -> None:
    with create_operator_app(validator=_validator(uuid4())) as (_, client):
        response = client.get("/v1/operator/agents")
    assert response.status_code == 401


def test_operator_agent_list_requires_metadata_permission() -> None:
    with create_operator_app(validator=_validator(uuid4(), permissions=0)) as (_, client):
        _login(client)
        response = client.get("/v1/operator/agents")
    assert response.status_code == 403


def test_operator_agent_list_projects_public_fields_and_forwards_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = uuid4()
    agent = _agent(org_id)
    seen: dict[str, object] = {}

    async def fake_list(_session: object, args: object) -> CursorPage[AgentResponse]:
        seen["org_id"] = args.org_id  # type: ignore[attr-defined]
        seen["status"] = args.filters.status  # type: ignore[attr-defined]
        seen["search"] = args.filters.search  # type: ignore[attr-defined]
        return CursorPage[AgentResponse](
            data=[agent], pagination=PaginationMeta(has_more=False)
        )

    monkeypatch.setattr("app.routers.operator_agents.agent_service.list_agents", fake_list)

    with create_operator_app(validator=_validator(org_id)) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: AsyncMock()
        _login(client)
        response = client.get("/v1/operator/agents?status=active&search=support")

    assert response.status_code == 200
    assert seen == {"org_id": org_id, "status": "active", "search": "support"}
    body = response.json()
    row = body["data"][0]
    assert row["name"] == "Support triage"
    assert row["total_memories"] == 34
    assert "org_id" not in row
    assert "config" not in row
    assert "metadata" not in row


def test_operator_agent_detail_projects_public_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = uuid4()
    agent = _agent(org_id)

    async def fake_get(_session: object, requested_org: object, agent_id: object) -> AgentResponse:
        assert requested_org == org_id
        assert agent_id == agent.id
        return agent

    monkeypatch.setattr("app.routers.operator_agents.agent_service.get_agent", fake_get)

    with create_operator_app(validator=_validator(org_id)) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: AsyncMock()
        _login(client)
        response = client.get(f"/v1/operator/agents/{agent.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(agent.id)
    assert "org_id" not in body
    assert "config" not in body
    assert "metadata" not in body


def test_operator_agent_detail_returns_not_found_for_another_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = uuid4()

    async def fake_get(_session: object, _org: object, _agent_id: object) -> AgentResponse:
        raise ApiError(code=NOT_FOUND, message="Agent not found")

    monkeypatch.setattr("app.routers.operator_agents.agent_service.get_agent", fake_get)

    with create_operator_app(validator=_validator(org_id)) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: AsyncMock()
        _login(client)
        response = client.get(f"/v1/operator/agents/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == NOT_FOUND
