"""Unit tests for agent management router wiring."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

from authclient.permissions import ADMIN

from app.auth.client import ValidateResult
from app.pagination import CursorPage, PaginationMeta
from app.schemas.agents import AgentResponse
from tests.unit.org_user_test_support import (
    ManagedClientOpts,
    bearer_headers,
    patched_managed_client,
)


def _agent_response(**overrides) -> AgentResponse:
    now = datetime.now(UTC)
    org_id = overrides.pop("org_id", uuid4())
    base = {
        "id": overrides.pop("id", uuid4()),
        "org_id": org_id,
        "slug": "support",
        "name": "Support",
        "description": None,
        "status": "active",
        "default_provider": None,
        "default_model": None,
        "active_directive_version_id": None,
        "config": {},
        "metadata": {},
        "tags": [],
        "total_sessions": 0,
        "total_memories": 0,
        "total_tokens_used": 0,
        "last_active_at": None,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return AgentResponse(**base)


def test_create_and_lifecycle_routes() -> None:
    org_id = uuid4()
    agent = _agent_response(org_id=org_id)
    paused = _agent_response(id=agent.id, org_id=org_id, status="paused")
    activated = _agent_response(id=agent.id, org_id=org_id, status="active")
    archived = _agent_response(id=agent.id, org_id=org_id, status="archived")
    create_fake = AsyncMock(return_value=agent)
    status_fake = AsyncMock(side_effect=[paused, activated, archived])
    with patched_managed_client(
        ManagedClientOpts(org_id=org_id),
        "app.routers.agents.agent_service.create_agent",
        create_fake,
    ) as (client, _res, _pub):
        from unittest.mock import patch

        with patch("app.routers.agents.agent_service.set_agent_status", new=status_fake):
            created = client.post(
                "/v1/agents",
                headers=bearer_headers(),
                json={"name": "Support", "slug": "support"},
            )
            assert created.status_code == 201
            assert created.json()["slug"] == "support"
            assert client.post(
                f"/v1/agents/{agent.id}/pause", headers=bearer_headers()
            ).json()["status"] == "paused"
            assert client.post(
                f"/v1/agents/{agent.id}/activate", headers=bearer_headers()
            ).json()["status"] == "active"
            assert client.post(
                f"/v1/agents/{agent.id}/archive", headers=bearer_headers()
            ).json()["status"] == "archived"


def test_list_get_patch_delete_routes() -> None:
    org_id = uuid4()
    agent = _agent_response(org_id=org_id)
    page = CursorPage(data=[agent], pagination=PaginationMeta(has_more=False))
    list_fake = AsyncMock(return_value=page)
    get_fake = AsyncMock(return_value=agent)
    patch_fake = AsyncMock(return_value=_agent_response(id=agent.id, org_id=org_id, name="N"))
    delete_fake = AsyncMock(return_value=None)
    with patched_managed_client(
        ManagedClientOpts(org_id=org_id),
        "app.routers.agents.agent_service.list_agents",
        list_fake,
    ) as (client, _res, _pub):
        from unittest.mock import patch

        with (
            patch("app.routers.agents.agent_service.get_agent", new=get_fake),
            patch("app.routers.agents.agent_service.patch_agent", new=patch_fake),
            patch("app.routers.agents.agent_service.soft_delete_agent", new=delete_fake),
        ):
            listed = client.get(
                "/v1/agents",
                headers=bearer_headers(),
                params={"status": "active", "tags": "prod", "search": "  Support  "},
            )
            assert listed.status_code == 200
            assert listed.json()["data"][0]["id"] == str(agent.id)

            got = client.get(f"/v1/agents/{agent.id}", headers=bearer_headers())
            assert got.status_code == 200

            patched = client.patch(
                f"/v1/agents/{agent.id}",
                headers=bearer_headers(),
                json={"name": "N"},
            )
            assert patched.status_code == 200
            assert patched.json()["name"] == "N"

            deleted = client.delete(f"/v1/agents/{agent.id}", headers=bearer_headers())
            assert deleted.status_code == 204
            delete_fake.assert_awaited()


def test_soft_provider_validation_on_create() -> None:
    org_id = uuid4()
    with patched_managed_client(
        ManagedClientOpts(org_id=org_id),
        "app.routers.agents.agent_service.create_agent",
        AsyncMock(),
    ) as (client, _res, _pub):
        resp = client.post(
            "/v1/agents",
            headers=bearer_headers(),
            json={"name": "A", "slug": "a", "default_provider": ""},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_optional_user_uuid_parsing() -> None:
    from app.routers.agents import _optional_user_uuid

    assert _optional_user_uuid(None) is None
    assert _optional_user_uuid("") is None
    assert _optional_user_uuid("not-a-uuid") is None
    uid = uuid4()
    assert _optional_user_uuid(str(uid)) == uid


def test_create_agent_tolerates_invalid_user_id() -> None:
    org_id = uuid4()
    agent = _agent_response(org_id=org_id)
    create_fake = AsyncMock(return_value=agent)
    with patched_managed_client(
        ManagedClientOpts(
            org_id=org_id,
            result=ValidateResult(
                org_id=org_id,
                permissions=ADMIN,
                user_id="not-a-uuid",
            ),
        ),
        "app.routers.agents.agent_service.create_agent",
        create_fake,
    ) as (client, _res, _pub):
        created = client.post(
            "/v1/agents",
            headers=bearer_headers(),
            json={"name": "Support", "slug": "support"},
        )
        assert created.status_code == 201
        assert create_fake.await_args.args[1].created_by is None
