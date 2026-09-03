"""HTTP writer for POST /v1/memories from extraction results."""

from __future__ import annotations

from hashlib import sha256
from typing import Protocol
from uuid import UUID, uuid5

import httpx

from app.extraction.provider import ExtractionTransportError
from app.extraction.schema import ExtractedMemory

_RETRYABLE = frozenset({408, 429, 500, 502, 503, 504})
_IDEM_NS = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


class MemoryWriter(Protocol):
    def write(
        self,
        *,
        org_id: UUID,
        agent_id: UUID,
        session_id: UUID,
        turn_index: int,
        memory: ExtractedMemory,
    ) -> None: ...


class HttpMemoryWriter:
    """POST /v1/memories with labels + temporal fields. Tenant is the bearer token."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("memory_base_url is required for extraction writes")
        if not token.strip():
            raise ValueError("memory_api_token is required for extraction writes")
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout_seconds = timeout_seconds
        self._client = client or httpx.Client()
        self._owns_client = client is None

    def write(
        self,
        *,
        org_id: UUID,
        agent_id: UUID,
        session_id: UUID,
        turn_index: int,
        memory: ExtractedMemory,
    ) -> None:
        payload = {
            "agent_id": str(agent_id),
            "content": memory.content,
            "confidence": memory.confidence,
            "labels": [
                {"label": item.label, "confidence": item.confidence}
                for item in memory.categories
            ],
            "session_id": str(session_id),
        }
        if memory.valid_from is not None:
            payload["valid_from"] = memory.valid_from.isoformat()
        if memory.valid_until is not None:
            payload["valid_until"] = memory.valid_until.isoformat()
        digest = sha256(
            f"{org_id}:{session_id}:{turn_index}:{memory.content}".encode()
        ).hexdigest()
        try:
            response = self._client.post(
                f"{self._base_url}/v1/memories",
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                    "X-Idempotency-Key": str(uuid5(_IDEM_NS, digest)),
                },
                json=payload,
                timeout=self._timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ExtractionTransportError("memory service timeout") from exc
        except httpx.TransportError as exc:
            raise ExtractionTransportError("memory service transport error") from exc
        if response.status_code in _RETRYABLE:
            raise ExtractionTransportError(
                f"memory service HTTP {response.status_code}"
            )
        if response.status_code >= 400:
            raise ValueError(f"memory service HTTP {response.status_code}")

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
