"""S05 / T1.5: context sends the assembly's org and a 403 is loud.

The client presents ``X-Ibex-Org-Id`` with the org the assembly is scoped to.
Memory refuses a mismatch with 403, and that refusal has to reach the branch as
an error — not as a successful branch with zero memories, which is the silent
under-retrieval this change removes.
"""

from __future__ import annotations

import logging
from uuid import uuid4

import httpx
import pytest

from app.budget import Message
from app.clients.directive import DirectivePayload
from app.clients.memory import (
    ORG_HEADER,
    HotMemoriesRequest,
    MemoryHttpClient,
    MemoryHttpConfig,
    MemoryHttpForbidden,
    SearchMemoriesRequest,
)
from app.config import ContextSettings
from app.retrieval import MEMORY_FORBIDDEN, ParallelRetriever, RetrievalRequest

ORG = uuid4()
OTHER_ORG = uuid4()
AGENT = uuid4()
TOKEN = "context-test-token"


class _DirectiveOk:
    async def lookup(self, org_id, agent_id) -> DirectivePayload:
        return DirectivePayload(content="", injection_mode="system_first", version_id=None)


def _hit_body(*, source: str, org_id=ORG) -> dict:
    return {
        "data": {
            "results": [
                {
                    "memory": {
                        "id": str(uuid4()),
                        "agent_id": str(AGENT),
                        "org_id": str(org_id),
                        "content": "dark mode",
                        "category": "preference",
                        "confidence": 0.9,
                        "status": "active",
                        "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-01-01T00:00:00Z",
                    },
                    "similarity": 0.9,
                    "rank": 1,
                    "source": source,
                }
            ]
        }
    }


def _settings() -> ContextSettings:
    return ContextSettings.model_construct(
        timeout_ms=45.0,
        retrieval_wall_ms=40.0,
        directive_timeout_ms=5.0,
        hot_timeout_ms=15.0,
        cold_timeout_ms=45.0,
    )


def _request(org_id=ORG) -> RetrievalRequest:
    return RetrievalRequest(
        org_id=org_id,
        agent_id=AGENT,
        query="theme",
        model="gpt-4o-mini",
        recent_messages=[Message(role="user", content="dark?")],
    )


def _client(handler) -> tuple[MemoryHttpClient, httpx.AsyncClient]:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    client = MemoryHttpClient(
        MemoryHttpConfig(base_url="http://memory.example", token=TOKEN),
        client=http,
    )
    return client, http


@pytest.mark.asyncio
async def test_client_sends_assembly_org_header_on_both_calls() -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get(ORG_HEADER.lower()))
        source = "hot_cache" if request.url.path.endswith("/hot") else "vector"
        return httpx.Response(200, json=_hit_body(source=source))

    client, http = _client(handler)
    try:
        await client.get_hot_memories(
            HotMemoriesRequest(org_id=ORG, agent_id=AGENT, timeout_seconds=0.1)
        )
        await client.search_memories(
            SearchMemoriesRequest(org_id=ORG, agent_id=AGENT, query="theme", timeout_seconds=0.1)
        )
    finally:
        await http.aclose()

    assert seen == [str(ORG), str(ORG)]


@pytest.mark.asyncio
async def test_retriever_sends_the_request_org_not_a_configured_one() -> None:
    """The header follows the assembly org; the client holds no org of its own."""
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        header_org = request.headers.get(ORG_HEADER.lower())
        seen.append(header_org)
        source = "hot_cache" if request.url.path.endswith("/hot") else "vector"
        return httpx.Response(200, json=_hit_body(source=source, org_id=header_org))

    client, http = _client(handler)
    retriever = ParallelRetriever(settings=_settings(), memory=client, directive=_DirectiveOk())
    try:
        await retriever.retrieve(_request(org_id=ORG))
        await retriever.retrieve(_request(org_id=OTHER_ORG))
    finally:
        await http.aclose()

    # Two assemblies, two orgs, two calls each.
    assert seen == [str(ORG), str(ORG), str(OTHER_ORG), str(OTHER_ORG)]


@pytest.mark.asyncio
async def test_client_raises_forbidden_with_status_403() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": {"code": "ORG_MISMATCH"}})

    client, http = _client(handler)
    try:
        with pytest.raises(MemoryHttpForbidden) as exc:
            await client.get_hot_memories(
                HotMemoriesRequest(org_id=OTHER_ORG, agent_id=AGENT, timeout_seconds=0.1)
            )
    finally:
        await http.aclose()

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_memory_403_is_a_branch_error_not_an_empty_success() -> None:
    """The refused branch fails; the healthy sibling still contributes."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/hot"):
            return httpx.Response(403, json={"detail": {"code": "ORG_MISMATCH"}})
        return httpx.Response(200, json=_hit_body(source="vector", org_id=OTHER_ORG))

    client, http = _client(handler)
    retriever = ParallelRetriever(settings=_settings(), memory=client, directive=_DirectiveOk())
    try:
        result = await retriever.retrieve(_request(org_id=OTHER_ORG))
    finally:
        await http.aclose()

    assert result.hot_outcome.status == "error"
    assert result.hot_outcome.detail == MEMORY_FORBIDDEN
    assert result.hot_memories == []
    assert "hot" not in result.sources_available
    assert result.cold_outcome.status == "success"
    assert len(result.cold_memories) == 1


@pytest.mark.asyncio
async def test_memory_403_is_logged_without_org_or_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": {"code": "ORG_MISMATCH"}})

    client, http = _client(handler)
    retriever = ParallelRetriever(settings=_settings(), memory=client, directive=_DirectiveOk())
    try:
        with caplog.at_level(logging.WARNING, logger="app.retrieval"):
            await retriever.retrieve(_request(org_id=OTHER_ORG))
    finally:
        await http.aclose()

    assert "context_memory_forbidden" in caplog.text
    assert str(OTHER_ORG) not in caplog.text
    assert "dark mode" not in caplog.text
