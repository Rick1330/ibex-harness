"""Independent attack tests for the rerank client's TEI batch split (ADR-0093).

The change under test moves the TEI ``--max-client-batch-size`` split into the
client. The oracle used here is the contract, not the implementation:

* a window larger than ``client_batch_size`` is sent as consecutive slices;
* the returned list is ``len(documents)`` long and aligned to input order;
* one batch in the window means one request;
* any batch failure raises and no partial list is returned;
* the setting is read from ``Settings`` and reaches the client;
* the read path still degrades to the fused order on every client failure.

These tests deliberately do not reuse the author's helpers so a broken helper
cannot mask a regression.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import httpx
import pytest
import respx
from httpx import Response
from pydantic import ValidationError

from app.clients.rerank import (
    RerankClient,
    RerankClientConfig,
    RerankInvalidResponseError,
    RerankRejectedError,
    RerankTimeoutError,
)
from app.config import Settings
from app.read.metrics import RERANK
from app.vectorstore.base import SearchHit
from tests.unit.find_similar_support import make_hydrated_map, make_query, make_repo

_BASE = "https://reranker.test"
_URL = f"{_BASE}/rerank"


def _client(
    batch_size: int = 32, *, max_retries: int = 0, read_timeout: float = 0.15
) -> RerankClient:
    return RerankClient(
        _BASE,
        "test-token",
        config=RerankClientConfig(
            connect_timeout=0.05,
            read_timeout=read_timeout,
            max_retries=max_retries,
            client_batch_size=batch_size,
        ),
    )


def _texts(request: httpx.Request) -> list[str]:
    return json.loads(request.content)["texts"]


def _scores_for(texts: list[str]) -> Response:
    """Score each document by its global position encoded in ``doc-<n>``."""
    return Response(
        200,
        json=[
            {"index": index, "score": int(text.split("-")[1]) / 100}
            for index, text in enumerate(texts)
        ],
    )


def _degraded() -> float:
    return RERANK.labels(result="degraded")._value.get()


# ---------------------------------------------------------------------------
# Batching boundaries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_default_batch_size_splits_fifty_candidates_into_32_and_18() -> None:
    """Acceptance #1: the stock 50-candidate window must fit a stock TEI server."""
    requests: list[list[str]] = []

    def handler(request: httpx.Request) -> Response:
        texts = _texts(request)
        requests.append(texts)
        if len(texts) > 32:  # a stock TEI server's --max-client-batch-size
            return Response(413, json={"error": "batch size exceeded"})
        return _scores_for(texts)

    respx.post(_URL).mock(side_effect=handler)
    # No config argument: this must hold for ``RerankClientConfig()`` itself.
    client = RerankClient(_BASE, "test-token")

    scores = await client.rerank("query", [f"doc-{index}" for index in range(50)])

    assert sorted(len(batch) for batch in requests) == [18, 32]
    requests.sort(key=lambda batch: int(batch[0].split("-")[1]))
    assert [int(batch[0].split("-")[1]) for batch in requests] == [0, 32]
    assert scores == pytest.approx([index / 100 for index in range(50)])
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_exact_multiple_does_not_emit_an_empty_trailing_request() -> None:
    seen: list[int] = []

    def handler(request: httpx.Request) -> Response:
        texts = _texts(request)
        seen.append(len(texts))
        return _scores_for(texts)

    respx.post(_URL).mock(side_effect=handler)
    client = _client(batch_size=32)

    scores = await client.rerank("query", [f"doc-{index}" for index in range(64)])

    assert seen == [32, 32]
    assert scores == pytest.approx([index / 100 for index in range(64)])
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_batch_size_one_sends_one_request_per_document_in_order() -> None:
    requests: list[list[str]] = []

    def handler(request: httpx.Request) -> Response:
        texts = _texts(request)
        requests.append(texts)
        return _scores_for(texts)

    respx.post(_URL).mock(side_effect=handler)
    client = _client(batch_size=1)

    scores = await client.rerank("query", ["doc-0", "doc-1", "doc-2"])

    assert sorted(requests) == [["doc-0"], ["doc-1"], ["doc-2"]]
    assert scores == pytest.approx([0.0, 0.01, 0.02])
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size", [0, -5], ids=["zero", "negative"])
@respx.mock
async def test_a_nonpositive_configured_batch_size_still_splits(batch_size: int) -> None:
    """The dataclass has no bounds, so the client must not build a step-0 range."""
    seen: list[int] = []

    def handler(request: httpx.Request) -> Response:
        texts = _texts(request)
        seen.append(len(texts))
        return _scores_for(texts)

    respx.post(_URL).mock(side_effect=handler)
    client = _client(batch_size=batch_size)

    scores = await client.rerank("query", ["doc-0", "doc-1", "doc-2"])

    assert seen == [1, 1, 1]
    assert scores == pytest.approx([0.0, 0.01, 0.02])
    await client.aclose()


# ---------------------------------------------------------------------------
# Index alignment inside split batches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_batch_entries_returned_out_of_order_are_realigned_globally() -> None:
    """Each batch restarts its ``index`` at 0; the merge must not ignore it."""

    def handler(request: httpx.Request) -> Response:
        texts = _texts(request)
        entries = [
            {"index": index, "score": int(text.split("-")[1]) / 100}
            for index, text in enumerate(texts)
        ]
        return Response(200, json=list(reversed(entries)))

    respx.post(_URL).mock(side_effect=handler)
    client = _client(batch_size=2)

    scores = await client.rerank("query", [f"doc-{index}" for index in range(5)])

    assert scores == pytest.approx([index / 100 for index in range(5)])
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_alignment_follows_slice_order_not_completion_order() -> None:
    """The first slice is allowed to finish last; scores still belong to their slice."""
    later_batch_finished = asyncio.Event()

    async def handler(request: httpx.Request) -> Response:
        texts = _texts(request)
        if texts[0] in {"doc-0", "doc-1"}:
            await later_batch_finished.wait()
        else:
            later_batch_finished.set()
        return _scores_for(texts)

    respx.post(_URL).mock(side_effect=handler)
    client = _client(batch_size=2)

    scores = await asyncio.wait_for(
        client.rerank("query", ["doc-0", "doc-1", "doc-2", "doc-3"]),
        timeout=2.0,
    )

    assert scores == pytest.approx([0.0, 0.01, 0.02, 0.03])
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    ("batched_response", "expected_error"),
    [
        ([{"index": 0, "score": 0.5}, {"index": 0, "score": 0.6}], "duplicated"),
        ([{"index": 0, "score": 0.5}], "scores for"),
        ([{"index": 0, "score": 0.5}, {"index": 2, "score": 0.6}], "out of range"),
    ],
    ids=["duplicate-index", "short-response", "out-of-range-index"],
)
async def test_a_malformed_later_batch_is_an_invalid_response(
    batched_response: list[dict[str, object]],
    expected_error: str,
) -> None:
    """Only one batch is answered badly: the other still parses cleanly.

    That is what separates a per-batch contract check from a global one — the
    good batch must not be able to hide, or be corrupted by, the bad one.
    """

    def handler(request: httpx.Request) -> Response:
        if _texts(request)[0] == "doc-2":
            return Response(200, json=batched_response)
        return _scores_for(_texts(request))

    respx.post(_URL).mock(side_effect=handler)
    client = _client(batch_size=2)

    with pytest.raises(RerankInvalidResponseError, match=expected_error):
        await client.rerank("query", ["doc-0", "doc-1", "doc-2", "doc-3"])

    await client.aclose()


# ---------------------------------------------------------------------------
# All-or-nothing failure semantics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_non_retryable_rejection_in_one_batch_propagates_as_rejection() -> None:
    calls: list[list[str]] = []

    def handler(request: httpx.Request) -> Response:
        texts = _texts(request)
        calls.append(texts)
        if texts[0] == "doc-2":
            return Response(413, json={"error": "batch size exceeded"})
        return _scores_for(texts)

    respx.post(_URL).mock(side_effect=handler)
    client = _client(batch_size=2, max_retries=2)

    with pytest.raises(RerankRejectedError):
        await client.rerank("query", ["doc-0", "doc-1", "doc-2", "doc-3"])

    # A 413 is not retryable, regardless of the retry budget.
    assert len(calls) == 2
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_retryable_failure_retries_only_the_affected_batch() -> None:
    calls: list[list[str]] = []
    failed_once = False

    def handler(request: httpx.Request) -> Response:
        nonlocal failed_once
        texts = _texts(request)
        calls.append(texts)
        if not failed_once:
            failed_once = True
            return Response(503)
        return _scores_for(texts)

    respx.post(_URL).mock(side_effect=handler)
    client = _client(batch_size=2, max_retries=1)

    with patch("app.clients.rerank.asyncio.sleep", AsyncMock()):
        scores = await client.rerank("query", ["doc-0", "doc-1", "doc-2", "doc-3"])

    assert len(calls) == 3  # two initial batches plus one retry
    assert scores == pytest.approx([0.0, 0.01, 0.02, 0.03])
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_timeout_in_one_batch_raises_timeout_and_returns_no_scores() -> None:
    def handler(request: httpx.Request) -> Response:
        texts = _texts(request)
        if texts[0] == "doc-2":
            raise httpx.ReadTimeout("slow", request=request)
        return _scores_for(texts)

    respx.post(_URL).mock(side_effect=handler)
    client = _client(batch_size=2)

    with pytest.raises(RerankTimeoutError):
        await client.rerank("query", ["doc-0", "doc-1", "doc-2", "doc-3"])

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_slices_are_issued_concurrently_not_serially() -> None:
    """ADR-0093 says the slices are concurrent; serial requests double the latency."""
    barrier = asyncio.Barrier(2)

    async def handler(request: httpx.Request) -> Response:
        # Both slices must be in flight for this to return; a serial client would
        # deadlock here and the outer timeout would fail the test.
        await barrier.wait()
        return _scores_for(_texts(request))

    respx.post(_URL).mock(side_effect=handler)
    client = _client(batch_size=32)

    scores = await asyncio.wait_for(
        client.rerank("query", [f"doc-{index}" for index in range(50)]),
        timeout=2.0,
    )

    assert scores == pytest.approx([index / 100 for index in range(50)])
    await client.aclose()


# ---------------------------------------------------------------------------
# Settings wiring
# ---------------------------------------------------------------------------


def test_settings_default_client_batch_size_is_the_tei_default() -> None:
    assert Settings().rerank_client_batch_size == 32


@pytest.mark.parametrize("value", [0, 65, -1])
def test_client_batch_size_outside_the_documented_range_is_rejected(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(rerank_client_batch_size=value)


@pytest.mark.parametrize("value", [1, 32, 64])
def test_client_batch_size_inside_the_documented_range_is_accepted(value: int) -> None:
    assert Settings(rerank_client_batch_size=value).rerank_client_batch_size == value


@pytest.mark.asyncio
@respx.mock
async def test_env_batch_size_reaches_the_client_and_changes_the_split(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance #4: ``IBEX_MEMORY_RERANK_CLIENT_BATCH_SIZE`` must actually split."""
    from app.main import _build_rerank

    monkeypatch.setenv("IBEX_MEMORY_RERANK_CLIENT_BATCH_SIZE", "16")
    cfg = Settings(
        rerank_enabled=True,
        search_hybrid_enabled=True,
        rerank_base_url=_BASE,
    )
    seen: list[int] = []

    def handler(request: httpx.Request) -> Response:
        texts = _texts(request)
        seen.append(len(texts))
        return _scores_for(texts)

    respx.post(_URL).mock(side_effect=handler)
    client = _build_rerank(cfg)
    assert client is not None

    scores = await client.rerank("query", [f"doc-{index}" for index in range(20)])

    assert sorted(seen) == [4, 16]
    assert scores == pytest.approx([index / 100 for index in range(20)])
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_operator_batch_size_above_the_server_limit_degrades_the_read_path() -> None:
    """The documented footgun: a value above TEI's limit re-creates the silent no-op.

    The client cannot know the server flag, so it must at least surface the 413 as
    a rejection, and the read path must degrade rather than return a 500.
    """
    from app.main import _build_rerank

    ids = [UUID(int=index) for index in range(1, 51)]
    cfg = Settings(
        rerank_enabled=True,
        search_hybrid_enabled=True,
        rerank_base_url=_BASE,
        rerank_client_batch_size=64,
        rerank_max_candidates=50,
        # This test is about the 413, not the latency budget.
        rerank_timeout_ms=5000,
    )
    client = _build_rerank(cfg)
    assert client is not None

    def handler(request: httpx.Request) -> Response:
        texts = _texts(request)
        if len(texts) > 32:
            return Response(413, json={"error": "batch size exceeded"})
        return _scores_for(texts)

    respx.post(_URL).mock(side_effect=handler)
    store = AsyncMock()
    store.search = AsyncMock(
        return_value=[SearchHit(memory_id=memory_id, similarity=0.9) for memory_id in ids]
    )
    repo = make_repo(store, cfg, rerank_client=client)
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        return_value=make_hydrated_map(
            [replace(_result(memory_id), content="content") for memory_id in ids]
        )
    )
    before = _degraded()

    with patch("app.read.repository.full_text_search", AsyncMock(return_value=[])):
        results = await repo.find_similar(make_query(limit=50))

    assert [item.id for item in results] == ids
    assert _degraded() > before
    await client.aclose()


# ---------------------------------------------------------------------------
# Surrounding read path (acceptance #5)
# ---------------------------------------------------------------------------


def _result(memory_id: UUID):
    from tests.unit.find_similar_support import make_result

    return make_result(memory_id)


@pytest.mark.asyncio
@respx.mock
async def test_split_window_scores_are_applied_end_to_end() -> None:
    """A split window must still produce one score per row for ``zip(..., strict=True)``."""
    ids = [UUID(int=index) for index in range(1, 51)]

    def handler(request: httpx.Request) -> Response:
        texts = _texts(request)
        # Higher global position earns a higher score: the page must reverse.
        return Response(
            200,
            json=[
                {"index": index, "score": 0.5 + int(text.split("-")[1]) / 200}
                for index, text in enumerate(texts)
            ],
        )

    respx.post(_URL).mock(side_effect=handler)
    client = _client(batch_size=32, read_timeout=5.0)
    cfg = Settings(
        rerank_enabled=True,
        search_hybrid_enabled=True,
        rerank_max_candidates=50,
        # This test is about score assembly, not the latency budget.
        rerank_timeout_ms=5000,
    )
    store = AsyncMock()
    store.search = AsyncMock(
        return_value=[SearchHit(memory_id=memory_id, similarity=0.9) for memory_id in ids]
    )
    repo = make_repo(store, cfg, rerank_client=client)
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        return_value=make_hydrated_map(
            [
                replace(_result(memory_id), content=f"doc-{index}")
                for index, memory_id in enumerate(ids)
            ]
        )
    )

    with patch("app.read.repository.full_text_search", AsyncMock(return_value=[])):
        results = await repo.find_similar(make_query(limit=50))

    assert [item.id for item in results] == list(reversed(ids))
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_stage_timeout_across_two_batches_degrades_to_the_fused_order() -> None:
    """The outer ``wait_for`` bounds the whole stage, not one request."""
    ids = [UUID(int=index) for index in range(1, 51)]
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> Response:
        await release.wait()
        return _scores_for(_texts(request))

    respx.post(_URL).mock(side_effect=handler)
    client = _client(batch_size=32, read_timeout=5.0)
    cfg = Settings(
        rerank_enabled=True,
        search_hybrid_enabled=True,
        rerank_max_candidates=50,
        rerank_timeout_ms=50,
    )
    store = AsyncMock()
    store.search = AsyncMock(
        return_value=[SearchHit(memory_id=memory_id, similarity=0.9) for memory_id in ids]
    )
    repo = make_repo(store, cfg, rerank_client=client)
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        return_value=make_hydrated_map([_result(memory_id) for memory_id in ids])
    )
    before = _degraded()

    with patch("app.read.repository.full_text_search", AsyncMock(return_value=[])):
        results = await repo.find_similar(make_query(limit=50))

    assert [item.id for item in results] == ids
    assert _degraded() > before
    release.set()
    await client.aclose()