"""Contract tests for HostedAPIBackend (shape, L2, profile)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from app.backends.hosted import HostedAPIBackend
from app.validate import vector_l2_norm
from tests.test_contract_stub import assert_backend_contract as _assert_contract


async def test_hosted_openai_contract_shape_and_l2() -> None:
    dim = 8
    raw = np.array([[3.0, 4.0] + [0.0] * (dim - 2)], dtype=np.float32)
    client = MagicMock()
    client.embed = AsyncMock(return_value=raw)
    backend = HostedAPIBackend(
        client,
        provider="openai",
        model_id="text-embedding-3-large",
        dimensions=dim,
    )
    _assert_contract(backend, dim)
    assert backend.profile == "hosted"
    assert backend.name == "openai"

    out = await backend.embed(["hello"])
    assert out.shape == (1, dim)
    assert vector_l2_norm(out[0]) == pytest.approx(1.0, abs=1e-5)
