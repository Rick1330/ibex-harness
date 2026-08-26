from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
import respx
from httpx import Response

from app.clients.embedding import (
    EmbeddingClient,
    EmbeddingClientConfig,
    EmbeddingInvalidResponseError,
    EmbeddingRejectedError,
    EmbeddingTimeoutError,
    EmbeddingUnavailableError,
)

_BASE = "https://embedder.test"
_ORG = uuid4()
_VEC = [0.0] * 1023 + [1.0]


def _client(*, max_retries: int = 2) -> EmbeddingClient:
    return EmbeddingClient(
        _BASE,
        "test-token",
        config=EmbeddingClientConfig(
            connect_timeout=1.0, read_timeout=2.0, max_retries=max_retries
        ),
    )


def _ok_body(*, n: int = 1) -> dict[str, object]:
    return {
        "vectors": [list(_VEC) for _ in range(n)],
        "model_id": "bge-m3",
        "dimensions": 1024,
        "backend": "tei",
    }


def _body_with_bad_dimensions() -> dict[str, object]:
    body = _ok_body()
    body["dimensions"] = 768
    return body


def _body_with_bad_component(bad: object) -> dict[str, object]:
    body = _ok_body()
    vectors = body["vectors"]
    assert isinstance(vectors, list)
    row = vectors[0]
    assert isinstance(row, list)
    row[0] = bad
    return body


@pytest.mark.asyncio
@respx.mock
async def test_embed_success() -> None:
    respx.post(f"{_BASE}/v1/embed").mock(return_value=Response(200, json=_ok_body(n=2)))
    client = _client()
    try:
        result = await client.embed(["a", "b"], org_id=_ORG)
    finally:
        await client.aclose()
    assert result.model_id == "bge-m3"
    assert result.dimensions == 1024
    assert len(result.vectors) == 2


@pytest.mark.asyncio
@respx.mock
async def test_embed_rejects_empty_texts() -> None:
    client = _client()
    try:
        with pytest.raises(EmbeddingRejectedError, match="non-empty"):
            await client.embed([], org_id=_ORG)
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_401_not_retried() -> None:
    route = respx.post(f"{_BASE}/v1/embed").mock(return_value=Response(401, text="nope"))
    client = _client(max_retries=2)
    try:
        with pytest.raises(EmbeddingUnavailableError, match="auth rejected"):
            await client.embed(["x"], org_id=_ORG)
    finally:
        await client.aclose()
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_400_rejected() -> None:
    respx.post(f"{_BASE}/v1/embed").mock(return_value=Response(400, text="bad"))
    client = _client()
    try:
        with pytest.raises(EmbeddingRejectedError, match="validation"):
            await client.embed(["x"], org_id=_ORG)
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    ("status", "headers", "max_retries"),
    [
        (429, {"Retry-After": "1"}, 2),
        (503, {}, 1),
    ],
)
async def test_retryable_status_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    headers: dict[str, str],
    max_retries: int,
) -> None:
    async def _no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("app.clients.embedding.asyncio.sleep", _no_sleep)
    respx.post(f"{_BASE}/v1/embed").mock(
        side_effect=[Response(status, headers=headers), Response(200, json=_ok_body())]
    )
    client = _client(max_retries=max_retries)
    try:
        result = await client.embed(["x"], org_id=_ORG)
    finally:
        await client.aclose()
    assert result.backend == "tei"
    assert len(result.vectors) == 1


@pytest.mark.asyncio
@respx.mock
async def test_500_not_retried() -> None:
    route = respx.post(f"{_BASE}/v1/embed").mock(return_value=Response(500, text="boom"))
    client = _client(max_retries=2)
    try:
        with pytest.raises(EmbeddingUnavailableError, match="unexpected status"):
            await client.embed(["x"], org_id=_ORG)
    finally:
        await client.aclose()
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    ("body_factory", "match"),
    [
        (_body_with_bad_dimensions, "1024"),
        (lambda: _body_with_bad_component(None), "finite number"),
        (lambda: _body_with_bad_component(True), "finite number"),
        (lambda: _body_with_bad_component("1.0"), "finite number"),
    ],
)
async def test_embed_rejects_invalid_response_body(
    body_factory: object,
    match: str,
) -> None:
    respx.post(f"{_BASE}/v1/embed").mock(
        return_value=Response(200, json=body_factory())  # type: ignore[operator]
    )
    client = _client()
    try:
        with pytest.raises(EmbeddingInvalidResponseError, match=match):
            await client.embed(["x"], org_id=_ORG)
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_timeout_maps_to_embedding_timeout() -> None:
    respx.post(f"{_BASE}/v1/embed").mock(side_effect=httpx.ReadTimeout("slow"))
    client = _client(max_retries=0)
    try:
        with pytest.raises(EmbeddingTimeoutError):
            await client.embed(["x"], org_id=_ORG)
    finally:
        await client.aclose()


def test_client_requires_token() -> None:
    with pytest.raises(ValueError, match="api_token"):
        EmbeddingClient(_BASE, "  ")


@pytest.mark.asyncio
@respx.mock
async def test_retry_log_omits_token_and_text(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("app.clients.embedding.asyncio.sleep", _no_sleep)
    respx.post(f"{_BASE}/v1/embed").mock(
        side_effect=[Response(429), Response(200, json=_ok_body())]
    )
    secret = "super-secret-token-value"
    client = EmbeddingClient(
        _BASE,
        secret,
        config=EmbeddingClientConfig(max_retries=1, connect_timeout=1.0, read_timeout=2.0),
    )
    with caplog.at_level("WARNING"):
        try:
            await client.embed(["do-not-log-this-text"], org_id=_ORG)
        finally:
            await client.aclose()
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert secret not in joined
    assert "do-not-log-this-text" not in joined


@pytest.mark.asyncio
async def test_embed_rejects_batch_over_64() -> None:
    client = _client()
    try:
        with pytest.raises(EmbeddingRejectedError, match="exceeds max 64"):
            await client.embed(["x"] * 65, org_id=_ORG)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_embed_rejects_text_over_32kib() -> None:
    client = _client()
    huge = "a" * (32 * 1024 + 1)
    try:
        with pytest.raises(EmbeddingRejectedError, match="exceeds"):
            await client.embed([huge], org_id=_ORG)
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_embed_accepts_batch_of_64() -> None:
    respx.post(f"{_BASE}/v1/embed").mock(return_value=Response(200, json=_ok_body(n=64)))
    client = _client()
    try:
        result = await client.embed(["x"] * 64, org_id=_ORG)
    finally:
        await client.aclose()
    assert len(result.vectors) == 64
