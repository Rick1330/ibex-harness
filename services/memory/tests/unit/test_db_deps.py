from __future__ import annotations

import ssl

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import (
    create_engine,
    create_session_factory,
    normalize_async_database_url,
    parse_async_database_url,
)
from app.deps import get_settings


def test_create_engine_requires_database_url() -> None:
    settings = Settings(database_url=None)
    with pytest.raises(RuntimeError, match="IBEX_MEMORY_DATABASE_URL"):
        create_engine(settings)


def test_normalize_plaintext_sslmode_disable() -> None:
    target = parse_async_database_url(
        "postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable"
    )
    assert target.url == "postgresql+asyncpg://ibex:ibex@localhost:5433/ibex_test"
    assert target.connect_args == {"ssl": False}
    assert normalize_async_database_url(
        "postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable"
    ) == target.url


def test_normalize_require_uses_encrypting_context() -> None:
    target = parse_async_database_url(
        "postgresql://ibex:ibex@db.example:5432/ibex?sslmode=require"
    )
    assert "sslmode" not in target.url
    ctx = target.connect_args["ssl"]
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False


def test_normalize_verify_full_enables_hostname_checks() -> None:
    target = parse_async_database_url(
        "postgresql://ibex:ibex@db.example:5432/ibex?sslmode=verify-full"
    )
    assert "sslmode" not in target.url
    ctx = target.connect_args["ssl"]
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


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
