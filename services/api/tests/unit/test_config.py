"""Unit tests for Settings / get_settings."""

from __future__ import annotations

from app.config import Settings, get_settings


def test_config_empty_and_nonempty_database_url() -> None:
    assert Settings(database_url="  ").database_url is None
    assert Settings(database_url="postgresql+asyncpg://x").database_url is not None
    get_settings.cache_clear()
    a = get_settings()
    b = get_settings()
    assert a is b
