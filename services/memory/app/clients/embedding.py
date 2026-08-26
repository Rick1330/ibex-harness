"""HTTP client for the embedder service ``POST /v1/embed``.

Retries only 429/502/503 + transport/timeout (mirrors embedder TEI/hosted clients).
Never logs texts, vectors, or the Bearer token.
"""

from __future__ import annotations

import asyncio
import logging
import math
import secrets
import time
from collections.abc import Generator, Sequence
from dataclasses import dataclass
from typing import Any, NoReturn
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS: frozenset[int] = frozenset({429, 502, 503})
_BACKOFF_BASE_SECONDS = 0.25
_BACKOFF_MAX_SECONDS = 8.0
_EMBED_PATH = "/v1/embed"
_EXPECTED_DIM = 1024
_MAX_BATCH_TEXTS = 64
_MAX_TEXT_BYTES = 32 * 1024


class EmbeddingClientError(Exception):
    """Base error for embedder HTTP client failures."""

    def __init__(self, message: str, *, code: str = "embedding_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class EmbeddingTimeoutError(EmbeddingClientError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="embedding_timeout")


class EmbeddingUnavailableError(EmbeddingClientError):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message, code="embedding_unavailable")
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class EmbeddingRejectedError(EmbeddingClientError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="embedding_rejected")


class EmbeddingInvalidResponseError(EmbeddingClientError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="embedding_invalid_response")


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
class EmbeddingResult:
    vectors: list[list[float]]
    model_id: str
    dimensions: int
    backend: str


@dataclass(frozen=True, slots=True)
class EmbeddingClientConfig:
    connect_timeout: float = 2.0
    read_timeout: float = 30.0
    max_retries: int = 2


def _jittered_backoff(attempt: int) -> float:
    cap = min(_BACKOFF_BASE_SECONDS * (2**attempt), _BACKOFF_MAX_SECONDS)
    return (secrets.randbelow(1_000_000) / 1_000_000) * cap


def _parse_retry_after_seconds(raw: str | None) -> float | None:
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped.isdigit():
        return None
    return min(_BACKOFF_MAX_SECONDS, float(int(stripped)))


def _retry_delay_seconds(attempt: int, retry_after_seconds: float | None) -> float:
    delay = _jittered_backoff(attempt)
    if retry_after_seconds is None:
        return delay
    return min(_BACKOFF_MAX_SECONDS, max(delay, retry_after_seconds))


class EmbeddingClient:
    """Long-lived async client for ``services/embedder`` ``POST /v1/embed``."""

    def __init__(
        self,
        base_url: str,
        api_token: str,
        *,
        config: EmbeddingClientConfig | None = None,
    ) -> None:
        if not base_url.strip():
            msg = "EmbeddingClient: base_url must not be empty"
            raise ValueError(msg)
        token = api_token.strip()
        if not token:
            msg = "EmbeddingClient: api_token must not be empty"
            raise ValueError(msg)
        cfg = config or EmbeddingClientConfig()
        self._max_retries = max(0, cfg.max_retries)
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Accept": "application/json"},
            auth=_RedactedBearerAuth(token),
            timeout=httpx.Timeout(cfg.read_timeout, connect=cfg.connect_timeout),
            follow_redirects=False,
        )

    def __repr__(self) -> str:
        return f"EmbeddingClient(max_retries={self._max_retries})"

    async def aclose(self) -> None:
        await self._client.aclose()

    async def embed(self, texts: Sequence[str], *, org_id: UUID) -> EmbeddingResult:
        _validate_texts(texts)
        payload = {"texts": list(texts), "org_id": str(org_id)}
        return await self._post_with_retry(payload, batch_size=len(texts))

    async def _post_with_retry(
        self, payload: dict[str, Any], *, batch_size: int
    ) -> EmbeddingResult:
        last_exc: Exception = EmbeddingUnavailableError(
            f"embedder {_EMBED_PATH}: no attempts made"
        )
        for attempt in range(self._max_retries + 1):
            try:
                return await self._attempt_post(payload, batch_size=batch_size)
            except (EmbeddingRejectedError, EmbeddingInvalidResponseError):
                raise
            except (EmbeddingUnavailableError, EmbeddingTimeoutError) as exc:
                last_exc = exc
                await self._maybe_schedule_retry(attempt, exc)
        raise last_exc

    async def _maybe_schedule_retry(
        self,
        attempt: int,
        exc: EmbeddingUnavailableError | EmbeddingTimeoutError,
    ) -> None:
        if isinstance(exc, EmbeddingUnavailableError) and not exc.retryable:
            raise exc
        if attempt >= self._max_retries:
            raise exc
        retry_after = (
            exc.retry_after_seconds if isinstance(exc, EmbeddingUnavailableError) else None
        )
        delay = _retry_delay_seconds(attempt, retry_after)
        logger.warning(
            "embedder %s transient error; retrying attempt=%d/%d delay_ms=%.0f error_class=%s",
            _EMBED_PATH,
            attempt + 1,
            self._max_retries + 1,
            delay * 1000,
            type(exc).__name__,
        )
        await asyncio.sleep(delay)

    async def _attempt_post(
        self, payload: dict[str, Any], *, batch_size: int
    ) -> EmbeddingResult:
        t0 = time.monotonic()
        try:
            resp = await self._client.post(_EMBED_PATH, json=payload)
        except httpx.TimeoutException as exc:
            raise EmbeddingTimeoutError(f"embedder {_EMBED_PATH} timed out") from exc
        except httpx.TransportError as exc:
            raise EmbeddingUnavailableError(
                f"embedder {_EMBED_PATH} connection error: {type(exc).__name__}",
                retryable=True,
            ) from exc

        latency_ms = (time.monotonic() - t0) * 1000
        logger.debug(
            "embedder response status=%d batch_size=%d latency_ms=%.1f",
            resp.status_code,
            batch_size,
            latency_ms,
        )
        if resp.status_code == 200:
            return _parse_success(resp)
        _raise_http_error(resp)


def _validate_one_text(i: int, item: object) -> None:
    if not isinstance(item, str):
        raise EmbeddingRejectedError(f"texts[{i}] must be a string")
    if len(item.encode("utf-8")) > _MAX_TEXT_BYTES:
        raise EmbeddingRejectedError(f"texts[{i}] exceeds {_MAX_TEXT_BYTES} bytes")


def _validate_texts(texts: Sequence[str]) -> None:
    if not texts:
        raise EmbeddingRejectedError("texts must be non-empty")
    if len(texts) > _MAX_BATCH_TEXTS:
        raise EmbeddingRejectedError(
            f"texts batch size {len(texts)} exceeds max {_MAX_BATCH_TEXTS}"
        )
    for i, item in enumerate(texts):
        _validate_one_text(i, item)


def _require_nonempty_str(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise EmbeddingInvalidResponseError(f"embedder response missing {field}")
    return value


def _require_dimensions(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise EmbeddingInvalidResponseError(
            f"embedder dimensions must be {_EXPECTED_DIM}, got {value!r}"
        )
    if value != _EXPECTED_DIM:
        raise EmbeddingInvalidResponseError(
            f"embedder dimensions must be {_EXPECTED_DIM}, got {value!r}"
        )
    return value


def _as_finite_float(value: object, *, vector_idx: int, component_idx: int) -> float:
    # bool is a subclass of int — reject explicitly.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EmbeddingInvalidResponseError(
            f"vector[{vector_idx}][{component_idx}] must be a finite number"
        )
    number = float(value)
    if not math.isfinite(number):
        raise EmbeddingInvalidResponseError(
            f"vector[{vector_idx}][{component_idx}] must be a finite number"
        )
    return number


def _parse_vector_row(row: object, *, idx: int) -> list[float]:
    if not isinstance(row, list) or len(row) != _EXPECTED_DIM:
        raise EmbeddingInvalidResponseError(f"vector[{idx}] length must be {_EXPECTED_DIM}")
    return [
        _as_finite_float(component, vector_idx=idx, component_idx=comp_i)
        for comp_i, component in enumerate(row)
    ]


def _parse_embed_body(body: dict[str, Any]) -> EmbeddingResult:
    vectors = body.get("vectors")
    if not isinstance(vectors, list) or not vectors:
        raise EmbeddingInvalidResponseError("embedder response missing vectors")
    model_id = _require_nonempty_str(body.get("model_id"), field="model_id")
    dimensions = _require_dimensions(body.get("dimensions"))
    backend = _require_nonempty_str(body.get("backend"), field="backend")
    return EmbeddingResult(
        vectors=[_parse_vector_row(row, idx=idx) for idx, row in enumerate(vectors)],
        model_id=model_id,
        dimensions=dimensions,
        backend=backend,
    )


def _parse_success(resp: httpx.Response) -> EmbeddingResult:
    try:
        body = resp.json()
    except ValueError as exc:
        raise EmbeddingInvalidResponseError("embedder returned malformed JSON") from exc
    if not isinstance(body, dict):
        raise EmbeddingInvalidResponseError("embedder response must be a JSON object")
    return _parse_embed_body(body)


def _raise_http_error(resp: httpx.Response) -> NoReturn:
    status = resp.status_code
    if status in (400, 413, 422):
        raise EmbeddingRejectedError(f"embedder validation error ({status})")
    if status in (401, 403):
        raise EmbeddingUnavailableError(
            f"embedder auth rejected ({status})",
            retryable=False,
        )
    retry_after = resp.headers.get("Retry-After")
    raise EmbeddingUnavailableError(
        _unavailable_message(status, retry_after or "unknown"),
        retryable=status in _RETRYABLE_STATUS,
        retry_after_seconds=_retry_after_for_status(status, retry_after),
    )


def _retry_after_for_status(status: int, retry_after: str | None) -> float | None:
    if status != 429:
        return None
    return _parse_retry_after_seconds(retry_after)


def _unavailable_message(status: int, retry_after: str) -> str:
    if status == 429:
        return f"embedder rate limited (429); Retry-After={retry_after!r}"
    if status in (502, 503):
        return f"embedder gateway/service unavailable ({status})"
    return f"embedder unexpected status {status}"
