"""Embedding-model fence: schema, search request, SQL placement, and store binding.

The vector query filtered org, agent, status and validity but not ``embedding_model``,
so a search embedded by one model was scored against vectors another model produced.
These tests pin the fence at every layer that has to carry it.
"""

from __future__ import annotations

from typing import Any, Self
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.search import SearchMemoriesRequest
from app.vectorstore.base import SearchMode, SearchRequest
from app.vectorstore.pgvector_store import SEARCH_SQL, PgVectorStore
from tests.unit.find_similar_support import make_query, make_repo, make_settings

_FENCE_CAST = "CAST(:embedding_model AS text)"
_FENCE_NULL_BRANCH = f"{_FENCE_CAST} IS NULL"
_FENCE_MATCH = f"OR embedding_model = {_FENCE_CAST}"
_QUERY = [0.0] * 1024


# --------------------------------------------------------------------------- schema


def test_schema_defaults_to_no_fence() -> None:
    request = SearchMemoriesRequest(agent_id=uuid4(), query="q")
    assert request.embedding_model is None


def test_schema_accepts_an_explicit_null_fence() -> None:
    """``"embedding_model": null`` is a real client payload, not only the default."""
    request = SearchMemoriesRequest(agent_id=uuid4(), query="q", embedding_model=None)
    assert request.embedding_model is None


def test_schema_accepts_and_trims_a_model_id() -> None:
    request = SearchMemoriesRequest(agent_id=uuid4(), query="q", embedding_model="  bge-m3 ")
    assert request.embedding_model == "bge-m3"


@pytest.mark.parametrize("value", ["", "   "])
def test_schema_refuses_a_blank_fence(value: str) -> None:
    """A blank fence must be a 422, not a vector-store ValueError surfacing as a 500."""
    with pytest.raises(ValidationError, match="embedding_model must be non-empty"):
        SearchMemoriesRequest(agent_id=uuid4(), query="q", embedding_model=value)


def test_schema_refuses_a_fence_longer_than_the_column() -> None:
    with pytest.raises(ValidationError):
        SearchMemoriesRequest(agent_id=uuid4(), query="q", embedding_model="m" * 257)


# -------------------------------------------------------------------- SearchRequest


def test_search_request_fence_is_none_by_default() -> None:
    request = SearchRequest(org_id=uuid4(), agent_id=uuid4(), query_embedding=_QUERY, limit=5)
    request.validate()
    assert request.embedding_model_fence is None


def test_search_request_fence_is_trimmed() -> None:
    request = SearchRequest(
        org_id=uuid4(),
        agent_id=uuid4(),
        query_embedding=_QUERY,
        limit=5,
        embedding_model="  bge-m3  ",
    )
    request.validate()
    assert request.embedding_model_fence == "bge-m3"


@pytest.mark.parametrize(
    ("value", "match"),
    [
        pytest.param("", "embedding_model must be non-empty", id="blank"),
        pytest.param("  ", "embedding_model must be non-empty", id="whitespace"),
        pytest.param("m" * 257, "at most 256", id="oversized"),
    ],
)
def test_search_request_refuses_an_unusable_fence(value: str, match: str) -> None:
    request = SearchRequest(
        org_id=uuid4(),
        agent_id=uuid4(),
        query_embedding=_QUERY,
        limit=5,
        embedding_model=value,
    )
    with pytest.raises(ValueError, match=match):
        request.validate()


# ------------------------------------------------------------------------ SQL shape


def test_search_sql_carries_the_fence_once_inside_the_ann_select() -> None:
    assert SEARCH_SQL.count(_FENCE_NULL_BRANCH) == 1
    assert SEARCH_SQL.count(_FENCE_MATCH) == 1
    inner = SEARCH_SQL.index(_FENCE_NULL_BRANCH)
    assert inner < SEARCH_SQL.index("ORDER BY embedding <=>")
    assert inner < SEARCH_SQL.index("LIMIT :limit")
    # Inside the derived table, not applied to its output: a post-LIMIT filter would
    # silently shorten the page instead of excluding rows from ANN admission.
    assert SEARCH_SQL.index(") ranked") > inner


def test_search_sql_fence_is_inert_without_a_value() -> None:
    """The NULL branch is what keeps an unfenced caller on the historical result set."""
    assert f"AND (\n          {_FENCE_NULL_BRANCH}\n          {_FENCE_MATCH}\n      )" in SEARCH_SQL


def test_search_sql_fence_casts_both_occurrences() -> None:
    """asyncpg prepares before it binds: an untyped ``$n IS NULL`` is ambiguous."""
    assert SEARCH_SQL.count(_FENCE_CAST) == 2
    assert "(:embedding_model IS NULL" not in SEARCH_SQL


# ---------------------------------------------------------------------- store binding


class _FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _FakeMappings:
        return _FakeMappings(self._rows)


class _RecordingSession:
    """Captures every statement and its bind parameters, in order."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.executions: list[tuple[str, dict[str, Any]]] = []
        self._rows = rows

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def begin(self) -> Self:
        return self

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> _FakeResult:
        self.executions.append((str(statement), dict(params or {})))
        return _FakeResult(self._rows)

    def search_params(self) -> dict[str, Any]:
        for statement, params in self.executions:
            if "SELECT memory_id, similarity" in statement:
                return params
        raise AssertionError("vector search statement was never executed")


def _store_with(rows: list[dict[str, Any]]) -> tuple[PgVectorStore, _RecordingSession]:
    session = _RecordingSession(rows)
    factory = MagicMock(return_value=session)
    return PgVectorStore(factory, make_settings()), session


@pytest.mark.parametrize(
    ("embedding_model", "bound"),
    [
        pytest.param(None, None, id="omitted"),
        pytest.param("bge-m3", "bge-m3", id="set"),
    ],
)
@pytest.mark.asyncio
async def test_store_binds_the_fence_it_was_given(
    embedding_model: str | None, bound: str | None
) -> None:
    """An omitted filter binds NULL, so the fence stays inert instead of matching ""."""
    store, session = _store_with([])
    await store.search(
        SearchRequest(
            org_id=uuid4(),
            agent_id=uuid4(),
            query_embedding=_QUERY,
            limit=5,
            mode=SearchMode.USER_RETRIEVAL,
            embedding_model=embedding_model,
        )
    )
    assert session.search_params()["embedding_model"] == bound


@pytest.mark.asyncio
async def test_store_maps_rows_to_hits_under_a_fence() -> None:
    memory_id = uuid4()
    store, _ = _store_with([{"memory_id": str(memory_id), "similarity": 0.91}])
    hits = await store.search(
        SearchRequest(
            org_id=uuid4(),
            agent_id=uuid4(),
            query_embedding=_QUERY,
            limit=5,
            embedding_model="bge-m3",
        )
    )
    assert [(hit.memory_id, hit.similarity) for hit in hits] == [(memory_id, 0.91)]


# --------------------------------------------------------------- repository plumbing


@pytest.mark.asyncio
async def test_repository_forwards_the_fence_to_the_store() -> None:
    store = MagicMock()
    store.search = AsyncMock(return_value=[])
    repo = make_repo(store, make_settings(search_fallback_enabled=False))
    repo._hydrate_hits = AsyncMock(return_value={})  # type: ignore[method-assign]

    assert await repo.find_similar(make_query(), embedding_model="bge-m3") == []

    request = store.search.await_args.args[0]
    assert request.embedding_model == "bge-m3"


@pytest.mark.asyncio
async def test_repository_omits_the_fence_by_default() -> None:
    store = MagicMock()
    store.search = AsyncMock(return_value=[])
    repo = make_repo(store, make_settings(search_fallback_enabled=False))
    repo._hydrate_hits = AsyncMock(return_value={})  # type: ignore[method-assign]

    await repo.find_similar(make_query())

    assert store.search.await_args.args[0].embedding_model is None


@pytest.mark.asyncio
async def test_repository_forwards_the_fence_on_the_hybrid_path() -> None:
    """The hybrid channel runs its own vector query; it must carry the same fence."""
    store = MagicMock()
    store.search = AsyncMock(return_value=[])
    repo = make_repo(store, make_settings(search_hybrid_enabled=True))

    with patch("app.read.repository.full_text_search", AsyncMock(return_value=[])):
        assert await repo.find_similar(make_query(), embedding_model="bge-m3") == []

    assert store.search.await_args.args[0].embedding_model == "bge-m3"
