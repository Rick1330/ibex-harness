"""Tests for TeiClient — respx-mocked HTTP interactions."""

from __future__ import annotations

import json

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
from app.tei.client import TeiClient, TeiClientConfig

_BASE_URL = "http://tei-test:8080"

# 1024-d L2-normalized unit vectors for two texts.
_VEC_A = ([1.0 / (1024**0.5)] * 1024)
_VEC_B = ([1.0 / (1024**0.5)] * 512 + [-1.0 / (1024**0.5)] * 512)
_TWO_VECS = [_VEC_A, _VEC_B]


@pytest.fixture
def client() -> TeiClient:
    return TeiClient(
        _BASE_URL,
        config=TeiClientConfig(connect_timeout=1.0, read_timeout=5.0, max_retries=2),
    )


class TestHealth:
    @respx.mock
    async def test_healthy(self, client: TeiClient) -> None:
        respx.get(f"{_BASE_URL}/health").mock(return_value=Response(200))
        assert await client.health() is True

    @respx.mock
    async def test_unhealthy_503(self, client: TeiClient) -> None:
        respx.get(f"{_BASE_URL}/health").mock(return_value=Response(503))
        assert await client.health() is False

    @respx.mock
    async def test_network_error_returns_false(self, client: TeiClient) -> None:
        import httpx
        respx.get(f"{_BASE_URL}/health").mock(side_effect=httpx.NetworkError("conn refused"))
        assert await client.health() is False

    @respx.mock
    async def test_transport_error_returns_false(self, client: TeiClient) -> None:
        import httpx
        respx.get(f"{_BASE_URL}/health").mock(side_effect=httpx.RemoteProtocolError("boom"))
        assert await client.health() is False


class TestInfo:
    @respx.mock
    async def test_returns_model_id(self, client: TeiClient) -> None:
        respx.get(f"{_BASE_URL}/info").mock(
            return_value=Response(200, json={"model_id": "BAAI/bge-m3"})
        )
        info = await client.info()
        assert info["model_id"] == "BAAI/bge-m3"

    @respx.mock
    async def test_non_200_raises_unavailable(self, client: TeiClient) -> None:
        respx.get(f"{_BASE_URL}/info").mock(return_value=Response(503))
        with pytest.raises(BackendUnavailableError):
            await client.info()

    @respx.mock
    async def test_timeout_raises_timeout_error(self, client: TeiClient) -> None:
        import httpx
        respx.get(f"{_BASE_URL}/info").mock(side_effect=httpx.TimeoutException(""))
        with pytest.raises(BackendTimeoutError):
            await client.info()


class TestEmbed:
    @respx.mock
    async def test_successful_embed_returns_ndarray(self, client: TeiClient) -> None:
        respx.post(f"{_BASE_URL}/embed").mock(
            return_value=Response(200, json=_TWO_VECS)
        )
        result = await client.embed(["text a", "text b"])
        assert result.shape == (2, 1024)
        assert result.dtype == np.float32

    @respx.mock
    async def test_normalize_true_sent(self, client: TeiClient) -> None:
        route = respx.post(f"{_BASE_URL}/embed").mock(
            return_value=Response(200, json=[_VEC_A])
        )
        await client.embed(["hello"])
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["normalize"] is True

    @respx.mock
    async def test_truncate_never_sent_true(self, client: TeiClient) -> None:
        route = respx.post(f"{_BASE_URL}/embed").mock(
            return_value=Response(200, json=[_VEC_A])
        )
        await client.embed(["hello"])
        sent_body = json.loads(route.calls[0].request.content)
        # truncate must be absent or False — never True.
        assert sent_body.get("truncate") is not True

    @respx.mock
    async def test_413_raises_rejected(self, client: TeiClient) -> None:
        respx.post(f"{_BASE_URL}/embed").mock(return_value=Response(413, text="too large"))
        with pytest.raises(BackendRejectedError):
            await client.embed(["x"])

    @respx.mock
    async def test_422_raises_rejected(self, client: TeiClient) -> None:
        respx.post(f"{_BASE_URL}/embed").mock(return_value=Response(422, text="unprocessable"))
        with pytest.raises(BackendRejectedError):
            await client.embed(["x"])

    @respx.mock
    async def test_424_raises_rejected_with_message(self, client: TeiClient) -> None:
        respx.post(f"{_BASE_URL}/embed").mock(
            return_value=Response(424, text="wrong model type")
        )
        with pytest.raises(BackendRejectedError, match="424"):
            await client.embed(["x"])

    @respx.mock
    async def test_500_raises_unavailable_without_retry(self, client: TeiClient) -> None:
        route = respx.post(f"{_BASE_URL}/embed").mock(return_value=Response(500, text="oops"))
        with pytest.raises(BackendUnavailableError):
            await client.embed(["x"])
        assert route.call_count == 1

    @respx.mock
    @pytest.mark.parametrize("status", [400, 401, 403, 404])
    async def test_non_retryable_client_errors_raise_once(
        self, client: TeiClient, status: int
    ) -> None:
        route = respx.post(f"{_BASE_URL}/embed").mock(return_value=Response(status, text="nope"))
        with pytest.raises(BackendUnavailableError):
            await client.embed(["x"])
        assert route.call_count == 1

    @respx.mock
    async def test_malformed_json_raises_invalid_vector(self, client: TeiClient) -> None:
        respx.post(f"{_BASE_URL}/embed").mock(
            return_value=Response(
                200,
                content=b"{not json",
                headers={"content-type": "application/json"},
            )
        )
        with pytest.raises(InvalidVectorError, match="malformed JSON"):
            await client.embed(["x"])

    @respx.mock
    async def test_object_payload_raises_invalid_vector(self, client: TeiClient) -> None:
        respx.post(f"{_BASE_URL}/embed").mock(
            return_value=Response(200, json={"embeddings": [[0.1]]})
        )
        with pytest.raises(InvalidVectorError, match="unexpected type"):
            await client.embed(["x"])

    @respx.mock
    async def test_429_retried_then_success(self, client: TeiClient) -> None:
        responses = iter([
            Response(429, headers={"Retry-After": "0"}),
            Response(429, headers={"Retry-After": "0"}),
            Response(200, json=[_VEC_A]),
        ])
        respx.post(f"{_BASE_URL}/embed").mock(side_effect=responses)
        # max_retries=2: 3 total attempts → should succeed
        result = await client.embed(["hello"])
        assert result.shape == (1, 1024)

    @respx.mock
    async def test_429_exhausted_raises_unavailable(self) -> None:
        # max_retries=0: only 1 attempt allowed → should fail immediately
        client = TeiClient(_BASE_URL, config=TeiClientConfig(max_retries=0))
        respx.post(f"{_BASE_URL}/embed").mock(return_value=Response(429))
        with pytest.raises(BackendUnavailableError):
            await client.embed(["x"])

    @respx.mock
    async def test_503_retried_then_success(self, client: TeiClient) -> None:
        responses = iter([
            Response(503),
            Response(200, json=[_VEC_A]),
        ])
        respx.post(f"{_BASE_URL}/embed").mock(side_effect=responses)
        result = await client.embed(["hello"])
        assert result.shape == (1, 1024)

    @respx.mock
    async def test_network_error_retried_then_success(self, client: TeiClient) -> None:
        import httpx
        responses = iter([
            httpx.NetworkError("conn refused"),
            Response(200, json=[_VEC_A]),
        ])
        respx.post(f"{_BASE_URL}/embed").mock(side_effect=responses)
        result = await client.embed(["hello"])
        assert result.shape == (1, 1024)

    @respx.mock
    async def test_network_error_exhausted_raises(self) -> None:
        import httpx
        client = TeiClient(_BASE_URL, config=TeiClientConfig(max_retries=0))
        respx.post(f"{_BASE_URL}/embed").mock(side_effect=httpx.NetworkError("conn refused"))
        with pytest.raises(BackendUnavailableError):
            await client.embed(["x"])

    @respx.mock
    async def test_timeout_exception_raises_backend_timeout(self) -> None:
        import httpx
        client = TeiClient(_BASE_URL, config=TeiClientConfig(max_retries=0))
        respx.post(f"{_BASE_URL}/embed").mock(side_effect=httpx.TimeoutException("timeout"))
        with pytest.raises(BackendTimeoutError):
            await client.embed(["x"])

    @respx.mock
    async def test_transport_error_raises_unavailable(self) -> None:
        import httpx
        client = TeiClient(_BASE_URL, config=TeiClientConfig(max_retries=0))
        respx.post(f"{_BASE_URL}/embed").mock(
            side_effect=httpx.RemoteProtocolError("peer closed")
        )
        with pytest.raises(BackendUnavailableError, match="connection error"):
            await client.embed(["x"])

    @respx.mock
    async def test_api_key_sent_in_header(self) -> None:
        client = TeiClient(_BASE_URL, config=TeiClientConfig(api_key="secret-token"))
        route = respx.post(f"{_BASE_URL}/embed").mock(
            return_value=Response(200, json=[_VEC_A])
        )
        await client.embed(["hello"])
        assert route.calls[0].request.headers["authorization"] == "Bearer secret-token"

    @respx.mock
    async def test_no_api_key_no_auth_header(self, client: TeiClient) -> None:
        route = respx.post(f"{_BASE_URL}/embed").mock(
            return_value=Response(200, json=[_VEC_A])
        )
        await client.embed(["hello"])
        assert "authorization" not in route.calls[0].request.headers

    async def test_aclose(self, client: TeiClient) -> None:
        await client.aclose()  # must not raise

    @respx.mock
    async def test_info_network_error_raises_unavailable(self, client: TeiClient) -> None:
        import httpx
        respx.get(f"{_BASE_URL}/info").mock(side_effect=httpx.NetworkError("refused"))
        with pytest.raises(BackendUnavailableError):
            await client.info()


class TestTeiClientConstruction:
    def test_empty_base_url_raises(self) -> None:
        with pytest.raises(ValueError, match="base_url must not be empty"):
            TeiClient("")

    def test_whitespace_base_url_raises(self) -> None:
        with pytest.raises(ValueError, match="base_url must not be empty"):
            TeiClient("   ")


class TestGetModelIdFromInfo:
    def test_extracts_model_id(self) -> None:
        client = TeiClient(_BASE_URL)
        assert client.model_id_from_info({"model_id": "x"}) == "x"

    def test_returns_none_for_missing(self) -> None:
        client = TeiClient(_BASE_URL)
        assert client.model_id_from_info({}) is None


class TestJitteredBackoff:
    def test_delay_stays_within_cap(self) -> None:
        from app.tei.client import _jittered_backoff

        for attempt in range(12):
            delay = _jittered_backoff(attempt)
            assert 0.0 <= delay <= 8.0
