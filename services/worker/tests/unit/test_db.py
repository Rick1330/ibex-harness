"""Unit tests for async database URL parsing."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.db import create_engine, create_session_factory


def test_create_engine_requires_database_url() -> None:
    settings = Settings(database_url=None)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_engine(settings)


def test_create_session_factory() -> None:
    settings = Settings(database_url="postgresql://u:p@localhost/ibex?sslmode=disable")
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    assert factory is not None
