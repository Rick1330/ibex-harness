"""Integration tests — worker process observability initialization."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.observability import _on_worker_process_init, reset_observability_for_tests

pytestmark = pytest.mark.integration


def test_worker_process_init_initializes_database_pool(
    integration_settings: Settings,
) -> None:
    from app import observability

    reset_observability_for_tests()
    _on_worker_process_init()
    assert observability._session_factory is not None
    assert observability._engine is not None
