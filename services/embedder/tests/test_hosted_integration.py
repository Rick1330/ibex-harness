"""End-to-end hosted profile tests: lifespan probe + POST /v1/embed (respx).

These exercise the real HostedAPIBackend through FastAPI, not a MagicMock
backend. Goal: break fail-closed paths (missing key, wrong geometry,
bad service token, upstream 401) the way an operator/attacker would.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

from app.config import get_settings
from app.main import app
from app.validate import vector_l2_norm

_TOKEN = "service-token"
_HOSTED_KEY = "sk-integration-secret"
_DIM = 8
_OPENAI_EMBED = "https://api.openai.com/v1/embeddings"
_COHERE_EMBED = "https://api.cohere.com/v2/embed"


def _openai_body(vectors: list[list[float]]) -> dict[str, Any]:
    return {
        "data": [
            {"index": i, "embedding": vec, "object": "embedding"}
            for i, vec in enumerate(vectors)
        ],
        "object": "list",
        "model": "text-embedding-3-large",
    }


def _unit_row(dim: int = _DIM) -> list[float]:
    raw = np.arange(1, dim + 1, dtype=np.float32)
    raw = raw / float(np.linalg.norm(raw))
    return raw.tolist()


@pytest.fixture(autouse=True)
def _clear_settings() -> Any:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _hosted_env(monkeypatch: pytest.MonkeyPatch, extra: dict[str, str | None] | None = None) -> None:
    monkeypatch.setenv("IBEX_EMBEDDING_PROFILE", "hosted")
    monkeypatch.setenv("IBEX_EMBEDDING_HOSTED_API_KEY", _HOSTED_KEY)
    monkeypatch.setenv("IBEX_EMBEDDING_API_TOKEN", _TOKEN)
    monkeypatch.setenv("IBEX_EMBEDDING_DIM", str(_DIM))
    monkeypatch.setenv("IBEX_EMBEDDING_MODEL", "text-embedding-3-large")
    monkeypatch.setenv("IBEX_EMBEDDING_HOSTED_MAX_RETRIES", "0")
    if extra:
        for key, value in extra.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, value)


class TestHostedLifespanAndEmbed:
    @respx.mock
    def test_ready_then_embed_l2_and_backend_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _hosted_env(monkeypatch)
        row = _unit_row()
        respx.post(_OPENAI_EMBED).mock(return_value=Response(200, json=_openai_body([row])))

        with TestClient(app) as tc:
            ready = tc.get("/ready")
            assert ready.status_code == 200
            health = tc.get("/health")
            assert health.status_code == 200
            resp = tc.post(
                "/v1/embed",
                json={"texts": ["hello"]},
                headers={"Authorization": f"Bearer {_TOKEN}"},
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["backend"] == "openai"
        assert body["model_id"] == "text-embedding-3-large"
        assert body["dimensions"] == _DIM
        vec = np.array(body["vectors"][0], dtype=np.float32)
        assert vec.shape == (_DIM,)
        assert vector_l2_norm(vec) == pytest.approx(1.0, abs=1e-4)
        assert _HOSTED_KEY not in resp.text

    @respx.mock
    def test_wrong_service_bearer_still_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _hosted_env(monkeypatch)
        respx.post(_OPENAI_EMBED).mock(
            return_value=Response(200, json=_openai_body([_unit_row()]))
        )
        with TestClient(app) as tc:
            assert tc.get("/ready").status_code == 200
            resp = tc.post(
                "/v1/embed",
                json={"texts": ["hello"]},
                headers={"Authorization": "Bearer wrong-token"},
            )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "authentication_failed"

    @respx.mock
    def test_probe_dim_mismatch_blocks_ready(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _hosted_env(monkeypatch)
        wrong = [[0.1, 0.2, 0.3, 0.4]]
        respx.post(_OPENAI_EMBED).mock(return_value=Response(200, json=_openai_body(wrong)))
        with TestClient(app) as tc:
            ready = tc.get("/ready")
            embed = tc.post(
                "/v1/embed",
                json={"texts": ["hello"]},
                headers={"Authorization": f"Bearer {_TOKEN}"},
            )
        assert ready.status_code == 503
        assert ready.json()["error"]["code"] == "service_not_ready"
        assert embed.status_code == 503
        assert _HOSTED_KEY not in ready.text

    @respx.mock
    def test_upstream_401_blocks_ready_without_leaking_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _hosted_env(monkeypatch)
        respx.post(_OPENAI_EMBED).mock(
            return_value=Response(401, text=f"invalid api key {_HOSTED_KEY}")
        )
        with TestClient(app) as tc:
            ready = tc.get("/ready")
        assert ready.status_code == 503
        assert _HOSTED_KEY not in ready.text
        assert "invalid api key" not in ready.text

    def test_missing_hosted_key_never_ready(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _hosted_env(monkeypatch, extra={"IBEX_EMBEDDING_HOSTED_API_KEY": None})
        with TestClient(app) as tc:
            ready = tc.get("/ready")
        assert ready.status_code == 503
        message = ready.json()["error"]["message"]
        assert "HOSTED_API_KEY" in message or "hosted" in message.lower()

    def test_voyage_never_ready(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _hosted_env(monkeypatch, extra={"IBEX_EMBEDDING_HOSTED_PROVIDER": "voyage"})
        with TestClient(app) as tc:
            ready = tc.get("/ready")
        assert ready.status_code == 503
        assert "voyage" in ready.json()["error"]["message"].lower()

    @respx.mock
    def test_cohere_path_ready_and_embed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _hosted_env(
            monkeypatch,
            extra={
                "IBEX_EMBEDDING_HOSTED_PROVIDER": "cohere",
                "IBEX_EMBEDDING_MODEL": "embed-english-v3.0",
                "IBEX_EMBEDDING_DIM": "1024",
            },
        )
        row = _unit_row(1024)
        respx.post(_COHERE_EMBED).mock(
            return_value=Response(200, json={"embeddings": {"float": [row]}})
        )
        with TestClient(app) as tc:
            assert tc.get("/ready").status_code == 200
            resp = tc.post(
                "/v1/embed",
                json={"texts": ["hello"]},
                headers={"Authorization": f"Bearer {_TOKEN}"},
            )
        assert resp.status_code == 200
        assert resp.json()["backend"] == "cohere"
        assert len(resp.json()["vectors"][0]) == 1024

    @respx.mock
    def test_malformed_upstream_json_returns_502_after_ready(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _hosted_env(monkeypatch)
        calls = {"n": 0}

        def _handler(_request: object) -> Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return Response(200, json=_openai_body([_unit_row()]))
            return Response(200, text="{not-json")

        respx.post(_OPENAI_EMBED).mock(side_effect=_handler)
        with TestClient(app) as tc:
            assert tc.get("/ready").status_code == 200
            resp = tc.post(
                "/v1/embed",
                json={"texts": ["hello"]},
                headers={"Authorization": f"Bearer {_TOKEN}"},
            )
        assert resp.status_code == 502
        assert resp.json()["error"]["code"] == "invalid_vector"
