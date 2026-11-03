"""Unit tests for the TEI reranker client (phase 5.A.3)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from httpx import Response

from app.clients.rerank import (
    RerankClient,
    RerankClientConfig,
    RerankInvalidResponseError,
    RerankRejectedError,
    RerankTimeoutError,
    RerankUnavailableError,
)

_BASE = "https://reranker.test"
_URL = f"{_BASE}/rerank"


def _client(*, max_retries: int = 0, read_timeout: float = 0.15) -> RerankClient:
    return RerankClient(
        _BASE,
        "test-token",
        config=RerankClientConfig(
            connect_timeout=0.05,
            read_timeout=read_timeout,
            max_retries=max_retries,
        ),
    )


@pytest.mark.asyncio
@respx.mock
async def test_scores_are_mapped_back_to_input_order() -> None:
    # TEI returns entries sorted by score; the index is what binds a score to a text.
    respx.post(_URL).mock(
        return_value=Response(
            200,
            json=[
                {"index": 2, "score": 0.91},
                {"index": 0, "score": 0.42},
                {"index": 1, "score": 0.07},
            ],
        )
    )
    client = _client()

    scores = await client.rerank("dark mode", ["a", "b", "c"])

    assert scores == pytest.approx([0.42, 0.07, 0.91])
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_request_asks_for_normalized_scores_and_sends_the_token() -> None:
    route = respx.post(_URL).mock(
        return_value=Response(200, json=[{"index": 0, "score": 0.5}])
    )
    client = _client()

    await client.rerank("query", ["document"])

    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer test-token"
    body = request.read().decode()
    assert '"raw_scores":false' in body
    assert "test-token" not in repr(client)
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_validation_errors_do_not_reach_the_network() -> None:
    route = respx.post(_URL).mock(return_value=Response(200, json=[]))
    client = _client()

    with pytest.raises(RerankRejectedError, match="query"):
        await client.rerank("   ", ["document"])
    with pytest.raises(RerankRejectedError, match="documents"):
        await client.rerank("query", [])
    with pytest.raises(RerankRejectedError, match="documents\\[0\\]"):
        await client.rerank("query", [""])

    assert route.calls.call_count == 0
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_oversized_batch_is_rejected_locally() -> None:
    route = respx.post(_URL).mock(return_value=Response(200, json=[]))
    client = _client()

    with pytest.raises(RerankRejectedError, match="exceeds max"):
        await client.rerank("query", ["document"] * 65)

    assert route.calls.call_count == 0
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_client_errors_are_rejected_without_retry() -> None:
    route = respx.post(_URL).mock(return_value=Response(422, json={"detail": "bad"}))
    client = _client(max_retries=2)

    with pytest.raises(RerankRejectedError):
        await client.rerank("query", ["document"])

    assert route.calls.call_count == 1
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_service_unavailable_is_not_retried_by_default() -> None:
    route = respx.post(_URL).mock(return_value=Response(503))
    client = _client()

    with pytest.raises(RerankUnavailableError) as excinfo:
        await client.rerank("query", ["document"])

    assert excinfo.value.code == "rerank_unavailable"
    assert route.calls.call_count == 1
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_retry_recovers_when_an_operator_raises_the_budget() -> None:
    route = respx.post(_URL).mock(
        side_effect=[
            Response(503),
            Response(200, json=[{"index": 0, "score": 0.8}]),
        ]
    )
    client = _client(max_retries=1)

    assert await client.rerank("query", ["document"]) == pytest.approx([0.8])
    assert route.calls.call_count == 2
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_timeout_surfaces_as_a_timeout_error() -> None:
    respx.post(_URL).mock(side_effect=httpx.ReadTimeout("slow"))
    client = _client()

    with pytest.raises(RerankTimeoutError):
        await client.rerank("query", ["document"])

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_transport_error_surfaces_as_unavailable() -> None:
    respx.post(_URL).mock(side_effect=httpx.ConnectError("refused"))
    client = _client()

    with pytest.raises(RerankUnavailableError):
        await client.rerank("query", ["document"])

    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"detail": "not a list"},
        [{"index": 0, "score": 0.5}],
        [{"index": 0, "score": 0.5}, {"index": 0, "score": 0.6}],
        [{"index": 0, "score": 0.5}, {"index": 2, "score": 0.6}],
        [{"index": 0, "score": 0.5}, {"index": "1", "score": 0.6}],
        [{"index": 0, "score": 0.5}, {"index": 1, "score": "high"}],
        [{"index": 0, "score": 0.5}, {"index": 1, "score": True}],
    ],
    ids=[
        "object-body",
        "missing-score",
        "duplicate-index",
        "out-of-range-index",
        "string-index",
        "string-score",
        "bool-score",
    ],
)
@respx.mock
async def test_contract_violations_are_invalid_responses(payload: object) -> None:
    respx.post(_URL).mock(return_value=Response(200, json=payload))
    client = _client()

    with pytest.raises(RerankInvalidResponseError):
        await client.rerank("query", ["a", "b"])

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_malformed_json_is_an_invalid_response() -> None:
    respx.post(_URL).mock(return_value=Response(200, content=b"<html>"))
    client = _client()

    with pytest.raises(RerankInvalidResponseError):
        await client.rerank("query", ["document"])

    await client.aclose()


def test_empty_base_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="base_url"):
        RerankClient("   ")


def test_bearer_repr_never_contains_the_token() -> None:
    from app.clients._http import RedactedBearerAuth

    assert repr(RedactedBearerAuth("super-secret")) == "RedactedBearerAuth()"
    assert "super-secret" not in repr(RerankClient(_BASE, "super-secret"))


@pytest.mark.asyncio
@respx.mock
async def test_oversized_query_is_rejected_locally() -> None:
    route = respx.post(_URL).mock(return_value=Response(200, json=[]))
    client = _client()

    with pytest.raises(RerankRejectedError, match="query exceeds"):
        await client.rerank("x" * 9000, ["document"])

    assert route.calls.call_count == 0
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_oversized_document_is_rejected_locally() -> None:
    route = respx.post(_URL).mock(return_value=Response(200, json=[]))
    client = _client()

    with pytest.raises(RerankRejectedError, match=r"documents\[0\] exceeds"):
        await client.rerank("query", ["x" * 33_000])

    assert route.calls.call_count == 0
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_auth_rejection_is_unavailable_and_not_retried() -> None:
    route = respx.post(_URL).mock(return_value=Response(401))
    client = _client(max_retries=2)

    with pytest.raises(RerankUnavailableError) as excinfo:
        await client.rerank("query", ["document"])

    assert excinfo.value.retryable is False
    assert route.calls.call_count == 1
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_retry_after_is_capped_for_the_caller() -> None:
    respx.post(_URL).mock(return_value=Response(503, headers={"Retry-After": "120"}))
    client = _client()

    with pytest.raises(RerankUnavailableError) as excinfo:
        await client.rerank("query", ["document"])

    assert excinfo.value.retry_after_seconds == pytest.approx(0.5)
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_non_numeric_retry_after_is_ignored() -> None:
    respx.post(_URL).mock(return_value=Response(503, headers={"Retry-After": "soon"}))
    client = _client()

    with pytest.raises(RerankUnavailableError) as excinfo:
        await client.rerank("query", ["document"])

    assert excinfo.value.retry_after_seconds is None
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_non_finite_score_is_an_invalid_response() -> None:
    # JSON has no inf literal; a server can still emit the non-standard token.
    respx.post(_URL).mock(
        return_value=Response(200, content=b'[{"index": 0, "score": Infinity}]')
    )
    client = _client()

    with pytest.raises(RerankInvalidResponseError):
        await client.rerank("query", ["document"])

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_non_object_entry_is_an_invalid_response() -> None:
    respx.post(_URL).mock(return_value=Response(200, json=[1, 2]))
    client = _client()

    with pytest.raises(RerankInvalidResponseError, match="entry"):
        await client.rerank("query", ["a", "b"])

    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("score", [-0.01, 1.01, 42.0], ids=["below-zero", "above-one", "unnormalized"])
@respx.mock
async def test_scores_outside_the_normalized_range_are_rejected(score: float) -> None:
    respx.post(_URL).mock(return_value=Response(200, json=[{"index": 0, "score": score}]))
    client = _client()

    with pytest.raises(RerankInvalidResponseError, match="normalized range"):
        await client.rerank("query", ["document"])

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_an_integer_too_large_for_a_float_is_an_invalid_response() -> None:
    # A 400-digit integer literal parses as a Python int, and float() overflows it.
    huge = b"1" + b"0" * 400
    respx.post(_URL).mock(
        return_value=Response(200, content=b'[{"index": 0, "score": ' + huge + b"}]")
    )
    client = _client()

    with pytest.raises(RerankInvalidResponseError):
        await client.rerank("query", ["document"])

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_retry_honors_retry_after_when_the_operator_enables_retries() -> None:
    route = respx.post(_URL).mock(
        side_effect=[
            Response(429, headers={"Retry-After": "1"}),
            Response(200, json=[{"index": 0, "score": 0.5}]),
        ]
    )
    client = _client(max_retries=1)

    with patch("app.clients.rerank.asyncio.sleep", AsyncMock()) as sleep:
        await client.rerank("query", ["document"])

    assert route.calls.call_count == 2
    assert sleep.await_args.args[0] == pytest.approx(0.5)
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_rerank_splits_the_window_at_the_client_batch_size() -> None:
    """TEI rejects a request above ``--max-client-batch-size`` (default 32) with 413.

    The candidate window is 50, so a single POST can never succeed against a stock
    server; the client must split and reassemble the scores in input order.
    """
    seen_sizes: list[int] = []

    def handler(request: httpx.Request) -> Response:
        body = json.loads(request.content)
        texts = body["texts"]
        seen_sizes.append(len(texts))
        if len(texts) > 32:
            return Response(413, json={"error": "batch size exceeded"})
        return Response(
            200,
            json=[{"index": index, "score": index / 100} for index in range(len(texts))],
        )

    respx.post(_URL).mock(side_effect=handler)
    client = RerankClient(
        _BASE,
        "test-token",
        config=RerankClientConfig(connect_timeout=0.05, read_timeout=0.15, client_batch_size=32),
    )

    scores = await client.rerank("query", [f"doc-{index}" for index in range(50)])

    assert seen_sizes == [32, 18]
    assert len(scores) == 50
    assert scores[0] == pytest.approx(0.0)
    assert scores[31] == pytest.approx(0.31)
    # The second batch restarts its indexes at 0, so these must be offset back.
    assert scores[32] == pytest.approx(0.0)
    assert scores[49] == pytest.approx(0.17)
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_rerank_never_returns_partial_scores_when_one_batch_fails() -> None:
    """A half-scored window would rank rows against scores that never arrived."""
    responses = [
        Response(200, json=[{"index": index, "score": 0.5} for index in range(32)]),
        Response(503, json={"error": "unavailable"}),
    ]
    respx.post(_URL).mock(side_effect=responses)
    client = RerankClient(
        _BASE,
        "test-token",
        config=RerankClientConfig(connect_timeout=0.05, read_timeout=0.15, client_batch_size=32),
    )

    with pytest.raises(RerankUnavailableError):
        await client.rerank("query", [f"doc-{index}" for index in range(50)])

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_rerank_sends_one_request_when_the_window_fits_the_batch() -> None:
    route = respx.post(_URL).mock(
        return_value=Response(
            200, json=[{"index": index, "score": 0.5} for index in range(3)]
        )
    )
    client = _client()

    await client.rerank("query", ["a", "b", "c"])

    assert len(route.calls) == 1
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_a_failed_batch_cancels_the_requests_still_in_flight() -> None:
    """The window is all-or-nothing, so a doomed stage must stop paying for it.

    Without cancellation the stage waits for the slowest sibling before it can
    degrade, which spends the whole latency budget on scores that are discarded.
    """
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def handler(request: httpx.Request) -> Response:
        if len(json.loads(request.content)["texts"]) == 32:
            # Let the sibling start first so the cancellation is observable.
            await asyncio.sleep(0.02)
            return Response(413, json={"error": "batch size exceeded"})
        started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    respx.post(_URL).mock(side_effect=handler)
    client = RerankClient(
        _BASE,
        "test-token",
        config=RerankClientConfig(connect_timeout=0.05, read_timeout=5.0),
    )

    # The timeout lives outside the `pytest.raises` block so the block holds exactly
    # one invocation that can raise the expected error.
    async with asyncio.timeout(2.0):
        with pytest.raises(RerankRejectedError):
            await client.rerank("query", [f"doc-{index}" for index in range(50)])

    assert started.is_set()
    assert cancelled.is_set()
    await client.aclose()
