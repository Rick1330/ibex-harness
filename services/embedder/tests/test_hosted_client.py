"""Tests for HostedClient — respx-mocked OpenAI / Cohere HTTP interactions."""

from __future__ import annotations

import json
import logging

import httpx
import numpy as np
import pytest
import respx
from httpx import Response

from app.errors import (
    BackendRejectedError,
    BackendTimeoutError,
    BackendUnavailableError,
    InvalidVectorError,
)
from app.hosted.client import (
    HostedClient,
    HostedClientConfig,
    _jittered_backoff,
    _parse_retry_after_seconds,
    _retry_delay_seconds,
)

_OPENAI_URL = "https://api.openai.com/v1"
_COHERE_URL = "https://api.cohere.com"

_DIM = 8
_VEC_A = [1.0] * _DIM
_VEC_B = [0.5] * _DIM
_API_KEY = "sk-test-secret-key"


def _openai_body(vectors: list[list[float]]) -> dict:
    return {
        "data": [
            {"index": i, "embedding": vec, "object": "embedding"}
            for i, vec in enumerate(vectors)
        ],
        "model": "text-embedding-3-large",
        "object": "list",
    }


def _hosted_client(
    base_url: str,
    *,
    api_key: str,
    defaults: dict[str, object],
    **overrides: object,
) -> HostedClient:
    cfg = {**defaults, **overrides}
    return HostedClient(base_url, api_key, config=HostedClientConfig(**cfg))  # type: ignore[arg-type]


def _openai_client(**kwargs: object) -> HostedClient:
    api_key = str(kwargs.pop("api_key", _API_KEY))
    return _hosted_client(
        _OPENAI_URL,
        api_key=api_key,
        defaults={
            "connect_timeout": 1.0,
            "read_timeout": 5.0,
            "max_retries": 2,
            "provider": "openai",
            "model_id": "text-embedding-3-large",
            "dimensions": 3072,
        },
        **kwargs,
    )


def _cohere_client(**kwargs: object) -> HostedClient:
    api_key = str(kwargs.pop("api_key", "cohere-test"))
    return _hosted_client(
        _COHERE_URL,
        api_key=api_key,
        defaults={
            "connect_timeout": 1.0,
            "read_timeout": 5.0,
            "max_retries": 2,
            "provider": "cohere",
            "model_id": "embed-english-v3.0",
            "dimensions": 1024,
        },
        **kwargs,
    )


class TestOpenAIEmbed:
    @respx.mock
    async def test_successful_embed(self) -> None:
        client = _openai_client(dimensions=_DIM, model_id="text-embedding-3-large")
        respx.post(f"{_OPENAI_URL}/embeddings").mock(
            return_value=Response(200, json=_openai_body([_VEC_A, _VEC_B]))
        )
        result = await client.embed(["a", "b"])
        assert result.shape == (2, _DIM)
        assert result.dtype == np.float32

    @respx.mock
    async def test_auth_header_present(self) -> None:
        client = _openai_client(dimensions=_DIM)
        route = respx.post(f"{_OPENAI_URL}/embeddings").mock(
            return_value=Response(200, json=_openai_body([_VEC_A]))
        )
        await client.embed(["hello"])
        assert route.calls[0].request.headers["Authorization"] == f"Bearer {_API_KEY}"

    @respx.mock
    async def test_matryoshka_dimensions_sent_when_not_default(self) -> None:
        client = _openai_client(dimensions=256, model_id="text-embedding-3-large")
        route = respx.post(f"{_OPENAI_URL}/embeddings").mock(
            return_value=Response(200, json=_openai_body([[0.1] * 256]))
        )
        await client.embed(["hello"])
        body = json.loads(route.calls[0].request.content)
        assert body["dimensions"] == 256
        assert body["model"] == "text-embedding-3-large"
        assert body["encoding_format"] == "float"

    @respx.mock
    async def test_default_dim_omits_dimensions_param(self) -> None:
        client = _openai_client(dimensions=3072, model_id="text-embedding-3-large")
        route = respx.post(f"{_OPENAI_URL}/embeddings").mock(
            return_value=Response(200, json=_openai_body([[0.1] * 8]))
        )
        await client.embed(["hello"])
        body = json.loads(route.calls[0].request.content)
        assert "dimensions" not in body

    @respx.mock
    async def test_401_non_retryable(self) -> None:
        client = _openai_client(dimensions=_DIM, max_retries=2)
        route = respx.post(f"{_OPENAI_URL}/embeddings").mock(
            return_value=Response(401, text="unauthorized secret-in-body")
        )
        with pytest.raises(BackendUnavailableError, match="auth rejected") as exc_info:
            await client.embed(["x"])
        assert route.call_count == 1
        assert "secret-in-body" not in str(exc_info.value)

    @respx.mock
    async def test_429_retries_then_succeeds(self) -> None:
        client = _openai_client(dimensions=_DIM, max_retries=2)
        route = respx.post(f"{_OPENAI_URL}/embeddings").mock(
            side_effect=[
                Response(429, text="rate", headers={"Retry-After": "1"}),
                Response(200, json=_openai_body([_VEC_A])),
            ]
        )
        result = await client.embed(["x"])
        assert result.shape == (1, _DIM)
        assert route.call_count == 2

    @respx.mock
    async def test_400_rejected_no_retry(self) -> None:
        client = _openai_client(dimensions=_DIM, max_retries=2)
        route = respx.post(f"{_OPENAI_URL}/embeddings").mock(
            return_value=Response(400, text="bad request including user text")
        )
        with pytest.raises(BackendRejectedError) as exc_info:
            await client.embed(["x"])
        assert route.call_count == 1
        assert "user text" not in str(exc_info.value)

    @respx.mock
    async def test_500_no_retry(self) -> None:
        client = _openai_client(dimensions=_DIM, max_retries=2)
        route = respx.post(f"{_OPENAI_URL}/embeddings").mock(return_value=Response(500))
        with pytest.raises(BackendUnavailableError, match="unexpected status 500"):
            await client.embed(["x"])
        assert route.call_count == 1

    @respx.mock
    async def test_timeout_raises(self) -> None:
        client = _openai_client(dimensions=_DIM, max_retries=0)
        respx.post(f"{_OPENAI_URL}/embeddings").mock(
            side_effect=httpx.TimeoutException("slow")
        )
        with pytest.raises(BackendTimeoutError):
            await client.embed(["x"])

    @respx.mock
    async def test_network_error_retried(self) -> None:
        client = _openai_client(dimensions=_DIM, max_retries=1)
        route = respx.post(f"{_OPENAI_URL}/embeddings").mock(
            side_effect=[
                httpx.NetworkError("conn refused"),
                Response(200, json=_openai_body([_VEC_A])),
            ]
        )
        result = await client.embed(["x"])
        assert result.shape == (1, _DIM)
        assert route.call_count == 2

    @respx.mock
    async def test_malformed_json(self) -> None:
        client = _openai_client(dimensions=_DIM, max_retries=0)
        respx.post(f"{_OPENAI_URL}/embeddings").mock(
            return_value=Response(200, text="{not-json")
        )
        with pytest.raises(InvalidVectorError):
            await client.embed(["x"])

    def test_empty_api_key_rejected(self) -> None:
        with pytest.raises(ValueError, match="api_key"):
            _openai_client(api_key="")

    def test_repr_and_httpx_do_not_leak_key(self) -> None:
        client = _openai_client()
        dumped = f"{client!r} {client._client!r} {client._client.auth!r}"
        assert _API_KEY not in dumped


class TestCohereEmbed:
    @respx.mock
    async def test_successful_embed_by_type(self) -> None:
        client = _cohere_client(dimensions=_DIM)
        respx.post(f"{_COHERE_URL}/v2/embed").mock(
            return_value=Response(
                200,
                json={"embeddings": {"float": [_VEC_A, _VEC_B]}, "id": "x"},
            )
        )
        result = await client.embed(["a", "b"])
        assert result.shape == (2, _DIM)

    @respx.mock
    async def test_request_shape(self) -> None:
        client = _cohere_client(dimensions=_DIM)
        route = respx.post(f"{_COHERE_URL}/v2/embed").mock(
            return_value=Response(200, json={"embeddings": {"float": [_VEC_A]}})
        )
        await client.embed(["hello"])
        body = json.loads(route.calls[0].request.content)
        assert body["model"] == "embed-english-v3.0"
        assert body["texts"] == ["hello"]
        assert body["input_type"] == "search_document"
        assert body["embedding_types"] == ["float"]
        assert route.calls[0].request.headers["Authorization"] == "Bearer cohere-test"

    @respx.mock
    async def test_503_retries(self) -> None:
        client = _cohere_client(dimensions=_DIM, max_retries=1)
        route = respx.post(f"{_COHERE_URL}/v2/embed").mock(
            side_effect=[
                Response(503, text="unavailable"),
                Response(200, json={"embeddings": {"float": [_VEC_A]}}),
            ]
        )
        await client.embed(["x"])
        assert route.call_count == 2


class TestLogsNeverContainSecret:
    @respx.mock
    async def test_retry_warning_omits_key(self, caplog: pytest.LogCaptureFixture) -> None:
        client = _openai_client(dimensions=_DIM, max_retries=1)
        respx.post(f"{_OPENAI_URL}/embeddings").mock(
            side_effect=[
                Response(429),
                Response(200, json=_openai_body([_VEC_A])),
            ]
        )
        with caplog.at_level(logging.WARNING):
            await client.embed(["secret-user-text-should-not-appear"])
        joined = " ".join(r.getMessage() for r in caplog.records)
        assert _API_KEY not in joined
        assert "secret-user-text-should-not-appear" not in joined


class TestJitter:
    def test_delay_bounded(self) -> None:
        for attempt in range(12):
            delay = _jittered_backoff(attempt)
            assert 0.0 <= delay <= 8.0


class TestRetryAfter:
    def test_numeric_seconds(self) -> None:
        assert _parse_retry_after_seconds("2") == 2.0
        assert _parse_retry_after_seconds(" 7 ") == 7.0

    def test_invalid_falls_back(self) -> None:
        assert _parse_retry_after_seconds(None) is None
        assert _parse_retry_after_seconds("Mon, 01 Jan 2024") is None
        assert _parse_retry_after_seconds("-1") is None
        assert _parse_retry_after_seconds("1.5") is None

    def test_delay_uses_retry_after_as_floor_and_caps(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.hosted.client._jittered_backoff", lambda _attempt: 0.1)
        assert _retry_delay_seconds(0, 2.0) == 2.0
        assert _retry_delay_seconds(0, 100.0) == 8.0
        assert _retry_delay_seconds(0, None) == 0.1

    @respx.mock
    async def test_429_sleeps_at_least_retry_after(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sleeps: list[float] = []

        async def _fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        monkeypatch.setattr("app.hosted.client.asyncio.sleep", _fake_sleep)
        monkeypatch.setattr("app.hosted.client._jittered_backoff", lambda _attempt: 0.05)
        client = _openai_client(dimensions=_DIM, max_retries=1)
        respx.post(f"{_OPENAI_URL}/embeddings").mock(
            side_effect=[
                Response(429, headers={"Retry-After": "3"}),
                Response(200, json=_openai_body([_VEC_A])),
            ]
        )
        await client.embed(["x"])
        assert sleeps == [3.0]
