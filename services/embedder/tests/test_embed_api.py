"""Tests for POST /v1/embed API endpoint."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.errors import (
    BackendRejectedError,
    BackendTimeoutError,
    BackendUnavailableError,
    BatchTooLargeError,
    EmptyBatchError,
    InvalidVectorError,
    TextTooLongError,
)
from app.main import app
from app.state import AppState

_DIM = 1024
_MODEL = "BAAI/bge-m3"
_API_TOKEN = "service-token"


def _l2_vecs(n: int, dim: int = _DIM) -> np.ndarray:
    rng = np.random.default_rng(0)
    raw = rng.standard_normal((n, dim)).astype(np.float32)
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    return (raw / norms).astype(np.float32)


@dataclass(frozen=True)
class _ReadyBackendSpec:
    embed_return: np.ndarray | None = None
    embed_side_effect: Exception | None = None
    model_id: str = _MODEL
    dimensions: int = _DIM
    backend_name: str = "tei"
    profile: str = "gpu"


def _make_ready_state(spec: _ReadyBackendSpec | None = None) -> AppState:
    from unittest.mock import MagicMock

    probe = spec or _ReadyBackendSpec()
    backend = MagicMock()
    backend.model_id = probe.model_id
    backend.dimensions = probe.dimensions
    backend.name = probe.backend_name
    backend.profile = probe.profile

    if probe.embed_side_effect is not None:
        backend.embed = AsyncMock(side_effect=probe.embed_side_effect)
    else:
        vecs = probe.embed_return if probe.embed_return is not None else _l2_vecs(1)
        backend.embed = AsyncMock(return_value=vecs)

    state = AppState()
    state.backend = backend
    state.ready = True
    return state


def _auth_headers(token: str = _API_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _post_v1_embed(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
    *,
    state: AppState | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    monkeypatch.setenv("IBEX_EMBEDDING_PROFILE", "cpu")
    monkeypatch.setenv("IBEX_EMBEDDING_API_TOKEN", _API_TOKEN)
    ready = state if state is not None else _make_ready_state()
    req_headers = _auth_headers() if headers is None else headers
    with TestClient(app) as tc:
        tc.app.state.embedder = ready
        return tc.post("/v1/embed", json=payload, headers=req_headers)


@pytest.fixture(autouse=True)
def _clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestEmbedSuccess:
    def test_single_text_returns_vector(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IBEX_EMBEDDING_PROFILE", "cpu")
        monkeypatch.setenv("IBEX_EMBEDDING_API_TOKEN", _API_TOKEN)
        vecs = _l2_vecs(1)
        state = _make_ready_state(_ReadyBackendSpec(embed_return=vecs))
        with TestClient(app) as tc:
            tc.app.state.embedder = state
            resp = tc.post("/v1/embed", json={"texts": ["hello"]}, headers=_auth_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["model_id"] == _MODEL
        assert body["dimensions"] == _DIM
        assert body["backend"] == "tei"
        assert len(body["vectors"]) == 1
        assert len(body["vectors"][0]) == _DIM

    def test_batch_returns_correct_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IBEX_EMBEDDING_PROFILE", "cpu")
        monkeypatch.setenv("IBEX_EMBEDDING_API_TOKEN", _API_TOKEN)
        vecs = _l2_vecs(3)
        state = _make_ready_state(_ReadyBackendSpec(embed_return=vecs))
        with TestClient(app) as tc:
            tc.app.state.embedder = state
            resp = tc.post("/v1/embed", json={"texts": ["a", "b", "c"]}, headers=_auth_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["vectors"]) == 3

    def test_response_shape_fields_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IBEX_EMBEDDING_PROFILE", "cpu")
        monkeypatch.setenv("IBEX_EMBEDDING_API_TOKEN", _API_TOKEN)
        state = _make_ready_state(_ReadyBackendSpec(embed_return=_l2_vecs(1)))
        with TestClient(app) as tc:
            tc.app.state.embedder = state
            resp = tc.post("/v1/embed", json={"texts": ["x"]}, headers=_auth_headers())
        body = resp.json()
        for field in ("vectors", "model_id", "dimensions", "backend"):
            assert field in body, f"missing field: {field}"


class TestEmbedNotReady:
    def test_503_when_not_ready(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IBEX_EMBEDDING_PROFILE", "cpu")
        monkeypatch.setenv("IBEX_EMBEDDING_API_TOKEN", _API_TOKEN)
        state = AppState()
        state.ready = False
        state.ready_error = "startup failed"
        with TestClient(app) as tc:
            tc.app.state.embedder = state
            resp = tc.post("/v1/embed", json={"texts": ["x"]}, headers=_auth_headers())
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"]["code"] == "service_not_ready"
        assert "startup failed" in body["error"]["message"]

    def test_503_when_backend_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IBEX_EMBEDDING_PROFILE", "cpu")
        monkeypatch.setenv("IBEX_EMBEDDING_API_TOKEN", _API_TOKEN)
        state = AppState()
        state.ready = True
        state.backend = None
        with TestClient(app) as tc:
            tc.app.state.embedder = state
            resp = tc.post("/v1/embed", json={"texts": ["x"]}, headers=_auth_headers())
        assert resp.status_code == 503


class TestEmbedValidationErrors:
    def _post(self, texts: list[str], *, side_effect: Exception, monkeypatch) -> Any:
        monkeypatch.setenv("IBEX_EMBEDDING_PROFILE", "cpu")
        monkeypatch.setenv("IBEX_EMBEDDING_API_TOKEN", _API_TOKEN)
        state = _make_ready_state(_ReadyBackendSpec(embed_side_effect=side_effect))
        with TestClient(app) as tc:
            tc.app.state.embedder = state
            return tc.post("/v1/embed", json={"texts": texts}, headers=_auth_headers())

    def test_empty_batch_from_backend_returns_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        resp = self._post([], side_effect=EmptyBatchError("empty"), monkeypatch=monkeypatch)
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "empty_batch"

    def test_batch_too_large_returns_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        resp = self._post(
            ["x"] * 65, side_effect=BatchTooLargeError("too many"), monkeypatch=monkeypatch
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "batch_too_large"

    def test_text_too_long_returns_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        resp = self._post(
            ["x" * 65536], side_effect=TextTooLongError("too long"), monkeypatch=monkeypatch
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "text_too_long"

    def test_backend_rejected_returns_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        resp = self._post(
            ["x"], side_effect=BackendRejectedError("bad input"), monkeypatch=monkeypatch
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "backend_rejected"


class TestEmbedBackendErrors:
    def _post(self, *, side_effect: Exception, monkeypatch) -> Any:
        monkeypatch.setenv("IBEX_EMBEDDING_PROFILE", "cpu")
        monkeypatch.setenv("IBEX_EMBEDDING_API_TOKEN", _API_TOKEN)
        state = _make_ready_state(_ReadyBackendSpec(embed_side_effect=side_effect))
        with TestClient(app) as tc:
            tc.app.state.embedder = state
            return tc.post("/v1/embed", json={"texts": ["hello"]}, headers=_auth_headers())

    def test_backend_unavailable_returns_503(self, monkeypatch: pytest.MonkeyPatch) -> None:
        resp = self._post(
            side_effect=BackendUnavailableError("TEI down"), monkeypatch=monkeypatch
        )
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "backend_unavailable"

    def test_backend_timeout_returns_503(self, monkeypatch: pytest.MonkeyPatch) -> None:
        resp = self._post(
            side_effect=BackendTimeoutError("timed out"), monkeypatch=monkeypatch
        )
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "backend_timeout"

    def test_invalid_vector_returns_502(self, monkeypatch: pytest.MonkeyPatch) -> None:
        resp = self._post(
            side_effect=InvalidVectorError("shape mismatch"),
            monkeypatch=monkeypatch,
        )
        assert resp.status_code == 502
        assert resp.json()["error"]["code"] == "invalid_vector"


class TestEmbedRequestSchema:
    def test_missing_texts_field_returns_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        state = _make_ready_state()
        resp = _post_v1_embed(monkeypatch, {}, state=state)
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == "invalid_request"
        assert "message" in body["error"]
        assert "detail" not in body

    def test_texts_not_list_returns_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        state = _make_ready_state()
        resp = _post_v1_embed(monkeypatch, {"texts": "not a list"}, state=state)
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == "invalid_request"
        assert "message" in body["error"]
        assert "detail" not in body


class TestEmbedAuth:
    def test_missing_bearer_token_returns_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        resp = _post_v1_embed(monkeypatch, {"texts": ["x"]}, headers={})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "authentication_failed"

    def test_invalid_bearer_token_returns_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        resp = _post_v1_embed(
            monkeypatch, {"texts": ["x"]}, headers=_auth_headers("wrong-token")
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "authentication_failed"

    def test_same_length_wrong_token_returns_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        wrong = "x" * len(_API_TOKEN)
        resp = _post_v1_embed(monkeypatch, {"texts": ["x"]}, headers=_auth_headers(wrong))
        assert resp.status_code == 401

    def test_valid_token_returns_200(self, monkeypatch: pytest.MonkeyPatch) -> None:
        state = _make_ready_state(_ReadyBackendSpec(embed_return=_l2_vecs(1)))
        resp = _post_v1_embed(monkeypatch, {"texts": ["x"]}, state=state)
        assert resp.status_code == 200


class TestEmbedDoesNotLeakContent:
    async def test_text_not_in_error_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IBEX_EMBEDDING_PROFILE", "cpu")
        monkeypatch.setenv("IBEX_EMBEDDING_API_TOKEN", _API_TOKEN)
        secret = "super-secret-content-xyz"
        state = _make_ready_state(
            _ReadyBackendSpec(embed_side_effect=BackendUnavailableError("TEI error"))
        )
        with TestClient(app) as tc:
            tc.app.state.embedder = state
            resp = tc.post("/v1/embed", json={"texts": [secret]}, headers=_auth_headers())
        # The secret text must not appear in the error response body.
        assert secret not in resp.text
