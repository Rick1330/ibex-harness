"""Async HTTP client for hosted embedding APIs (OpenAI / Cohere).

Mirrors TeiClient constraints:
  - One long-lived AsyncClient; retries only on 429/502/503 + transport/timeout.
  - Logging: status, batch_size, latency, error_class — NEVER api key, text, or vectors.
  - api_key is not stored on HostedClientConfig; Authorization is applied per-request
    via a redacted auth helper so client/httpx repr cannot leak the secret.
  - follow_redirects is False so a 3xx cannot bounce the Bearer token to another host.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any, Literal, NoReturn

import httpx
import numpy as np
from numpy.typing import NDArray

from app.errors import (
    BackendRejectedError,
    BackendTimeoutError,
    BackendUnavailableError,
    InvalidVectorError,
)
from app.hosted.protocol import parse_cohere_embed_response, parse_openai_embed_response
from app.hosted.providers import openai_request_dimensions

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS: frozenset[int] = frozenset({429, 502, 503})
_BACKOFF_BASE_SECONDS = 0.25
_BACKOFF_MAX_SECONDS = 8.0

HostedClientProvider = Literal["openai", "cohere"]


class _RedactedBearerAuth(httpx.Auth):
    """Attach Authorization without putting the token in default headers/repr."""

    __slots__ = ("_token",)

    def __init__(self, token: str) -> None:
        self._token = token

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request

    def __repr__(self) -> str:
        return "RedactedBearerAuth()"


@dataclass(frozen=True, slots=True)
class HostedClientConfig:
    connect_timeout: float = 2.0
    read_timeout: float = 30.0
    max_retries: int = 2
    provider: HostedClientProvider = "openai"
    model_id: str = "text-embedding-3-large"
    dimensions: int = 3072


def _jittered_backoff(attempt: int) -> float:
    cap = min(_BACKOFF_BASE_SECONDS * (2**attempt), _BACKOFF_MAX_SECONDS)
    return (secrets.randbelow(1_000_000) / 1_000_000) * cap


def _parse_retry_after_seconds(raw: str | None) -> float | None:
    """Parse RFC 9110 delay-seconds Retry-After. HTTP-dates and junk are ignored."""
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped or len(stripped) > 8 or not stripped.isdigit():
        return None
    return float(int(stripped))


def _retry_delay_seconds(attempt: int, retry_after_seconds: float | None) -> float:
    delay = _jittered_backoff(attempt)
    if retry_after_seconds is None:
        return delay
    return min(_BACKOFF_MAX_SECONDS, max(delay, retry_after_seconds))


class HostedClient:
    """Long-lived async HTTP client for one hosted provider instance."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        config: HostedClientConfig,
    ) -> None:
        if not base_url or not base_url.strip():
            raise ValueError("HostedClient: base_url must not be empty")
        token = api_key.strip() if api_key else ""
        if not token:
            raise ValueError("HostedClient: api_key must not be empty")
        self._base_url = base_url.rstrip("/")
        self._max_retries = max(0, config.max_retries)
        self._provider = config.provider
        self._model_id = config.model_id
        self._dimensions = config.dimensions

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Accept": "application/json"},
            auth=_RedactedBearerAuth(token),
            timeout=httpx.Timeout(
                config.read_timeout,
                connect=config.connect_timeout,
            ),
            follow_redirects=False,
        )

    def __repr__(self) -> str:
        return (
            f"HostedClient(provider={self._provider!r}, model_id={self._model_id!r}, "
            f"dimensions={self._dimensions})"
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def embed(self, texts: list[str]) -> NDArray[np.float32]:
        path, payload = self._build_request(texts)
        return await self._post_with_retry(path, payload, batch_size=len(texts))

    def _build_request(self, texts: list[str]) -> tuple[str, dict[str, Any]]:
        if self._provider == "openai":
            return self._openai_request(texts)
        return self._cohere_request(texts)

    def _openai_request(self, texts: list[str]) -> tuple[str, dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": self._model_id,
            "input": texts,
            "encoding_format": "float",
        }
        dims = openai_request_dimensions(self._model_id, self._dimensions)
        if dims is not None:
            payload["dimensions"] = dims
        return "/embeddings", payload

    def _cohere_request(self, texts: list[str]) -> tuple[str, dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": self._model_id,
            "texts": texts,
            "input_type": "search_document",
            "embedding_types": ["float"],
            "truncate": "NONE",
        }
        return "/v2/embed", payload

    async def _post_with_retry(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        batch_size: int,
    ) -> NDArray[np.float32]:
        last_exc: Exception = BackendUnavailableError(f"hosted {path}: no attempts made")
        for attempt in range(self._max_retries + 1):
            try:
                return await self._attempt_post(path, payload, batch_size=batch_size)
            except (BackendRejectedError, InvalidVectorError):
                raise
            except (BackendUnavailableError, BackendTimeoutError) as exc:
                last_exc = exc
                await self._maybe_schedule_retry(path, attempt, exc)
        raise last_exc

    async def _maybe_schedule_retry(
        self, path: str, attempt: int, exc: BackendUnavailableError | BackendTimeoutError
    ) -> None:
        if not _is_retryable(exc):
            raise exc
        if attempt >= self._max_retries:
            raise exc
        retry_after = (
            exc.retry_after_seconds if isinstance(exc, BackendUnavailableError) else None
        )
        delay = _retry_delay_seconds(attempt, retry_after)
        logger.warning(
            "hosted %s transient error; retrying attempt=%d/%d delay_ms=%.0f error_class=%s",
            path,
            attempt + 1,
            self._max_retries + 1,
            delay * 1000,
            type(exc).__name__,
        )
        await asyncio.sleep(delay)

    async def _attempt_post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        batch_size: int,
    ) -> NDArray[np.float32]:
        t0 = time.monotonic()
        try:
            resp = await self._client.post(path, json=payload)
        except httpx.TimeoutException as exc:
            raise BackendTimeoutError(f"hosted {path} timed out") from exc
        except httpx.TransportError as exc:
            raise BackendUnavailableError(
                f"hosted {path} connection error: {type(exc).__name__}",
                retryable=True,
            ) from exc

        latency_ms = (time.monotonic() - t0) * 1000
        return self._parse_response(resp, path=path, latency_ms=latency_ms, batch_size=batch_size)

    def _parse_response(
        self,
        resp: httpx.Response,
        *,
        path: str,
        latency_ms: float,
        batch_size: int,
    ) -> NDArray[np.float32]:
        logger.debug(
            "hosted response path=%s status=%d batch_size=%d latency_ms=%.1f provider=%s",
            path,
            resp.status_code,
            batch_size,
            latency_ms,
            self._provider,
        )
        if resp.status_code == 200:
            try:
                body = resp.json()
            except ValueError as exc:
                raise InvalidVectorError("hosted embed returned malformed JSON") from exc
            return self._parse_body(body)
        self._raise_http_error(resp)

    def _parse_body(self, body: Any) -> NDArray[np.float32]:
        if self._provider == "openai":
            return parse_openai_embed_response(body)
        return parse_cohere_embed_response(body)

    def _raise_http_error(self, resp: httpx.Response) -> NoReturn:
        status = resp.status_code
        if status in (400, 413, 422):
            raise BackendRejectedError(f"hosted validation error ({status})")
        if status in (401, 403):
            raise BackendUnavailableError(
                f"hosted auth rejected ({status})",
                retryable=False,
            )
        retry_after = resp.headers.get("Retry-After")
        raise BackendUnavailableError(
            _unavailable_message(status, retry_after or "unknown"),
            retryable=status in _RETRYABLE_STATUS,
            retry_after_seconds=_retry_after_seconds_for_status(status, retry_after),
        )


def _retry_after_seconds_for_status(status: int, retry_after: str | None) -> float | None:
    if status != 429:
        return None
    return _parse_retry_after_seconds(retry_after)


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, BackendTimeoutError):
        return True
    return isinstance(exc, BackendUnavailableError) and exc.retryable


def _unavailable_message(status: int, retry_after: str) -> str:
    if status == 429:
        return f"hosted rate limited (429); Retry-After={retry_after!r}"
    if status in (502, 503):
        return f"hosted gateway/service unavailable ({status})"
    return f"hosted unexpected status {status}"
