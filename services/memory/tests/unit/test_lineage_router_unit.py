"""Unit tests for GET /v1/memories/{id}/lineage HTTP surface."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.deps import get_lineage_repository
from app.main import create_app
from app.permissions import MEMORY_READ, MEMORY_WRITE
from app.read.lineage import (
    LineageEdge,
    LineageEndpoint,
    LineageResult,
    LineageRoot,
)

TOKEN = "test-lineage-token"
ORG = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
AGENT = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
MEMORY = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _result(*, edges: int = 1) -> LineageResult:
    root = LineageRoot(
        memory_id=MEMORY,
        status="superseded",
        tombstoned=False,
        supersession_tip=uuid4(),
    )
    return LineageResult(
        root=root,
        edges=tuple(
            LineageEdge(
                source_memory_id=uuid4(),
                target_memory_id=uuid4(),
                relationship_type="supersedes",
                confidence=0.9,
                depth=index + 1,
                from_memory_id=MEMORY,
                other=LineageEndpoint(
                    memory_id=uuid4(),
                    status="superseded",
                    tombstoned=False,
                ),
            )
            for index in range(edges)
        ),
        truncated=False,
        max_depth=3,
    )


def _client(
    *,
    permissions: int = MEMORY_READ,
    agent_id: UUID | None = AGENT,
    repo: AsyncMock | None = None,
) -> tuple[TestClient, AsyncMock]:
    settings = Settings(
        database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex",
        embedding_api_token="unit-test-token",
    )
    validator = StaticTokenValidator(
        {TOKEN: ValidateResult(org_id=ORG, permissions=permissions, agent_id=agent_id)}
    )
    app = create_app(settings=settings, validator=validator)
    if repo is None:
        repo = AsyncMock()
        repo.get_lineage = AsyncMock(return_value=_result())
    app.dependency_overrides[get_lineage_repository] = lambda: repo
    return TestClient(app), repo


def _get(http: TestClient, *, memory_id: UUID = MEMORY, params: dict | None = None):
    return http.get(
        f"/v1/memories/{memory_id}/lineage",
        params=params or {},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )


def test_lineage_returns_root_and_edges() -> None:
    http, _repo = _client()

    with http:
        response = _get(http, params={"max_depth": 4})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["memory_id"] == str(MEMORY)
    assert data["status"] == "superseded"
    assert data["max_depth"] == 3  # repository echo, not the query parameter
    assert data["edges"][0]["relationship_type"] == "supersedes"
    assert data["edges"][0]["other"]["status"] == "superseded"


def test_lineage_defaults_to_depth_three() -> None:
    http, repo = _client()

    with http:
        assert _get(http).status_code == 200
    query = repo.get_lineage.await_args.args[0]
    assert query.max_depth == 3


def test_lineage_passes_the_token_agent_scope() -> None:
    http, repo = _client()

    with http:
        assert _get(http).status_code == 200
    query = repo.get_lineage.await_args.args[0]
    assert query.agent_id == AGENT
    assert query.org_id == ORG


def test_org_scoped_token_passes_no_agent_scope() -> None:
    http, repo = _client(agent_id=None)

    with http:
        assert _get(http).status_code == 200
    assert repo.get_lineage.await_args.args[0].agent_id is None


def test_unknown_memory_is_not_found() -> None:
    repo = AsyncMock()
    repo.get_lineage = AsyncMock(return_value=None)
    http, _repo = _client(repo=repo)

    with http:
        response = _get(http)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"


def test_database_failure_is_service_unavailable() -> None:
    repo = AsyncMock()
    repo.get_lineage = AsyncMock(side_effect=SQLAlchemyError("boom"))
    http, _repo = _client(repo=repo)

    with http:
        response = _get(http)

    assert response.status_code == 503


def test_lineage_requires_memory_read() -> None:
    http, repo = _client(permissions=MEMORY_WRITE)

    with http:
        response = _get(http)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "INSUFFICIENT_PERMISSIONS"
    repo.get_lineage.assert_not_awaited()


@pytest.mark.parametrize("depth", [0, 6])
def test_max_depth_outside_one_to_five_is_rejected(depth: int) -> None:
    http, repo = _client()

    with http:
        response = _get(http, params={"max_depth": depth})

    # The service normalises request-validation failures to the stable 400 shape.
    assert response.status_code == 400
    repo.get_lineage.assert_not_awaited()


def test_empty_lineage_is_a_successful_empty_page() -> None:
    repo = AsyncMock()
    repo.get_lineage = AsyncMock(return_value=_result(edges=0))
    http, _repo = _client(repo=repo)

    with http:
        response = _get(http)

    assert response.status_code == 200
    assert response.json()["data"]["edges"] == []
