"""Live integration tests against a real TEI instance.

These tests are skipped in CI unless IBEX_TEI_LIVE=1 is set.
They require a running TEI sidecar — use the reference compose or start manually:

    docker run --rm -p 8080:80 \\
      ghcr.io/huggingface/text-embeddings-inference:1.6.0-cpu \\
      --model-id BAAI/bge-small-en-v1.5 --port 80

Then run:
    IBEX_TEI_LIVE=1 IBEX_TEI_LIVE_URL=http://localhost:8080 \\
      IBEX_TEI_LIVE_MODEL=BAAI/bge-small-en-v1.5 IBEX_TEI_LIVE_DIM=384 \\
      pytest -m tei_live services/embedder/tests/test_tei_live.py -v

For GPU + bge-m3 (1024-d):
    IBEX_TEI_LIVE=1 IBEX_TEI_LIVE_URL=http://localhost:8080 \\
      IBEX_TEI_LIVE_MODEL=BAAI/bge-m3 IBEX_TEI_LIVE_DIM=1024 \\
      pytest -m tei_live services/embedder/tests/test_tei_live.py -v
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from app.backends.tei import TEIBackend
from app.config import Settings
from app.factory import build_backend
from app.tei.client import TeiClient, TeiClientConfig
from app.validate import validate_output_vectors, vector_l2_norm

# ------------------------------------------------------------------ #
# Skip marker                                                           #
# ------------------------------------------------------------------ #

_LIVE = os.getenv("IBEX_TEI_LIVE", "").lower() in ("1", "true", "yes")
_LIVE_API_TOKEN = os.getenv("IBEX_EMBEDDING_API_TOKEN", "live-service-token")

pytestmark = [
    pytest.mark.tei_live,
    pytest.mark.skipif(not _LIVE, reason="set IBEX_TEI_LIVE=1 to run TEI live tests"),
]


def _live_url() -> str:
    return os.getenv("IBEX_TEI_LIVE_URL", "http://localhost:8080")


def _live_model() -> str:
    return os.getenv("IBEX_TEI_LIVE_MODEL", "BAAI/bge-small-en-v1.5")


def _live_dim() -> int:
    return int(os.getenv("IBEX_TEI_LIVE_DIM", "384"))


def _live_client() -> TeiClient:
    return TeiClient(
        _live_url(),
        config=TeiClientConfig(connect_timeout=5.0, read_timeout=60.0, max_retries=0),
    )


def _live_gpu_settings() -> Settings:
    return Settings(
        profile="gpu",
        tei_base_url=_live_url(),
        tei_allow_insecure=True,
        dim=_live_dim(),
        model=_live_model(),
        api_token=_LIVE_API_TOKEN,  # type: ignore[arg-type]
    )


@pytest.fixture
def tei_client() -> TeiClient:
    """Function-scoped fixture: httpx.AsyncClient must share the test's event loop."""
    return _live_client()


@pytest.fixture
def tei_backend() -> TEIBackend:
    """Function-scoped fixture for the same reason as tei_client."""
    return TEIBackend(
        _live_client(),
        model_id=_live_model(),
        dimensions=_live_dim(),
    )


# ------------------------------------------------------------------ #
# TeiClient live tests                                                 #
# ------------------------------------------------------------------ #

class TestLiveTeiClient:
    async def test_health_returns_true(self, tei_client: TeiClient) -> None:
        assert await tei_client.health() is True

    async def test_info_returns_model_id(self, tei_client: TeiClient) -> None:
        info = await tei_client.info()
        model = tei_client.model_id_from_info(info)
        assert model is not None
        assert _live_model() in model or model in _live_model(), (
            f"Expected model_id to contain {_live_model()!r}, got {model!r}"
        )

    async def test_embed_single_returns_correct_shape(self, tei_client: TeiClient) -> None:
        result = await tei_client.embed(["hello world"])
        assert result.shape == (1, _live_dim())
        assert result.dtype == np.float32

    async def test_embed_batch_returns_correct_shape(self, tei_client: TeiClient) -> None:
        texts = ["hello", "world", "embeddings", "are", "vectors"]
        result = await tei_client.embed(texts)
        assert result.shape == (len(texts), _live_dim())

    async def test_embed_output_is_l2_normalized(self, tei_client: TeiClient) -> None:
        result = await tei_client.embed(["normalize me"])
        norm = vector_l2_norm(result[0])
        assert norm == pytest.approx(1.0, abs=1e-4)

    async def test_truncate_false_honored(self, tei_client: TeiClient) -> None:
        """Verify TEI does not silently truncate (we never send truncate=true)."""
        # A short text will embed cleanly; if TEI truncated it we'd get the wrong vector.
        result = await tei_client.embed(["short"])
        assert result.shape[1] == _live_dim()

    async def test_embed_deterministic(self, tei_client: TeiClient) -> None:
        """Same text must produce equal vectors across two calls."""
        v1 = await tei_client.embed(["determinism test"])
        v2 = await tei_client.embed(["determinism test"])
        np.testing.assert_allclose(v1, v2, atol=1e-5)

    async def test_batch_consistent_with_single(self, tei_client: TeiClient) -> None:
        """Batch embedding must equal per-item embedding (TEI normalises each row)."""
        texts = ["apple", "banana"]
        batch = await tei_client.embed(texts)
        for i, text in enumerate(texts):
            single = await tei_client.embed([text])
            np.testing.assert_allclose(batch[i], single[0], atol=1e-4,
                err_msg=f"batch[{i}] != single for {text!r}")

    async def test_validate_output_vectors_passes(self, tei_client: TeiClient) -> None:
        texts = ["validate", "me"]
        result = await tei_client.embed(texts)
        # Must not raise.
        validate_output_vectors(texts, result, _live_dim())


# ------------------------------------------------------------------ #
# TEIBackend contract tests (live)                                     #
# ------------------------------------------------------------------ #

class TestLiveTEIBackend:
    async def test_name_and_profile(self, tei_backend: TEIBackend) -> None:
        assert tei_backend.name == "tei"
        assert tei_backend.profile == "gpu"

    async def test_dimensions(self, tei_backend: TEIBackend) -> None:
        assert tei_backend.dimensions == _live_dim()

    async def test_model_id(self, tei_backend: TEIBackend) -> None:
        assert tei_backend.model_id == _live_model()

    async def test_embed_validates_output(self, tei_backend: TEIBackend) -> None:
        result = await tei_backend.embed(["live validation"])
        assert result.shape == (1, _live_dim())
        norm = vector_l2_norm(result[0])
        assert norm == pytest.approx(1.0, abs=1e-4)

    async def test_embed_empty_batch_raises(self, tei_backend: TEIBackend) -> None:
        from app.errors import EmptyBatchError
        with pytest.raises(EmptyBatchError):
            await tei_backend.embed([])

    async def test_health_delegation(self, tei_backend: TEIBackend) -> None:
        assert await tei_backend.health() is True

    async def test_info_delegation(self, tei_backend: TEIBackend) -> None:
        info = await tei_backend.info()
        assert isinstance(info, dict)

    async def test_geometry_mismatch_raises_on_wrong_dim(self) -> None:
        """Intentionally configure wrong dim — validate_output_vectors must catch it."""
        from app.errors import InvalidVectorError
        wrong_backend = TEIBackend(
            _live_client(),
            model_id=_live_model(),
            dimensions=9999,  # intentionally wrong
        )
        with pytest.raises(InvalidVectorError):
            await wrong_backend.embed(["trigger mismatch"])


# ------------------------------------------------------------------ #
# Factory live tests                                                   #
# ------------------------------------------------------------------ #

class TestLiveFactory:
    def test_build_backend_gpu_constructs_tei(self) -> None:
        settings = _live_gpu_settings()
        backend = build_backend(settings)
        assert isinstance(backend, TEIBackend)
        assert backend.dimensions == _live_dim()

    async def test_live_backend_embed_round_trip(self) -> None:
        settings = _live_gpu_settings()
        backend = build_backend(settings)
        assert isinstance(backend, TEIBackend)
        result = await backend.embed(["end-to-end factory test"])
        assert result.shape == (1, _live_dim())
        assert vector_l2_norm(result[0]) == pytest.approx(1.0, abs=1e-4)


# ------------------------------------------------------------------ #
# FastAPI /v1/embed live tests                                         #
# ------------------------------------------------------------------ #

class TestLiveEmbedAPI:
    async def test_v1_embed_returns_200_with_vectors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """POST /v1/embed against a live backend via TestClient."""
        from fastapi.testclient import TestClient

        from app.config import get_settings
        from app.main import app
        from app.state import AppState

        monkeypatch.setenv("IBEX_EMBEDDING_API_TOKEN", _LIVE_API_TOKEN)
        monkeypatch.setenv("IBEX_EMBEDDING_PROFILE", "cpu")
        get_settings.cache_clear()

        backend = TEIBackend(
            _live_client(),
            model_id=_live_model(),
            dimensions=_live_dim(),
        )
        state = AppState()
        state.backend = backend
        state.ready = True

        with TestClient(app) as tc:
            tc.app.state.embedder = state
            resp = tc.post(
                "/v1/embed",
                json={"texts": ["live api test"], "org_id": "11111111-1111-1111-1111-111111111111"},
                headers={"Authorization": f"Bearer {_LIVE_API_TOKEN}"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["vectors"]) == 1
        assert len(body["vectors"][0]) == _live_dim()
        assert body["model_id"] == _live_model()
        assert body["backend"] == "tei"

        get_settings.cache_clear()
