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


def test_non_development_operator_sessions_require_auth_service_token() -> None:
    kwargs = {
        "environment": "staging",
        "operator_feature_enabled": True,
        "jwt_public_keys_pem": "configured",
        "redis_url": "redis://localhost",
        "dashboard_csrf_secret": "configured",
        "cookie_secure": True,
    }
    try:
        Settings(**kwargs)
    except ValueError as exc:
        assert "IBEX_AUTH_SERVICE_TOKEN" in str(exc)
    else:
        raise AssertionError("missing AuthService token must fail closed")
    assert (
        Settings(auth_service_token="service-token", **kwargs).auth_service_token == "service-token"
    )
