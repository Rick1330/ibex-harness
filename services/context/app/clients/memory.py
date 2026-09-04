"""Async HTTP client for memory hot + cold read surfaces (milestone 3.5.C.2).

Mirrors services/worker HttpMemoryWriter conventions (Bearer auth, per-call
timeout, typed transport errors) but uses httpx.AsyncClient and does not
retry — assembly fail-opens on branch failure.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx


class MemoryHttpError(Exception):
    """Non-retryable memory HTTP failure for a retrieval branch."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class MemoryHttpTimeout(MemoryHttpError):
    """Memory HTTP call timed out."""


@dataclass(frozen=True, slots=True)
class MemoryHttpConfig:
    base_url: str
    token: str


@dataclass(frozen=True, slots=True)
class MemoryHitPayload:
    """Normalized search/hot hit for RetrievalResult.MemoryHit mapping."""

    memory_id: str
    org_id: str
    agent_id: str
    content: str
    category: str
    confidence: float
    similarity: float
    rank: int
    source: str


@dataclass(frozen=True, slots=True)
class HotMemoriesRequest:
    agent_id: UUID
    timeout_seconds: float
    limit: int = 20
    min_confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class SearchMemoriesRequest:
    agent_id: UUID
    query: str
    timeout_seconds: float
    limit: int = 10
    min_confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class _MemoryCall:
    method: str
    path: str
    params: Mapping[str, Any] | None = None
    json: Mapping[str, Any] | None = None


class MemoryHttpClient:
    """GET /v1/memories/hot and POST /v1/memories/search."""

    def __init__(
        self,
        config: MemoryHttpConfig,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not config.base_url.strip():
            raise ValueError("memory_base_url is required for retrieval")
        if not config.token.strip():
            raise ValueError("memory_api_token is required for retrieval")
        self._config = config
        self._client = client or httpx.AsyncClient()
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_hot_memories(self, request: HotMemoriesRequest) -> list[MemoryHitPayload]:
        call = _MemoryCall(
            method="GET",
            path="/v1/memories/hot",
            params={
                "agent_id": str(request.agent_id),
                "limit": request.limit,
                "min_confidence": request.min_confidence,
            },
        )
        return await self._execute(call, request.timeout_seconds)

    async def search_memories(self, request: SearchMemoriesRequest) -> list[MemoryHitPayload]:
        call = _MemoryCall(
            method="POST",
            path="/v1/memories/search",
            json={
                "agent_id": str(request.agent_id),
                "query": request.query,
                "limit": request.limit,
                "min_confidence": request.min_confidence,
            },
        )
        return await self._execute(call, request.timeout_seconds)

    async def _execute(self, call: _MemoryCall, timeout_seconds: float) -> list[MemoryHitPayload]:
        url = f"{self._config.base_url.rstrip('/')}{call.path}"
        response = await self._send(call, url, timeout_seconds)
        return _hits_from_search_response(response)

    async def _send(
        self,
        call: _MemoryCall,
        url: str,
        timeout_seconds: float,
    ) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self._config.token}",
            "Accept": "application/json",
        }
        if call.json is not None:
            headers["Content-Type"] = "application/json"
        try:
            response = await self._client.request(
                call.method,
                url,
                headers=headers,
                params=call.params,
                json=call.json,
                timeout=timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise MemoryHttpTimeout("memory service timeout") from exc
        except httpx.TransportError as exc:
            raise MemoryHttpError("memory service transport error") from exc
        if response.status_code >= 400:
            raise MemoryHttpError(
                f"memory service HTTP {response.status_code}",
                status_code=response.status_code,
            )
        return response


def _hits_from_search_response(response: httpx.Response) -> list[MemoryHitPayload]:
    results = _results_list(response)
    hits: list[MemoryHitPayload] = []
    for item in results:
        hit = _hit_from_item(item)
        if hit is not None:
            hits.append(hit)
    return hits


def _results_list(response: httpx.Response) -> list[object]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise MemoryHttpError("memory service returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise MemoryHttpError("memory service returned non-object JSON")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise MemoryHttpError("memory service response missing data")
    results = data.get("results")
    if not isinstance(results, list):
        raise MemoryHttpError("memory service response missing results")
    return results


def _hit_from_item(item: object) -> MemoryHitPayload | None:
    if not isinstance(item, dict):
        return None
    memory = item.get("memory")
    if not isinstance(memory, dict):
        return None
    return MemoryHitPayload(
        memory_id=str(memory.get("id", "")),
        org_id=str(memory.get("org_id", "")),
        agent_id=str(memory.get("agent_id", "")),
        content=str(memory.get("content", "")),
        category=str(memory.get("category", "")),
        confidence=float(memory.get("confidence", 0.0)),
        similarity=float(item.get("similarity", 0.0)),
        rank=int(item.get("rank", 0)),
        source=str(item.get("source", "")),
    )
