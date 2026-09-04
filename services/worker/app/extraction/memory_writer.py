"""HTTP writer for POST /v1/memories from extraction results.

Idempotency keys are identity-based, not content-based (ADR-0065):

  key_material = f"{org_id}:{session_id}:{turn_index}:{memory_ordinal}"

where memory_ordinal is the 0-based index in TurnExtraction.memories for that
turn in a single provider result. Retries with different LLM wording for the
same ordinal reuse the same X-Idempotency-Key.

Residual limitation (accepted, not solved here): if a retry's LLM call returns
a different NUMBER of memories for the same turn, ordinals can misalign.
Exact/near-dedup in services/memory is defense-in-depth for that residual case.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol
from uuid import UUID, uuid5

import httpx

from app.extraction.provider import ExtractionTransportError
from app.extraction.schema import ExtractedMemory

_RETRYABLE = frozenset({408, 429, 500, 502, 503, 504})
_IDEM_NS = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
# Memory-service 409 codes that mean "already durable for this slot" on retry.
_SUCCESS_409_CODES = frozenset({"IDEMPOTENCY_CONFLICT", "DUPLICATE_CONTENT"})


@dataclass(frozen=True, slots=True)
class MemoryWriteRequest:
    org_id: UUID
    agent_id: UUID
    session_id: UUID
    turn_index: int
    memory: ExtractedMemory
    ordinal: int


@dataclass(frozen=True, slots=True)
class MemoryHttpConfig:
    base_url: str
    token: str
    timeout_seconds: float = 30.0


class MemoryWriter(Protocol):
    def write(self, request: MemoryWriteRequest) -> None: ...


def memory_idempotency_digest(request: MemoryWriteRequest) -> str:
    """SHA-256 hex digest for identity-based idempotency (no LLM content)."""
    # Residual: ordinal misaligns if retry returns a different memory COUNT.
    return sha256(
        f"{request.org_id}:{request.session_id}:{request.turn_index}:"
        f"{request.ordinal}".encode()
    ).hexdigest()


def memory_idempotency_key(request: MemoryWriteRequest) -> str:
    """X-Idempotency-Key value for one memory write."""
    return str(uuid5(_IDEM_NS, memory_idempotency_digest(request)))


def content_derived_idempotency_digest(
    *,
    org_id: UUID,
    session_id: UUID,
    turn_index: int,
    content: str,
) -> str:
    """Pre-3.5.B.3 digest (content-keyed) — retained for regression tests only."""
    return sha256(
        f"{org_id}:{session_id}:{turn_index}:{content}".encode()
    ).hexdigest()


class HttpMemoryWriter:
    """POST /v1/memories with labels + temporal fields. Tenant is the bearer token."""

    def __init__(
        self,
        config: MemoryHttpConfig,
        client: httpx.Client | None = None,
    ) -> None:
        if not config.base_url.strip():
            raise ValueError("memory_base_url is required for extraction writes")
        if not config.token.strip():
            raise ValueError("memory_api_token is required for extraction writes")
        self._config = config
        self._client = client or httpx.Client()
        self._owns_client = client is None

    def write(self, request: MemoryWriteRequest) -> None:
        payload = _memory_payload(request)
        response = _post_memory(
            self._client, self._config, payload, memory_idempotency_key(request)
        )
        _raise_for_memory_status(response)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def _memory_payload(request: MemoryWriteRequest) -> dict[str, object]:
    memory = request.memory
    payload: dict[str, object] = {
        "agent_id": str(request.agent_id),
        "content": memory.content,
        "confidence": memory.confidence,
        "labels": [
            {"label": item.label, "confidence": item.confidence}
            for item in memory.categories
        ],
        "session_id": str(request.session_id),
    }
    if memory.valid_from is not None:
        payload["valid_from"] = memory.valid_from.isoformat()
    if memory.valid_until is not None:
        payload["valid_until"] = memory.valid_until.isoformat()
    return payload


def _post_memory(
    client: httpx.Client,
    config: MemoryHttpConfig,
    payload: dict[str, object],
    idempotency_key: str,
) -> httpx.Response:
    try:
        return client.post(
            f"{config.base_url.rstrip('/')}/v1/memories",
            headers={
                "Authorization": f"Bearer {config.token}",
                "Content-Type": "application/json",
                "X-Idempotency-Key": idempotency_key,
            },
            json=payload,
            timeout=config.timeout_seconds,
        )
    except httpx.TimeoutException as exc:
        raise ExtractionTransportError("memory service timeout") from exc
    except httpx.TransportError as exc:
        raise ExtractionTransportError("memory service transport error") from exc


def _raise_for_memory_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    if response.status_code in _RETRYABLE:
        raise ExtractionTransportError(f"memory service HTTP {response.status_code}")
    if response.status_code == 409:
        _raise_for_memory_conflict(response)
        return
    raise ValueError(f"memory service HTTP {response.status_code}")


def _raise_for_memory_conflict(response: httpx.Response) -> None:
    if _detail_code(response) in _SUCCESS_409_CODES:
        return
    if _detail_code(response) == "IDEMPOTENCY_IN_PROGRESS":
        raise ExtractionTransportError("memory service HTTP 409 IDEMPOTENCY_IN_PROGRESS")
    raise ValueError("memory service HTTP 409")


def _detail_code(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    detail = payload.get("detail")
    if isinstance(detail, dict):
        code = detail.get("code")
        return code if isinstance(code, str) else None
    return None
