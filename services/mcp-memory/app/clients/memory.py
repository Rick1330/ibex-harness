"""Async HTTP client for memory search/write (milestone 3.5.E.2).

Fail-closed: timeouts, transport errors, and HTTP ≥400 raise typed errors for
MCP tools to surface as CallToolResult(isError=true). Empty search results on
HTTP 200 are a normal success (results=[]), not degradation.

Token is supplied per call (forwarded caller PAT) — never logged.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, TypeVar
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

_T = TypeVar("_T")


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
class FeedbackResult:
    memory_id: str
    feedback: str
    new_usefulness_score: float
    total_positive_feedback: int
    total_negative_feedback: int


@dataclass(frozen=True, slots=True)
class LineageEdge:
    """One relationship edge, with the hop that reached it."""

    source_memory_id: str
    target_memory_id: str
    relationship_type: str
    confidence: float
    depth: int
    from_memory_id: str
    other_memory_id: str
    other_status: str
    other_tombstoned: bool


@dataclass(frozen=True, slots=True)
class LineageResult:
    """Bounded lineage for one memory, as returned by the memory service."""

    memory_id: str
    status: str
    tombstoned: bool
    # None when the supersession chain is longer than the 5-hop resolution cap.
    supersession_tip: str | None
    max_depth: int
    truncated: bool
    edges: tuple[LineageEdge, ...]


@dataclass(frozen=True, slots=True)
class _BodyCall:
    token: str
    body: Mapping[str, Any]
    extra_headers: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class _QueryCall:
    token: str
    params: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class _CallSpec:
    """Bundles outbound request fields so the sender stays under arg limits."""

    method: str
    path: str
    token: str
    body: Mapping[str, Any] | None = None
    params: Mapping[str, Any] | None = None
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


class _FeedbackBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    memory_id: UUID
    feedback: Literal["positive", "negative", "neutral"]
    new_usefulness_score: float = Field(ge=0.0, le=1.0)
    total_positive_feedback: int = Field(ge=0)
    total_negative_feedback: int = Field(ge=0)


class _LineageEndpointBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    memory_id: UUID
    status: str
    tombstoned: bool


class _LineageEdgeBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_memory_id: UUID
    target_memory_id: UUID
    # Plain string, not an enum: a new edge type must degrade the projection,
    # not fail the whole tool call for every caller.
    relationship_type: str
    confidence: float = Field(ge=0.0, le=1.0)
    depth: int = Field(ge=1)
    from_memory_id: UUID
    other: _LineageEndpointBody


class _LineageBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    memory_id: UUID
    status: str
    tombstoned: bool
    supersession_tip: UUID | None
    max_depth: int = Field(ge=1, le=5)
    truncated: bool
    edges: list[_LineageEdgeBody]


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
        return await self._post(
            "/v1/memories/search",
            _BodyCall(
                token=token,
                body={
                    "agent_id": str(agent_id),
                    "query": query,
                    "limit": limit,
                },
            ),
            _parse_search_hits,
        )

    async def create_memory(
        self,
        *,
        token: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> CreateMemoryResult:
        return await self._post(
            "/v1/memories",
            _BodyCall(
                token=token,
                body=dict(payload),
                extra_headers={"X-Idempotency-Key": idempotency_key},
            ),
            _parse_create_result,
        )

    async def record_feedback(
        self,
        *,
        token: str,
        memory_id: UUID,
        body: Mapping[str, Any],
    ) -> FeedbackResult:
        return await self._post(
            f"/v1/memories/{memory_id}/feedback",
            _BodyCall(token=token, body=dict(body)),
            _parse_feedback_result,
        )

    async def get_lineage(
        self,
        *,
        token: str,
        memory_id: UUID,
        max_depth: int,
    ) -> LineageResult:
        return await self._get(
            f"/v1/memories/{memory_id}/lineage",
            _QueryCall(token=token, params={"max_depth": max_depth}),
            _parse_lineage_result,
        )

    async def _post(self, path: str, call: _BodyCall, parse: Callable[[httpx.Response], _T]) -> _T:
        return await self._call(
            _CallSpec(
                method="POST",
                path=path,
                token=call.token,
                body=call.body,
                extra_headers=call.extra_headers,
            ),
            parse,
        )

    async def _get(self, path: str, call: _QueryCall, parse: Callable[[httpx.Response], _T]) -> _T:
        return await self._call(
            _CallSpec(method="GET", path=path, token=call.token, params=call.params),
            parse,
        )

    async def _call(self, spec: _CallSpec, parse: Callable[[httpx.Response], _T]) -> _T:
        """Send one call and parse its body; the single place the two steps meet."""
        return parse(await self._send(spec))

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
                params=call.params,
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


def _parse_feedback_result(response: httpx.Response) -> FeedbackResult:
    try:
        body = _FeedbackBody.model_validate(_response_data(response))
    except ValidationError as exc:
        raise MemoryHttpError(
            f"memory feedback response invalid: {exc.errors()[0]['msg']}"
        ) from exc
    return FeedbackResult(
        memory_id=str(body.memory_id),
        feedback=body.feedback,
        new_usefulness_score=body.new_usefulness_score,
        total_positive_feedback=body.total_positive_feedback,
        total_negative_feedback=body.total_negative_feedback,
    )


def _parse_lineage_result(response: httpx.Response) -> LineageResult:
    try:
        body = _LineageBody.model_validate(_response_data(response))
    except ValidationError as exc:
        raise MemoryHttpError(
            f"memory lineage response invalid: {exc.errors()[0]['msg']}"
        ) from exc
    return LineageResult(
        memory_id=str(body.memory_id),
        status=body.status,
        tombstoned=body.tombstoned,
        supersession_tip=(
            str(body.supersession_tip) if body.supersession_tip is not None else None
        ),
        max_depth=body.max_depth,
        truncated=body.truncated,
        edges=tuple(
            LineageEdge(
                source_memory_id=str(edge.source_memory_id),
                target_memory_id=str(edge.target_memory_id),
                relationship_type=edge.relationship_type,
                confidence=edge.confidence,
                depth=edge.depth,
                from_memory_id=str(edge.from_memory_id),
                other_memory_id=str(edge.other.memory_id),
                other_status=edge.other.status,
                other_tombstoned=edge.other.tombstoned,
            )
            for edge in body.edges
        ),
    )
