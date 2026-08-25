from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import create_engine, create_session_factory
from app.deps import get_settings


def test_create_engine_requires_database_url() -> None:
    settings = Settings(database_url=None)
    with pytest.raises(RuntimeError, match="IBEX_MEMORY_DATABASE_URL"):
        create_engine(settings)


def test_create_session_factory_returns_async_sessionmaker() -> None:
    settings = Settings(database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex")
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    assert factory.class_ is AsyncSession


def test_deps_get_settings_cached() -> None:
    get_settings.cache_clear()
    a = get_settings()
    b = get_settings()
    assert a is b
