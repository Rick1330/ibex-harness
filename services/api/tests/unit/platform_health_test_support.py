"""Shared fixtures for operator platform health unit tests.

Kept in one module so the platform-health and outbox-probe test modules describe
the same operator session instead of each carrying a copy (CodeScene LCOM4:
a second copy splits the module into unrelated behaviours).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from authclient.permissions import OPERATOR_METADATA_READ

from app.session_stub import SESSION_KIND_ACCESS, SessionClaims


def claims(*, permissions: int = OPERATOR_METADATA_READ) -> SessionClaims:
    """A verified operator session with the platform read permission."""
    return SessionClaims(
        sub="user-1",
        org_id=uuid4(),
        permissions=permissions,
        session_kind=SESSION_KIND_ACCESS,
        exp=9999999999,
        iat=1,
        jti="jti-1",
        verify_method="HS256",
    )


def authed_request(
    *,
    feature: bool = True,
    redis_url: str | None = "redis://localhost:6379/0",
) -> MagicMock:
    """A request whose app state looks like a ready API with no session factory."""
    req = MagicMock()
    req.app.state.settings = MagicMock(
        operator_feature_enabled=feature,
        environment="development",
        jwt_hmac_secret="sekrit",
        jwt_public_keys_pem=None,
        jwt_issuer="ibex",
        jwt_audience="ibex-dashboard",
        dashboard_session_cookie_name="ibex_session",
        redis_url=redis_url,
        platform_retention_horizon_days=90,
    )
    req.cookies = {"ibex_session": "valid.token.here"}
    api = MagicMock()
    api.ready = True
    validator = MagicMock()
    validator.ready = AsyncMock(return_value=True)
    api.validator = validator
    api.session_factory = None
    api.drain = MagicMock(is_draining=lambda: False)
    req.app.state.api = api
    return req
