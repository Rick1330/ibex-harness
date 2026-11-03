"""Wire compatibility for the additive `conflict_groups` field (ADR-0094).

The ADR states the field "is additive and defaults to an empty list, so a
consumer that ignores it sees no change; the context client treats the field as
optional for the same reason". These tests pin that claim on the client that
actually consumes the field.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
import pytest

from app.budget import Message
from app.clients.directive import DirectivePayload
from app.clients.memory import (
    MemoryHttpClient,
    MemoryHttpConfig,
    MemoryHttpError,
    SearchMemoriesRequest,
)
from app.config import ContextSettings
from app.retrieval import ParallelRetriever, RetrievalRequest

ORG = uuid4()
AGENT = uuid4()
TOKEN = "context-conflict-groups-token"


def _body(*, conflict_groups: Any = None, include: bool = False) -> dict:
    memory: dict[str, Any] = {
        "id": str(uuid4()),
        "agent_id": str(AGENT),
        "org_id": str(ORG),
        "content": "the sky is blue",
        "category": "factual",
        "confidence": 0.9,
        "status": "active",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    if include:
        memory["conflict_groups"] = conflict_groups
    return {
        "data": {
            "results": [
                {
                    "memory": memory,
                    "similarity": 0.88,
                    "rank": 1,
                    "source": "vector",
                }
            ]
        }
    }


def _client(handler) -> MemoryHttpClient:
    transport = httpx.MockTransport(handler)
    httpx_client = httpx.AsyncClient(transport=transport)
    return MemoryHttpClient(
        MemoryHttpConfig(base_url="http://memory.example", token=TOKEN),
        client=httpx_client,
    )


class _DirectiveOk:
    async def lookup(self, org_id, agent_id) -> DirectivePayload:
        return DirectivePayload(content="", injection_mode="system_first", version_id=None)


async def _retrieve(body: dict):
    client = _client(lambda _request: httpx.Response(200, json=body))
    retriever = ParallelRetriever(
        settings=ContextSettings.model_construct(
            timeout_ms=45.0,
            retrieval_wall_ms=40.0,
            directive_timeout_ms=5.0,
            hot_timeout_ms=15.0,
            cold_timeout_ms=45.0,
        ),
        memory=client,
        directive=_DirectiveOk(),
    )
    try:
        return await retriever.retrieve(
            RetrievalRequest(
                org_id=ORG,
                agent_id=AGENT,
                query="sky",
                model="gpt-4o-mini",
                recent_messages=[Message(role="user", content="hi")],
            )
        )
    finally:
        await client._client.aclose()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_absent_field_reads_as_conflict_free() -> None:
    result = await _retrieve(_body(include=False))

    assert result.cold_outcome.status == "success"
    assert [hit.conflict_groups for hit in result.cold_memories] == [()]


@pytest.mark.asyncio
async def test_null_field_reads_as_conflict_free() -> None:
    result = await _retrieve(_body(include=True, conflict_groups=None))

    assert result.cold_outcome.status == "success"
    assert [hit.conflict_groups for hit in result.cold_memories] == [()]


@pytest.mark.asyncio
async def test_present_field_reaches_the_retrieval_hit() -> None:
    group = str(uuid4())
    result = await _retrieve(_body(include=True, conflict_groups=[group]))

    assert result.cold_outcome.status == "success"
    assert result.cold_memories[0].conflict_groups == (group,)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    [
        "11111111-1111-1111-1111-111111111111",  # a bare string, not a list
        ["not-a-uuid"],
        [123],
        {"0": "11111111-1111-1111-1111-111111111111"},
    ],
)
async def test_malformed_field_fails_the_branch_closed(value: Any) -> None:
    """A malformed list must not silently read as "no conflict"."""
    result = await _retrieve(_body(include=True, conflict_groups=value))

    assert result.cold_outcome.status == "error"
    assert result.cold_memories == []


@pytest.mark.asyncio
async def test_client_raises_on_a_non_list_field() -> None:
    client = _client(
        lambda _request: httpx.Response(
            200, json=_body(include=True, conflict_groups="not-a-list")
        )
    )
    try:
        with pytest.raises(MemoryHttpError, match="conflict_groups"):
            await client.search_memories(
                SearchMemoriesRequest(agent_id=AGENT, query="sky", timeout_seconds=0.1)
            )
    finally:
        await client._client.aclose()  # type: ignore[attr-defined]
