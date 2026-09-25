"""Shared fixtures for 4.P.0 operator topology unit tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from authclient.permissions import OPERATOR_METADATA_READ
from fastapi.testclient import TestClient

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.main import create_app

HMAC_SECRET = "test-hmac-secret-for-4p0-32b-min!!"
CSRF_SECRET = "test-csrf-secret-for-4p0-32b-min!!"


def operator_settings(**kwargs: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex",
        "allowed_origins": "http://localhost:3100,https://operator.ibexharness.com",
        "jwt_hmac_secret": HMAC_SECRET,
        "dashboard_csrf_secret": CSRF_SECRET,
        "cookie_secure": False,
        "cookie_samesite": "lax",
        "operator_feature_enabled": True,
        "environment": "development",
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def mock_engine() -> MagicMock:
    engine = MagicMock()
    engine.dispose = AsyncMock()
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)
    engine.connect = MagicMock(return_value=conn)
    return engine


@pytest.fixture
def settings() -> Settings:
    return operator_settings()


@pytest.fixture
def validator() -> StaticTokenValidator:
    return StaticTokenValidator(
        {
            "ibex_pat_test_secret": ValidateResult(
                org_id=uuid4(), permissions=OPERATOR_METADATA_READ, user_id="u1"
            )
        }
    )


@pytest.fixture
def app_client(settings: Settings, validator: StaticTokenValidator):
    engine = mock_engine()
    with (
        patch("app.main.create_engine", return_value=engine),
        patch("app.main.create_session_factory", return_value=MagicMock()),
        patch("authclient.revoke.GRPCTokenRevoker") as revoker_cls,
        patch("authclient.tokens.GRPCTokenManager") as manager_cls,
        patch("authclient.provider_credentials.GRPCProviderCredentialManager") as cred_cls,
    ):
        for cls in (revoker_cls, manager_cls, cred_cls):
            inst = MagicMock()
            inst.aclose = AsyncMock()
            cls.return_value = inst
        app = create_app(settings=settings, validator=validator)
        client = TestClient(app)
        client.__enter__()
        try:
            yield app, client
        finally:
            client.__exit__(None, None, None)


def login_with_csrf(client: TestClient, pat: str = "ibex_pat_test_secret") -> str:
    """POST login and return CSRF token; asserts HTTP 200."""
    login = client.post("/v1/operator/session/login", json={"pat": pat})
    assert login.status_code == 200
    return login.json()["csrf_token"]


def create_operator_app(
    *,
    settings: Settings | None = None,
    validator: StaticTokenValidator | None = None,
):
    """Context manager: patched create_app + TestClient for operator tests."""
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        s = settings or operator_settings()
        v = validator or StaticTokenValidator(
            {
                "ibex_pat_test_secret": ValidateResult(
                    org_id=uuid4(), permissions=OPERATOR_METADATA_READ, user_id="u1"
                )
            }
        )
        with (
            patch("app.main.create_engine", return_value=mock_engine()),
            patch("app.main.create_session_factory", return_value=MagicMock()),
            patch("authclient.revoke.GRPCTokenRevoker", return_value=MagicMock(aclose=AsyncMock())),
            patch("authclient.tokens.GRPCTokenManager", return_value=MagicMock(aclose=AsyncMock())),
            patch(
                "authclient.provider_credentials.GRPCProviderCredentialManager",
                return_value=MagicMock(aclose=AsyncMock()),
            ),
        ):
            app = create_app(settings=s, validator=v)
            with TestClient(app) as client:
                yield app, client

    return _cm()
