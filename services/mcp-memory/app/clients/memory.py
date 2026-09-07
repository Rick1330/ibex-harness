"""Async HTTP client for memory search/write (milestone 3.5.E.2).

Fail-closed: timeouts, transport errors, and HTTP ≥400 raise typed errors for
MCP tools to surface as CallToolResult(isError=true). Empty search results on
HTTP 200 are a normal success (results=[]), not degradation.

Conventions mirror services/context MemoryHttpClient (async httpx, Bearer,
per-call timeout) and services/worker HttpMemoryWriter (X-Idempotency-Key on
writes). Token is supplied per call (forwarded caller PAT) — never logged.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx


class MemoryHttpError(Exception):
    """Memory HTTP failure — tools must fail closed (never invent empty hits)."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class MemoryHttpTimeout(MemoryHttpError):
    """Memory HTTP call timed out."""


@dataclass(frozen=True, slots=True)
class MemoryHttpConfig:
    base_url: str
    timeout_seconds: float = 5.0


@dataclass(frozen=True, slots=True)
class SearchHit:
    memory_id: str
    content: str
    score: float
    category: str
    similarity: float
    rank: int
    source: str


@dataclass(frozen=True, slots=True)
class CreateMemoryResult:
    memory_id: str
    org_id: str
    agent_id: str
    category: str
    confidence: float
    status: str
    source: str
    metadata: dict[str, Any]


class MemoryHttpClient:
    """POST /v1/memories/search and POST /v1/memories with shared AsyncClient."""

    def __init__(
        self,
        config: MemoryHttpConfig,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not config.base_url.strip():
            raise ValueError("IBEX_MEMORY_HTTP_URL is required for memory tools")
        if config.timeout_seconds <= 0:
            raise ValueError("memory_timeout_seconds must be positive")
        self._config = config
        self._client = client or httpx.AsyncClient()
        self._owns_client = client is None

    @property
    def base_url(self) -> str:
        return self._config.base_url.rstrip("/")

    @property
    def timeout_seconds(self) -> float:
        return self._config.timeout_seconds

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search_memories(
        self,
        *,
        token: str,
        agent_id: UUID,
        query: str,
        limit: int,
    ) -> list[SearchHit]:
        response = await self._request(
            "POST",
            "/v1/memories/search",
            token=token,
            json={
                "agent_id": str(agent_id),
                "query": query,
                "limit": limit,
            },
        )
        return _hits_from_search_response(response)

    async def create_memory(
        self,
        *,
        token: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> CreateMemoryResult:
        response = await self._request(
            "POST",
            "/v1/memories",
            token=token,
            json=dict(payload),
            extra_headers={"X-Idempotency-Key": idempotency_key},
        )
        return _create_result_from_response(response)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        token: str,
        json: Mapping[str, Any] | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        if not token.strip():
            raise MemoryHttpError("missing bearer token for memory service call")
        url = f"{self.base_url}{path}"
        headers: dict[str, str] = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        if json is not None:
            headers["Content-Type"] = "application/json"
        if extra_headers:
            headers.update(extra_headers)
        try:
            response = await self._client.request(
                method,
                url,
                headers=headers,
                json=json,
                timeout=self._config.timeout_seconds,
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


def _hits_from_search_response(response: httpx.Response) -> list[SearchHit]:
    return [_hit_from_item(item) for item in _results_list(response)]


def _results_list(response: httpx.Response) -> list[object]:
    payload = _json_object(response)
    data = _require_mapping(payload.get("data"), "data")
    results = data.get("results")
    if not isinstance(results, list):
        raise MemoryHttpError("memory service response missing results")
    return results


def _create_result_from_response(response: httpx.Response) -> CreateMemoryResult:
    payload = _json_object(response)
    data = _require_mapping(payload.get("data"), "data")
    metadata_raw = data.get("metadata")
    if metadata_raw is None:
        metadata: dict[str, Any] = {}
    elif isinstance(metadata_raw, dict):
        metadata = dict(metadata_raw)
    else:
        raise MemoryHttpError("memory.data.metadata must be an object")
    return CreateMemoryResult(
        memory_id=_require_uuid_str(data.get("id"), "memory.id"),
        org_id=_require_uuid_str(data.get("org_id"), "memory.org_id"),
        agent_id=_require_uuid_str(data.get("agent_id"), "memory.agent_id"),
        category=_require_str(data.get("category"), "memory.category"),
        confidence=_require_unit_float(data.get("confidence"), "memory.confidence"),
        status=_require_str(data.get("status"), "memory.status"),
        source=_require_str(data.get("source"), "memory.source"),
        metadata=metadata,
    )


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise MemoryHttpError("memory service returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise MemoryHttpError("memory service returned non-object JSON")
    return payload


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MemoryHttpError(f"memory service response missing {label}")
    return value


def _hit_from_item(item: object) -> SearchHit:
    if not isinstance(item, dict):
        raise MemoryHttpError("memory search result item must be an object")
    memory = item.get("memory")
    if not isinstance(memory, dict):
        raise MemoryHttpError("memory search result missing memory object")
    similarity = _require_finite_float(item.get("similarity"), "similarity")
    return SearchHit(
        memory_id=_require_uuid_str(memory.get("id"), "memory.id"),
        content=_require_str(memory.get("content"), "memory.content"),
        score=similarity,
        category=_require_str(memory.get("category"), "memory.category"),
        similarity=similarity,
        rank=_require_positive_int(item.get("rank"), "rank"),
        source=_require_str(item.get("source"), "source"),
    )


def _require_str(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise MemoryHttpError(f"{label} must be a string")
    return value


def _require_uuid_str(value: object, label: str) -> str:
    text = _require_str(value, label)
    try:
        return str(UUID(text))
    except ValueError as exc:
        raise MemoryHttpError(f"{label} must be a UUID") from exc


def _require_finite_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MemoryHttpError(f"{label} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise MemoryHttpError(f"{label} must be finite")
    return number


def _require_unit_float(value: object, label: str) -> float:
    number = _require_finite_float(value, label)
    if number < 0.0 or number > 1.0:
        raise MemoryHttpError(f"{label} must be in [0, 1]")
    return number


def _require_positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MemoryHttpError(f"{label} must be an integer")
    if value < 1:
        raise MemoryHttpError(f"{label} must be >= 1")
    return value
