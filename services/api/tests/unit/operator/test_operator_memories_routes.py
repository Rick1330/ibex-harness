"""Mounted-route contract tests for the metadata-only operator memory projection."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from apierror_py import NOT_FOUND
from authclient.permissions import OPERATOR_METADATA_READ

from app.auth.client import StaticTokenValidator, ValidateResult
from app.deps import operator_org_session
from app.errors import ApiError
from app.pagination import CursorPage, PaginationMeta
from app.schemas.operator_memories import OperatorMemory
from tests.unit.operator.conftest import create_operator_app
from tests.unit.operator.memory_fixtures import memory_record

PAT = "ibex_pat_operator_memories"


def _validator(org_id: object, permissions: int = OPERATOR_METADATA_READ) -> StaticTokenValidator:
    return StaticTokenValidator(
        {PAT: ValidateResult(org_id=org_id, permissions=permissions, user_id="u1")}
    )


def _login(client: object) -> None:
    response = client.post("/v1/operator/session/login", json={"pat": PAT})  # type: ignore[attr-defined]
    assert response.status_code == 200


def test_operator_memory_list_requires_a_verified_session() -> None:
    with create_operator_app(validator=_validator(uuid4())) as (_, client):
        response = client.get("/v1/operator/memories")
    assert response.status_code == 401


def test_operator_memory_list_requires_metadata_permission() -> None:
    with create_operator_app(validator=_validator(uuid4(), permissions=0)) as (_, client):
        _login(client)
        response = client.get("/v1/operator/memories")
    assert response.status_code == 403


def test_operator_memory_list_projects_metadata_and_forwards_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = uuid4()
    memory = memory_record()
    seen: dict[str, object] = {}

    async def fake_list(_session: object, args: object) -> CursorPage[OperatorMemory]:
        seen["org_id"] = args.org_id  # type: ignore[attr-defined]
        seen["agent_id"] = args.filters.agent_id  # type: ignore[attr-defined]
        seen["status"] = args.filters.status  # type: ignore[attr-defined]
        seen["category"] = args.filters.category  # type: ignore[attr-defined]
        return CursorPage[OperatorMemory](
            data=[memory], pagination=PaginationMeta(has_more=False)
        )

    monkeypatch.setattr(
        "app.routers.operator_memories.memory_service.list_operator_memories",
        fake_list,
    )

    with create_operator_app(validator=_validator(org_id)) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: AsyncMock()
        _login(client)
        response = client.get(
            f"/v1/operator/memories?agent_id={memory.agent_id}"
            "&status=active&category=factual&limit=10"
        )

    assert response.status_code == 200
    assert seen == {
        "org_id": org_id,
        "agent_id": memory.agent_id,
        "status": "active",
        "category": "factual",
    }
    body = response.json()
    row = body["data"][0]
    assert row["content_tokens"] == 12
    assert row["tags"] == ["support"]
    assert "org_id" not in row
    assert "content" not in row
    assert "content_hash" not in row
    assert "embedding" not in row
    assert "metadata" not in row


def test_operator_memory_detail_projects_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = uuid4()
    memory = memory_record()

    async def fake_get(
        _session: object, requested_org: object, memory_id: object
    ) -> OperatorMemory:
        assert requested_org == org_id
        assert memory_id == memory.id
        return memory

    monkeypatch.setattr(
        "app.routers.operator_memories.memory_service.get_operator_memory",
        fake_get,
    )

    with create_operator_app(validator=_validator(org_id)) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: AsyncMock()
        _login(client)
        response = client.get(f"/v1/operator/memories/{memory.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(memory.id)
    assert "org_id" not in body
    assert "content" not in body
    assert "metadata" not in body


def test_operator_memory_detail_returns_not_found_for_another_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = uuid4()

    async def fake_get(
        _session: object, _org: object, _memory_id: object
    ) -> OperatorMemory:
        raise ApiError(code=NOT_FOUND, message="Memory not found")

    monkeypatch.setattr(
        "app.routers.operator_memories.memory_service.get_operator_memory",
        fake_get,
    )

    with create_operator_app(validator=_validator(org_id)) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: AsyncMock()
        _login(client)
        response = client.get(f"/v1/operator/memories/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == NOT_FOUND
