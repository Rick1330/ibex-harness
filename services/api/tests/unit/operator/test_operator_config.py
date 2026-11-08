"""Config validation for operator topology."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings
from tests.unit.operator.conftest import HMAC_SECRET, operator_settings

_PEM = "-----BEGIN PUBLIC KEY-----\nconfigured-key-material\n-----END PUBLIC KEY-----\n"


def test_redis_url_accepts_shared_env_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://:pw@redis:6379/0")
    monkeypatch.delenv("IBEX_API_REDIS_URL", raising=False)
    assert Settings().redis_url == "redis://:pw@redis:6379/0"


def test_redis_url_accepts_prefixed_env_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("IBEX_API_REDIS_URL", "redis://:pw@redis:6379/1")
    assert Settings().redis_url == "redis://:pw@redis:6379/1"


def test_redis_url_prefers_api_specific_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://:pw@shared:6379/0")
    monkeypatch.setenv("IBEX_API_REDIS_URL", "redis://:pw@api:6379/0")
    assert Settings().redis_url == "redis://:pw@api:6379/0"


def test_shutdown_timeout_accepts_go_duration() -> None:
    s = Settings(shutdown_timeout_seconds="45s")  # type: ignore[arg-type]
    assert s.shutdown_timeout_seconds == 45


def test_cookie_samesite_normalized() -> None:
    s = Settings(cookie_samesite="STRICT")  # type: ignore[arg-type]
    assert s.cookie_samesite == "strict"


def test_cookie_samesite_rejects_invalid() -> None:
    with pytest.raises(ValidationError):
        Settings(cookie_samesite="invalid")  # type: ignore[arg-type]


def test_hmac_secret_requires_32_bytes() -> None:
    with pytest.raises(ValidationError):
        operator_settings(jwt_hmac_secret="too-short")


def test_wildcard_origin_rejected() -> None:
    with pytest.raises(ValidationError):
        operator_settings(allowed_origins="http://localhost:3100,*")


def test_operator_feature_defaults_off() -> None:
    s = Settings()
    assert s.operator_feature_enabled is False


def test_operator_sessions_require_explicit_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IBEX_ENV", raising=False)
    monkeypatch.delenv("IBEX_API_ENV", raising=False)
    with pytest.raises(ValidationError, match="must be explicitly set"):
        Settings(_env_file=None, operator_feature_enabled=True)


def test_operator_sessions_allow_explicit_development_environment() -> None:
    settings = Settings(operator_feature_enabled=True, environment="development")
    assert settings.environment == "development"


def test_operator_sessions_accept_explicit_api_environment_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("IBEX_ENV", raising=False)
    monkeypatch.setenv("IBEX_API_ENV", "development")
    settings = Settings(_env_file=None, operator_feature_enabled=True)
    assert settings.environment == "development"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"jwt_hmac_secret": HMAC_SECRET}, "only in development"),
        ({"jwt_public_keys_pem": None}, "DASHBOARD_JWT_PUBLIC_KEYS_PEM"),
        ({"redis_url": None}, "REDIS_URL"),
        ({"dashboard_csrf_secret": None}, "DASHBOARD_CSRF_SECRET"),
        ({"operator_cursor_secret": None}, "IBEX_OPERATOR_CURSOR_SECRET"),
        ({"cookie_secure": False}, "DASHBOARD_COOKIE_SECURE"),
    ],
)
def test_non_development_operator_profile_rejects_each_missing_security_control(
    overrides: dict[str, object], message: str
) -> None:
    settings_kwargs: dict[str, object] = {
        "environment": "staging",
        "jwt_hmac_secret": None,
        "jwt_public_keys_pem": "configured-public-key-set",
        "redis_url": "redis://127.0.0.1:6379/0",
        "dashboard_csrf_secret": "csrf-secret-for-staging-32-bytes",
        "operator_cursor_secret": "cursor-secret-for-staging-32-bytes",
        "cookie_secure": True,
    }
    settings_kwargs.update(overrides)
    with pytest.raises(ValidationError, match=message):
        operator_settings(**settings_kwargs)


def test_hmac_secret_accepts_long_value() -> None:
    s = operator_settings(jwt_hmac_secret=HMAC_SECRET)
    assert s.jwt_hmac_secret == HMAC_SECRET


def test_cookie_samesite_non_string_passthrough() -> None:
    # before-validator returns non-str unchanged; after-validator still coerces via pydantic.
    s = Settings(cookie_samesite="Lax")  # type: ignore[arg-type]
    assert s.cookie_samesite == "lax"


def test_shutdown_timeout_accepts_plain_digits() -> None:
    s = Settings(shutdown_timeout_seconds="30")  # type: ignore[arg-type]
    assert s.shutdown_timeout_seconds == 30


def test_shutdown_timeout_non_duration_passthrough() -> None:
    s = Settings(shutdown_timeout_seconds=12)
    assert s.shutdown_timeout_seconds == 12


def test_cookie_names_must_be_distinct() -> None:
    with pytest.raises(ValidationError):
        operator_settings(
            dashboard_session_cookie_name="same",
            dashboard_refresh_cookie_name="same",
            dashboard_csrf_cookie_name="ibex_csrf",
        )


def test_cookie_names_must_be_non_empty() -> None:
    with pytest.raises(ValidationError):
        operator_settings(dashboard_session_cookie_name="  ")


def test_non_development_rejects_hmac_operator_sessions() -> None:
    with pytest.raises(ValidationError, match="only in development"):
        operator_settings(environment="staging", jwt_hmac_secret=HMAC_SECRET)


def test_non_development_operator_profile_requires_rs256_browser_config() -> None:
    with pytest.raises(ValidationError, match="DASHBOARD_JWT_PUBLIC_KEYS_PEM"):
        operator_settings(
            environment="staging",
            jwt_hmac_secret=None,
            operator_cursor_secret="cursor-secret-for-staging-32-bytes",
        )


def test_jwt_public_keys_file_loads_into_effective_value(tmp_path: Path) -> None:
    pem_file = tmp_path / "public-keys.pem"
    pem_file.write_text(_PEM, encoding="utf-8")

    settings = operator_settings(jwt_public_keys_file=str(pem_file))

    assert settings.jwt_public_keys_pem == _PEM


def test_missing_jwt_public_keys_file_fails_naming_the_variable(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="DASHBOARD_JWT_PUBLIC_KEYS_FILE"):
        operator_settings(jwt_public_keys_file=str(tmp_path / "missing.pem"))


def test_empty_jwt_public_keys_file_fails_naming_the_variable(tmp_path: Path) -> None:
    pem_file = tmp_path / "empty.pem"
    pem_file.write_text("  \n", encoding="utf-8")

    with pytest.raises(ValidationError, match="DASHBOARD_JWT_PUBLIC_KEYS_FILE"):
        operator_settings(jwt_public_keys_file=str(pem_file))


def test_inline_pem_wins_over_configured_file(tmp_path: Path) -> None:
    """A set PEM short-circuits the file read, so a broken path must not matter."""
    settings = operator_settings(
        jwt_public_keys_pem=_PEM,
        jwt_public_keys_file=str(tmp_path / "missing.pem"),
    )

    assert settings.jwt_public_keys_pem == _PEM


def test_development_without_pem_material_is_unchanged() -> None:
    settings = operator_settings()

    assert settings.jwt_public_keys_pem is None
    assert settings.jwt_public_keys_file is None


def test_jwt_public_keys_file_alias_is_read_from_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pem_file = tmp_path / "public-keys.pem"
    pem_file.write_text(_PEM, encoding="utf-8")
    monkeypatch.setenv("DASHBOARD_JWT_PUBLIC_KEYS_FILE", str(pem_file))

    settings = operator_settings()

    assert settings.jwt_public_keys_pem == _PEM


def test_non_development_profile_accepts_the_loaded_file(tmp_path: Path) -> None:
    """The file load must run before the non-development material check."""
    pem_file = tmp_path / "public-keys.pem"
    pem_file.write_text(_PEM, encoding="utf-8")

    settings = operator_settings(
        environment="staging",
        jwt_hmac_secret=None,
        jwt_public_keys_pem=None,
        jwt_public_keys_file=str(pem_file),
        redis_url="redis://127.0.0.1:6379/0",
        cookie_secure=True,
    )

    assert settings.jwt_public_keys_pem == _PEM
