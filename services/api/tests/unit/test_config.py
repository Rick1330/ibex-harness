"""Unit tests for Settings / get_settings."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

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
        "operator_cursor_secret": "cursor-secret-for-tests-32-bytes-min!!",
        "cookie_secure": True,
        "auth_grpc_ca_file": "/etc/ibex/auth-grpc-ca.pem",
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
        # A protected profile now requires the AuthService client CA even when
        # operator sessions are off; the API still validates bearer tokens.
        auth_grpc_ca_file="/etc/ibex/auth-grpc-ca.pem",
    )
    assert settings.operator_feature_enabled is False


def test_non_development_requires_auth_ca() -> None:
    with pytest.raises(ValidationError, match="IBEX_AUTH_GRPC_CA_FILE"):
        Settings(environment="production", jwt_hmac_secret=None)
    Settings(environment="development")
    Settings(
        environment="production",
        auth_grpc_ca_file="/etc/ibex/auth-grpc-ca.pem",
        jwt_hmac_secret=None,
    )
