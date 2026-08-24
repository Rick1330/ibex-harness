"""Optional live tests against real OpenAI / Cohere hosted APIs.

Skipped unless IBEX_HOSTED_LIVE=1 and IBEX_EMBEDDING_HOSTED_API_KEY (or provider key) is set.

    IBEX_HOSTED_LIVE=1 \\
      IBEX_EMBEDDING_HOSTED_API_KEY=sk-... \\
      IBEX_EMBEDDING_HOSTED_PROVIDER=openai \\
      pytest -m hosted_live services/embedder/tests/test_hosted_live.py -v

Cohere:
    IBEX_HOSTED_LIVE=1 \\
      IBEX_EMBEDDING_HOSTED_API_KEY=... \\
      IBEX_EMBEDDING_HOSTED_PROVIDER=cohere \\
      IBEX_EMBEDDING_MODEL=embed-english-v3.0 \\
      IBEX_EMBEDDING_DIM=1024 \\
      pytest -m hosted_live services/embedder/tests/test_hosted_live.py -v
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from app.backends.hosted import HostedAPIBackend
from app.config import Settings
from app.factory import build_backend
from app.validate import vector_l2_norm

_LIVE = os.getenv("IBEX_HOSTED_LIVE", "").lower() in ("1", "true", "yes")
_LIVE_KEY = (
    os.getenv("IBEX_EMBEDDING_HOSTED_API_KEY")
    or os.getenv("OPENAI_EMBEDDING_API_KEY")
    or ""
).strip()

pytestmark = [
    pytest.mark.hosted_live,
    pytest.mark.skipif(not _LIVE, reason="set IBEX_HOSTED_LIVE=1 to run hosted live tests"),
    pytest.mark.skipif(not _LIVE_KEY, reason="IBEX_EMBEDDING_HOSTED_API_KEY required for live"),
]


def _live_provider() -> str:
    return os.getenv("IBEX_EMBEDDING_HOSTED_PROVIDER", "openai").strip().lower()


def _live_settings() -> Settings:
    provider = _live_provider()
    kwargs: dict = {
        "profile": "hosted",
        "hosted_provider": provider,
        "hosted_api_key": _LIVE_KEY,
        "hosted_max_retries": 1,
        "api_token": "live-service-token",
    }
    if provider == "cohere":
        kwargs["model"] = os.getenv("IBEX_EMBEDDING_MODEL", "embed-english-v3.0")
        kwargs["dim"] = int(os.getenv("IBEX_EMBEDDING_DIM", "1024"))
    elif os.getenv("IBEX_EMBEDDING_DIM"):
        kwargs["dim"] = int(os.environ["IBEX_EMBEDDING_DIM"])
    if os.getenv("IBEX_EMBEDDING_MODEL") and provider != "cohere":
        kwargs["model"] = os.environ["IBEX_EMBEDDING_MODEL"]
    return Settings(**kwargs)  # type: ignore[arg-type]


class TestLiveHostedBackend:
    async def test_embed_shape_and_l2(self) -> None:
        settings = _live_settings()
        backend = build_backend(settings)
        assert isinstance(backend, HostedAPIBackend)
        try:
            result = await backend.embed(["ibex hosted live probe"])
            assert result.shape == (1, backend.dimensions)
            assert result.dtype == np.float32
            assert vector_l2_norm(result[0]) == pytest.approx(1.0, abs=1e-4)
        finally:
            await backend.aclose()
