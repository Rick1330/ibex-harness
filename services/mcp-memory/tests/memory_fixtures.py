"""Shared memory MockTransport helpers for mcp-memory tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import httpx

from app.clients.memory import MemoryHttpClient, build_memory_client

ORG = UUID("11111111-1111-1111-1111-111111111111")
AGENT = UUID("22222222-2222-2222-2222-222222222222")


@dataclass(frozen=True, slots=True)
class CreatedMemory:
    """Fixture knobs for a successful POST /v1/memories response body."""

    memory_id: str | None = None
    org_id: UUID = ORG
    agent_id: UUID = AGENT
    category: str = "factual"
    confidence: float = 0.6
    metadata: dict[str, Any] = field(default_factory=lambda: {"mcp_source": "mcp_explicit"})


def memory_client_for(handler: Callable[[httpx.Request], httpx.Response]) -> MemoryHttpClient:
    return build_memory_client(
        base_url="http://memory.test",
        timeout_seconds=1.0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def empty_search_response() -> httpx.Response:
    return httpx.Response(200, json={"data": {"results": []}})


def create_memory_response(created: CreatedMemory | None = None) -> httpx.Response:
    spec = created or CreatedMemory()
    mid = spec.memory_id or str(uuid4())
    return httpx.Response(
        201,
        json={
            "data": {
                "id": mid,
                "agent_id": str(spec.agent_id),
                "org_id": str(spec.org_id),
                "category": spec.category,
                "confidence": spec.confidence,
                "source": "user_provided",
                "status": "active",
                "metadata": dict(spec.metadata),
            }
        },
    )


@dataclass(frozen=True, slots=True)
class FeedbackResultSpec:
    """Fixture knobs for a successful POST /v1/memories/{id}/feedback response."""

    memory_id: str | None = None
    feedback: str = "positive"
    score: float = 0.67
    positive: int = 1
    negative: int = 0


def feedback_response(spec: FeedbackResultSpec | None = None) -> httpx.Response:
    resolved = spec or FeedbackResultSpec()
    mid = resolved.memory_id or str(uuid4())
    return httpx.Response(
        200,
        json={
            "data": {
                "memory_id": mid,
                "feedback": resolved.feedback,
                "new_usefulness_score": resolved.score,
                "total_positive_feedback": resolved.positive,
                "total_negative_feedback": resolved.negative,
            }
        },
    )


def _feedback_memory_id(path: str) -> str | None:
    """Return memory_id for `/v1/memories/{id}/feedback`, else None."""
    prefix = "/v1/memories/"
    suffix = "/feedback"
    if not path.startswith(prefix):
        return None
    if not path.endswith(suffix):
        return None
    memory_id = path.removeprefix(prefix).removesuffix(suffix)
    if not memory_id or "/" in memory_id:
        return None
    return memory_id


def stub_memory_handler(
    *,
    org_id: UUID = ORG,
    agent_id: UUID = AGENT,
) -> Callable[[httpx.Request], httpx.Response]:
    mid = str(uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/search"):
            return empty_search_response()
        if request.method != "POST":
            return create_memory_response(
                CreatedMemory(memory_id=mid, org_id=org_id, agent_id=agent_id)
            )
        memory_id = _feedback_memory_id(path)
        if memory_id is not None:
            return feedback_response(FeedbackResultSpec(memory_id=memory_id))
        return create_memory_response(
            CreatedMemory(memory_id=mid, org_id=org_id, agent_id=agent_id)
        )

    return handler


def stub_memory_client(
    *,
    org_id: UUID = ORG,
    agent_id: UUID = AGENT,
) -> MemoryHttpClient:
    return memory_client_for(stub_memory_handler(org_id=org_id, agent_id=agent_id))
