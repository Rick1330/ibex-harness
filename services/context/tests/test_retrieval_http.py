"""MockTransport integration for MemoryHttpClient + ParallelRetriever."""

from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest

from app.budget import Message
from app.clients.directive import DirectivePayload
from app.clients.memory import (
    HotMemoriesRequest,
    MemoryHttpClient,
    MemoryHttpConfig,
    SearchMemoriesRequest,
)
from app.config import ContextSettings
from app.retrieval import ParallelRetriever, RetrievalRequest

ORG = uuid4()
AGENT = uuid4()
TOKEN = "context-test-token"


def _search_body(*, source: str, content: str) -> dict:
    mid = str(uuid4())
    return {
        "data": {
            "results": [
                {
                    "memory": {
                        "id": mid,
                        "agent_id": str(AGENT),
                        "org_id": str(ORG),
                        "content": content,
                        "category": "preference",
                        "confidence": 0.9,
                        "status": "active",
                        "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-01-01T00:00:00Z",
                    },
                    "similarity": 0.88,
                    "rank": 1,
                    "source": source,
                }
            ]
        }
    }


class _DirectiveOk:
    async def lookup(self, org_id, agent_id) -> DirectivePayload:
        return DirectivePayload(
            content="Stay concise.",
            injection_mode="system_first",
            version_id=str(uuid4()),
        )


@pytest.mark.asyncio
async def test_memory_http_client_hot_and_search_via_mock_transport() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.setdefault("paths", []).append(request.url.path)  # type: ignore[union-attr]
        captured["auth"] = request.headers.get("authorization")
        if request.method == "GET" and request.url.path.endswith("/v1/memories/hot"):
            assert request.url.params.get("agent_id") == str(AGENT)
            return httpx.Response(200, json=_search_body(source="hot_cache", content="hot hit"))
        if request.method == "POST" and request.url.path.endswith("/v1/memories/search"):
            body = json.loads(request.content.decode())
            captured["search_body"] = body
            assert body["query"] == "theme"
            return httpx.Response(200, json=_search_body(source="vector", content="cold hit"))
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        memory = MemoryHttpClient(
            MemoryHttpConfig(base_url="http://memory.example", token=TOKEN),
            client=client,
        )
        hot = await memory.get_hot_memories(
            HotMemoriesRequest(agent_id=AGENT, timeout_seconds=0.1)
        )
        cold = await memory.search_memories(
            SearchMemoriesRequest(agent_id=AGENT, query="theme", timeout_seconds=0.1)
        )

    assert captured["auth"] == f"Bearer {TOKEN}"
    assert hot[0].source == "hot_cache"
    assert cold[0].source == "vector"
    assert "/v1/memories/hot" in captured["paths"]  # type: ignore[operator]
    assert "/v1/memories/search" in captured["paths"]  # type: ignore[operator]


@pytest.mark.asyncio
async def test_parallel_retriever_uses_real_http_client_mock_transport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/hot"):
            return httpx.Response(200, json=_search_body(source="hot_cache", content="from-hot"))
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json=_search_body(source="vector", content="from-cold"))
        return httpx.Response(500, json={"detail": "unexpected"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        memory = MemoryHttpClient(
            MemoryHttpConfig(base_url="http://memory.example", token=TOKEN),
            client=client,
        )
        retriever = ParallelRetriever(
            settings=ContextSettings.model_construct(
                timeout_ms=45.0,
                directive_timeout_ms=5.0,
                hot_timeout_ms=15.0,
                cold_timeout_ms=45.0,
            ),
            memory=memory,
            directive=_DirectiveOk(),
        )
        result = await retriever.retrieve(
            RetrievalRequest(
                org_id=ORG,
                agent_id=AGENT,
                query="theme",
                model="gpt-4o-mini",
                recent_messages=[Message(role="user", content="dark?")],
            )
        )

    assert result.sources_available == frozenset({"directive", "hot", "cold"})
    assert result.hot_memories[0].content == "from-hot"
    assert result.cold_memories[0].content == "from-cold"
    assert result.directive is not None
    assert result.directive.content == "Stay concise."
