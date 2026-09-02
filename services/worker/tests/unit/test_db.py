"""Unit tests for async database URL parsing."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.db import create_engine, create_session_factory, parse_async_database_url


def test_parse_postgres_url_to_asyncpg() -> None:
    target = parse_async_database_url("postgres://u:p@localhost:5432/ibex?sslmode=disable")
    assert target.url.startswith("postgresql+asyncpg://")
    assert "sslmode" not in target.url
    assert target.connect_args.get("ssl") is False


def test_parse_postgres_url_ssl_prefer() -> None:
    target = parse_async_database_url("postgresql://u:p@localhost/ibex?sslmode=prefer")
    assert target.connect_args.get("ssl") == "prefer"


def test_parse_postgres_url_ssl_require() -> None:
    target = parse_async_database_url("postgresql://u:p@localhost/ibex?sslmode=require")
    assert target.connect_args.get("ssl") is True


def test_parse_unsupported_sslmode_raises() -> None:
    with pytest.raises(ValueError, match="unsupported sslmode"):
        parse_async_database_url("postgresql://u:p@localhost/ibex?sslmode=weird")


def test_create_engine_requires_database_url() -> None:
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_engine(Settings(database_url=None))


def test_create_session_factory() -> None:
    settings = Settings(database_url="postgresql://u:p@localhost/ibex?sslmode=disable")
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    assert factory is not None
