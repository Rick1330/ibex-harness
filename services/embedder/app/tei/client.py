"""Async HTTP client for the TEI (Text Embeddings Inference) sidecar.

Design constraints (enforced, not aspirational):
  - One long-lived AsyncClient per TeiClient instance (connection pool reuse).
  - Retries: jittered exponential backoff, only for transient errors (429/502/503/network).
  - 4xx validation errors (413/422/424) are never retried — they are caller bugs.
  - Timeout errors ARE retried up to max_retries; BackendTimeoutError on exhaustion.
  - Logging: only status, error_class, batch_size, latency_ms — NEVER text or vectors.
  - truncate is always False; normalize is always True (defense-in-depth, not trust).
  - api_key is accepted as a plain str (caller strips SecretStr); never logged.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any, NoReturn

import httpx
import numpy as np
from numpy.typing import NDArray

from app.errors import (
    BackendRejectedError,
    BackendTimeoutError,
    BackendUnavailableError,
    InvalidVectorError,
)
from app.tei.protocol import parse_info_response, parse_native_embed_response

logger = logging.getLogger(__name__)

# Transient HTTP status codes that merit a retry.
_RETRYABLE_STATUS: frozenset[int] = frozenset({429, 502, 503})

# Jitter parameters: delay = base * 2^attempt ± uniform(0, base).
_BACKOFF_BASE_SECONDS = 0.25
_BACKOFF_MAX_SECONDS = 8.0


@dataclass(frozen=True, slots=True)
class TeiClientConfig:
    connect_timeout: float = 2.0
    read_timeout: float = 30.0
    api_key: str | None = None
    max_retries: int = 2


def _jittered_backoff(attempt: int) -> float:
    """Return backoff duration for the given (0-indexed) attempt.

    Uses full jitter strategy: delay ∈ [0, cap] where cap doubles per attempt,
    bounded at _BACKOFF_MAX_SECONDS. This avoids thundering herd on shared TEI.
    """
    cap = min(_BACKOFF_BASE_SECONDS * (2**attempt), _BACKOFF_MAX_SECONDS)
    # secrets.randbelow is CSPRNG; used only for retry jitter, not tokens.
    return (secrets.randbelow(1_000_000) / 1_000_000) * cap


class TeiClient:
    """Long-lived async HTTP client for a single TEI instance.

    Concurrent embed calls are safe: httpx.AsyncClient uses an internal
    connection pool and its request methods are coroutine-safe.

    Lifecycle: construct at startup, call aclose() on shutdown.
    """

    def __init__(
        self,
        base_url: str,
        *,
        config: TeiClientConfig | None = None,
    ) -> None:
        client_config = config or TeiClientConfig()
        if not base_url or not base_url.strip():
            raise ValueError("TeiClient: base_url must not be empty")
        self._base_url = base_url.rstrip("/")
        self._max_retries = max(0, client_config.max_retries)

        default_headers: dict[str, str] = {"Accept": "application/json"}
        if client_config.api_key:
            # api_key is already a plain str extracted from SecretStr by the factory;
            # we never store or log it beyond constructing the header.
            default_headers["Authorization"] = f"Bearer {client_config.api_key}"

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=default_headers,
            timeout=httpx.Timeout(
                client_config.read_timeout,
                connect=client_config.connect_timeout,
            ),
        )

    async def aclose(self) -> None:
        """Release the underlying connection pool. Safe to call multiple times."""
        await self._client.aclose()

    # ------------------------------------------------------------------ #
    # Probe methods                                                         #
    # ------------------------------------------------------------------ #

    async def health(self, timeout_seconds: float | None = None) -> bool:
        """Return True if TEI /health responds 200, False on any error."""
        try:
            resp = await self._client.get(
                "/health",
                timeout=None if timeout_seconds is None else timeout_seconds,
            )
            return resp.status_code == 200
        except (httpx.TimeoutException, httpx.TransportError):
            return False

    async def info(self) -> dict[str, Any]:
        """Fetch GET /info and return the parsed JSON dict.

        Raises BackendTimeoutError or BackendUnavailableError on failure.
        Caller treats /info as mandatory for gpu readiness (see main.py).
        """
        try:
            resp = await self._client.get("/info")
        except httpx.TimeoutException as exc:
            raise BackendTimeoutError("TEI /info request timed out") from exc
        except httpx.TransportError as exc:
            raise BackendUnavailableError(f"TEI /info request failed: {exc}") from exc
        if resp.status_code != 200:
            raise BackendUnavailableError(
                f"TEI /info returned unexpected status {resp.status_code}"
            )
        return resp.json()  # type: ignore[return-value]

    def model_id_from_info(self, info: dict[str, Any]) -> str | None:
        """Extract model_id from a /info response dict. Returns None if absent."""
        return parse_info_response(info)

    # ------------------------------------------------------------------ #
    # Embed                                                                 #
    # ------------------------------------------------------------------ #

    async def embed(self, texts: list[str]) -> NDArray[np.float32]:
        """POST /embed (native TEI format); retries on transient errors.

        Key invariants:
          - truncate is always False (truncation silently mutates vectors).
          - normalize is always True (defense-in-depth for L2 property).
          - Never logs text content or returned vectors.
        """
        payload: dict[str, Any] = {
            "inputs": texts,
            "normalize": True,
            "truncate": False,
        }
        return await self._post_with_retry("/embed", payload, batch_size=len(texts))

    # ------------------------------------------------------------------ #
    # Internal helpers                                                      #
    # ------------------------------------------------------------------ #

    async def _post_with_retry(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        batch_size: int,
    ) -> NDArray[np.float32]:
        """Execute a POST with retry on transient errors.

        Retry policy:
          - Total attempts = max_retries + 1.
          - Retryable: BackendTimeoutError and BackendUnavailableError(retryable=True)
            (429/502/503 and transport errors).
          - Not retryable: BackendRejectedError, InvalidVectorError, and
            non-retryable BackendUnavailableError (400/401/403/404/500 and other).
          - Backoff: full-jitter exponential, bounded at _BACKOFF_MAX_SECONDS.
        """
        last_exc: Exception = BackendUnavailableError(f"TEI {path}: no attempts made")

        for attempt in range(self._max_retries + 1):
            try:
                return await self._attempt_post(path, payload, batch_size=batch_size)
            except (BackendRejectedError, InvalidVectorError):
                raise
            except (BackendUnavailableError, BackendTimeoutError) as exc:
                if not _is_retryable_tei_error(exc):
                    raise
                last_exc = exc
                if attempt < self._max_retries:
                    await self._log_and_sleep_retry(path, attempt, exc)

        raise last_exc

    async def _attempt_post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        batch_size: int,
    ) -> NDArray[np.float32]:
        """Make one HTTP POST and return the parsed NDArray, or raise on error."""
        t0 = time.monotonic()
        try:
            resp = await self._client.post(path, json=payload)
        except httpx.TimeoutException as exc:
            raise BackendTimeoutError(f"TEI {path} timed out") from exc
        except httpx.TransportError as exc:
            raise BackendUnavailableError(
                f"TEI {path} connection error: {exc}",
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
            "TEI response path=%s status=%d batch_size=%d latency_ms=%.1f",
            path,
            resp.status_code,
            batch_size,
            latency_ms,
        )
        if resp.status_code == 200:
            try:
                body = resp.json()
            except ValueError as exc:
                raise InvalidVectorError("TEI /embed returned malformed JSON") from exc
            return parse_native_embed_response(body)
        self._raise_tei_http_error(resp)

    def _raise_tei_http_error(self, resp: httpx.Response) -> NoReturn:
        status = resp.status_code
        excerpt = resp.text[:200]
        if status in (413, 422, 424):
            raise BackendRejectedError(_rejected_message(status, excerpt))
        retry_after = resp.headers.get("Retry-After", "unknown")
        raise BackendUnavailableError(
            _unavailable_message(status, excerpt, retry_after),
            retryable=status in _RETRYABLE_STATUS,
        )

    async def _log_and_sleep_retry(
        self, path: str, attempt: int, exc: Exception
    ) -> None:
        delay = _jittered_backoff(attempt)
        logger.warning(
            "TEI %s transient error; retrying attempt=%d/%d delay_ms=%.0f error_class=%s",
            path,
            attempt + 1,
            self._max_retries + 1,
            delay * 1000,
            type(exc).__name__,
        )
        await asyncio.sleep(delay)


def _is_retryable_tei_error(exc: Exception) -> bool:
    if isinstance(exc, BackendTimeoutError):
        return True
    return isinstance(exc, BackendUnavailableError) and exc.retryable


def _rejected_message(status: int, excerpt: str) -> str:
    if status == 413:
        return f"TEI payload too large (413): {excerpt}"
    if status == 422:
        return f"TEI validation error (422): {excerpt}"
    return (
        f"TEI model dependency failed (424) — check IBEX_EMBEDDING_TEI_BASE_URL "
        f"points to the correct model: {excerpt}"
    )


def _unavailable_message(status: int, excerpt: str, retry_after: str) -> str:
    if status == 429:
        return f"TEI rate limited (429); Retry-After={retry_after!r}"
    if status in (502, 503):
        return f"TEI gateway/service unavailable ({status})"
    return f"TEI unexpected status {status}: {excerpt}"
