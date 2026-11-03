"""HTTP contract attacks on GET /v1/memories/{id}/lineage query handling.

ADR-0094 / API_DOCUMENTATION.md promise: `max_depth` is 1-5 (default 3), an
invalid value is a `400` in the stable validation envelope, and the depth cap is
enforced in the traversal query. The repository is mocked here, so these tests
only prove the edge of the HTTP surface; the SQL cap is proved in
`tests/integration/test_lineage_boundaries.py`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.deps import get_lineage_repository
from app.main import create_app
from app.permissions import MEMORY_READ
from app.read.lineage import LineageQuery

TOKEN = "lineage-http-token"
ORG = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
AGENT = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
MEMORY = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


@pytest.fixture
def http_repo() -> tuple[TestClient, AsyncMock]:
    settings = Settings(
        database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex",
        embedding_api_token="unit-test-token",
    )
    validator = StaticTokenValidator(
        {TOKEN: ValidateResult(org_id=ORG, permissions=MEMORY_READ, agent_id=AGENT)}
    )
    app = create_app(settings=settings, validator=validator)
    repo = AsyncMock()
    repo.get_lineage = AsyncMock(return_value=None)
    app.dependency_overrides[get_lineage_repository] = lambda: repo
    with TestClient(app) as client:
        yield client, repo


def _get(client: TestClient, query: str = "") -> object:
    suffix = f"?{query}" if query else ""
    return client.get(
        f"/v1/memories/{MEMORY}/lineage{suffix}",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )


@pytest.mark.parametrize("depth", [1, 2, 3, 4, 5])
def test_every_valid_depth_reaches_the_query(
    http_repo: tuple[TestClient, AsyncMock], depth: int
) -> None:
    client, repo = http_repo

    response = _get(client, f"max_depth={depth}")

    # The repository stub answers 404; what matters is that the request was
    # accepted and the depth survived to the query object.
    assert response.status_code == 404
    query = repo.get_lineage.await_args.args[0]
    assert isinstance(query, LineageQuery)
    assert query.max_depth == depth


@pytest.mark.parametrize(
    "query",
    [
        "max_depth=0",
        "max_depth=6",
        "max_depth=-1",
        "max_depth=abc",
        "max_depth=",
        "max_depth=1.5",
        "max_depth=1&max_depth=9",
    ],
)
def test_invalid_depth_is_a_400_and_never_traverses(
    http_repo: tuple[TestClient, AsyncMock], query: str
) -> None:
    client, repo = http_repo

    response = _get(client, query)

    assert response.status_code == 400, response.text
    body = response.json()
    assert body["detail"]["code"] == "VALIDATION_ERROR"
    assert body["detail"]["field_errors"][0]["field"] == "max_depth"
    repo.get_lineage.assert_not_awaited()


def test_default_depth_is_three(http_repo: tuple[TestClient, AsyncMock]) -> None:
    client, repo = http_repo

    _get(client)

    assert repo.get_lineage.await_args.args[0].max_depth == 3


def test_non_uuid_memory_id_is_a_validation_error(
    http_repo: tuple[TestClient, AsyncMock],
) -> None:
    client, repo = http_repo

    response = client.get(
        "/v1/memories/not-a-uuid/lineage",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"
    repo.get_lineage.assert_not_awaited()


def test_unauthenticated_request_is_rejected_before_the_traversal(
    http_repo: tuple[TestClient, AsyncMock],
) -> None:
    client, repo = http_repo

    response = client.get(f"/v1/memories/{MEMORY}/lineage")

    assert response.status_code == 401
    repo.get_lineage.assert_not_awaited()
