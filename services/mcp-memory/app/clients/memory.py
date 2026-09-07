"""Async HTTP client for memory search/write (milestone 3.5.E.2).

Fail-closed: timeouts, transport errors, and HTTP ≥400 raise typed errors for
MCP tools to surface as CallToolResult(isError=true). Empty search results on
HTTP 200 are a normal success (results=[]), not degradation.

Token is supplied per call (forwarded caller PAT) — never logged.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError


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


@dataclass(frozen=True, slots=True)
class _CallSpec:
    """Bundles outbound request fields so the sender stays under arg limits."""

    method: str
    path: str
    token: str
    body: Mapping[str, Any] | None = None
    extra_headers: Mapping[str, str] | None = None


class _SearchMemoryBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    content: str
    category: str


class _SearchResultRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    memory: _SearchMemoryBody
    similarity: float
    rank: int = Field(ge=1)
    source: str


class _SearchEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    results: list[_SearchResultRow]


class _CreateMemoryBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    org_id: UUID
    agent_id: UUID
    category: str
    confidence: float = Field(ge=0.0, le=1.0)
    status: str
    source: str
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_memory_client(
    *,
    base_url: str,
    timeout_seconds: float,
    client: httpx.AsyncClient | None = None,
) -> MemoryHttpClient:
    return MemoryHttpClient(
        MemoryHttpConfig(base_url=base_url, timeout_seconds=timeout_seconds),
        client=client,
    )


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
        response = await self._send(
            _CallSpec(
                method="POST",
                path="/v1/memories/search",
                token=token,
                body={
                    "agent_id": str(agent_id),
                    "query": query,
                    "limit": limit,
                },
            )
        )
        return _parse_search_hits(response)

    async def create_memory(
        self,
        *,
        token: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> CreateMemoryResult:
        response = await self._send(
            _CallSpec(
                method="POST",
                path="/v1/memories",
                token=token,
                body=dict(payload),
                extra_headers={"X-Idempotency-Key": idempotency_key},
            )
        )
        return _parse_create_result(response)

    async def _send(self, call: _CallSpec) -> httpx.Response:
        if not call.token.strip():
            raise MemoryHttpError("missing bearer token for memory service call")
        headers = {
            "Authorization": f"Bearer {call.token}",
            "Accept": "application/json",
        }
        if call.body is not None:
            headers["Content-Type"] = "application/json"
        if call.extra_headers:
            headers.update(call.extra_headers)
        response = await self._exchange(call, headers)
        _raise_http_error(response)
        return response

    async def _exchange(
        self, call: _CallSpec, headers: dict[str, str]
    ) -> httpx.Response:
        try:
            return await self._client.request(
                call.method,
                f"{self.base_url}{call.path}",
                headers=headers,
                json=call.body,
                timeout=self._config.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise MemoryHttpTimeout("memory service timeout") from exc
        except httpx.TransportError as exc:
            raise MemoryHttpError("memory service transport error") from exc


def _raise_http_error(response: httpx.Response) -> None:
    if response.status_code >= 400:
        raise MemoryHttpError(
            f"memory service HTTP {response.status_code}",
            status_code=response.status_code,
        )


def _response_data(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise MemoryHttpError("memory service returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise MemoryHttpError("memory service returned non-object JSON")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise MemoryHttpError("memory service response missing data")
    return data


def _parse_search_hits(response: httpx.Response) -> list[SearchHit]:
    try:
        envelope = _SearchEnvelope.model_validate(_response_data(response))
    except ValidationError as exc:
        raise MemoryHttpError(f"memory search response invalid: {exc.errors()[0]['msg']}") from exc
    return [
        SearchHit(
            memory_id=str(row.memory.id),
            content=row.memory.content,
            score=row.similarity,
            category=row.memory.category,
            similarity=row.similarity,
            rank=row.rank,
            source=row.source,
        )
        for row in envelope.results
    ]


def _parse_create_result(response: httpx.Response) -> CreateMemoryResult:
    try:
        body = _CreateMemoryBody.model_validate(_response_data(response))
    except ValidationError as exc:
        raise MemoryHttpError(f"memory create response invalid: {exc.errors()[0]['msg']}") from exc
    return CreateMemoryResult(
        memory_id=str(body.id),
        org_id=str(body.org_id),
        agent_id=str(body.agent_id),
        category=body.category,
        confidence=body.confidence,
        status=body.status,
        source=body.source,
        metadata=dict(body.metadata),
    )
