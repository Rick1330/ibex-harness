"""P1-14: the protected transport posture must be configurable and fail closed."""

from __future__ import annotations

import asyncio

from starlette.requests import HTTPConnection

from app.config import Settings
from app.server import _transport_security


def _accepts(settings, host: str) -> bool:
    """Run the SDK's Host check for one Host header value."""
    from mcp.server.transport_security import TransportSecurityMiddleware

    middleware = TransportSecurityMiddleware(settings)
    connection = HTTPConnection({"type": "http", "headers": [(b"host", host.encode())]})
    return asyncio.run(middleware.validate_request(connection)) is None


def test_production_with_an_allow_list_accepts_the_configured_host_and_rejects_another() -> None:
    # Before this, production built the SDK settings with an empty allow-list
    # and the pinned SDK rejected every request with 421.
    cfg = Settings(
        env="production",
        redis_url="redis://redis:6379/0",
        auth_grpc_ca_file="/etc/ibex/auth-grpc-ca.pem",
        resource_url="https://mcp.example.com/mcp",
        auth_server_url="https://auth.example.com",
        allowed_hosts="mcp.example.com,mcp.example.com:8443",
    )
    settings = _transport_security(
        allow_test_hosts=cfg.env == "development",
        allowed_hosts=cfg.allowed_host_list,
        allowed_origins=cfg.allowed_origin_list,
    )
    assert settings.enable_dns_rebinding_protection is True
    assert _accepts(settings, "mcp.example.com") is True
    assert _accepts(settings, "mcp.example.com:8443") is True
    assert _accepts(settings, "evil.example.com") is False


def test_production_without_an_allow_list_rejects_every_host() -> None:
    # Fail-closed on purpose. An unconfigured production deployment answers 421
    # to every request, which is recorded behaviour, not a bug: the audit's
    # defect was that no configuration could make production work at all.
    settings = _transport_security(allow_test_hosts=False)
    assert settings.enable_dns_rebinding_protection is True
    assert settings.allowed_hosts == []
    assert _accepts(settings, "127.0.0.1:8090") is False
    assert _accepts(settings, "mcp.example.com") is False


def test_development_keeps_the_test_host_posture() -> None:
    settings = _transport_security(allow_test_hosts=True)
    assert settings.enable_dns_rebinding_protection is False
    assert _accepts(settings, "testserver") is True
