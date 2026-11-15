"""Async HTTP client for memory hot + cold read surfaces (milestone 3.5.C.2).

Mirrors services/worker HttpMemoryWriter conventions (Bearer auth, per-call
timeout, typed transport errors) but uses httpx.AsyncClient and does not
retry — assembly fail-opens on branch failure.

Every call presents the shared service token *and* the org the assembly is
serving, as ``X-Ibex-Org-Id``. Memory derives the tenant from the token and
refuses a header that disagrees with it (403), so a wrong or stale credential
is a loud branch error instead of a silent empty result.

This does **not** let context serve an org its token does not belong to. The
token still fixes the tenant; sending the header only makes the mismatch
visible. Serving more than one org needs per-org credentials and is deferred
(stage 2 of the v1 tenancy release plan).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx

# Header carrying the org the assembly is scoped to; memory compares it to the
# token's org and answers 403 on a mismatch (never a silent re-scope).
ORG_HEADER = "X-Ibex-Org-Id"


class MemoryHttpError(Exception):
    """Non-retryable memory HTTP failure for a retrieval branch."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class MemoryHttpTimeout(MemoryHttpError):
    """Memory HTTP call timed out."""


class MemoryHttpForbidden(MemoryHttpError):
    """Memory refused the call for this org or token (HTTP 403).

    Kept distinct from the generic ``MemoryHttpError`` so retrieval can report
    ``memory_forbidden`` instead of an opaque status: a 403 is the one memory
    failure that means "the answer you got would have been wrong", and it must
    not be mistaken for "this org has no memories".
    """


@dataclass(frozen=True, slots=True)
class MemoryHttpConfig:
    base_url: str
    token: str


@dataclass(frozen=True, slots=True)
class MemoryHitPayload:
    """Normalized search/hot hit for RetrievalResult.MemoryHit mapping.

    ``conflict_groups`` carries the memory service's unresolved-conflict
    escalation ids. Optional on the wire: a memory service that predates the
    field simply sends nothing and every hit is treated as conflict-free.
    """

    memory_id: str
    org_id: str
    agent_id: str
    content: str
    category: str
    confidence: float
    similarity: float
    rank: int
    source: str
    conflict_groups: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HotMemoriesRequest:
    org_id: UUID
    agent_id: UUID
    timeout_seconds: float
    limit: int = 20
    min_confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class SearchMemoriesRequest:
    org_id: UUID
    agent_id: UUID
    query: str
    timeout_seconds: float
    limit: int = 10
    min_confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class _MemoryCall:
    method: str
    path: str
    org_id: str
    params: Mapping[str, Any] | None = None
    json: Mapping[str, Any] | None = None


def _build_memory_call(request: HotMemoriesRequest | SearchMemoriesRequest) -> _MemoryCall:
    if isinstance(request, HotMemoriesRequest):
        return _MemoryCall(
            method="GET",
            path="/v1/memories/hot",
            org_id=str(request.org_id),
            params={
                "agent_id": str(request.agent_id),
                "limit": request.limit,
                "min_confidence": request.min_confidence,
            },
        )
    return _MemoryCall(
        method="POST",
        path="/v1/memories/search",
        org_id=str(request.org_id),
        json={
            "agent_id": str(request.agent_id),
            "query": request.query,
            "limit": request.limit,
            "min_confidence": request.min_confidence,
        },
    )


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
        call = _build_memory_call(request)
        return await self._execute(call, request.timeout_seconds)

    async def search_memories(self, request: SearchMemoriesRequest) -> list[MemoryHitPayload]:
        return await self._execute(
            _build_memory_call(request),
            request.timeout_seconds,
        )

    async def _execute(self, call: _MemoryCall, timeout_seconds: float) -> list[MemoryHitPayload]:
        url = f"{self._config.base_url.rstrip('/')}{call.path}"
        response = await self._send(call, url, timeout_seconds)
        return _hits_from_search_response(response)

    def _headers(self, call: _MemoryCall) -> dict[str, str]:
        """Auth, accept, and the org this call is scoped to."""
        headers = {
            "Authorization": f"Bearer {self._config.token}",
            "Accept": "application/json",
            ORG_HEADER: call.org_id,
        }
        if call.json is not None:
            headers["Content-Type"] = "application/json"
        return headers

    async def _send(
        self,
        call: _MemoryCall,
        url: str,
        timeout_seconds: float,
    ) -> httpx.Response:
        response = await self._request(call, url, timeout_seconds)
        _raise_for_status(response)
        return response

    async def _request(
        self,
        call: _MemoryCall,
        url: str,
        timeout_seconds: float,
    ) -> httpx.Response:
        try:
            return await self._client.request(
                call.method,
                url,
                headers=self._headers(call),
                params=call.params,
                json=call.json,
                timeout=timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise MemoryHttpTimeout("memory service timeout") from exc
        except httpx.TransportError as exc:
            raise MemoryHttpError("memory service transport error") from exc


def _raise_for_status(response: httpx.Response) -> None:
    """Map a refused or failed memory response to the typed client errors."""
    if response.status_code == 403:
        raise MemoryHttpForbidden(
            "memory service refused this org",
            status_code=response.status_code,
        )
    if response.status_code >= 400:
        raise MemoryHttpError(
            f"memory service HTTP {response.status_code}",
            status_code=response.status_code,
        )


def _hits_from_search_response(response: httpx.Response) -> list[MemoryHitPayload]:
    return [_hit_from_item(item) for item in _results_list(response)]


def _results_list(response: httpx.Response) -> list[object]:
    payload = _json_object(response)
    data = _require_mapping(payload.get("data"), "data")
    results = data.get("results")
    if not isinstance(results, list):
        raise MemoryHttpError("memory service response missing results")
    return results


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


def _hit_from_item(item: object) -> MemoryHitPayload:
    if not isinstance(item, dict):
        raise MemoryHttpError("memory search result item must be an object")
    memory = item.get("memory")
    if not isinstance(memory, dict):
        raise MemoryHttpError("memory search result missing memory object")
    return MemoryHitPayload(
        memory_id=_require_uuid_str(memory.get("id"), "memory.id"),
        org_id=_require_uuid_str(memory.get("org_id"), "memory.org_id"),
        agent_id=_require_uuid_str(memory.get("agent_id"), "memory.agent_id"),
        content=_require_str(memory.get("content"), "memory.content"),
        category=_require_str(memory.get("category"), "memory.category"),
        confidence=_require_unit_float(memory.get("confidence"), "memory.confidence"),
        similarity=_require_finite_float(item.get("similarity"), "similarity"),
        rank=_require_positive_int(item.get("rank"), "rank"),
        source=_require_str(item.get("source"), "source"),
        conflict_groups=_conflict_groups(memory.get("conflict_groups")),
    )


def _conflict_groups(value: object) -> tuple[str, ...]:
    """Parse the optional pending-conflict escalation ids; absent means none."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise MemoryHttpError("memory.conflict_groups must be a list")
    return tuple(
        _require_uuid_str(item, "memory.conflict_groups[]") for item in value
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
