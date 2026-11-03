"""HTTP client for a Text Embeddings Inference (TEI) reranker ``POST /rerank``.

The reranker is a cross-encoder: it scores each ``(query, document)`` pair jointly,
which a bi-encoder cannot do. It sits after fusion and before composite scoring, so
it is on the read hot path: the client defaults to **no retries** and a tight read
timeout, and every failure is a degrade to the fused order rather than an error.

TEI returns ``[{"index": int, "score": float}]`` with ``raw_scores=false``, i.e. a
normalized score in ``[0, 1]`` that is directly usable as a composite relevance.

Never logs document text, the query, or the bearer token.
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

import httpx

logger = logging.getLogger(__name__)

_RERANK_PATH = "/rerank"
_MAX_DOCUMENTS = 64
_MAX_QUERY_BYTES = 8 * 1024
_MAX_DOCUMENT_BYTES = 32 * 1024
_RETRYABLE_STATUS: frozenset[int] = frozenset({429, 502, 503})
_BACKOFF_BASE_SECONDS = 0.05
_BACKOFF_MAX_SECONDS = 0.5


class RerankClientError(Exception):
    """Base error for reranker HTTP client failures."""

    def __init__(self, message: str, *, code: str = "rerank_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class RerankTimeoutError(RerankClientError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="rerank_timeout")


class RerankUnavailableError(RerankClientError):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message, code="rerank_unavailable")
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class RerankRejectedError(RerankClientError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="rerank_rejected")


class RerankInvalidResponseError(RerankClientError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="rerank_invalid_response")


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
class RerankClientConfig:
    """Read-path defaults: one attempt inside the ranking sub-budget.

    A read request that reranks must still answer inside its latency budget, so a
    retry queue behind a slow reranker is worse than the degraded order. Operators
    who can afford one retry set ``IBEX_MEMORY_RERANK_MAX_RETRIES=1``.
    """

    connect_timeout: float = 0.05
    read_timeout: float = 0.15
    max_retries: int = 0


def _jittered_backoff(attempt: int) -> float:
    cap = min(_BACKOFF_BASE_SECONDS * (2**attempt), _BACKOFF_MAX_SECONDS)
    return (secrets.randbelow(1_000_000) / 1_000_000) * cap


class RerankClient:
    """Long-lived async client for a TEI ``POST /rerank`` endpoint."""

    def __init__(
        self,
        base_url: str,
        api_token: str | None = None,
        *,
        config: RerankClientConfig | None = None,
    ) -> None:
        if not base_url.strip():
            msg = "RerankClient: base_url must not be empty"
            raise ValueError(msg)
        cfg = config or RerankClientConfig()
        self._max_retries = max(0, cfg.max_retries)
        token = (api_token or "").strip()
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Accept": "application/json"},
            auth=_RedactedBearerAuth(token) if token else None,
            timeout=httpx.Timeout(cfg.read_timeout, connect=cfg.connect_timeout),
            follow_redirects=False,
        )

    def __repr__(self) -> str:
        return f"RerankClient(max_retries={self._max_retries})"

    async def aclose(self) -> None:
        await self._client.aclose()

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        """Score ``documents`` against ``query``, returning scores in input order."""
        _validate_request(query, documents)
        payload = {"query": query, "texts": list(documents), "raw_scores": False}
        return await self._post_with_retries(payload, expected=len(documents))

    async def _post_with_retries(self, payload: dict[str, Any], *, expected: int) -> list[float]:
        for attempt in range(self._max_retries + 1):
            try:
                return await self._attempt_post(payload, expected=expected)
            except (RerankRejectedError, RerankInvalidResponseError):
                raise
            except (RerankUnavailableError, RerankTimeoutError) as exc:
                if not self._may_retry(exc, attempt=attempt):
                    raise
                await asyncio.sleep(_jittered_backoff(attempt))
        msg = "reranker retry loop exhausted without a result"  # pragma: no cover
        raise RerankUnavailableError(msg)  # pragma: no cover

    def _may_retry(self, exc: RerankUnavailableError | RerankTimeoutError, *, attempt: int) -> bool:
        """One attempt inside the read budget by default; a non-retryable error never retries."""
        if isinstance(exc, RerankUnavailableError) and not exc.retryable:
            return False
        return attempt < self._max_retries

    async def _attempt_post(self, payload: dict[str, Any], *, expected: int) -> list[float]:
        t0 = time.monotonic()
        try:
            resp = await self._client.post(_RERANK_PATH, json=payload)
        except httpx.TimeoutException as exc:
            raise RerankTimeoutError(f"reranker {_RERANK_PATH} timed out") from exc
        except httpx.TransportError as exc:
            raise RerankUnavailableError(
                f"reranker {_RERANK_PATH} connection error: {type(exc).__name__}",
                retryable=True,
            ) from exc

        latency_ms = (time.monotonic() - t0) * 1000
        logger.debug(
            "reranker response status=%d documents=%d latency_ms=%.1f",
            resp.status_code,
            expected,
            latency_ms,
        )
        if resp.status_code == 200:
            return _parse_scores(resp, expected=expected)
        _raise_http_error(resp)


def _validate_request(query: str, documents: Sequence[str]) -> None:
    _validate_query(query)
    _validate_documents(documents)


def _validate_query(query: str) -> None:
    if not isinstance(query, str) or not query.strip():
        raise RerankRejectedError("query must be a non-empty string")
    if len(query.encode("utf-8")) > _MAX_QUERY_BYTES:
        raise RerankRejectedError(f"query exceeds {_MAX_QUERY_BYTES} bytes")


def _validate_documents(documents: Sequence[str]) -> None:
    if not documents:
        raise RerankRejectedError("documents must be non-empty")
    if len(documents) > _MAX_DOCUMENTS:
        raise RerankRejectedError(
            f"documents batch size {len(documents)} exceeds max {_MAX_DOCUMENTS}"
        )
    for i, document in enumerate(documents):
        _validate_document(i, document)


def _validate_document(index: int, document: str) -> None:
    if not isinstance(document, str) or not document:
        raise RerankRejectedError(f"documents[{index}] must be a non-empty string")
    if len(document.encode("utf-8")) > _MAX_DOCUMENT_BYTES:
        raise RerankRejectedError(f"documents[{index}] exceeds {_MAX_DOCUMENT_BYTES} bytes")


def _load_json_list(resp: httpx.Response) -> list[Any]:
    try:
        body = resp.json()
    except ValueError as exc:
        raise RerankInvalidResponseError("reranker returned malformed JSON") from exc
    if not isinstance(body, list):
        raise RerankInvalidResponseError("reranker response must be a JSON array")
    return body


def _as_finite_score(value: object, *, index: int) -> float:
    # bool is a subclass of int — reject explicitly.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RerankInvalidResponseError(f"score for index {index} must be a number")
    score = float(value)
    if not math.isfinite(score):
        raise RerankInvalidResponseError(f"score for index {index} must be finite")
    return score


def _parse_scores(resp: httpx.Response, *, expected: int) -> list[float]:
    """Map TEI's ``[{index, score}]`` onto the input order.

    TEI returns one entry per submitted document. Anything else — a missing index,
    a duplicate, an out-of-range index, or a short list — is a contract violation
    and degrades the request rather than silently mixing scores with documents.
    """
    body = _load_json_list(resp)
    if len(body) != expected:
        raise RerankInvalidResponseError(
            f"reranker returned {len(body)} scores for {expected} documents"
        )
    scores = [0.0] * expected
    seen: set[int] = set()
    for entry in body:
        index, score = _parse_entry(entry, expected=expected)
        if index in seen:
            raise RerankInvalidResponseError(f"reranker index {index} is duplicated")
        seen.add(index)
        scores[index] = score
    return scores


def _parse_entry(entry: object, *, expected: int) -> tuple[int, float]:
    if not isinstance(entry, dict):
        raise RerankInvalidResponseError("reranker entry must be a JSON object")
    index = _require_index(entry.get("index"), expected=expected)
    return index, _as_finite_score(entry.get("score"), index=index)


def _require_index(value: object, *, expected: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RerankInvalidResponseError("reranker entry missing integer index")
    if value < 0 or value >= expected:
        raise RerankInvalidResponseError(f"reranker index {value} is out of range")
    return value


def _raise_http_error(resp: httpx.Response) -> NoReturn:
    status = resp.status_code
    if status in (400, 413, 422):
        raise RerankRejectedError(f"reranker validation error ({status})")
    if status in (401, 403):
        raise RerankUnavailableError(f"reranker auth rejected ({status})", retryable=False)
    raise RerankUnavailableError(
        f"reranker unavailable ({status})",
        retryable=status in _RETRYABLE_STATUS,
        retry_after_seconds=_retry_after_seconds(resp.headers.get("Retry-After")),
    )


def _retry_after_seconds(raw: str | None) -> float | None:
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped.isdigit():
        return None
    return min(_BACKOFF_MAX_SECONDS, float(int(stripped)))
