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


def test_cors_origin_list_trims_and_skips_empty() -> None:
    settings = Settings.model_construct(allowed_origins=" https://a.example , ,https://b.example ")
    assert settings.cors_origin_list() == ["https://a.example", "https://b.example"]


def test_cookie_names_reject_whitespace_padding() -> None:
    try:
        Settings(
            environment="development",
            dashboard_session_cookie_name=" ibex_session",
            dashboard_refresh_cookie_name="ibex_refresh",
            dashboard_csrf_cookie_name="ibex_csrf",
        )
    except ValueError as exc:
        assert "whitespace" in str(exc)
    else:
        raise AssertionError("padded cookie names must fail")


def test_staging_operator_feature_disabled_allows_minimal_config() -> None:
    settings = Settings(
        environment="staging",
        operator_feature_enabled=False,
        redis_url="redis://localhost",
        cookie_secure=True,
    )
    assert settings.operator_feature_enabled is False
