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
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, NoReturn

import httpx

from app.clients._http import RedactedBearerAuth, jittered_backoff, retry_after_seconds

logger = logging.getLogger(__name__)

_RERANK_PATH = "/rerank"
_MAX_DOCUMENTS = 64
_MAX_QUERY_BYTES = 8 * 1024
_MAX_DOCUMENT_BYTES = 32 * 1024
_RETRYABLE_STATUS: frozenset[int] = frozenset({429, 502, 503})
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
    # TEI rejects a request larger than its ``--max-client-batch-size`` (default 32)
    # with 413, and the read path treats a rejection as "degrade to the fused order".
    # Splitting keeps the candidate window independent of the server's setting: a
    # 50-candidate window against a stock server used to rerank nothing at all.
    client_batch_size: int = 32


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
        self._batch_size = max(1, cfg.client_batch_size)
        token = (api_token or "").strip()
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Accept": "application/json"},
            auth=RedactedBearerAuth(token) if token else None,
            timeout=httpx.Timeout(cfg.read_timeout, connect=cfg.connect_timeout),
            follow_redirects=False,
        )

    def __repr__(self) -> str:
        return f"RerankClient(max_retries={self._max_retries})"

    async def aclose(self) -> None:
        await self._client.aclose()

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        """Score ``documents`` against ``query``, returning scores in input order.

        A window larger than ``client_batch_size`` is split across concurrent
        requests, because a stock TEI server returns 413 above its own limit. All
        batches must succeed: a partially scored window would rank rows against
        scores that never arrived, so the first failure cancels the requests still
        in flight and propagates, and the caller degrades to the fused order as
        usual.
        """
        _validate_request(query, documents)
        batches = _split_batches(documents, self._batch_size)
        if len(batches) == 1:
            payload = _payload(query, batches[0])
            return await self._post_with_retries(payload, expected=len(batches[0]))
        tasks = [
            asyncio.create_task(
                self._post_with_retries(_payload(query, batch), expected=len(batch))
            )
            for batch in batches
        ]
        try:
            # ``gather`` without ``return_exceptions`` surfaces the first failure
            # immediately instead of waiting for every sibling to settle.
            batches_scores = await asyncio.gather(*tasks)
        except BaseException:
            # The window is all-or-nothing, so a doomed stage must stop paying for
            # inference whose scores will be discarded. Gathering the cancelled
            # tasks also consumes their exceptions, which would otherwise be
            # reported as "never retrieved".
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        scores: list[float] = []
        for batch_scores in batches_scores:
            scores.extend(batch_scores)
        return scores

    async def _post_with_retries(self, payload: dict[str, Any], *, expected: int) -> list[float]:
        for attempt in range(self._max_retries + 1):
            try:
                return await self._attempt_post(payload, expected=expected)
            except (RerankRejectedError, RerankInvalidResponseError):
                raise
            except (RerankUnavailableError, RerankTimeoutError) as exc:
                if not self._may_retry(exc, attempt=attempt):
                    raise
                await asyncio.sleep(_retry_delay(exc, attempt=attempt))
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


def _retry_delay(exc: RerankUnavailableError | RerankTimeoutError, *, attempt: int) -> float:
    """Short backoff, raised to the server's ``Retry-After`` when it asked for one."""
    delay = jittered_backoff(attempt, base_seconds=0.05, max_seconds=_BACKOFF_MAX_SECONDS)
    requested = exc.retry_after_seconds if isinstance(exc, RerankUnavailableError) else None
    if requested is None:
        return delay
    return min(_BACKOFF_MAX_SECONDS, max(delay, requested))


def _payload(query: str, documents: Sequence[str]) -> dict[str, Any]:
    return {"query": query, "texts": list(documents), "raw_scores": False}


def _split_batches(
    documents: Sequence[str], batch_size: int
) -> list[Sequence[str]]:
    """Consecutive slices of at most ``batch_size``; order is preserved."""
    return [
        documents[start : start + batch_size]
        for start in range(0, len(documents), batch_size)
    ]


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
    _require_number(value, index=index)
    score = _to_float(value, index=index)
    _require_finite(score, index=index)
    # ``raw_scores=false`` promises a normalized score; anything else means the
    # server ignored the flag and the value cannot be a composite relevance.
    _require_normalized(score, index=index)
    return score


def _require_number(value: object, *, index: int) -> None:
    # bool is a subclass of int — reject explicitly.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RerankInvalidResponseError(f"score for index {index} must be a number")


def _to_float(value: object, *, index: int) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except OverflowError as exc:  # an integer literal too large for a float
        raise RerankInvalidResponseError(
            f"score for index {index} is not a representable number"
        ) from exc


def _require_finite(score: float, *, index: int) -> None:
    if not math.isfinite(score):
        raise RerankInvalidResponseError(f"score for index {index} must be finite")


def _require_normalized(score: float, *, index: int) -> None:
    if score < 0.0 or score > 1.0:
        raise RerankInvalidResponseError(
            f"score for index {index} is outside the normalized range [0, 1]"
        )


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
        retry_after_seconds=retry_after_seconds(
            resp.headers.get("Retry-After"), max_seconds=_BACKOFF_MAX_SECONDS
        ),
    )
