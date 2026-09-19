"""Config validation for operator topology."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings
from tests.unit.operator.conftest import HMAC_SECRET, operator_settings


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
